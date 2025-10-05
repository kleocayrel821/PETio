from django.db import migrations


def seed_categories(apps, schema_editor):
    Category = apps.get_model("marketplace", "Category")
    defaults = [
        {"name": "Pet Food", "slug": "pet-food", "description": "Food for pets, dry/wet, brands."},
        {"name": "Accessories & Treats", "slug": "accessories-treats", "description": "Accessories, gear, and treats."},
        {"name": "Health", "slug": "health", "description": "Health products and wellness."},
        {"name": "Pet Housing", "slug": "pet-housing", "description": "Beds, crates, cages, houses."},
        {"name": "Others", "slug": "others", "description": "Miscellaneous pet items."},
    ]

    for data in defaults:
        try:
            Category.objects.get_or_create(slug=data["slug"], defaults=data)
        except Exception:
            # Best-effort: skip on any constraint or validation issues
            pass


def unseed_categories(apps, schema_editor):
    Category = apps.get_model("marketplace", "Category")
    slugs = [
        "pet-food",
        "accessories-treats",
        "health",
        "pet-housing",
        "others",
    ]
    Category.objects.filter(slug__in=slugs).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("marketplace", "0010_alter_transactionlog_action"),
    ]

    operations = [
        migrations.RunPython(seed_categories, reverse_code=unseed_categories),
    ]