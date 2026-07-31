from django.shortcuts import render, redirect
from django.conf import settings
from django.http import FileResponse


def home(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    return render(request, "home.html")


def service_worker(request):
    resp = FileResponse(open(settings.BASE_DIR / "static" / "sw.js", "rb"), content_type="application/javascript")
    resp["Service-Worker-Allowed"] = "/"
    resp["Cache-Control"] = "no-cache"
    return resp
