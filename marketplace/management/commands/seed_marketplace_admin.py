from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
import os


class Command(BaseCommand):
    help = "Seed a default Marketplace Admin user for testing"

    def add_arguments(self, parser):
        parser.add_argument("--username", default=os.getenv("MARKETPLACE_ADMIN_USERNAME", "mpadmin"))
        parser.add_argument("--email", default=os.getenv("MARKETPLACE_ADMIN_EMAIL", "mpadmin@example.com"))
        parser.add_argument("--password", default=os.getenv("MARKETPLACE_ADMIN_PASSWORD", "admin123"))

    def handle(self, *args, **options):
        User = get_user_model()
        username = options["username"]
        email = options["email"]
        password = options["password"]

        group_name = "Marketplace Admin"
        group, _ = Group.objects.get_or_create(name=group_name)

        user, created = User.objects.get_or_create(username=username, defaults={"email": email})
        if created:
            user.set_password(password)
            # Keep separation: this role should not require staff or superuser
            if hasattr(user, "is_staff"):
                user.is_staff = False
            if hasattr(user, "is_superuser"):
                user.is_superuser = False
            user.save()
            self.stdout.write(self.style.SUCCESS(f"Created user '{username}'"))
        else:
            self.stdout.write(self.style.WARNING(f"User '{username}' already exists"))

        if not user.groups.filter(name=group_name).exists():
            user.groups.add(group)
            self.stdout.write(self.style.SUCCESS(f"Added '{username}' to group '{group_name}'"))
        else:
            self.stdout.write(self.style.WARNING(f"User '{username}' is already in group '{group_name}'"))

        self.stdout.write(self.style.SUCCESS("Marketplace Admin seeding complete."))