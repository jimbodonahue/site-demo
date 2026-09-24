import json
import secrets
from copy import deepcopy
from datetime import datetime, timezone

from django.contrib import messages
from django.db.models import Prefetch
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, ListView

from apps.exercises.dataframe_providers import extract_task_prompt, enrich_data_state_visuals
from apps.exercises.data_zoo import (
	DATA_SCIENCE_SECTORS,
	ZOO_BACKED_SOURCES,
	default_sector_for_source,
	refresh_scenario_state,
)
from apps.exercises.missing_values import DEFAULT_DATASET_FILE, DEFAULT_SECTOR
from apps.exercises.rate_limit import check_rate_limit
from apps.exercises.spotter_tips import get_spotter_tips

from .models import Exercise, ExerciseAttempt, Track
from .services import run_notebook


def _reject_placeholder(exercise):
	if exercise.is_placeholder:
		return JsonResponse(
			{"success": False, "error": "This exercise is not available yet."},
			status=404,
		)
	return None


def _visitor_key(request):
	if request.user.is_authenticated:
		return f"user:{request.user.pk}"

	visitor_key = request.session.get("exercise_visitor_key")
	if not visitor_key:
		visitor_key = secrets.token_hex(16)
		request.session["exercise_visitor_key"] = visitor_key
	return visitor_key


def _profile_topic_preference(request) -> str | None:
	"""Return the learner's rank-1 zoo topic, if any."""
	if not getattr(request, "user", None) or not request.user.is_authenticated:
		return None
	profile = getattr(request.user, "profile", None)
	if not profile:
		return None
	topic = (profile.primary_topic() or "").strip().lower()
	if topic in DATA_SCIENCE_SECTORS:
		return topic
	return None


def _profile_ranked_topics(request) -> list[str]:
	"""Return the learner's ranked preferred topics (may be empty)."""
	if not getattr(request, "user", None) or not request.user.is_authenticated:
		return []
	profile = getattr(request.user, "profile", None)
	if not profile:
		return []
	return list(profile.ranked_topics())


def _profile_dataset_file(request) -> str | None:
	if not getattr(request, "user", None) or not request.user.is_authenticated:
		return None
	profile = getattr(request.user, "profile", None)
	if not profile:
		return None
	file_name = (profile.dataset_file or "").strip()
	return file_name or None


def _with_dataset_selection(request, data_state: dict | None, exercise: Exercise | None = None) -> dict:
	"""Apply zoo topic defaults: profile rank-1 preference first, else exercise default."""
	state = deepcopy(data_state or {})
	source = (
		state.get("dataframe_source")
		or (exercise.data_definition.get("dataframe_source") if exercise else None)
		or ""
	)
	source = str(source).strip()
	if source not in ZOO_BACKED_SOURCES:
		return state

	preferred_topic = _profile_topic_preference(request)
	exercise_default = default_sector_for_source(source)

	if not (state.get("data_field") or state.get("topic")):
		topic = preferred_topic or exercise_default
		state["data_field"] = topic
		state["topic"] = topic

	# Prefer the profile dataset file only when it matches the chosen topic.
	if not state.get("dataset_file"):
		profile_file = _profile_dataset_file(request)
		topic = str(state.get("data_field") or state.get("topic") or "").strip().lower()
		if profile_file and preferred_topic and topic == preferred_topic:
			state["dataset_file"] = profile_file
		elif source == "missing_values" and topic == DEFAULT_SECTOR:
			state["dataset_file"] = DEFAULT_DATASET_FILE

	return state


def _apply_refresh_overrides(state: dict, payload: dict | None, request=None) -> dict:
	"""Refresh seed/dataset (and maybe topic), honoring explicit client overrides."""
	body = payload or {}
	explicit_topic = body.get("data_field") or body.get("topic")
	lock_topic = bool(body.get("lock_topic") or body.get("keep_topic") or body.get("force_topic"))
	preferred = _profile_ranked_topics(request) if request is not None else []

	if explicit_topic and lock_topic:
		refreshed = refresh_scenario_state(
			state,
			force_topic=str(explicit_topic),
			change_topic_probability=0.0,
			preferred_topics=preferred,
		)
	else:
		refreshed = refresh_scenario_state(
			state,
			change_topic_probability=0.5,
			preferred_topics=preferred,
		)

	difficulty = body.get("difficulty") or body.get("selected_feature")
	if difficulty:
		refreshed["difficulty"] = difficulty
		refreshed["selected_feature"] = difficulty
		if body.get("selected_feature_label"):
			refreshed["selected_feature_label"] = body["selected_feature_label"]
	if body.get("selected_topic_label"):
		refreshed["selected_topic_label"] = body["selected_topic_label"]
	return refreshed


