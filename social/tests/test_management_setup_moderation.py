"""Tests for the `setup_moderation` management command.

Verifies that the Moderators group is created and receives expected
permissions on moderation-related models.
"""

from django.test import TestCase
from django.core.management import call_command
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType

from social.models import SocialReport, ModerationAction, UserSuspension


class SetupModerationCommandTests(TestCase):
    """Test cases for the setup_moderation command."""

    def test_creates_group_and_assigns_permissions(self):
        """Run command and assert group and key permissions exist."""
        # Run the command
        call_command('setup_moderation')

        # Moderators group should exist
        group = Group.objects.get(name='Moderators')

        # Check that default permissions for moderation models are included
        for model in (SocialReport, ModerationAction, UserSuspension):
            ct = ContentType.objects.get_for_model(model)
            for codename in [f'add_{ct.model}', f'change_{ct.model}', f'delete_{ct.model}', f'view_{ct.model}']:
                perm = Permission.objects.get(content_type=ct, codename=codename)
                self.assertTrue(group.permissions.filter(id=perm.id).exists())