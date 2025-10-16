from django import forms
from .models import Post, Comment, UserProfile


class PostForm(forms.ModelForm):
    class Meta:
        model = Post
        fields = ["title", "content", "category", "image"]
        widgets = {
            "title": forms.TextInput(attrs={
                "class": "input input-bordered w-full",
                "placeholder": "Enter a concise, descriptive title",
                "maxlength": 200,
            }),
            "content": forms.Textarea(attrs={
                "class": "textarea textarea-bordered w-full min-h-[160px]",
                "placeholder": "Share detailed content...",
            }),
            "category": forms.Select(attrs={
                "class": "select select-bordered w-full",
            }),
            "image": forms.ClearableFileInput(attrs={
                "class": "file-input file-input-bordered w-full",
                "accept": "image/*",
            }),
        }

    def clean_title(self):
        title = self.cleaned_data.get("title", "").strip()
        if len(title) < 3:
            raise forms.ValidationError("Title must be at least 3 characters long.")
        return title

    def clean_content(self):
        content = self.cleaned_data.get("content", "").strip()
        if len(content) < 10:
            raise forms.ValidationError("Content must be at least 10 characters long.")
        return content


class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ["content"]
        widgets = {
            "content": forms.Textarea(attrs={
                "class": "textarea textarea-bordered w-full min-h-[100px]",
                "placeholder": "Write a comment...",
            })
        }

    def clean_content(self):
        content = self.cleaned_data.get("content", "").strip()
        if len(content) < 2:
            raise forms.ValidationError("Comment must be at least 2 characters long.")
        return content


class ProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = [
            "bio",
            "avatar",
            "location",
            "website",
            "birth_date",
            "is_private",
        ]
        widgets = {
            "bio": forms.Textarea(attrs={
                "class": "textarea textarea-bordered w-full",
                "placeholder": "Share a bit about yourself...",
                "maxlength": 500,
            }),
            "avatar": forms.ClearableFileInput(attrs={
                "class": "file-input file-input-bordered w-full",
                "accept": "image/*",
            }),
            "location": forms.TextInput(attrs={
                "class": "input input-bordered w-full",
                "placeholder": "City, Country",
            }),
            "website": forms.URLInput(attrs={
                "class": "input input-bordered w-full",
                "placeholder": "https://example.com",
            }),
            "birth_date": forms.DateInput(attrs={
                "class": "input input-bordered w-full",
                "type": "date",
            }),
            "is_private": forms.CheckboxInput(attrs={
                "class": "toggle toggle-primary",
            }),
        }