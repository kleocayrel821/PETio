import requests
from django.conf import settings

def send_brevo_email(to_email, subject, html_content):
    api_key = getattr(settings, "BREVO_API_KEY", None)
    if not api_key:
        raise RuntimeError("BREVO_API_KEY is not configured")
    url = "https://api.brevo.com/v3/smtp/email"
    payload = {
        "sender": {
            "name": "PETio",
            "email": "no-reply@petio.site",
        },
        "to": [{"email": to_email}],
        "subject": subject,
        "htmlContent": html_content,
    }
    headers = {
        "accept": "application/json",
        "api-key": api_key,
        "content-type": "application/json",
    }
    response = requests.post(url, json=payload, headers=headers, timeout=10)
    response.raise_for_status()


def send_account_verification_email(*, to_email: str, activation_url: str) -> None:
    subject = "Verify your PETio account"
    context = {"activation_url": activation_url}
    from django.template.loader import render_to_string
    html_body = render_to_string("accounts/activation_email.html", context)
    text_body = render_to_string("accounts/activation_email.txt", context)

    if getattr(settings, "BREVO_API_KEY", None):
        try:
            send_brevo_email(to_email=to_email, subject=subject, html_content=html_body)
            return
        except Exception:
            pass

    from django.core.mail import EmailMultiAlternatives
    email = EmailMultiAlternatives(subject=subject, body=text_body, from_email=None, to=[to_email])
    email.attach_alternative(html_body, "text/html")
    try:
        email.send(fail_silently=True)
    except Exception:
        return
