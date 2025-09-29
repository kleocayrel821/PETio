"""
Forms for marketplace app: ListingForm with server-side validations.
- Validates price > 0
- Validates quantity > 0
- Validates main_image size <= 5MB (if provided)
"""
from django import forms
from django.core.exceptions import ValidationError

from .models import Listing


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