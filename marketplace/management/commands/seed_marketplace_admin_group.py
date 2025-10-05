from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission


class Command(BaseCommand):
    help = "Create/ensure 'Marketplace Admin' group and assign marketplace model permissions"

    GROUP_NAME = "Marketplace Admin"
    MARKETPLACE_PERMISSION_CODENAMES = [
        "can_approve_listing",
        "can_view_analytics",
        "can_manage_transactions",
        "can_moderate_reports",
        "can_broadcast_notifications",
    ]

    def handle(self, *args, **options):
        group, created = Group.objects.get_or_create(name=self.GROUP_NAME)

        assigned = []
        missing = []

        for codename in self.MARKETPLACE_PERMISSION_CODENAMES:
            perm = Permission.objects.filter(
                codename=codename, content_type__app_label="marketplace"
            ).first()
            if not perm:
                missing.append(codename)
                continue
            group.permissions.add(perm)
            assigned.append(codename)

        group.save()

        if created:
            self.stdout.write(self.style.SUCCESS(f"Created group '{self.GROUP_NAME}'."))
        else:
            self.stdout.write(self.style.WARNING(f"Group '{self.GROUP_NAME}' already exists."))

        if assigned:
            self.stdout.write(
                self.style.SUCCESS(
                    "Assigned permissions: " + ", ".join(sorted(assigned))
                )
            )
        if missing:
            self.stdout.write(
                self.style.ERROR(
                    "Missing permissions (ensure migrations applied): "
                    + ", ".join(sorted(missing))
                )
            )

        if not missing:
            self.stdout.write(
                self.style.SUCCESS(
                    f"'{self.GROUP_NAME}' group is seeded with all marketplace permissions."
                )
            )