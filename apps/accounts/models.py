from django.contrib.auth.models import User
from django.db import models


class UserProfile(models.Model):
    """Optional extended profile for PLeC learners."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    organisation = models.CharField(max_length=120, blank=True)
    job_title = models.CharField(max_length=120, blank=True)
    bio = models.TextField(blank=True)

    def __str__(self):
        return f"Profile for {self.user.username}"
