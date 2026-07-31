from django.utils import timezone


def active_timezone(request):
    tz = timezone.get_current_timezone()
    name = getattr(tz, "zone", None) or str(tz)
    return {"active_timezone": name}
