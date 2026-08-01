from urllib.parse import urlparse
from django.conf import settings
from django.core.cache import cache
from .models import StatusPage


class CustomDomainMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host = request.META.get('HTTP_HOST') or request.META.get('SERVER_NAME') or ''
        host = host.split(':')[0].lower()

        site_host = urlparse(settings.SITE_URL).netloc.split(':')[0].lower() if settings.SITE_URL else ''
        is_local = host in ('localhost', '127.0.0.1', '::1')
        is_site = bool(site_host) and host == site_host

        if not is_local and host:
            if host not in settings.ALLOWED_HOSTS:
                settings.ALLOWED_HOSTS.append(host)

            if is_site:
                return self.get_response(request)

            cache_key = f'sp_domain_{host}'
            page_id = cache.get(cache_key)

            if page_id is not None and page_id > 0:
                try:
                    request.status_page = StatusPage.objects.get(pk=page_id)
                    request.urlconf = 'statuspage.custom_domain_urls'
                except StatusPage.DoesNotExist:
                    pass
            elif page_id is None:
                try:
                    page = StatusPage.objects.get(
                        custom_domain=host,
                        domain_verified=True,
                        is_published=True
                    )
                    request.status_page = page
                    request.urlconf = 'statuspage.custom_domain_urls'
                    cache.set(cache_key, page.pk, 300)
                except StatusPage.DoesNotExist:
                    cache.set(cache_key, 0, 300)

        response = self.get_response(request)
        return response
