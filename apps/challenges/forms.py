from django import forms
from django.core.exceptions import ValidationError

from .models import Contest, Submission


class DataVizSubmissionForm(forms.ModelForm):
    class Meta:
        model = Submission
        fields = ("title", "image", "notes")
        widgets = {
            "title": forms.TextInput(
                attrs={
                    "class": "w-full rounded-xl border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:border-sky-500 focus:outline-none",
                    "placeholder": "Chart title",
                }
            ),
            "notes": forms.Textarea(
                attrs={
                    "rows": 3,
                    "class": "w-full rounded-xl border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:border-sky-500 focus:outline-none",
                    "placeholder": "Optional caption or what the chart shows…",
                }
            ),
            "image": forms.ClearableFileInput(
                attrs={
                    "accept": "image/png,.png",
                    "class": "w-full text-sm text-slate-500 file:mr-3 file:py-1.5 file:px-3 file:rounded-xl file:border-0 file:text-xs file:font-semibold file:bg-sky-50 file:text-sky-700 hover:file:bg-sky-100",
                }
            ),
        }

    def clean_image(self):
        image = self.cleaned_data.get("image")
        if not image:
            raise ValidationError("Please upload a PNG image.")

        if image.size > 2 * 1024 * 1024:
            raise ValidationError("PNG files must be smaller than 2 MB.")

        name = (getattr(image, "name", "") or "").lower()
        if not name.endswith(".png"):
            raise ValidationError("Only .png files are accepted for Data Viz.")

        try:
            from PIL import Image

            image.seek(0)
            with Image.open(image) as img:
                img.verify()
            image.seek(0)
            with Image.open(image) as img:
                if img.format != "PNG":
                    raise ValidationError("Only PNG images are accepted for Data Viz.")
            image.seek(0)
        except ValidationError:
            raise
        except Exception:
            raise ValidationError("The uploaded file is not a valid PNG image.")
        return image


class ResourceSubmissionForm(forms.ModelForm):
    class Meta:
        model = Submission
        fields = ("title", "url", "notes")
        widgets = {
            "title": forms.TextInput(
                attrs={
                    "class": "w-full rounded-xl border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:border-sky-500 focus:outline-none",
                    "placeholder": "Resource name",
                }
            ),
            "url": forms.URLInput(
                attrs={
                    "class": "w-full rounded-xl border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:border-sky-500 focus:outline-none",
                    "placeholder": "https://…",
                }
            ),
            "notes": forms.Textarea(
                attrs={
                    "rows": 3,
                    "class": "w-full rounded-xl border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:border-sky-500 focus:outline-none",
                    "placeholder": "Why is this worth checking out?",
                }
            ),
        }

    def clean_url(self):
        url = (self.cleaned_data.get("url") or "").strip()
        if not url:
            raise ValidationError("Please provide a link.")
        return url


class MisleadingHeadlineSubmissionForm(forms.ModelForm):
    class Meta:
        model = Submission
        fields = ("title", "url", "notes")
        widgets = {
            "title": forms.TextInput(
                attrs={
                    "class": "w-full rounded-xl border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:border-sky-500 focus:outline-none",
                    "placeholder": "The misleading headline…",
                }
            ),
            "url": forms.URLInput(
                attrs={
                    "class": "w-full rounded-xl border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:border-sky-500 focus:outline-none",
                    "placeholder": "https://… (optional source link)",
                }
            ),
            "notes": forms.Textarea(
                attrs={
                    "rows": 3,
                    "class": "w-full rounded-xl border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:border-sky-500 focus:outline-none",
                    "placeholder": "What makes this headline misleading?",
                }
            ),
        }

    def clean_title(self):
        title = (self.cleaned_data.get("title") or "").strip()
        if not title:
            raise ValidationError("Please provide the misleading headline.")
        return title


def build_submission_form(contest: Contest, data=None, files=None):
    if contest.is_data_viz:
        return DataVizSubmissionForm(data=data, files=files)
    if contest.is_misleading_headline:
        return MisleadingHeadlineSubmissionForm(data=data, files=files)
    return ResourceSubmissionForm(data=data, files=files)
