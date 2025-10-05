from django.conf import settings


class DisableAuthUser:
    """Dummy user object to bypass authentication checks when enabled.

    Provides common attributes and methods expected by views and permissions.
    """

    def __init__(self):
        self.id = None
        self.pk = None
        self.username = "guest"
        self.email = ""
        self.is_staff = True
        self.is_superuser = True
        # Many auth checks (including DRF) expect this flag
        self.is_active = True

    @property
    def is_authenticated(self):
        return True

    @property
    def is_anonymous(self):
        return False

    def get_username(self):
        return self.username

    def has_perm(self, perm, obj=None):
        return True

    def has_perms(self, perm_list):
        return True

    def has_module_perms(self, app_label):
        return True


class DisableAuthMiddleware:
    """Middleware that replaces request.user when DISABLE_AUTH is True.

    Useful for temporarily disabling authentication site-wide in non-production
    environments or for demos. Do not enable in real deployments.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if getattr(settings, "DISABLE_AUTH", False):
            # Preserve real authenticated users (from session) and only inject placeholder for anonymous
            try:
                auth_uid = None
                if hasattr(request, "session"):
                    auth_uid = request.session.get("_auth_user_id")
                is_real_user = bool(auth_uid)
                is_authenticated = bool(getattr(getattr(request, "user", None), "is_authenticated", False))
                if not (is_real_user or is_authenticated):
                    request.user = DisableAuthUser()
            except Exception:
                request.user = DisableAuthUser()
        return self.get_response(request)


class AdminSessionCookieMiddleware:
    """Isolate admin authentication by using a separate session cookie.

    For requests under ``/admin/``, switch the session cookie name/path to
    admin-specific values so that logging into the admin does not log the user
    into the public site.

    IMPORTANT: This approach is intended for local/dev environments. It mutates
    settings during the request and resets them afterward. Place this middleware
    BEFORE Django's ``SessionMiddleware`` so that it takes effect.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        # Defaults captured once
        self.default_name = getattr(settings, "SESSION_COOKIE_NAME", "sessionid")
        self.default_path = getattr(settings, "SESSION_COOKIE_PATH", "/")
        # Admin-specific values (configurable via settings)
        self.admin_name = getattr(settings, "ADMIN_SESSION_COOKIE_NAME", "adminid")
        self.admin_path = getattr(settings, "ADMIN_SESSION_COOKIE_PATH", "/admin")

    def __call__(self, request):
        is_admin = request.path.startswith("/admin/") or request.path == "/admin"

        if is_admin:
            settings.SESSION_COOKIE_NAME = self.admin_name
            settings.SESSION_COOKIE_PATH = self.admin_path
        else:
            settings.SESSION_COOKIE_NAME = self.default_name
            settings.SESSION_COOKIE_PATH = self.default_path

        try:
            response = self.get_response(request)
        finally:
            # Reset to defaults to avoid any bleed across subsequent requests
            settings.SESSION_COOKIE_NAME = self.default_name
            settings.SESSION_COOKIE_PATH = self.default_path

        return response