import json
import secrets
from copy import deepcopy
from datetime import datetime, timezone

from django.contrib import messages
from django.db.models import Prefetch
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import DetailView, ListView, TemplateView

from apps.exercises.dataframe_providers import (
	extract_task_prompt,
	enrich_data_state_visuals,
	render_task_prompt_html,
)
from apps.exercises.data_zoo import (
	DATA_SCIENCE_SECTORS,
	ZOO_BACKED_SOURCES,
	build_zoo_explore_notebook,
	default_sector_for_source,
	default_topic_choices,
	refresh_scenario_state,
	sector_label,
	topic_dataset_summaries,
)
from apps.exercises.missing_values import DEFAULT_DATASET_FILE, DEFAULT_SECTOR
from apps.exercises.notebook_layout import without_imports_cells
from apps.exercises.rate_limit import check_rate_limit
from apps.exercises.spotter_tips import get_spotter_tips
from apps.forum.models import Post, Topic
from apps.forum.utils import ensure_forum_topics
from apps.forum.views import get_or_create_forum_user

from .models import Exercise, ExerciseAttempt, Track
from .services import run_notebook


def _reject_placeholder(exercise):
	if exercise.is_placeholder:
		return JsonResponse(
			{"success": False, "error": "This exercise is not available yet."},
			status=404,
		)
	return None


def _track_neighbors(exercise: Exercise) -> tuple[Exercise | None, Exercise | None]:
	"""Return the previous and next published exercises in the same track."""
	if not exercise.track_id:
		return None, None
	siblings = list(
		Exercise.objects.filter(track_id=exercise.track_id, published=True).order_by(
			"order", "title", "pk"
		)
	)
	try:
		index = next(i for i, item in enumerate(siblings) if item.pk == exercise.pk)
	except StopIteration:
		return None, None
	previous_exercise = siblings[index - 1] if index > 0 else None
	next_exercise = siblings[index + 1] if index + 1 < len(siblings) else None
	return previous_exercise, next_exercise


def _json_body(request) -> tuple[dict | None, JsonResponse | None]:
	"""Parse a JSON request body, returning an error response instead of a 500."""
	try:
		payload = json.loads(request.body or b"{}")
	except (json.JSONDecodeError, UnicodeDecodeError):
		return None, JsonResponse(
			{"success": False, "error": "Invalid JSON request body."},
			status=400,
		)
	if not isinstance(payload, dict):
		return None, JsonResponse(
			{"success": False, "error": "Request body must be a JSON object."},
			status=400,
		)
	return payload, None


def _task_prompt_fields(data_state, allowed_imports=None) -> dict:
	from apps.exercises.dataframe_providers import prepare_exercise_namespace
	from apps.exercises.notebook_layout import with_preloaded_libraries_note
	from apps.exercises.plotting_bonus import format_plotting_bonus_prompt

	prompt = ""
	bonus_prompt = ""
	try:
		prepared = prepare_exercise_namespace(data_state or {})
		task = prepared.get("task")
		if isinstance(task, dict):
			prompt = str(task.get("prompt") or "").strip()
			bonus_prompt = format_plotting_bonus_prompt(task.get("plotting_bonus"))
	except Exception:
		prompt = extract_task_prompt(data_state)
	prompt = with_preloaded_libraries_note(prompt, allowed_imports)
	return {
		"task_prompt": prompt,
		"task_prompt_html": str(render_task_prompt_html(prompt)) if prompt else "",
		"plotting_bonus_prompt": bonus_prompt,
		"plotting_bonus_prompt_html": (
			str(render_task_prompt_html(bonus_prompt)) if bonus_prompt else ""
		),
	}


def _starter_cells_for_state(exercise: Exercise, data_state) -> list:
	fields = _task_prompt_fields(data_state, allowed_imports=exercise.allowed_imports)
	return without_imports_cells(
		exercise.starter_cells(plotting_bonus_prompt=fields.get("plotting_bonus_prompt") or "")
	)


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


_MAX_ATTEMPT_HISTORY = 50


def _minute_timestamp() -> str:
    """UTC timestamp truncated to the minute for student-facing try labels."""
    return datetime.now(timezone.utc).replace(second=0, microsecond=0).isoformat()


def _seed_from_state(data_state: dict | None):
    if not isinstance(data_state, dict):
        return None
    seed = data_state.get("seed")
    if seed is None:
        return None
    try:
        return int(seed)
    except (TypeError, ValueError):
        return seed


