from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group


class Command(BaseCommand):
    help = (
        "Convert existing moderators into Marketplace Admin users by adding them "
        "to the 'Marketplace Admin' group. Moderators are defined as users that "
        "satisfy the current _is_moderator logic (is_staff or is_superuser)."
    )

    GROUP_NAME = "Marketplace Admin"

    def handle(self, *args, **options):
        User = get_user_model()

        # Align with marketplace.views._is_moderator: is_staff OR is_superuser
        moderators_qs = User.objects.filter(is_active=True).filter(
            is_staff=True
        ) | User.objects.filter(is_active=True).filter(is_superuser=True)

        moderators = list({u.id: u for u in moderators_qs}.values())

        group, created = Group.objects.get_or_create(name=self.GROUP_NAME)
        if created:
            self.stdout.write(self.style.WARNING(f"Group '{self.GROUP_NAME}' did not exist; created it."))

        updated_usernames = []
        for user in moderators:
            if not user.groups.filter(id=group.id).exists():
                user.groups.add(group)
                updated_usernames.append(user.username)

        count = len(updated_usernames)
        if count == 0:
            self.stdout.write(self.style.NOTICE("No moderators required updates. No deletions performed."))
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Updated {count} moderator(s) to Marketplace Admin group."
                )
            )
            self.stdout.write("Usernames: " + ", ".join(sorted(updated_usernames)))

        # Explicitly confirm no removals performed
        self.stdout.write(self.style.SUCCESS("Moderator group memberships were NOT removed."))