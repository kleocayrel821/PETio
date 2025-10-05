"""
Accounts views: Signup, Login redirect mixin, and Profile view.
Uses Django auth forms for security and simplicity.
"""
from django.contrib.auth import login
from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView
from django.urls import reverse_lazy
from django.views.generic import CreateView, DetailView
from django.db.models import Avg, Count
from django.contrib.auth import get_user_model
from django.contrib import messages
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import EmailMultiAlternatives
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes
from django.urls import reverse
from django.views import View
from django.views.generic import UpdateView
from django.shortcuts import resolve_url
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
        """On successful form submission, create user and conditionally require activation."""
        response = super().form_valid(form)
        # Conditionally require activation based on settings
        activation_required = getattr(settings, "ACCOUNT_ACTIVATION_REQUIRED", False)
        self.object.is_active = not activation_required
        # Assign optional fields captured during signup
        # Note: UserCreationForm already saved the instance; update extra fields
        cleaned = form.cleaned_data
        self.object.email = cleaned.get("email", "")
        self.object.mobile_number = cleaned.get("mobile_number", "")
        self.object.age = cleaned.get("age")
        self.object.marketing_opt_in = cleaned.get("marketing_opt_in", False)
        self.object.email_marketplace_notifications = cleaned.get("email_marketplace_notifications", True)
        self.object.email_on_request_updates = cleaned.get("email_on_request_updates", True)
        self.object.email_on_messages = cleaned.get("email_on_messages", True)
        self.object.save()

        # Build activation URL
        uidb64 = urlsafe_base64_encode(force_bytes(self.object.pk))
        token = default_token_generator.make_token(self.object)
        activation_path = reverse("accounts:activate", kwargs={"uidb64": uidb64, "token": token})
        activation_url = self.request.build_absolute_uri(activation_path)

        # Render and send email content only when activation is required
        if activation_required:
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

        messages.info(self.request, "Account created. " + ("Please check your email to activate your account." if activation_required else "You can now log in."))
        return response

    def render_to_string(self, template_name, context):
        """Helper to render template as string for emails."""
        from django.template.loader import render_to_string
        return render_to_string(template_name, context)

    def get_success_url(self):
        """Redirect to login and prefill username; preserve next if provided."""
        next_url = self.request.GET.get("next") or self.request.POST.get("next")
        username = getattr(self.object, "username", "")
        base = str(self.success_url)
        # Build query string with username and optional next
        if next_url:
            return f"{base}?username={username}&next={next_url}"
        return f"{base}?username={username}"

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


class AdminAwareLoginView(LoginView):
    """Custom login view that redirects staff/superusers to moderator dashboard.

    Honors the "next" parameter if present; otherwise redirects based on role.
    Regular users follow settings.LOGIN_REDIRECT_URL.
    """

    def get_success_url(self):
        # Respect explicit next/redirect if provided
        redirect_to = self.get_redirect_url()
        if redirect_to:
            return redirect_to
        user = getattr(self.request, "user", None)
        if user and (getattr(user, "is_staff", False) or getattr(user, "is_superuser", False)):
            from django.urls import reverse
            return reverse("marketplace:moderator_dashboard")
        # Fallback to configured default
        return resolve_url(getattr(settings, "LOGIN_REDIRECT_URL", "/"))

class ProfileDetailView(LoginRequiredMixin, DetailView):
    """Simple profile page showing current user's info."""
    template_name = "accounts/profile.html"
    context_object_name = "user_obj"

    def get_object(self, queryset=None):
        return self.request.user

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        try:
            from marketplace.models import SellerRating
            agg = SellerRating.objects.filter(seller_id=user.id).aggregate(avg=Avg("score"), count=Count("id"))
            ctx["seller_rating_avg"] = agg.get("avg") or 0.0
            ctx["seller_rating_count"] = agg.get("count") or 0
            ctx["recent_ratings"] = (
                SellerRating.objects.filter(seller_id=user.id)
                .select_related("buyer", "listing")
                .order_by("-created_at")[:5]
            )
        except Exception:
            ctx["seller_rating_avg"] = 0.0
            ctx["seller_rating_count"] = 0
            ctx["recent_ratings"] = []
        return ctx

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
        """Save profile and persist user email notification preferences."""
        # Update user email preferences from posted toggles
        try:
            user = self.request.user
            post = self.request.POST
            user.email_marketplace_notifications = bool(post.get("email_marketplace_notifications"))
            user.email_on_request_updates = bool(post.get("email_on_request_updates"))
            user.email_on_messages = bool(post.get("email_on_messages"))
            # In-app notification preferences
            user.notify_marketplace_notifications = bool(post.get("notify_marketplace_notifications"))
            user.notify_on_request_updates = bool(post.get("notify_on_request_updates"))
            user.notify_on_messages = bool(post.get("notify_on_messages"))
            user.save(update_fields=[
                "email_marketplace_notifications",
                "email_on_request_updates",
                "email_on_messages",
                "notify_marketplace_notifications",
                "notify_on_request_updates",
                "notify_on_messages",
                "updated_at" if hasattr(user, "updated_at") else None,
            ])
        except Exception:
            # Non-blocking; preferences update should not prevent profile save
            pass
        messages.success(self.request, "Your profile has been updated.")
        return super().form_valid(form)

    def get_form_kwargs(self):
        """Ensure request.FILES are handled for avatar uploads."""
        kwargs = super().get_form_kwargs()
        if self.request.method in ("POST", "PUT"):
            kwargs.update({"files": self.request.FILES})
        return kwargs