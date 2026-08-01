from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from statuspage.models import StatusPage
import dns.resolver
from django.conf import settings


class Command(BaseCommand):
    help = 'Re-verify all custom domains for status pages'

    def handle(self, *args, **options):
        prefix = settings.VERIFICATION_PREFIX

        # Release domains claimed > 48h without verification (squatting guard)
        deadline = timezone.now() - timedelta(hours=48)
        expired = StatusPage.objects.filter(
            custom_domain__isnull=False,
            domain_verified=False,
            domain_claimed_at__lt=deadline,
        )
        count = expired.count()
        for page in expired:
            self.stdout.write(f'Releasing unverified domain: {page.custom_domain}')
            page.custom_domain = None
            page.domain_claimed_at = None
            page.domain_verification_token = ''
            page.save()
        if count:
            self.stdout.write(f'Released {count} squatted domain(s)')

        for page in StatusPage.objects.filter(
            custom_domain__isnull=False, is_published=True
        ):
            try:
                answers = dns.resolver.resolve(
                    f'{prefix}.{page.custom_domain}', 'TXT'
                )
                for rdata in answers:
                    if page.domain_verification_token in ''.join(rdata.strings):
                        if not page.domain_verified:
                            page.domain_verified = True
                            page.save()
                            self.stdout.write(f'Verified: {page.custom_domain}')
                        break
                else:
                    page.domain_verified = False
                    page.save()
            except Exception:
                page.domain_verified = False
                page.save()
