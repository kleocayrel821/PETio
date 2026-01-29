"""Forms for the accounts app.

Provides:
- CustomUserCreationForm to create accounts using the custom User model
- ProfileForm to allow users to edit their profile fields with validation
"""
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from .models import Profile

MAX_AVATAR_SIZE_MB = 5
MAX_AVATAR_SIZE_BYTES = MAX_AVATAR_SIZE_MB * 1024 * 1024

User = get_user_model()

class CustomUserCreationForm(UserCreationForm):
    """User creation form for the custom User model with extra fields.

    Captures email (unique), and optional fields to gather more info.
    """
    email = forms.EmailField(required=False, help_text="We'll use this for notifications and activation.")
    mobile_number = forms.CharField(required=False, max_length=32)
    age = forms.IntegerField(required=False, min_value=0)
    marketing_opt_in = forms.BooleanField(required=False)
    email_marketplace_notifications = forms.BooleanField(required=False, initial=True, label="Marketplace emails")
    email_on_request_updates = forms.BooleanField(required=False, initial=True, label="Emails on request updates")
    email_on_messages = forms.BooleanField(required=False, initial=True, label="Emails on new messages")

    class Meta(UserCreationForm.Meta):
        model = User
        fields = (
            "username",
            "email",
            "password1",
            "password2",
            "mobile_number",
            "age",
            "marketing_opt_in",
            "email_marketplace_notifications",
            "email_on_request_updates",
            "email_on_messages",
        )

    def __init__(self, *args, **kwargs):
        """Initialize form and set user-friendly widget attributes.

        Moving placeholder/id/class attributes into widgets avoids invalid
        template method calls like ``as_widget(attrs=...)`` and keeps
        rendering simple in templates.
        """
        super().__init__(*args, **kwargs)

        # Common input styling class used by base template
        base_input_class = "form-control-enhanced"

        # Username
        if "username" in self.fields:
            self.fields["username"].widget.attrs.update({
                "id": "username",
                "placeholder": "Choose a unique username",
                "class": base_input_class,
                "autocomplete": "username",
            })

        # Email
        if "email" in self.fields:
            self.fields["email"].widget.attrs.update({
                "id": "email",
                "placeholder": "you@example.com",
                "class": base_input_class,
                "autocomplete": "email",
            })

        # Passwords
        if "password1" in self.fields:
            self.fields["password1"].widget.attrs.update({
                "id": "password1",
                "placeholder": "Create a strong password",
                "class": base_input_class,
                "autocomplete": "new-password",
            })
        if "password2" in self.fields:
            self.fields["password2"].widget.attrs.update({
                "id": "password2",
                "placeholder": "Re-enter your password",
                "class": base_input_class,
                "autocomplete": "new-password",
            })

        # Optional fields
        if "mobile_number" in self.fields:
            self.fields["mobile_number"].widget.attrs.update({
                "id": "mobile_number",
                "placeholder": "+63 912 345 6789",
                "class": base_input_class,
                "inputmode": "tel",
                "autocomplete": "tel",
            })
        if "age" in self.fields:
            self.fields["age"].widget.attrs.update({
                "id": "age",
                "placeholder": "25",
                "class": base_input_class,
                "min": "13",
                "max": "120",
            })

class ProfileForm(forms.ModelForm):
    """ModelForm for editing Profile fields.

    Includes basic validation for avatar file size and uses clean labels.
    """

    class Meta:
        model = Profile
        fields = [
            "display_name",
            "bio",
            "location",
            "phone",
            "avatar",
        ]
        widgets = {
            "bio": forms.Textarea(attrs={"rows": 4}),
        }
        labels = {
            "display_name": "Display Name",
            "bio": "Bio",
            "location": "Location",
            "phone": "Phone",
            "avatar": "Avatar (optional)",
        }

    def clean_avatar(self):
        """Validate that avatar file size does not exceed MAX_AVATAR_SIZE_MB."""
        avatar = self.cleaned_data.get("avatar")
        if avatar and hasattr(avatar, "size") and avatar.size > MAX_AVATAR_SIZE_BYTES:
            raise forms.ValidationError(
                f"Avatar file too large. Max size is {MAX_AVATAR_SIZE_MB}MB."
            )
        return avatar