def _data_state_for_storage(data_state: dict | None) -> dict:
	"""Persist scenario settings without bulky generated artifacts."""
	state = deepcopy(data_state or {})
	state.pop("reference_plot", None)
	state.pop("dataset_preview_html", None)
	return state


def _save_personal_exercise_progress(request, exercise: Exercise, attempt: ExerciseAttempt) -> None:
	if not getattr(request, "user", None) or not request.user.is_authenticated:
		return
	profile = getattr(request.user, "profile", None)
	if profile is None:
		return

	progress = deepcopy(profile.exercise_progress or {})
	progress[exercise.slug] = {
		"data_state": _data_state_for_storage(attempt.data_state),
		"notebook_state": deepcopy(attempt.notebook_state or exercise.starter_cells()),
		"progress_state": deepcopy(attempt.progress_state or {}),
		"updated_at": datetime.now(timezone.utc).isoformat(),
	}
	profile.exercise_progress = progress
	profile.save(update_fields=["exercise_progress", "updated_at"])


def _personal_exercise_progress(request, exercise: Exercise) -> dict | None:
	if not getattr(request, "user", None) or not request.user.is_authenticated:
		return None
	profile = getattr(request.user, "profile", None)
	if not profile:
		return None
	saved = (profile.exercise_progress or {}).get(exercise.slug)
	return saved if isinstance(saved, dict) else None


def _get_attempt(request, exercise):
	visitor_key = _visitor_key(request)
	initial_state = _with_dataset_selection(request, exercise.initial_data_state(), exercise)
	personal = _personal_exercise_progress(request, exercise)
	defaults = {
		"notebook_state": exercise.starter_cells(),
		"data_state": initial_state,
		"progress_state": {"passed": False, "completed_cells": 0},
	}
	if personal:
		defaults["notebook_state"] = personal.get("notebook_state") or defaults["notebook_state"]
		defaults["data_state"] = _with_dataset_selection(
			request,
			personal.get("data_state") or initial_state,
			exercise,
		)
		defaults["progress_state"] = personal.get("progress_state") or defaults["progress_state"]

	attempt, created = ExerciseAttempt.objects.get_or_create(
		exercise=exercise,
		visitor_key=visitor_key,
		defaults=defaults,
	)
	if not attempt.notebook_state:
		attempt.notebook_state = defaults["notebook_state"]
	if not attempt.data_state:
		attempt.data_state = defaults["data_state"]
	else:
		attempt.data_state = _with_dataset_selection(request, attempt.data_state, exercise)
	if not attempt.progress_state:
		attempt.progress_state = defaults["progress_state"]
	# Prefer personal profile state for authenticated returning users.
	if not created and personal and personal.get("data_state"):
		attempt.data_state = _with_dataset_selection(request, personal.get("data_state"), exercise)
		if personal.get("notebook_state"):
			attempt.notebook_state = personal["notebook_state"]
		if personal.get("progress_state"):
			attempt.progress_state = personal["progress_state"]
	attempt.save(update_fields=["notebook_state", "data_state", "progress_state", "updated_at"])
	return attempt


class TrackListView(ListView):
	model = Track
	template_name = "exercises/track_list.html"
	context_object_name = "tracks"

	def get_queryset(self):
		return Track.objects.filter(published=True).prefetch_related(
			Prefetch(
				"exercises",
				queryset=Exercise.objects.filter(published=True).order_by("order", "title"),
			)
		)


class TrackDetailView(DetailView):
	model = Track
	template_name = "exercises/track_detail.html"
	context_object_name = "track"

	def get_queryset(self):
		return Track.objects.filter(published=True).prefetch_related(
			Prefetch(
				"exercises",
				queryset=Exercise.objects.filter(published=True).order_by("order", "title"),
			)
		)