def _legacy_progress_as_attempts(saved: dict | None) -> list:
    """Convert a pre-history personal progress blob into a one-entry attempts list."""
    if not isinstance(saved, dict):
        return []
    if isinstance(saved.get("attempts"), list) and saved["attempts"]:
        return deepcopy(saved["attempts"])
    data_state = saved.get("data_state")
    if not isinstance(data_state, dict):
        return []
    return [
        {
            "try_number": 1,
            "created_at": saved.get("updated_at") or _minute_timestamp(),
            "seed": _seed_from_state(data_state),
            "data_state": _data_state_for_storage(data_state),
            "notebook_state": deepcopy(saved.get("notebook_state") or []),
            "progress_state": deepcopy(saved.get("progress_state") or {}),
        }
    ]


def _public_attempt_list(history: list | None) -> list[dict]:
    """Student-visible try metadata (seed intentionally omitted)."""
    public = []
    for entry in history or []:
        if not isinstance(entry, dict):
            continue
        try_number = entry.get("try_number")
        if try_number is None:
            continue
        created_at = entry.get("created_at") or entry.get("updated_at") or ""
        public.append(
            {
                "try_number": int(try_number),
                "created_at": created_at,
            }
        )
    return public


def _upsert_attempt_history(
    history: list | None,
    *,
    data_state: dict | None,
    notebook_state,
    progress_state: dict | None,
) -> list:
    """
    Append a new try when the lesson seed changes; otherwise refresh the latest try.
    Seed is stored for restoration but never exposed in public listings.
    """
    entries = deepcopy(history) if isinstance(history, list) else []
    stored_state = _data_state_for_storage(data_state)
    seed = _seed_from_state(stored_state)
    snapshot = {
        "seed": seed,
        "data_state": stored_state,
        "notebook_state": deepcopy(notebook_state or []),
        "progress_state": deepcopy(progress_state or {}),
    }

    if entries:
        last = entries[-1]
        if isinstance(last, dict) and last.get("seed") == seed:
            last.update(snapshot)
            return entries[-_MAX_ATTEMPT_HISTORY:]

    try_number = 1
    if entries:
        try:
            try_number = int(entries[-1].get("try_number") or len(entries)) + 1
        except (TypeError, ValueError):
            try_number = len(entries) + 1

    entries.append(
        {
            "try_number": try_number,
            "created_at": _minute_timestamp(),
            **snapshot,
        }
    )
    return entries[-_MAX_ATTEMPT_HISTORY:]


def _load_attempt_history(request, exercise: Exercise, attempt: ExerciseAttempt | None = None) -> list:
    personal = _personal_exercise_progress(request, exercise)
    if personal:
        history = _legacy_progress_as_attempts(personal)
        if history:
            return history
    if attempt is not None and isinstance(attempt.attempt_history, list):
        return deepcopy(attempt.attempt_history)
    return []


def _persist_attempt_history(request, exercise: Exercise, attempt: ExerciseAttempt) -> list:
    """Record the current attempt snapshot into history and sync personal progress."""
    history = _load_attempt_history(request, exercise, attempt)
    history = _upsert_attempt_history(
        history,
        data_state=attempt.data_state,
        notebook_state=attempt.notebook_state,
        progress_state=attempt.progress_state,
    )
    attempt.attempt_history = history
    return history


