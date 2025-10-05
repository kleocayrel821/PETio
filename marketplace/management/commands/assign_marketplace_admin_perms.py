from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.apps import apps


class Command(BaseCommand):
    help = "Assign granular Marketplace Admin permissions to the 'Marketplace Admin' group. Creates custom perms if missing."

    def handle(self, *args, **options):
        group_name = "Marketplace Admin"
        group, _ = Group.objects.get_or_create(name=group_name)

        desired_perms = [
            ("marketplace", "listing", "can_approve_listing", "Can approve or reject listings"),
            ("marketplace", "transaction", "can_manage_transactions", "Can manage marketplace transactions"),
            ("marketplace", "transaction", "can_view_analytics", "Can view marketplace analytics"),
            ("marketplace", "notification", "can_broadcast_notifications", "Can broadcast notifications"),
            # Built-in style perms for managing users (custom user model lives in 'accounts')
            ("accounts", "user", "view_user", "Can view user"),
            ("accounts", "user", "change_user", "Can change user"),
        ]

        assigned = []
        for app_label, model_name, codename, name in desired_perms:
            model = apps.get_model(app_label, model_name)
            if not model:
                self.stdout.write(self.style.WARNING(f"Model {app_label}.{model_name} not found; skipping {codename}"))
                continue
            ct = ContentType.objects.get_for_model(model)
            perm, created = Permission.objects.get_or_create(
                codename=codename,
                content_type=ct,
                defaults={"name": name},
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f"Created permission: {app_label}.{codename}"))
            group.permissions.add(perm)
            assigned.append(f"{app_label}.{codename}")

        group.save()
        self.stdout.write(self.style.SUCCESS(f"Assigned permissions to group '{group_name}': {', '.join(assigned)}"))