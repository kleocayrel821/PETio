"""Setup Moderators group and permissions for the social app.

This management command creates a `Moderators` group (if missing) and
assigns appropriate permissions to manage moderation-related models:
`SocialReport`, `ModerationAction`, `UserSuspension`, and limited change
permissions on `Post`, `Comment`, and `UserProfile`.

Usage:
    python manage.py setup_moderation
    python manage.py setup_moderation --assign-moderator <username>

The optional `--assign-moderator` flag adds the specified user to the
`Moderators` group.
"""

import logging
from typing import List

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import Group, Permission, User
from django.contrib.contenttypes.models import ContentType

from social.models import (
    Post,
    Comment,
    UserProfile,
    SocialReport,
    ModerationAction,
    UserSuspension,
)


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Django management command to bootstrap moderation roles and permissions."""

    help = "Create 'Moderators' group with permissions; optionally assign a user to it."

    def add_arguments(self, parser):
        """Add CLI arguments for the command."""
        parser.add_argument(
            "--assign-moderator",
            dest="assign_moderator",
            type=str,
            help="Username to add to the 'Moderators' group.",
        )

    def handle(self, *args, **options):
        """Execute the moderation setup routine.

        - Ensures the Moderators group exists
        - Grants CRUD permissions to moderation models
        - Grants change/view permissions to Post, Comment, UserProfile
        - Optionally assigns a user to the group
        """
        # Configure basic logging to stdout if not configured
        logging.basicConfig(level=logging.INFO)

        # Create or get the Moderators group
        moderators, created = Group.objects.get_or_create(name="Moderators")
        if created:
            logger.info("Created group 'Moderators'.")
        else:
            logger.info("Group 'Moderators' already exists.")

        # Collect content types for models involved in moderation
        ct_report = ContentType.objects.get_for_model(SocialReport)
        ct_action = ContentType.objects.get_for_model(ModerationAction)
        ct_suspension = ContentType.objects.get_for_model(UserSuspension)
        ct_post = ContentType.objects.get_for_model(Post)
        ct_comment = ContentType.objects.get_for_model(Comment)
        ct_profile = ContentType.objects.get_for_model(UserProfile)

        # Helper to fetch default perms for a content type
        def _default_perms(content_type: ContentType) -> List[Permission]:
            """Return add/change/delete/view permissions for given content type."""
            app_label = content_type.app_label
            model = content_type.model
            codenames = [
                f"add_{model}",
                f"change_{model}",
                f"delete_{model}",
                f"view_{model}",
            ]
            return list(Permission.objects.filter(content_type=content_type, codename__in=codenames))

        # Permissions to grant
        perms_to_add: List[Permission] = []
        # Full CRUD on moderation models
        perms_to_add += _default_perms(ct_report)
        perms_to_add += _default_perms(ct_action)
        perms_to_add += _default_perms(ct_suspension)
        # Limited rights on content and profiles: change/view is sufficient for flags
        perms_to_add += [
            *Permission.objects.filter(content_type=ct_post, codename__in=[f"change_{ct_post.model}", f"view_{ct_post.model}"]),
            *Permission.objects.filter(content_type=ct_comment, codename__in=[f"change_{ct_comment.model}", f"view_{ct_comment.model}"]),
            *Permission.objects.filter(content_type=ct_profile, codename__in=[f"change_{ct_profile.model}", f"view_{ct_profile.model}"]),
        ]

        # Assign permissions to Moderators group
        before_count = moderators.permissions.count()
        moderators.permissions.add(*perms_to_add)
        after_count = moderators.permissions.count()
        added = max(after_count - before_count, 0)
        logger.info("Assigned %d permissions to 'Moderators' group.", added)

        # Optionally assign a user to Moderators
        username = options.get("assign_moderator")
        if username:
            try:
                user = User.objects.get(username=username)
            except User.DoesNotExist as exc:
                raise CommandError(f"User '{username}' not found.") from exc

            user.groups.add(moderators)
            logger.info("Added user '%s' to 'Moderators' group.", username)

        self.stdout.write(self.style.SUCCESS("Moderation setup complete."))