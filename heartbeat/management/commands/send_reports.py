from django.core.management.base import BaseCommand

from heartbeat.reports import send_monthly_reports, send_weekly_reports


class Command(BaseCommand):
    help = "Send weekly/monthly report emails"

    def add_arguments(self, parser):
        parser.add_argument(
            "--period", type=str, choices=["weekly", "monthly"], required=True
        )

    def handle(self, *args, **options):
        period = options["period"]
        if period == "weekly":
            send_weekly_reports()
        else:
            send_monthly_reports()
        self.stdout.write(f"{period.title()} reports sent")
