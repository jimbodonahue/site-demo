from copy import deepcopy

import bleach
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils.safestring import mark_safe

from apps.exercises.markdown_utils import render_markdown_html


def _default_json_list():
	return []


def _default_json_dict():
	return {}


class Track(models.Model):
	"""A learning track that groups related exercises."""

	title = models.CharField(max_length=200)
	slug = models.SlugField(unique=True)
	summary = models.TextField(blank=True)
	order = models.PositiveIntegerField(default=0)
	published = models.BooleanField(default=False)
	is_placeholder = models.BooleanField(
		default=False,
		help_text="Placeholder tracks appear in the catalog but have no exercises yet.",
	)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["order", "title"]

	def __str__(self):
		return self.title

	def get_absolute_url(self):
		return reverse("exercises:track_detail", args=[self.slug])


class Exercise(models.Model):
	track = models.ForeignKey(
		Track,
		on_delete=models.PROTECT,
		related_name="exercises",
		null=True,
		blank=True,
	)
	title = models.CharField(max_length=200)
	slug = models.SlugField(unique=True)
	intro_markdown = models.TextField(blank=True)
	starter_code = models.TextField(blank=True)
	allowed_imports = models.JSONField(default=_default_json_list, blank=True)
	data_definition = models.JSONField(default=_default_json_dict, blank=True)
	evaluation_rules = models.JSONField(default=_default_json_dict, blank=True)
	graphic_markup = models.TextField(blank=True)
	soft_skill_prompt = models.TextField(
		blank=True,
		help_text="Reflective soft-skill question shown at the end of the exercise.",
	)
	order = models.PositiveIntegerField(default=0)
	published = models.BooleanField(default=False)
	is_placeholder = models.BooleanField(
		default=False,
		help_text="Placeholder exercises appear in the track catalog but are not playable yet.",
	)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["order", "title"]

	def __str__(self):
		return self.title

	def display_intro_markdown(self) -> str:
		"""Prefer content-file intro when present; fall back to the DB field."""
		from apps.exercises.content import get_intro

		return get_intro(self.slug) or self.intro_markdown or ""

	def display_soft_skill_prompt(self) -> str:
		from apps.exercises.content import get_soft_skill

		return get_soft_skill(self.slug) or self.soft_skill_prompt or ""

	def display_graphic_markup(self) -> str:
		from apps.exercises.content import get_graphic_markup

		return get_graphic_markup(self.slug) or self.graphic_markup or ""

	def display_starter_code(self) -> str:
		from apps.exercises.content import get_starter_code

		return get_starter_code(self.slug) or self.starter_code or ""

	def display_evaluation_rules(self) -> dict:
		from apps.exercises.content import apply_messages_to_rules

		return apply_messages_to_rules(self.slug, self.evaluation_rules)

	def clean(self):
		if self.published and not self.track_id:
			raise ValidationError("A published exercise must belong to a track.")

	def render_intro_html(self):
		return render_markdown_html(self.display_intro_markdown())

	def render_soft_skill_html(self):
		return render_markdown_html(self.display_soft_skill_prompt())

	def render_graphic_html(self):
		placeholder = (
			"<div class='rounded-2xl border border-dashed border-slate-300 dark:border-slate-600 "
			"bg-slate-50 dark:bg-slate-900 p-6 text-sm text-slate-500 dark:text-slate-400'>"
			"Exercise graphic placeholder</div>"
		)
		raw = self.display_graphic_markup() or placeholder
		sanitized = bleach.clean(
			raw,
			tags=[
				"p",
				"strong",
				"b",
				"em",
				"i",
				"ul",
				"ol",
				"li",
				"blockquote",
				"code",
				"pre",
				"div",
				"span",
				"table",
				"thead",
				"tbody",
				"tr",
				"th",
				"td",
				"a",
				"hr",
				"br",
				"h1",
				"h2",
				"h3",
				"h4",
				"img",
			],
			attributes={
				"a": ["href", "title"],
				"code": ["class"],
				"div": ["class"],
				"span": ["class"],
				"p": ["class"],
				"img": ["src", "alt", "class", "width", "height"],
			},
			protocols=["http", "https", "mailto"],
			strip=True,
		)
		return mark_safe(sanitized)

	def starter_cells(self, plotting_bonus_prompt: str | None = None):
		"""Default notebook: work cells and plotting-bonus cells (imports are preloaded)."""
		from apps.exercises.notebook_layout import build_starter_notebook

		return build_starter_notebook(
			self.allowed_imports,
			plotting_bonus_prompt=plotting_bonus_prompt or "",
		)

	def initial_data_state(self):
		state = deepcopy(self.data_definition.get("initial_data", {}))
		for key, val in self.data_definition.items():
			if key != "initial_data" and key not in state:
				state[key] = deepcopy(val)
		return state

	def feature_choices(self):
		choices = self.data_definition.get("feature_choices") or []
		if not choices:
			choices = self.data_definition.get("difficulty_choices") or []
		cleaned = []
		for choice in choices:
			item = {key: value for key, value in dict(choice).items() if key != "description"}
			cleaned.append(item)
		return cleaned

	def topic_choices(self):
		"""Return Data Zoo topic options for exercises that expose a topic selector."""
		choices = self.data_definition.get("topic_choices") or []
		if choices:
			cleaned = []
			for choice in choices:
				item = {key: value for key, value in dict(choice).items() if key != "description"}
				cleaned.append(item)
			return cleaned

		source = (
			self.data_definition.get("dataframe_source")
			or (self.data_definition.get("initial_data") or {}).get("dataframe_source")
		)
		# All playable generators draw from the Data Zoo and expose a sector picker.
		zoo_sources = {
			"data_quality",
			"missing_values",
			"pandas_intro",
			"data_transformation",
			"messy_dataset",
			"ab_testing",
			"descriptive_statistics",
		}
		if source not in zoo_sources:
			return []

		from apps.exercises.data_zoo import default_topic_choices

		return default_topic_choices()


class ExerciseAttempt(models.Model):
	exercise = models.ForeignKey(Exercise, on_delete=models.CASCADE, related_name="attempts")
	visitor_key = models.CharField(max_length=64, db_index=True)
	notebook_state = models.JSONField(default=_default_json_list, blank=True)
	data_state = models.JSONField(default=_default_json_dict, blank=True)
	result_state = models.JSONField(default=_default_json_dict, blank=True)
	progress_state = models.JSONField(default=_default_json_dict, blank=True)
	attempt_history = models.JSONField(
		default=_default_json_list,
		blank=True,
		help_text="Prior tries for this visitor (try number, timestamp, seed, saved state).",
	)
	soft_skill_response = models.TextField(blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		constraints = [
			models.UniqueConstraint(
				fields=["exercise", "visitor_key"],
				name="exercise_attempt_unique_visitor",
			)
		]

	def __str__(self):
		return f"{self.exercise.title} / {self.visitor_key}"

	@property
	def is_complete(self):
		return bool(self.progress_state.get("passed"))

	def reset_to_baseline(self):
		self.notebook_state = self.exercise.starter_cells()
		self.data_state = self.exercise.initial_data_state()
		self.result_state = {}
		self.progress_state = {
			"passed": False,
			"completed_cells": 0,
			"message": "Reset to the original starting state.",
		}
