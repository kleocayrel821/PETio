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

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email", "password1", "password2", "mobile_number", "age", "marketing_opt_in")

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