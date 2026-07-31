from django.utils import timezone


class TimezoneMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            tz = None
            try:
                tz = getattr(request.user.profile, "timezone", None)
            except Exception:
                tz = None
            if tz:
                try:
                    timezone.activate(tz)
                    return self.get_response(request)
                except Exception:
                    pass
        timezone.deactivate()
        return self.get_response(request)
