from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from apps.exercises.data_zoo import DATA_SCIENCE_SECTORS, list_zoo_datasets

from .models import AccountDeletionRequest, UserProfile


class UserProfileForm(forms.ModelForm):
    nickname = forms.CharField(
        max_length=40,
        required=True,
        label=_("Nickname"),
        widget=forms.TextInput(
            attrs={
                "class": "w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900 focus:border-primary-500 focus:outline-none dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100",
                "placeholder": "DataNerd",
            }
        ),
    )
    photo = forms.ImageField(
        required=False,
        label=_("Avatar"),
        widget=forms.ClearableFileInput(
            attrs={
                "class": "w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-700 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200",
            }
        ),
        help_text=_("Optional. PNG, JPG, JPEG, or WEBP under 2 MB."),
    )
    short_description = forms.CharField(
        required=False,
        max_length=180,
        label=_("Short intro"),
        widget=forms.TextInput(
            attrs={
                "class": "w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900 focus:border-primary-500 focus:outline-none dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100",
                "placeholder": "I enjoy finding patterns in messy datasets.",
            }
        ),
    )
    motivation = forms.CharField(
        required=False,
        label=_("About me"),
        widget=forms.Textarea(
            attrs={
                "class": "w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900 focus:border-primary-500 focus:outline-none dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100",
                "rows": 6,
                "placeholder": (
                    "Share as much or as little as you like: your background, "
                    "programming and statistical experience, and non-technical hobbies."
                ),
            }
        ),
        help_text=_(
            "Optional. Background, programming and statistical experience, and hobbies."
        ),
    )

    class Meta:
        model = UserProfile
        fields = ("nickname", "photo", "short_description", "motivation")

    def clean_nickname(self):
        nickname = self.cleaned_data.get("nickname")
        if not nickname:
            return nickname

        nickname = nickname.strip()
        if not nickname:
            raise forms.ValidationError(_("Nickname cannot be blank."))

        if UserProfile.objects.exclude(pk=self.instance.pk).filter(nickname__iexact=nickname).exists():
            raise forms.ValidationError(_("This nickname is already in use."))
        return nickname

    def clean_photo(self):
        photo = self.cleaned_data.get("photo")
        if not photo:
            return photo

        if photo.size > 2 * 1024 * 1024:
            raise ValidationError(_("Profile photos must be smaller than 2 MB."))

        if not photo.name.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
            raise ValidationError(_("Please upload a PNG, JPG, JPEG, or WEBP image."))

        try:
            from PIL import Image

            img = Image.open(photo)
            img.verify()
        except Exception:
            raise ValidationError(_("The uploaded file is not a valid image."))
        return photo


class EmailPasskeyForm(forms.Form):
    """One-shot email address for mailing the passkey. Never persisted on the user."""

    email = forms.EmailField(
        label=_("Your email address"),
        required=True,
        widget=forms.EmailInput(
            attrs={
                "class": "w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900 focus:border-primary-500 focus:outline-none dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100",
                "placeholder": "you@example.com",
                "autocomplete": "email",
            }
        ),
        help_text=_(
            "We will send your passkey to this address once and will not store the email."
        ),
    )


class AccountDeletionForm(forms.Form):
    reason = forms.ChoiceField(
        label=_("Reason for leaving"),
        choices=AccountDeletionRequest.REASON_CHOICES,
        required=True,
        widget=forms.Select(
            attrs={
                "class": (
                    "w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900 "
                    "focus:border-primary-500 focus:outline-none dark:border-slate-600 "
                    "dark:bg-slate-900 dark:text-slate-100"
                ),
            }
        ),
    )
    details = forms.CharField(
        label=_("Tell us more (optional)"),
        required=False,
        max_length=5000,
        widget=forms.Textarea(
            attrs={
                "rows": 4,
                "class": (
                    "w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900 "
                    "focus:border-primary-500 focus:outline-none dark:border-slate-600 "
                    "dark:bg-slate-900 dark:text-slate-100"
                ),
                "placeholder": "Anything that would help us understand why you are leaving…",
            }
        ),
    )
    feedback = forms.CharField(
        label=_("Feedback or complaints (optional)"),
        required=False,
        max_length=5000,
        widget=forms.Textarea(
            attrs={
                "rows": 4,
                "class": (
                    "w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900 "
                    "focus:border-primary-500 focus:outline-none dark:border-slate-600 "
                    "dark:bg-slate-900 dark:text-slate-100"
                ),
                "placeholder": "Suggestions, bugs, or complaints for the team…",
            }
        ),
    )
    confirm = forms.BooleanField(
        label=_(
            "I understand that my account and associated data will be deleted within 48 hours, "
            "and that this cannot be undone."
        ),
        required=True,
        widget=forms.CheckboxInput(
            attrs={"class": "h-4 w-4 rounded border-slate-300 text-red-600 focus:ring-red-500"}
        ),
    )

    def clean_confirm(self):
        if not self.cleaned_data.get("confirm"):
            raise ValidationError(
                _("Please confirm that you understand your data will be deleted within 48 hours.")
            )
        return True


