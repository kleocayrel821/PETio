from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
import os


class Command(BaseCommand):
    help = "Seed a default Marketplace Admin user and ensure group membership"

    def add_arguments(self, parser):
        parser.add_argument("--create", action="store_true", help="Create the default admin user if missing")
        parser.add_argument("--username", default=os.getenv("MARKETPLACE_ADMIN_USERNAME", "mpadmin"))
        parser.add_argument("--email", default=os.getenv("MARKETPLACE_ADMIN_EMAIL", "mpadmin@example.com"))
        parser.add_argument("--password", default=os.getenv("MARKETPLACE_ADMIN_PASSWORD", ""))

    def handle(self, *args, **options):
        User = get_user_model()
        username = options["username"]
        email = options["email"]
        password = options["password"]
        create = options["create"]

        group_name = "Marketplace Admin"
        group, _ = Group.objects.get_or_create(name=group_name)

        user = User.objects.filter(username=username).first()
        if user is None:
            if not create:
                self.stdout.write(self.style.WARNING(
                    f"User '{username}' not found. Pass --create to create the default admin."
                ))
                return
            if not password:
                self.stdout.write(self.style.ERROR(
                    "No password provided. Set MARKETPLACE_ADMIN_PASSWORD env var or pass --password."
                ))
                return
            user = User.objects.create(username=username, email=email)
            user.set_password(password)
            # Marketplace Admins are not superusers or staff by default
            if hasattr(user, "is_staff"):
                user.is_staff = False
            if hasattr(user, "is_superuser"):
                user.is_superuser = False
            user.save()
            self.stdout.write(self.style.SUCCESS(f"Created user '{username}'"))
        else:
            # If password provided, allow rotating it safely
            if password:
                user.set_password(password)
                user.save()
                self.stdout.write(self.style.SUCCESS(f"Updated password for '{username}'"))
            self.stdout.write(self.style.WARNING(f"User '{username}' already exists"))

        if not user.groups.filter(name=group_name).exists():
            user.groups.add(group)
            self.stdout.write(self.style.SUCCESS(f"Added '{username}' to group '{group_name}'"))
        else:
            self.stdout.write(self.style.WARNING(f"User '{username}' is already in group '{group_name}'"))

        self.stdout.write(self.style.SUCCESS("Default Marketplace Admin seeding complete."))