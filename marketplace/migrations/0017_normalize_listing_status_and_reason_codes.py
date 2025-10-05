from django.db import migrations


def normalize_listing_status_and_reason_codes(apps, schema_editor):
    Listing = apps.get_model("marketplace", "Listing")

    # Normalize invalid listing statuses
    try:
        status_field = Listing._meta.get_field("status")
        allowed_statuses = {c[0] for c in getattr(status_field, "choices", [])} or {
            "draft", "pending", "rejected", "active", "reserved", "sold", "archived"
        }
    except Exception:
        allowed_statuses = {"draft", "pending", "rejected", "active", "reserved", "sold", "archived"}

    Listing.objects.exclude(status__in=list(allowed_statuses)).update(status="pending")

    # Normalize invalid rejection reason codes to 'other' for rejected listings
    try:
        code_field = Listing._meta.get_field("rejected_reason_code")
        allowed_codes = {c[0] for c in getattr(code_field, "choices", [])} or {
            "spam",
            "prohibited_item",
            "missing_info",
            "inappropriate_content",
            "fake_photos",
            "pricing_issue",
            "other",
        }
    except Exception:
        allowed_codes = {
            "spam",
            "prohibited_item",
            "missing_info",
            "inappropriate_content",
            "fake_photos",
            "pricing_issue",
            "other",
        }

    # Set invalid non-empty codes to 'other' for rejected listings
    Listing.objects.filter(status="rejected").exclude(
        rejected_reason_code__in=list(allowed_codes)
    ).exclude(rejected_reason_code="").update(rejected_reason_code="other")


def noop_reverse(apps, schema_editor):
    # Data normalization; reversing not required/supported
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("marketplace", "0016_alter_listing_options_alter_report_options_and_more"),
    ]

    operations = [
        migrations.RunPython(normalize_listing_status_and_reason_codes, noop_reverse),
    ]