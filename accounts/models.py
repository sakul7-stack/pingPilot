from django.db import models
from django.contrib.auth.models import User


class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True)
    timezone = models.CharField(max_length=64, default="UTC")
    weekly_report = models.BooleanField(default=True)
    monthly_report = models.BooleanField(default=True)
    auto_refresh = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class TelegramConnection(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="telegram_connection")
    chat_id = models.BigIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
