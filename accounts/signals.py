import logging
from allauth.account.signals import user_signed_up
from django.dispatch import receiver
from django.db.models.signals import post_save
from django.contrib.auth.models import User
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags

from .models import Profile


@receiver(post_save, sender=User)
def create_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)

logger = logging.getLogger(__name__)

@receiver(user_signed_up)
def welcome_email(request, user, **kwargs):
    logger.info(f"user_signed_up signal fired for {user.email}")
    try:
        subject = "Welcome to PingPilot!"
        dashboard_url = request.build_absolute_uri("/dashboard/")
        html_content = render_to_string("email/welcome.html", {
            "user": user,
            "dashboard_url": dashboard_url,
        })
        text_content = strip_tags(html_content)

        msg = EmailMultiAlternatives(
            subject,
            text_content,
            None,
            [user.email],
        )
        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)

        logger.info(f"Welcome email sent to {user.email}")
    except Exception as e:
        logger.error(f"Failed to send welcome email to {user.email}: {e}")
