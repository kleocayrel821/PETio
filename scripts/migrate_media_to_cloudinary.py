# scripts/migrate_media_to_cloudinary.py

import os
import django

# Setup Django environment
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project.settings.prod")  # use prod settings
django.setup()

from django.core.files import File
from your_app.models import UserProfile  # change to your actual model

for profile in UserProfile.objects.all():
    if profile.avatar:  # replace 'avatar' with your ImageField name
        old_file_path = profile.avatar.path  # local /media/ file
        with open(old_file_path, "rb") as f:
            profile.avatar.save(os.path.basename(old_file_path), File(f), save=True)
        print(f"Uploaded {profile.user} avatar to Cloudinary")
