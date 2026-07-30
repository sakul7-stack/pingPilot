from django.db import migrations


def backfill_alertlogs(apps, schema_editor):
    AlertLog = apps.get_model("heartbeat", "AlertLog")
    Incident = apps.get_model("heartbeat", "Incident")

    if AlertLog.objects.exists():
        return

    logs = []
    for inc in Incident.objects.iterator():
        logs.append(AlertLog(monitor=inc.monitor, event="down", channel="incident"))
        if inc.closed_at:
            logs.append(AlertLog(monitor=inc.monitor, event="up", channel="incident"))

    AlertLog.objects.bulk_create(logs)


class Migration(migrations.Migration):

    dependencies = [
        ("heartbeat", "0006_alertlog"),
    ]

    operations = [
        migrations.RunPython(backfill_alertlogs, migrations.RunPython.noop),
    ]
