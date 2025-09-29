"""
Accounts views: Signup, Login redirect mixin, and Profile view.
Uses Django auth forms for security and simplicity.
"""
from django.contrib.auth import login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView, DetailView
from django.contrib.auth import get_user_model
from django.contrib import messages
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import EmailMultiAlternatives
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes
from django.urls import reverse
from django.views import View
from django.views.generic import UpdateView
from .models import Profile
try:
    # Local import; this file edit assumes forms.py will be created in the same app
    from .forms import ProfileForm, CustomUserCreationForm
except Exception:  # pragma: no cover - during initial load before file exists
    ProfileForm = None
    CustomUserCreationForm = None

User = get_user_model()

class SignupView(CreateView):
    """Allow visitors to create an account. Sends activation email and requires confirmation."""
    form_class = CustomUserCreationForm
    template_name = "accounts/signup.html"
    success_url = reverse_lazy("login")

    def form_valid(self, form):
        """On successful form submission, create inactive user and send activation email."""
        response = super().form_valid(form)
        # Ensure the new user is inactive until email is confirmed
        self.object.is_active = False
        # Assign optional fields captured during signup
        # Note: UserCreationForm already saved the instance; update extra fields
        cleaned = form.cleaned_data
        self.object.email = cleaned.get("email", "")
        self.object.mobile_number = cleaned.get("mobile_number", "")
        self.object.age = cleaned.get("age")
        self.object.marketing_opt_in = cleaned.get("marketing_opt_in", False)
        self.object.save()

        # Build activation URL
        uidb64 = urlsafe_base64_encode(force_bytes(self.object.pk))
        token = default_token_generator.make_token(self.object)
        activation_path = reverse("accounts:activate", kwargs={"uidb64": uidb64, "token": token})
        activation_url = self.request.build_absolute_uri(activation_path)

        # Render and send email content (fail silently if templates or email backend missing)
        try:
            subject = "Activate your PETio account"
            from_email = None  # Use DEFAULT_FROM_EMAIL from settings
            to = [self.object.email] if getattr(self.object, "email", "") else []
            if to:
                html_body = self.render_to_string("accounts/activation_email.html", {"activation_url": activation_url})
                text_body = self.render_to_string("accounts/activation_email.txt", {"activation_url": activation_url})
                email = EmailMultiAlternatives(subject=subject, body=text_body, from_email=from_email, to=to)
                email.attach_alternative(html_body, "text/html")
                try:
                    email.send(fail_silently=True)
                except Exception:
                    pass
        except Exception:
            # Ignore email rendering errors in development/testing
            pass

        messages.info(self.request, "Account created. Please check your email to activate your account.")
        return response

    def render_to_string(self, template_name, context):
        """Helper to render template as string for emails."""
        from django.template.loader import render_to_string
        return render_to_string(template_name, context)

    def get_success_url(self):
        """Prefer next param if present; redirect to login with next preserved."""
        next_url = self.request.GET.get("next") or self.request.POST.get("next")
        if next_url:
            return f"{str(self.success_url)}?next={next_url}"
        return str(self.success_url)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        return kwargs

    def get_queryset(self):
        return User.objects.all()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["title"] = "Create your PETio account"
        return ctx

class ActivationView(View):
    """Handle account activation via uidb64 and token."""
    template_name = "accounts/activation_confirm.html"

    def get(self, request, uidb64, token):
        activated = False
        try:
            uid = urlsafe_base64_decode(uidb64).decode()
            user = User.objects.get(pk=uid)
        except Exception:
            user = None
        if user and default_token_generator.check_token(user, token):
            user.is_active = True
            user.save()
            activated = True
        context = {"activated": activated}
        from django.shortcuts import render
        return render(request, self.template_name, context)

class ProfileDetailView(LoginRequiredMixin, DetailView):
    """Simple profile page showing current user's info."""
    template_name = "accounts/profile.html"
    context_object_name = "user_obj"

    def get_object(self, queryset=None):
        return self.request.user

class ProfileUpdateView(LoginRequiredMixin, UpdateView):
    """Allow the authenticated user to update their Profile fields.

    Uses a ModelForm to provide validation and CSRF protection. Only the
    logged-in user's own Profile object is editable; no ID is exposed in the URL.
    """
    model = Profile
    form_class = ProfileForm
    template_name = "accounts/profile_edit.html"
    success_url = reverse_lazy("accounts:profile")

    def get_object(self, queryset=None):
        """Return the current user's Profile instance."""
        return self.request.user.profile

    def form_valid(self, form):
        """Display a success message and proceed with the update."""
        messages.success(self.request, "Your profile has been updated.")
        return super().form_valid(form)

    def get_form_kwargs(self):
        """Ensure request.FILES are handled for avatar uploads."""
        kwargs = super().get_form_kwargs()
        if self.request.method in ("POST", "PUT"):
            kwargs.update({"files": self.request.FILES})
        return kwargs