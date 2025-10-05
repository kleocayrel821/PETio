"""
Forms for marketplace app: ListingForm with server-side validations.
- Validates price > 0
- Validates quantity > 0
- Validates main_image size <= 5MB (if provided)
"""
from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import Listing, SellerRating
from decimal import Decimal


class ListingForm(forms.ModelForm):
    """ModelForm for creating/editing a Listing with basic validations.

    Enforces:
    - Positive price
    - Positive quantity
    - Image size must be <= 5 MB when provided
    """

    MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB

    class Meta:
        model = Listing
        # seller is set in the view; do not expose it via the form
        fields = [
            "title",
            "category",
            "price",
            "quantity",
            "description",
            "main_image",
        ]
        widgets = {
            "title": forms.TextInput(attrs={
                "placeholder": "Short, clear product name",
                "maxlength": "120",
                "class": "input input-bordered w-full",
            }),
            "category": forms.Select(attrs={
                "class": "select select-bordered w-full",
            }),
            "price": forms.NumberInput(attrs={
                "min": "0.01",
                "step": "0.01",
                "inputmode": "decimal",
                "placeholder": "e.g., 19.99",
                "class": "input input-bordered w-full",
            }),
            "quantity": forms.NumberInput(attrs={
                "min": "1",
                "step": "1",
                "inputmode": "numeric",
                "placeholder": "e.g., 10",
                "class": "input input-bordered w-full",
            }),
            "description": forms.Textarea(attrs={
                "placeholder": "Describe the item, condition, size, and any important details",
                "class": "textarea textarea-bordered h-32 w-full",
            }),
            "main_image": forms.ClearableFileInput(attrs={
                "accept": "image/*",
                "class": "file-input file-input-bordered w-full",
            }),
        }

    def clean_price(self):
        """Ensure price is greater than 0."""
        price = self.cleaned_data.get("price")
        if price is None or price <= 0:
            raise ValidationError("Price must be greater than 0.")
        return price

    def clean_quantity(self):
        """Ensure quantity is a positive integer."""
        qty = self.cleaned_data.get("quantity")
        if qty is None or qty <= 0:
            raise ValidationError("Quantity must be greater than 0.")
        return qty

    def clean_main_image(self):
        """Validate uploaded image size if present (<= 5 MB)."""
        image = self.cleaned_data.get("main_image")
        if not image:
            return image
        # UploadedFile provides size in bytes
        if getattr(image, "size", 0) > self.MAX_IMAGE_SIZE_BYTES:
            raise ValidationError("Image file too large (max 5 MB).")
        return image


class SellerRatingForm(forms.ModelForm):
    """ModelForm for buyer rating of seller post-completion.

    Provides a constrained score field and optional comment.
    """

    SCORE_CHOICES = [(i, str(i)) for i in range(1, 6)]

    score = forms.ChoiceField(choices=SCORE_CHOICES, widget=forms.RadioSelect)
    comment = forms.CharField(required=False, widget=forms.Textarea(attrs={
        "placeholder": "Optional feedback for the seller",
        "class": "textarea textarea-bordered h-24 w-full",
    }))

    class Meta:
        model = SellerRating
        fields = ["score", "comment"]

    def clean_score(self):
        """Ensure score is in 1..5."""
        val = self.cleaned_data.get("score")
        try:
            iv = int(val)
        except (TypeError, ValueError):
            raise ValidationError("Invalid score value")
        if iv < 1 or iv > 5:
            raise ValidationError("Score must be between 1 and 5")
        return iv


