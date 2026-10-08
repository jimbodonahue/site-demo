from django import forms
from django.utils.translation import gettext_lazy as _


class FeedbackForm(forms.Form):
	previous_page = forms.CharField(required=False, widget=forms.HiddenInput())
	message = forms.CharField(
		label=_("Your feedback"),
		required=True,
		min_length=10,
		max_length=5000,
		widget=forms.Textarea(
			attrs={
				"rows": 6,
				"class": (
					"w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900 "
					"focus:border-primary-500 focus:outline-none dark:border-slate-600 "
					"dark:bg-slate-900 dark:text-slate-100"
				),
				"placeholder": "What worked well? What could be clearer?",
			}
		),
	)
	want_reply = forms.BooleanField(
		label=_("I would like a reply"),
		required=False,
		widget=forms.CheckboxInput(
			attrs={"class": "h-4 w-4 rounded border-slate-300 text-primary-600 focus:ring-primary-500"}
		),
	)
	email = forms.EmailField(
		label=_("Email for reply"),
		required=False,
		widget=forms.EmailInput(
			attrs={
				"class": (
					"w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900 "
					"focus:border-primary-500 focus:outline-none dark:border-slate-600 "
					"dark:bg-slate-900 dark:text-slate-100"
				),
				"placeholder": "you@example.com",
				"autocomplete": "email",
			}
		),
		help_text=_("Only used if you ask for a reply. Not stored as an account email."),
	)

	def __init__(self, *args, is_bug_report: bool = False, **kwargs):
		super().__init__(*args, **kwargs)
		if is_bug_report:
			self.fields["message"].label = _("What went wrong?")
			self.fields["message"].widget.attrs["placeholder"] = (
				"Describe the bug: what you expected, what happened, and which exercise or page."
			)

	def clean(self):
		cleaned = super().clean()
		want_reply = cleaned.get("want_reply")
		email = (cleaned.get("email") or "").strip()
		if want_reply and not email:
			self.add_error("email", _("Please enter an email address so we can reply."))
		cleaned["email"] = email
		return cleaned