def _save_personal_exercise_progress(request, exercise: Exercise, attempt: ExerciseAttempt) -> None:
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return
    profile = getattr(request.user, "profile", None)
    if profile is None:
        return

    history = (
        deepcopy(attempt.attempt_history)
        if isinstance(attempt.attempt_history, list)
        else _legacy_progress_as_attempts(_personal_exercise_progress(request, exercise))
    )
    progress = deepcopy(profile.exercise_progress or {})
    progress[exercise.slug] = {
        "data_state": _data_state_for_storage(attempt.data_state),
        "notebook_state": deepcopy(
            attempt.notebook_state
            or _starter_cells_for_state(exercise, attempt.data_state or exercise.initial_data_state())
        ),
        "progress_state": deepcopy(attempt.progress_state or {}),
        "attempts": history,
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
        "notebook_state": _starter_cells_for_state(exercise, initial_state),
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
		previous_exercise, next_exercise = _track_neighbors(exercise)
		context["previous_exercise"] = previous_exercise
		context["next_exercise"] = next_exercise
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
		previous_attempts = _public_attempt_list(
			_load_attempt_history(self.request, exercise, attempt)
		)
		prompt_fields = _task_prompt_fields(
			initial_data, allowed_imports=exercise.allowed_imports
		)
		context.update(
			{
				"attempt": attempt,
				"starter_cells": without_imports_cells(
					exercise.starter_cells(
						plotting_bonus_prompt=prompt_fields.get("plotting_bonus_prompt") or ""
					)
				),
				"feature_choices": exercise.feature_choices(),
				"topic_choices": exercise.topic_choices(),
				"allowed_imports": exercise.allowed_imports,
				"data_definition": exercise.data_definition,
				"evaluation_rules": exercise.display_evaluation_rules(),
				"initial_data": initial_data,
				"previous_attempts": previous_attempts,
				**prompt_fields,
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
	post_to_forum = request.POST.get("post_to_forum") in {"1", "on", "true", "yes"}

	if not exercise.display_soft_skill_prompt():
		messages.error(request, "This exercise does not have a soft skill question.")
		return redirect("exercises:detail", slug=slug)

	if not response_text:
		messages.error(request, "Please write a response before submitting.")
		return redirect("exercises:detail", slug=slug)

	attempt = _get_attempt(request, exercise)
	attempt.soft_skill_response = response_text
	attempt.save(update_fields=["soft_skill_response", "updated_at"])

	if not post_to_forum:
		messages.success(request, "Your soft skill reflection was saved.")
		return redirect("exercises:detail", slug=slug)

	ensure_forum_topics()
	user, _token = get_or_create_forum_user(request)
	from apps.forum.access import forum_participation_allowed

	if not forum_participation_allowed(user):
		messages.success(
			request,
			"Your soft skill reflection was saved. Forum posting is unavailable while your forum access is suspended.",
		)
		return redirect("exercises:detail", slug=slug)

	topic, _created = Topic.objects.get_or_create(
		exercise=exercise,
		defaults={
			"title": f"Discussion: {exercise.title}",
			"created_by": user,
			"section": Topic.SECTION_EXERCISE,
		},
	)
	content = (
		f"Soft skill reflection — {exercise.title}\n\n"
		f"Question:\n{exercise.display_soft_skill_prompt()}\n\n"
		f"Response:\n{response_text}"
	)
	post = Post.objects.create(topic=topic, author=user, content=content)
	from apps.badges.services import record_forum_post

	record_forum_post(user, post_id=post.pk)
	messages.success(request, "Your soft skill reflection was posted to the forum.")
	return redirect(topic.get_absolute_url())


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
	payload, error = _json_body(request)
	if error:
		return error
	# Establish passkey identity before loading the attempt so progress and
	# badges share the same user-scoped visitor key.
	from apps.forum.views import get_or_create_forum_user
	from apps.badges.services import record_exercise_run

	get_or_create_forum_user(request)
	data_state = _with_dataset_selection(
		request,
		payload.get("data_state") or exercise.initial_data_state(),
		exercise,
	)
	cells = payload.get("cells") or _starter_cells_for_state(exercise, data_state)
	previous_results = payload.get("previous_results") or []
	mode = (payload.get("mode") or "run").strip().lower()
	if mode not in {"run", "evaluate"}:
		mode = "run"
	cells_to_run = cells
	until_index = payload.get("until_index")
	if until_index is not None and mode == "run":
		try:
			idx = int(until_index)
		except (TypeError, ValueError):
			idx = -1
		if 0 <= idx < len(cells):
			cells_to_run = cells[: idx + 1]
	attempt = _get_attempt(request, exercise)
	result = run_notebook(
		cells=cells_to_run,
		allowed_imports=exercise.allowed_imports,
		data_state=data_state,
		previous_results=previous_results,
		evaluation_rules=exercise.display_evaluation_rules(),
		mode=mode,
		soft_skill_response=attempt.soft_skill_response or "",
		soft_skill_prompt=exercise.display_soft_skill_prompt() or "",
		reveal_expected=bool(payload.get("reveal_expected")),
	)
	attempt.notebook_state = without_imports_cells(cells)
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
	history = _persist_attempt_history(request, exercise, attempt)
	attempt.save()
	_save_personal_exercise_progress(request, exercise, attempt)

	# Badge credit only on Evaluate — Run executes code without grading.
	if mode == "evaluate":
		record_exercise_run(
			request,
			exercise,
			ran=bool(result.get("ran")),
			core_passed=bool(result.get("core_passed") or result.get("evaluation", {}).get("core_passed")),
			plotting_bonus=result.get("plotting_bonus") or result.get("evaluation", {}).get("plotting_bonus"),
		)
	result = dict(result)
	result["previous_attempts"] = _public_attempt_list(history)
	return JsonResponse(result)


@require_POST
def reset_exercise(request, slug):
	exercise = get_object_or_404(Exercise.objects.filter(published=True), slug=slug)
	rejected = _reject_placeholder(exercise)
	if rejected:
		return rejected
	payload, error = _json_body(request)
	if error:
		return error
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
		# Non-zoo exercises: preserve baseline semantics, apply difficulty overrides.
		refreshed = deepcopy(base_state)
		difficulty = payload.get("difficulty") or payload.get("selected_feature")
		if difficulty:
			refreshed["difficulty"] = difficulty
			refreshed["selected_feature"] = difficulty
		summary = "Reset to the original starting state."

	attempt.data_state = _data_state_for_storage(refreshed)
	prompt_fields = _task_prompt_fields(
		attempt.data_state, allowed_imports=exercise.allowed_imports
	)
	attempt.notebook_state = without_imports_cells(
		exercise.starter_cells(
			plotting_bonus_prompt=prompt_fields.get("plotting_bonus_prompt") or ""
		)
	)
	attempt.result_state = {}
	attempt.progress_state = {
		"passed": False,
		"completed_cells": 0,
		"message": summary,
		"summary": summary,
	}
	history = _persist_attempt_history(request, exercise, attempt)
	attempt.save()
	_save_personal_exercise_progress(request, exercise, attempt)
	visual_state = enrich_data_state_visuals(attempt.data_state)
	return JsonResponse(
		{
			"success": True,
			"cells": attempt.notebook_state,
			"data_state": visual_state,
			**prompt_fields,
			"progress": attempt.progress_state,
			"previous_attempts": _public_attempt_list(history),
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
	payload, error = _json_body(request)
	if error:
		return error
	visitor_key = _visitor_key(request)
	attempt = (
		ExerciseAttempt.objects.filter(exercise=exercise, visitor_key=visitor_key)
		.order_by("-updated_at")
		.first()
	)
	history = _load_attempt_history(request, exercise, attempt)
	public_attempts = _public_attempt_list(history)

	# Listing only — used when the student opens the previous-attempt picker.
	if payload.get("try_number") is None and not payload.get("restore"):
		return JsonResponse(
			{
				"success": True,
				"attempts": public_attempts,
				"previous_attempts": public_attempts,
			}
		)

	try:
		try_number = int(payload.get("try_number"))
	except (TypeError, ValueError):
		return JsonResponse(
			{
				"success": False,
				"error": "Choose a previous attempt to restore.",
				"attempts": public_attempts,
				"previous_attempts": public_attempts,
			},
			status=400,
		)

	entry = next(
		(
			item
			for item in history
			if isinstance(item, dict) and int(item.get("try_number") or 0) == try_number
		),
		None,
	)
	if not entry:
		baseline = enrich_data_state_visuals(
			_with_dataset_selection(request, exercise.initial_data_state(), exercise)
		)
		return JsonResponse(
			{
				"success": False,
				"error": "No previous attempt was found for this user.",
				"cells": _starter_cells_for_state(exercise, baseline),
				"data_state": baseline,
				**_task_prompt_fields(baseline, allowed_imports=exercise.allowed_imports),
				"attempts": public_attempts,
				"previous_attempts": public_attempts,
				"progress": {
					"passed": False,
					"completed_cells": 0,
					"summary": "No previous attempt found.",
				},
				"evaluation": {
					"passed": False,
					"summary": "No previous attempt found.",
					"checks": [],
				},
			},
			status=404,
		)

	data_state = _with_dataset_selection(
		request,
		entry.get("data_state") or exercise.initial_data_state(),
		exercise,
	)
	notebook_state = without_imports_cells(
		entry.get("notebook_state") or _starter_cells_for_state(exercise, data_state)
	)
	progress_state = entry.get("progress_state") or {
		"passed": False,
		"completed_cells": 0,
		"summary": f"Restored try {try_number}.",
	}
	if not progress_state.get("summary"):
		progress_state = {
			**progress_state,
			"summary": f"Restored try {try_number}.",
		}

	if attempt is None:
		attempt = ExerciseAttempt.objects.create(
			exercise=exercise,
			visitor_key=visitor_key,
			notebook_state=notebook_state,
			data_state=data_state,
			progress_state=progress_state,
			attempt_history=history,
		)
	else:
		attempt.notebook_state = notebook_state
		attempt.data_state = data_state
		attempt.progress_state = progress_state
		attempt.attempt_history = history
		attempt.save(
			update_fields=[
				"notebook_state",
				"data_state",
				"progress_state",
				"attempt_history",
				"updated_at",
			]
		)
	_save_personal_exercise_progress(request, exercise, attempt)

	visual_state = enrich_data_state_visuals(data_state)
	return JsonResponse(
		{
			"success": True,
			"cells": notebook_state,
			"data_state": visual_state,
			**_task_prompt_fields(data_state, allowed_imports=exercise.allowed_imports),
			"progress": progress_state,
			"attempts": public_attempts,
			"previous_attempts": public_attempts,
			"evaluation": {
				"passed": bool(progress_state.get("passed")),
				"summary": progress_state.get("summary") or f"Restored try {try_number}.",
				"checks": [],
			},
		}
	)


ZOO_EXPLORE_IMPORTS = [
	"numpy",
	"pandas",
	"matplotlib.pyplot",
	"seaborn",
	"sklearn",
]


def _zoo_topic_from_request(request, payload: dict | None = None) -> str:
	raw = ""
	if payload:
		raw = str(payload.get("topic") or payload.get("data_field") or "").strip().lower()
	if not raw:
		raw = str(request.GET.get("topic") or "").strip().lower()
	if raw in DATA_SCIENCE_SECTORS:
		return raw
	preferred = _profile_topic_preference(request)
	if preferred in DATA_SCIENCE_SECTORS:
		return preferred
	return "healthcare"


def _zoo_explore_data_state(topic: str, dataset_file: str = "", seed: int = 42, n_rows: int = 800) -> dict:
	return {
		"dataframe_source": "zoo_explore",
		"topic": topic,
		"data_field": topic,
		"dataset_file": (dataset_file or "").strip(),
		"seed": int(seed or 42),
		"n_rows": int(n_rows or 800),
	}


class DataZooView(TemplateView):
	template_name = "exercises/data_zoo.html"

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		topic = _zoo_topic_from_request(self.request)
		datasets = topic_dataset_summaries(topic)
		selected_file = str(self.request.GET.get("dataset") or "").strip()
		if selected_file and not any(item.get("dataset_file") == selected_file for item in datasets):
			selected_file = ""
		if not selected_file and datasets:
			selected_file = str(datasets[0].get("dataset_file") or "")
		data_state = _zoo_explore_data_state(topic, selected_file)
		prompt_fields = _task_prompt_fields(data_state)
		context.update(
			{
				"topics": default_topic_choices(),
				"selected_topic": topic,
				"selected_topic_label": sector_label(topic),
				"datasets": datasets,
				"selected_dataset": selected_file,
				"starter_cells": build_zoo_explore_notebook(),
				"allowed_imports": ZOO_EXPLORE_IMPORTS,
				"initial_data": enrich_data_state_visuals(data_state),
				"run_url": reverse("exercises:zoo_run"),
				"catalog_url": reverse("exercises:zoo_catalog"),
				**prompt_fields,
			}
		)
		return context


@require_GET
def zoo_catalog(request):
	topic = _zoo_topic_from_request(request)
	try:
		datasets = topic_dataset_summaries(topic)
	except ValueError as exc:
		return JsonResponse({"success": False, "error": str(exc)}, status=400)
	return JsonResponse(
		{
			"success": True,
			"topic": topic,
			"topic_label": sector_label(topic),
			"datasets": datasets,
		}
	)


@require_POST
def run_zoo_explore(request):
	allowed, retry_after = check_rate_limit(request, action="zoo_explore_run")
	if not allowed:
		return JsonResponse(
			{
				"success": False,
				"ran": False,
				"error": "Too many sandbox runs. Please wait a moment and try again.",
				"retry_after": retry_after,
			},
			status=429,
		)
	payload, error = _json_body(request)
	if error:
		return error

	topic = _zoo_topic_from_request(request, payload)
	dataset_file = str(payload.get("dataset_file") or "").strip()
	try:
		seed = int(payload.get("seed", 42) or 42)
	except (TypeError, ValueError):
		seed = 42
	try:
		n_rows = int(payload.get("n_rows", 800) or 800)
	except (TypeError, ValueError):
		n_rows = 800

	data_state = _zoo_explore_data_state(topic, dataset_file, seed=seed, n_rows=n_rows)
	cells = payload.get("cells") or build_zoo_explore_notebook()
	previous_results = payload.get("previous_results") or []
	cells_to_run = cells
	until_index = payload.get("until_index")
	if until_index is not None:
		try:
			idx = int(until_index)
		except (TypeError, ValueError):
			idx = -1
		if 0 <= idx < len(cells):
			cells_to_run = cells[: idx + 1]
	result = run_notebook(
		cells=cells_to_run,
		allowed_imports=ZOO_EXPLORE_IMPORTS,
		data_state=data_state,
		previous_results=previous_results,
		evaluation_rules={},
		mode="run",
	)
	result = dict(result)
	result["data_state"] = enrich_data_state_visuals(result.get("data_state") or data_state)
	# Strip any libraries note run_notebook may have attached; Zoo still shows an imports cell.
	result.update(_task_prompt_fields(result["data_state"]))
	return JsonResponse(result)