class ExerciseDetailView(DetailView):
	model = Exercise
	context_object_name = "exercise"

	def get_template_names(self):
		if self.object.is_placeholder:
			return ["exercises/exercise_placeholder.html"]
		return ["exercises/exercise_detail.html"]

	def get_queryset(self):
		return Exercise.objects.filter(published=True).select_related("track")

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		exercise = self.object
		if exercise.is_placeholder:
			return context
		attempt = _get_attempt(self.request, exercise)
		initial_data = enrich_data_state_visuals(
			_with_dataset_selection(
				self.request,
				attempt.data_state or exercise.initial_data_state(),
				exercise,
			)
		)
		context.update(
			{
				"attempt": attempt,
				"starter_cells": exercise.starter_cells(),
				"feature_choices": exercise.feature_choices(),
				"topic_choices": exercise.topic_choices(),
				"allowed_imports": exercise.allowed_imports,
				"data_definition": exercise.data_definition,
				"evaluation_rules": exercise.evaluation_rules,
				"initial_data": initial_data,
				"task_prompt": extract_task_prompt(initial_data),
				"spotter_tips": get_spotter_tips(
					initial_data.get("dataframe_source")
					or (exercise.data_definition or {}).get("dataframe_source")
				),
				"run_url": reverse("exercises:run", args=[exercise.slug]),
				"reset_url": reverse("exercises:reset", args=[exercise.slug]),
				"repeat_url": reverse("exercises:repeat", args=[exercise.slug]),
				"soft_skill_url": reverse("exercises:soft_skill", args=[exercise.slug]),
			}
		)
		return context


@require_POST
def submit_soft_skill(request, slug):
	exercise = get_object_or_404(Exercise.objects.filter(published=True), slug=slug)
	if exercise.is_placeholder:
		messages.error(request, "This exercise is not available yet.")
		return redirect("exercises:detail", slug=slug)
	response_text = (request.POST.get("soft_skill_response") or "").strip()

	if not exercise.soft_skill_prompt:
		messages.error(request, "This exercise does not have a soft skill question.")
		return redirect("exercises:detail", slug=slug)

	if not response_text:
		messages.error(request, "Please write a response before submitting.")
		return redirect("exercises:detail", slug=slug)

	attempt = _get_attempt(request, exercise)
	attempt.soft_skill_response = response_text
	attempt.save(update_fields=["soft_skill_response", "updated_at"])

	messages.success(request, "Your soft skill reflection was saved.")
	return redirect("exercises:detail", slug=slug)


@require_POST
def run_exercise(request, slug):
	exercise = get_object_or_404(Exercise.objects.filter(published=True), slug=slug)
	rejected = _reject_placeholder(exercise)
	if rejected:
		return rejected
	allowed, retry_after = check_rate_limit(request, action="exercise_run")
	if not allowed:
		return JsonResponse(
			{
				"success": False,
				"ran": False,
				"error": "Too many notebook runs. Please wait a moment and try again.",
				"retry_after": retry_after,
			},
			status=429,
		)
	payload = json.loads(request.body or b"{}")
	cells = payload.get("cells") or exercise.starter_cells()
	previous_results = payload.get("previous_results") or []
	mode = (payload.get("mode") or "run").strip().lower()
	if mode not in {"run", "evaluate"}:
		mode = "run"
	data_state = _with_dataset_selection(
		request,
		payload.get("data_state") or exercise.initial_data_state(),
		exercise,
	)
	attempt = _get_attempt(request, exercise)
	result = run_notebook(
		cells=cells,
		allowed_imports=exercise.allowed_imports,
		data_state=data_state,
		previous_results=previous_results,
		evaluation_rules=exercise.evaluation_rules,
		mode=mode,
		soft_skill_response=attempt.soft_skill_response or "",
		soft_skill_prompt=exercise.soft_skill_prompt or "",
		reveal_expected=bool(payload.get("reveal_expected")),
	)
	attempt.notebook_state = cells
	attempt.data_state = _with_dataset_selection(request, result["data_state"], exercise)
	attempt.result_state = result
	attempt.progress_state = {
		"passed": bool(result.get("core_passed") or result.get("evaluation", {}).get("core_passed")),
		"completed_cells": result["completed_cells"],
		"summary": result["evaluation"].get("summary"),
		"band": result.get("band") or result.get("evaluation", {}).get("band"),
		"ran": bool(result.get("ran")),
		"mode": mode,
	}
	attempt.save()
	_save_personal_exercise_progress(request, exercise, attempt)
	return JsonResponse(result)


