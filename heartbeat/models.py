from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator



from .enums import HttpMethod, Status


class Monitor(models.Model):
    user=models.ForeignKey(User,on_delete=models.CASCADE)
    name=models.CharField(max_length=100)
    url=models.URLField()
    method=models.CharField(
        max_length=4,
        choices=HttpMethod.choices,
        default=HttpMethod.GET
    )
    expected_status=models.IntegerField(default=200)
    expected_keyword=models.CharField(max_length=100,blank=True,null=True)
    timeout=models.IntegerField(default=10)
    check_interval_seconds=models.PositiveIntegerField(
        default=300,
        validators=[MinValueValidator(180),MaxValueValidator(86400)],
    )
    next_check_at=models.DateTimeField(default=timezone.now)
    consecutive_failures=models.IntegerField(default=0)
    last_checked_at=models.DateTimeField(null=True,blank=True)
    last_status=models.CharField(
        max_length=10,
        choices=Status.choices,null=True
    )
    last_alert_sent_at=models.DateTimeField(null=True,blank=True)
    is_active=models.BooleanField(default=True)
    created_at=models.DateTimeField(auto_now_add=True)
    updated_at=models.DateTimeField(auto_now=True)

    email_alerts=models.BooleanField(default=True)
    share_token = models.CharField(max_length=64, unique=True, null=True, blank=True)

    class Meta:
        indexes=[
            models.Index(fields=["next_check_at"]),
            models.Index(fields=["user"]),
        ]




class HeartBeat(models.Model):
    monitor=models.ForeignKey(
        Monitor,on_delete=models.CASCADE,related_name="heartbeats"
    )
    status=models.CharField(max_length=10,choices=Status.choices)
    status_code=models.IntegerField(null=True,blank=True)
    error=models.CharField(max_length=200,blank=True)
    response_time_ms=models.FloatField(null=True,blank=True)
    body_size=models.IntegerField(null=True,blank=True)
    checked_at=models.DateTimeField(auto_now_add=True)


    class Meta:
        indexes=[models.Index(fields=["monitor","-checked_at"])]


class APIKey(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="api_keys")
    name = models.CharField(max_length=100, default="Unnamed")
    prefix = models.CharField(max_length=8)
    key_hash = models.CharField(max_length=64)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["key_hash"])]


class Incident(models.Model):
    monitor=models.ForeignKey(
        Monitor,on_delete=models.CASCADE,related_name="indidents"
    )
    opened_at=models.DateTimeField(auto_now_add=True)
    closed_at=models.DateTimeField(null=True,blank=True)
    reason=models.TextField(blank=True)

    class Meta:
        indexes=[models.Index(fields=["monitor","closed_at"])]



class NotificationChannel(models.Model):
    PROVIDERS=[
        ("webhook","Webhook"),
        ("telegram","Telegram"),
        ("discord","Discord"),
        ("slack","Slack"),
        ("teams","Microsoft Teams"),
        ("pushover","Pushover"),
    ]

    monitor=models.ForeignKey(
        Monitor,on_delete=models.CASCADE,related_name="channels"
    )
    provider=models.CharField(max_length=50,blank=True)
    label=models.CharField(max_length=50,blank=True)
    config=models.JSONField(default=dict)


    class Meta:
        ordering=["provider"]


class AlertLog(models.Model):
    EVENT_CHOICES = [
        ("down", "Down Alert"),
        ("up", "Recovery Alert"),
    ]
    monitor = models.ForeignKey(Monitor, on_delete=models.CASCADE, related_name="alert_logs")
    event = models.CharField(max_length=10, choices=EVENT_CHOICES)
    channel = models.CharField(max_length=50, blank=True, default="email")
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-sent_at"]