"""
URL configuration for dataprocessing project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include, re_path
from django.views.static import serve
from django.conf import settings
from django.conf.urls.static import static
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from drf_yasg.generators import OpenAPISchemaGenerator
from collections import OrderedDict
from rest_framework import permissions

endpoints_order = [  # Register all swagger ui url in specific order of display.
    '/api/v1/query/spot',
    '/api/v1/query/trends',
    '/api/v1/query/list',
    '/api/v1/query/data_syncing/trends',
    '/api/v1/export/processed',
    '/api/v1/api/gateway/last-connection', #TODO: this is changed to /api/v1/gateway/last-connection
    '/api/v1/update_cache', #TODO: check if this is needed
    '/api/v1/upload',
    '/api/v1/submit-health-input',
    '/api/v1/processing',
    '/api/v1/data/other/bp-device',
    '/api/v1/data/emr',
    '/api/v1/query/spot/bp-device',
    '/api/v1/vitals/readings',
    '/api/v1/api/dashboard/list'

]


class CustomOpenAPISquemaGenerator(OpenAPISchemaGenerator):

    def get_paths(self, endpoints, components, request, public):
        if not endpoints:
            return openapi.Paths(paths={}), ''
        prefix = self.determine_path_prefix(list(endpoints.keys())) or ''
        assert '{' not in prefix, "base path cannot be templated in swagger 2.0"

        paths = OrderedDict()
        for path in endpoints_order:
            view_cls, methods = endpoints[path]
            operations = {}
            for method, view in methods:
                if not self.should_include_endpoint(path, method, view, public):
                    continue

                operation = self.get_operation(
                    view, path, prefix, method, components, request)
                if operation is not None:
                    operations[method.lower()] = operation

            if operations:
                path_suffix = path[len(prefix):]
                if not path_suffix.startswith('/'):
                    path_suffix = '/' + path_suffix
                paths[path_suffix] = self.get_path_item(
                    path, view_cls, operations)
        return self.get_paths_object(paths), prefix


schema_view = get_schema_view(
    openapi.Info(
        title="Respiree Data Processing API",
        default_version='',
        description="",
        terms_of_service="",
        contact=openapi.Contact(email=""),
    ),
    public=True,
    permission_classes=[permissions.AllowAny],
    generator_class=CustomOpenAPISquemaGenerator,  # Use custom Squema Generator
)
# swagger schema related code

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/', include('data_app.urls')),
    path('api/v1/api/', include('gateway.urls')),
    re_path(r'^swagger(?P<format>\.json|\.yaml)$',
            schema_view.without_ui(cache_timeout=0), name='schema-json'),
    re_path(r'^swagger/$', schema_view.with_ui('swagger',
            cache_timeout=0), name='schema-swagger-ui'),
    # re_path(r'^redoc/$', schema_view.with_ui('redoc',
    #         cache_timeout=0), name='schema-redoc'),
    re_path(r'^static/(?P<path>.*)$', serve,
            {'document_root': settings.STATIC_ROOT}),
    # re_path(r'^swagger/login/$', swagger_login_user, name='swagger-login'),
    # re_path(r'^swagger/logout/$', swagger_logout_user, name='swagger-logout'),
] + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)