class ContactShareForm(forms.Form):
    contact_details = forms.CharField(
        label=_("Contact details"),
        required=True,
        max_length=2000,
        widget=forms.Textarea(
            attrs={
                "class": "w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900 focus:border-primary-500 focus:outline-none dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100",
                "rows": 4,
                "placeholder": "Email, chat handle, or other ways to reach you…",
            }
        ),
        help_text=_("This text is delivered once and is not stored after the other person views it."),
    )

    def clean_contact_details(self):
        details = (self.cleaned_data.get("contact_details") or "").strip()
        if not details:
            raise forms.ValidationError(_("Please enter the contact details you want to share."))
        return details


class UserOnboardingForm(forms.Form):
	"""Rank up to five preferred Data Zoo topics (first choice is required)."""

	topic_1 = forms.ChoiceField(
		label=_("1st choice (default)"),
		choices=[],
		required=True,
		widget=forms.Select(attrs={"class": "form-control"}),
	)
	topic_2 = forms.ChoiceField(
		label=_("2nd choice (optional)"),
		choices=[],
		required=False,
		widget=forms.Select(attrs={"class": "form-control"}),
	)
	topic_3 = forms.ChoiceField(
		label=_("3rd choice (optional)"),
		choices=[],
		required=False,
		widget=forms.Select(attrs={"class": "form-control"}),
	)
	topic_4 = forms.ChoiceField(
		label=_("4th choice (optional)"),
		choices=[],
		required=False,
		widget=forms.Select(attrs={"class": "form-control"}),
	)
	topic_5 = forms.ChoiceField(
		label=_("5th choice (optional)"),
		choices=[],
		required=False,
		widget=forms.Select(attrs={"class": "form-control"}),
	)
	dataset_file = forms.ChoiceField(
		label=_("Preferred dataset for 1st choice (optional)"),
		choices=[],
		required=False,
		widget=forms.Select(attrs={"class": "form-control"}),
	)

	TOPIC_FIELDS = ("topic_1", "topic_2", "topic_3", "topic_4", "topic_5")

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		blank = [("", _("— none —"))]
		field_choices = [(sector, sector.replace("_", " ").title()) for sector in DATA_SCIENCE_SECTORS]
		for index, name in enumerate(self.TOPIC_FIELDS):
			self.fields[name].choices = field_choices if index == 0 else blank + field_choices

		selected_field = (
			self.data.get("topic_1")
			or self.initial.get("topic_1")
			or self.initial.get("data_field")
			or field_choices[0][0]
		)
		file_choices = self._dataset_choices(selected_field)
		self.fields["dataset_file"].choices = blank + file_choices

	def _dataset_choices(self, sector):
		files = []
		for path in list_zoo_datasets(sector or ""):
			files.append((path.name, path.name))
		return files

	def clean(self):
		cleaned_data = super().clean()
		ranked: list[str] = []
		for name in self.TOPIC_FIELDS:
			value = (cleaned_data.get(name) or "").strip().lower()
			if not value:
				continue
			if value not in DATA_SCIENCE_SECTORS:
				self.add_error(name, _("Please choose a valid Data Zoo topic."))
				continue
			if value in ranked:
				self.add_error(name, _("Each preferred topic must be unique."))
				continue
			ranked.append(value)

		if not ranked:
			self.add_error("topic_1", _("Please choose at least one preferred topic."))
			return cleaned_data

		cleaned_data["preferred_topics"] = ranked
		cleaned_data["data_field"] = ranked[0]

		selected_file = (cleaned_data.get("dataset_file") or "").strip()
		if selected_file:
			valid_files = {item[0] for item in self._dataset_choices(ranked[0])}
			if selected_file not in valid_files:
				self.add_error(
					"dataset_file",
					_("Please select a valid dataset file for your 1st-choice topic."),
				)
		else:
			cleaned_data["dataset_file"] = ""
		return cleaned_data
