from django.core.cache import cache
from django.shortcuts import get_object_or_404
from django.http import Http404
from .models import StatusPage


class CustomDomainMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host = request.get_host().split(':')[0].lower()

        # Short-circuit: only attempt lookup for non-local hosts
        if host in ('localhost', '127.0.0.1', '::1') or host == request.get_host():
            pass
        else:
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
