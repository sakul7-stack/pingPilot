from django.core.management.base import BaseCommand

from heartbeat.reports import check_ssl_expiry


class Command(BaseCommand):
    help = "Check SSL certificates and email alerts when expiring within 7 days"

    def handle(self, *args, **options):
        check_ssl_expiry()
        self.stdout.write("SSL expiry check complete")
