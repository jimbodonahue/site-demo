from copy import deepcopy

import bleach
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from markdown import markdown
from django.utils.safestring import mark_safe


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

	def clean(self):
		if self.published and not self.track_id:
			raise ValidationError("A published exercise must belong to a track.")

	def render_intro_html(self):
		if not self.intro_markdown:
			return ""
		html = markdown(self.intro_markdown, extensions=["fenced_code", "tables"])
		sanitized = bleach.clean(
			html,
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
			],
			attributes={
				"a": ["href", "title"],
				"code": ["class"],
			},
			protocols=["http", "https", "mailto"],
			strip=True,
		)
		return mark_safe(sanitized)

	def render_graphic_html(self):
		if self.graphic_markup:
			return mark_safe(self.graphic_markup)
		return mark_safe(
			"<div class='rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-6 text-sm text-slate-500'>"
			"Exercise graphic placeholder</div>"
		)

	def starter_cells(self):
		"""Student notebooks always start with two empty cells and no output."""
		return [{"source": ""}, {"source": ""}]

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
		# Data quality cleanup uses generated zoo samples by sector.
		# Missing-values exercises also need a dataset file, so they opt in via topic_choices.
		if source != "data_quality":
			return []

		from apps.exercises.data_zoo import DATA_SCIENCE_SECTORS

		return [
			{"label": sector.replace("_", " ").title(), "value": sector}
			for sector in DATA_SCIENCE_SECTORS
		]


class ExerciseAttempt(models.Model):
	exercise = models.ForeignKey(Exercise, on_delete=models.CASCADE, related_name="attempts")
	visitor_key = models.CharField(max_length=64, db_index=True)
	notebook_state = models.JSONField(default=_default_json_list, blank=True)
	data_state = models.JSONField(default=_default_json_dict, blank=True)
	result_state = models.JSONField(default=_default_json_dict, blank=True)
	progress_state = models.JSONField(default=_default_json_dict, blank=True)
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