@require_POST
def reset_exercise(request, slug):
	exercise = get_object_or_404(Exercise.objects.filter(published=True), slug=slug)
	rejected = _reject_placeholder(exercise)
	if rejected:
		return rejected
	payload = json.loads(request.body or b"{}")
	attempt = _get_attempt(request, exercise)

	base_state = _with_dataset_selection(
		request,
		attempt.data_state or exercise.initial_data_state(),
		exercise,
	)
	source = str(
		base_state.get("dataframe_source")
		or (exercise.data_definition or {}).get("dataframe_source")
		or ""
	).strip()

	if source in ZOO_BACKED_SOURCES:
		# Keep current scenario settings as the base, then refresh seed/dataset
		# (and maybe topic). Difficulty/topic overrides come from the client.
		refreshed = _apply_refresh_overrides(base_state, payload, request=request)
		refreshed = _with_dataset_selection(request, refreshed, exercise)
		summary = "Refreshed with a new dataset. Notebook reset."
	else:
		# Non-zoo exercises: restore the authored baseline, then apply difficulty overrides.
		refreshed = deepcopy(exercise.initial_data_state())
		difficulty = payload.get("difficulty") or payload.get("selected_feature")
		if difficulty:
			refreshed["difficulty"] = difficulty
			refreshed["selected_feature"] = difficulty
		summary = "Reset to the original starting state."

	attempt.notebook_state = exercise.starter_cells()
	attempt.data_state = _data_state_for_storage(refreshed)
	attempt.result_state = {}
	attempt.progress_state = {
		"passed": False,
		"completed_cells": 0,
		"message": summary,
		"summary": summary,
	}
	attempt.save()
	_save_personal_exercise_progress(request, exercise, attempt)
	visual_state = enrich_data_state_visuals(attempt.data_state)
	return JsonResponse(
		{
			"success": True,
			"cells": attempt.notebook_state,
			"data_state": visual_state,
			"task_prompt": extract_task_prompt(attempt.data_state),
			"progress": attempt.progress_state,
			"evaluation": {
				"passed": False,
				"summary": summary,
				"checks": [],
			},
		}
	)


@require_POST
def repeat_exercise(request, slug):
	exercise = get_object_or_404(Exercise.objects.filter(published=True), slug=slug)
	rejected = _reject_placeholder(exercise)
	if rejected:
		return rejected
	personal = _personal_exercise_progress(request, exercise)
	visitor_key = _visitor_key(request)
	attempt = (
		ExerciseAttempt.objects.filter(exercise=exercise, visitor_key=visitor_key)
		.order_by("-updated_at")
		.first()
	)

	if personal:
		data_state = _with_dataset_selection(request, personal.get("data_state"), exercise)
		notebook_state = personal.get("notebook_state") or exercise.starter_cells()
		progress_state = personal.get("progress_state") or {
			"passed": False,
			"completed_cells": 0,
			"summary": "Restored saved state.",
		}
		if attempt:
			attempt.notebook_state = notebook_state
			attempt.data_state = data_state
			attempt.progress_state = progress_state
			attempt.save(update_fields=["notebook_state", "data_state", "progress_state", "updated_at"])
		visual_state = enrich_data_state_visuals(data_state)
		return JsonResponse(
			{
				"success": True,
				"cells": notebook_state,
				"data_state": visual_state,
				"task_prompt": extract_task_prompt(data_state),
				"progress": progress_state,
				"evaluation": {
					"passed": bool(progress_state.get("passed")),
					"summary": progress_state.get("summary") or "Restored saved state.",
					"checks": [],
				},
			}
		)

	if not attempt:
		baseline = enrich_data_state_visuals(
			_with_dataset_selection(request, exercise.initial_data_state(), exercise)
		)
		return JsonResponse(
			{
				"success": False,
				"error": "No saved attempt was found for this user.",
				"cells": exercise.starter_cells(),
				"data_state": baseline,
				"task_prompt": extract_task_prompt(baseline),
				"progress": {"passed": False, "completed_cells": 0, "summary": "No saved attempt found."},
				"evaluation": {"passed": False, "summary": "No saved attempt found.", "checks": []},
			},
			status=404,
		)

	restored_state = enrich_data_state_visuals(
		_with_dataset_selection(
			request,
			attempt.data_state or exercise.initial_data_state(),
			exercise,
		)
	)
	return JsonResponse(
		{
			"success": True,
			"cells": attempt.notebook_state or exercise.starter_cells(),
			"data_state": restored_state,
			"task_prompt": extract_task_prompt(restored_state),
			"progress": attempt.progress_state or {"passed": False, "completed_cells": 0, "summary": "Restored saved state."},
			"evaluation": {
				"passed": bool(attempt.progress_state.get("passed")) if attempt.progress_state else False,
				"summary": (attempt.progress_state or {}).get("summary") or "Restored saved state.",
				"checks": [],
			},
		}
	)
