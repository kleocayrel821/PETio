from django.db import migrations


def create_marketplace_admin_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    group_name = "Marketplace Admin"
    if not Group.objects.filter(name=group_name).exists():
        Group.objects.create(name=group_name)


def remove_marketplace_admin_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name="Marketplace Admin").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("marketplace", "0013_alter_notification_type_and_more"),
    ]

    operations = [
        migrations.RunPython(create_marketplace_admin_group, remove_marketplace_admin_group),
    ]