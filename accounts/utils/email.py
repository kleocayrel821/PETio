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
