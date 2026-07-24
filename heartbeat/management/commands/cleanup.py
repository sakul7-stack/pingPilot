from django.core.management.base import BaseCommand

from heartbeat.cleanup import prune_old_heartbeats


class Command(BaseCommand):
    help = "Prune old heartbeats and aggregate stats"

    def handle(self, *args, **options):
        deleted = prune_old_heartbeats(days=90)
        self.stdout.write(f"Cleanup complete — {deleted} heartbeats deleted")