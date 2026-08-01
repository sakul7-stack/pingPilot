import re
from datetime import timedelta
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.contrib.auth.hashers import make_password
from django.utils import timezone
from heartbeat.models import Monitor


def validate_hostname(value):
    if not value:
        return
    if not re.match(r'^([a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$', value):
        raise ValidationError('Enter a valid hostname (e.g. status.example.com)')


class StatusPage(models.Model):
    THEME_CHOICES = [
        ('light', 'Light'),
        ('dark', 'Dark'),
        ('minimal', 'Minimal'),
        ('corporate', 'Corporate'),
    ]

    LAYOUT_CHOICES = [
        ('list', 'List View'),
        ('grid', 'Grid View'),
        ('compact', 'Compact'),
    ]

    SORT_CHOICES = [
        ('alpha', 'Alphabetical'),
        ('status', 'Status (DOWN first)'),
        ('manual', 'Custom Order'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='status_pages'
    )
    title = models.CharField(max_length=200, default='Service Status')
    slug = models.SlugField(unique=True, max_length=64)
    description = models.TextField(blank=True, help_text="Shown below the title")
    logo_url = models.URLField(blank=True, help_text="URL to your logo image")

    theme = models.CharField(max_length=20, choices=THEME_CHOICES, default='dark')
    layout = models.CharField(max_length=20, choices=LAYOUT_CHOICES, default='list')
    sort_order = models.CharField(max_length=20, choices=SORT_CHOICES, default='status')
    show_uptime = models.BooleanField(default=True)
    show_response_time = models.BooleanField(default=True)
    show_incidents = models.BooleanField(default=True)
    show_timeline = models.BooleanField(default=True)
    show_graph = models.BooleanField(default=False)

    header_color = models.CharField(max_length=7, default='#1a1a2e', blank=True)
    accent_color = models.CharField(max_length=7, default='#00d4aa', blank=True)
    custom_domain = models.CharField(
        max_length=255, blank=True, null=True, unique=True,
        validators=[validate_hostname],
        help_text="e.g. status.yourdomain.com"
    )
    domain_verified = models.BooleanField(default=False)
    domain_verification_token = models.CharField(max_length=64, blank=True)
    domain_claimed_at = models.DateTimeField(null=True, blank=True)
    dns_instructions = models.TextField(blank=True, editable=False)

    meta_description = models.CharField(max_length=300, blank=True)
    favicon_url = models.URLField(blank=True)
    footer_text = models.CharField(max_length=500, blank=True, default='Powered by PingPilot')

    is_published = models.BooleanField(default=True)
    password_protected = models.BooleanField(default=False)
    access_password = models.CharField(max_length=128, blank=True)

    view_count = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['slug']),
            models.Index(fields=['user']),
            models.Index(fields=['custom_domain']),
            models.Index(fields=['custom_domain', 'domain_verified', 'is_published']),
        ]

    @staticmethod
    def _password_is_hashed(password):
        return '$' in password

    def save(self, *args, **kwargs):
        if self.access_password and not self._password_is_hashed(self.access_password):
            self.access_password = make_password(self.access_password)
        if self.custom_domain and not self.domain_verified:
            if not self.domain_claimed_at:
                self.domain_claimed_at = timezone.now()
        elif not self.custom_domain:
            self.domain_claimed_at = None
            self.domain_verified = False
        super().save(*args, **kwargs)

    @property
    def domain_verification_deadline(self):
        if self.domain_claimed_at and not self.domain_verified:
            return self.domain_claimed_at + timedelta(hours=48)
        return None

    def __str__(self):
        return f"{self.title} ({self.slug})"

    def public_url(self):
        site = settings.SITE_URL.rstrip('/')
        return f"{site}/dashboard/public/status/{self.slug}/"

    def custom_url(self):
        if self.custom_domain and self.domain_verified:
            proto = 'https' if self.custom_domain != 'localhost' else 'http'
            return f"{proto}://{self.custom_domain}/"
        return None


class StatusPageMonitor(models.Model):
    status_page = models.ForeignKey(
        StatusPage, on_delete=models.CASCADE, related_name='monitors'
    )
    monitor = models.ForeignKey(
        Monitor, on_delete=models.CASCADE, related_name='status_pages'
    )
    order = models.PositiveIntegerField(default=0)
    display_name = models.CharField(max_length=200, blank=True,
                                    help_text="Override the monitor name on this page")
    show_on_page = models.BooleanField(default=True)

    class Meta:
        ordering = ['order']
        unique_together = ['status_page', 'monitor']

    def __str__(self):
        return f"{self.status_page.slug} → {self.monitor.name}"


class StatusPageIncident(models.Model):
    status_page = models.ForeignKey(
        StatusPage, on_delete=models.CASCADE, related_name='incident_posts'
    )
    title = models.CharField(max_length=300)
    message = models.TextField()
    severity = models.CharField(
        max_length=20,
        choices=[
            ('maintenance', 'Scheduled Maintenance'),
            ('investigating', 'Investigating'),
            ('identified', 'Identified'),
            ('monitoring', 'Monitoring'),
            ('resolved', 'Resolved'),
        ],
        default='investigating'
    )
    started_at = models.DateTimeField()
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-started_at']
