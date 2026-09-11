from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserChangeForm, UserCreationForm
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from apps.exercises.data_zoo import DATA_SCIENCE_SECTORS, list_zoo_datasets

from .models import CustomUser, UserProfile


class CustomUserCreationForm(UserCreationForm):
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(
            attrs={
                "placeholder": "you@example.com",
            }
        ),
    )
    username = forms.CharField(
        required=False,
        widget=forms.TextInput(
            attrs={
                "placeholder": "username",
            }
        ),
    )
    first_name = forms.CharField(
        required=True,
        widget=forms.TextInput(
            attrs={
                "placeholder": "John",
            }
        ),
    )
    last_name = forms.CharField(
        required=True,
        widget=forms.TextInput(
            attrs={
                "placeholder": "Doe",
            }
        ),
    )
    password1 = forms.CharField(
        widget=forms.PasswordInput(
            attrs={
                "placeholder": "*********",
            }
        )
    )
    password2 = forms.CharField(
        widget=forms.PasswordInput(
            attrs={
                "placeholder": "*********",
            }
        )
    )

    class Meta:
        model = CustomUser
        fields = (
            "email",
            "username",
            "first_name",
            "last_name",
            "password1",
            "password2",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control"

    def clean_email(self):
        email = self.cleaned_data.get("email")
        if CustomUser.objects.exclude(pk=self.instance.pk).filter(email=email).exists():
            raise forms.ValidationError(_("This email address is already in use."))
        return email

    def clean_username(self):
        username = self.cleaned_data.get("username")
        if username:
            if CustomUser.objects.filter(username=username).exists():
                raise forms.ValidationError(_("This username is already in use."))
            if (
                not username.replace("_", "")
                .replace("-", "")
                .replace(".", "")
                .replace("@", "")
                .replace("+", "")
                .isalnum()
            ):
                raise forms.ValidationError(
                    _("Username can only contain letters, digits and @/./+/-/_")
                )
        return username

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.username = self.cleaned_data.get("username")
        user.first_name = self.cleaned_data["first_name"]
        user.last_name = self.cleaned_data["last_name"]
        if commit:
            user.save()
        return user


class CustomUserChangeForm(UserChangeForm):
    password = None

    email = forms.EmailField(
        required=True, widget=forms.EmailInput(attrs={"class": "form-control"})
    )
    username = forms.CharField(
        required=False,
        max_length=150,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    first_name = forms.CharField(
        required=True, widget=forms.TextInput(attrs={"class": "form-control"})
    )
    last_name = forms.CharField(
        required=True, widget=forms.TextInput(attrs={"class": "form-control"})
    )

    class Meta:
        model = CustomUser
        fields = ("email", "username", "first_name", "last_name")

    def clean_username(self):
        username = self.cleaned_data.get("username")
        if username:
            if (
                CustomUser.objects.exclude(pk=self.instance.pk)
                .filter(username=username)
                .exists()
            ):
                raise forms.ValidationError(_("This username is already in use."))
            if (
                not username.replace("_", "")
                .replace("-", "")
                .replace(".", "")
                .replace("@", "")
                .replace("+", "")
                .isalnum()
            ):
                raise forms.ValidationError(
                    _("Username can only contain letters, digits and @/./+/-/_")
                )
        return username


class UserProfileForm(forms.ModelForm):
    nickname = forms.CharField(
        max_length=40,
        required=True,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "DataNerd"}),
    )
    photo = forms.ImageField(
        required=False,
        widget=forms.ClearableFileInput(attrs={"class": "form-control"}),
    )
    short_description = forms.CharField(
        required=False,
        max_length=180,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "I enjoy finding patterns in messy datasets."}),
    )
    motivation = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 4, "placeholder": "I got into data analysis because..."}),
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


class UserOnboardingForm(forms.Form):
    data_field = forms.ChoiceField(
        label=_("Field"),
        choices=[],
        required=True,
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    dataset_file = forms.ChoiceField(
        label=_("Dataset file"),
        choices=[],
        required=True,
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        field_choices = [(sector, sector.replace("_", " ").title()) for sector in DATA_SCIENCE_SECTORS]
        self.fields["data_field"].choices = field_choices
        selected_field = self.data.get("data_field") or self.initial.get("data_field") or field_choices[0][0]
        self.fields["dataset_file"].choices = self._dataset_choices(selected_field)

    def _dataset_choices(self, sector):
        files = []
        for path in list_zoo_datasets(sector):
            files.append((path.name, path.name))
        return files or [("", _("No datasets available"))]

    def clean(self):
        cleaned_data = super().clean()
        selected_field = cleaned_data.get("data_field")
        selected_file = cleaned_data.get("dataset_file")
        if not selected_field or not selected_file:
            return cleaned_data

        valid_files = {item[0] for item in self._dataset_choices(selected_field)}
        if selected_file not in valid_files:
            raise forms.ValidationError(_("Please select a valid dataset file for the chosen field."))
        return cleaned_data


class CustomLoginForm(AuthenticationForm):
    username = forms.EmailField(
        label=_("Email"),
        widget=forms.EmailInput(attrs={"class": "form-control", "autocomplete": "email"}),
    )
    password = forms.CharField(
        label=_("Password"),
        strip=False,
        widget=forms.PasswordInput(attrs={"class": "form-control", "autocomplete": "current-password"}),
    )