class MeetupProposalForm(forms.Form):
    """Form for proposing or updating meetup details.

    Validates that meetup_time is timezone-aware and in the future, and that
    meetup_place is non-empty and within reasonable length.
    """

    # Accept common HTML5 datetime-local and ISO formats
    meetup_time = forms.DateTimeField(
        required=True,
        input_formats=[
            "%Y-%m-%dT%H:%M",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d %H:%M:%S",
        ],
        widget=forms.DateTimeInput(attrs={
            "type": "datetime-local",
            "class": "input input-bordered w-56",
        }),
    )
    meetup_place = forms.CharField(
        required=True,
        max_length=200,
        widget=forms.TextInput(attrs={
            "placeholder": "Place (e.g., cafe, park)",
            "class": "input input-bordered w-64",
        }),
    )
    # Optional timezone selector; defaults to server's current timezone
    meetup_timezone = forms.ChoiceField(
        required=False,
        choices=[
            ("", "Use local timezone"),
            ("UTC", "UTC"),
            ("US/Eastern", "US/Eastern"),
            ("US/Central", "US/Central"),
            ("US/Mountain", "US/Mountain"),
            ("US/Pacific", "US/Pacific"),
            ("Europe/London", "Europe/London"),
            ("Europe/Paris", "Europe/Paris"),
            ("Asia/Singapore", "Asia/Singapore"),
            ("Asia/Tokyo", "Asia/Tokyo"),
            ("Australia/Sydney", "Australia/Sydney"),
        ],
        widget=forms.Select(attrs={
            "class": "select select-bordered w-56",
        }),
    )
    # Optional reason when updating/rescheduling
    reschedule_reason = forms.CharField(
        required=False,
        max_length=240,
        widget=forms.TextInput(attrs={
            "placeholder": "Reason for reschedule (optional)",
            "class": "input input-bordered w-full",
        }),
    )

    def clean_meetup_time(self):
        dt = self.cleaned_data.get("meetup_time")
        if dt is None:
            raise ValidationError("Meetup time is required")
        # Localize naive datetime to default timezone
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt, timezone.get_default_timezone())
        # Require future datetime
        if dt <= timezone.now():
            raise ValidationError("Meetup time must be in the future")
        return dt

    def clean_meetup_place(self):
        place = (self.cleaned_data.get("meetup_place") or "").strip()
        if not place:
            raise ValidationError("Meetup place is required")
        return place

    def clean_meetup_timezone(self):
        tz = (self.cleaned_data.get("meetup_timezone") or "").strip()
        # Allow empty (use server default)
        if not tz:
            return ""
        try:
            # Validate against zoneinfo; fallback to pytz if available
            try:
                from zoneinfo import ZoneInfo
                ZoneInfo(tz)
            except Exception:
                import pytz  # type: ignore
                if tz not in getattr(pytz, "common_timezones", []):
                    raise Exception("invalid tz")
        except Exception:
            raise ValidationError("Invalid timezone")
        return tz


class OfferForm(forms.Form):
    """Form for buyers to submit a price offer and quantity."""

    offer_price = forms.DecimalField(
        required=True,
        min_value=Decimal("0.01"),
        max_digits=10,
        decimal_places=2,
        widget=forms.NumberInput(attrs={
            "min": "0.01",
            "step": "0.01",
            "class": "input input-bordered w-32",
            "placeholder": "Offer price",
        }),
    )
    quantity = forms.IntegerField(
        required=True,
        min_value=1,
        widget=forms.NumberInput(attrs={
            "min": "1",
            "step": "1",
            "class": "input input-bordered w-24",
            "placeholder": "Qty",
        }),
    )

    def __init__(self, *args, listing=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.listing = listing

    def clean_quantity(self):
        qty = self.cleaned_data.get("quantity")
        listing = self.listing
        if listing and qty is not None:
            max_qty = getattr(listing, "quantity", 0)
            if qty > max_qty:
                raise ValidationError(f"Quantity cannot exceed available stock ({max_qty}).")
        return qty


class RespondOfferForm(forms.Form):
    """Form for sellers to respond: accept/reject/counter with price."""

    action = forms.ChoiceField(choices=[
        ("accept", "Accept"),
        ("reject", "Reject"),
        ("counter", "Counter"),
    ])
    counter_offer = forms.DecimalField(
        required=False,
        min_value=Decimal("0.01"),
        max_digits=10,
        decimal_places=2,
        widget=forms.NumberInput(attrs={
            "min": "0.01",
            "step": "0.01",
            "class": "input input-bordered w-32",
            "placeholder": "Counter price",
        }),
    )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("action") == "counter" and not cleaned.get("counter_offer"):
            raise ValidationError("Counter price is required when countering.")
        return cleaned