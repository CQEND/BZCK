import datetime
import hashlib
import json
import os
from collections import namedtuple
from email.utils import formatdate, parsedate_to_datetime
from importlib import import_module
from typing import Any, Dict, List, Optional, Type

from django.conf import settings
from django.http import HttpResponse
from django.templatetags.static import static
from django.utils import translation
from django.utils.translation import gettext_lazy as _
from django.views.generic import RedirectView
from rest_framework.renderers import TemplateHTMLRenderer
from rest_framework.response import Response
from rest_framework.reverse import reverse
from rest_framework.settings import api_settings
from rest_framework.views import APIView

from drf_spectacular.generators import SchemaGenerator
from drf_spectacular.plumbing import get_relative_url, set_query_parameters
from drf_spectacular.renderers import (
    OpenApiJsonRenderer, OpenApiJsonRenderer2, OpenApiYamlRenderer, OpenApiYamlRenderer2,
)
from drf_spectacular.settings import patched_settings, spectacular_settings
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema

if spectacular_settings.SERVE_INCLUDE_SCHEMA:
    SCHEMA_KWARGS: Dict[str, Any] = {'responses': {200: OpenApiTypes.OBJECT}}

    if settings.USE_I18N:
        SCHEMA_KWARGS['parameters'] = [
            OpenApiParameter(
                'lang', str, OpenApiParameter.QUERY, enum=list(dict(settings.LANGUAGES).keys())
            )
        ]
else:
    SCHEMA_KWARGS = {'exclude': True}

if spectacular_settings.SERVE_AUTHENTICATION is not None:
    AUTHENTICATION_CLASSES = spectacular_settings.SERVE_AUTHENTICATION
else:
    AUTHENTICATION_CLASSES = api_settings.DEFAULT_AUTHENTICATION_CLASSES


class SpectacularAPIView(APIView):
    __doc__ = _("""
    OpenApi3 schema for this API. Format can be selected via content negotiation.

    - YAML: application/vnd.oai.openapi
    - JSON: application/vnd.oai.openapi+json
    """)  # type: ignore
    renderer_classes = [
        OpenApiYamlRenderer, OpenApiYamlRenderer2, OpenApiJsonRenderer, OpenApiJsonRenderer2
    ]
    permission_classes = spectacular_settings.SERVE_PERMISSIONS
    authentication_classes = AUTHENTICATION_CLASSES
    generator_class: Type[SchemaGenerator] = spectacular_settings.DEFAULT_GENERATOR_CLASS
    serve_public: bool = spectacular_settings.SERVE_PUBLIC
    urlconf: Optional[str] = spectacular_settings.SERVE_URLCONF
    api_version: Optional[str] = None
    custom_settings: Optional[Dict[str, Any]] = None
    patterns: Optional[List[Any]] = None

    @extend_schema(**SCHEMA_KWARGS)
    def get(self, request, *args, **kwargs):
        # special handling of custom urlconf parameter
        if isinstance(self.urlconf, list) or isinstance(self.urlconf, tuple):
            ModuleWrapper = namedtuple('ModuleWrapper', ['urlpatterns'])
            if all(isinstance(i, str) for i in self.urlconf):
                # list of import string for urlconf
                patterns = []
                for item in self.urlconf:
                    url = import_module(item)
                    patterns += url.urlpatterns
                self.urlconf = ModuleWrapper(tuple(patterns))
            else:
                # explicitly resolved urlconf
                self.urlconf = ModuleWrapper(tuple(self.urlconf))

        last_modified = self._get_schema_last_modified()

        # HTTP If-Modified-Since check: skip full schema regeneration when client
        # already has an up-to-date copy. This avoids unnecessary CPU load from
        # Swagger UI auto-refresh or similar frequent document consumers.
        if_modified_since = request.META.get('HTTP_IF_MODIFIED_SINCE')
        if if_modified_since and last_modified is not None:
            try:
                if_modified_since_dt = parsedate_to_datetime(if_modified_since)
            except (TypeError, ValueError):
                if_modified_since_dt = None
            if if_modified_since_dt is not None:
                if last_modified <= if_modified_since_dt:
                    not_modified = HttpResponse(status=304)
                    not_modified['Last-Modified'] = formatdate(
                        last_modified.timestamp(), usegmt=True
                    )
                    return not_modified

        with patched_settings(self.custom_settings):
            if settings.USE_I18N and request.GET.get('lang'):
                with translation.override(request.GET.get('lang')):
                    return self._get_schema_response(request, last_modified)
            else:
                return self._get_schema_response(request, last_modified)

    def _get_schema_last_modified(self):
        """
        Compute a proxy datetime for the "last modified" time of the generated
        schema. The heuristic considers the following sources in order:

        1. mtime of the project's ``pyproject.toml`` (if discoverable), which
           usually changes on dependency/version bumps.
        2. A stable hash derived from the configured API ``VERSION`` and the
           effective ``SPECTACULAR_SETTINGS`` values. Changes in either will
           yield a new datetime so clients always re-fetch when the schema
           might have changed.

        Returns a timezone-aware ``datetime.datetime`` in UTC, or ``None`` if
        no reliable timestamp can be determined.
        """
        candidates = []

        # proxy 1: pyproject.toml modification time
        for rel_dir in ('', os.pardir):
            candidate_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                rel_dir, 'pyproject.toml'
            )
            if os.path.isfile(candidate_path):
                try:
                    candidates.append(os.path.getmtime(candidate_path))
                except OSError:
                    pass
                break

        # proxy 2: VERSION + SPECTACULAR_SETTINGS hash. We map a hash digest
        # to a stable datetime so any configuration change shifts the
        # Last-Modified value and thus invalidates client caches.
        version = getattr(settings, 'VERSION', '') or ''
        raw_settings = getattr(spectacular_settings, 'user_settings', None) or {}
        try:
            settings_payload = json.dumps(
                raw_settings, sort_keys=True, default=str, ensure_ascii=False
            )
        except TypeError:
            settings_payload = ''
        digest = hashlib.sha1(
            f'{version}|{settings_payload}'.encode('utf-8')
        ).digest()
        # fold the first 8 bytes of the SHA-1 digest into a pseudo-timestamp
        # that lies in the past so Last-Modified is always strictly less than
        # the current time.
        pseudo_ts = 0
        for byte in digest[:8]:
            pseudo_ts = (pseudo_ts << 8) | byte
        epoch_days = pseudo_ts % (365 * 50)  # keep within 50-year window
        base = datetime.datetime(
            2020, 1, 1, tzinfo=datetime.timezone.utc
        )
        candidates.append((base + datetime.timedelta(days=epoch_days)).timestamp())

        if not candidates:
            return None
        latest_ts = max(candidates)
        return datetime.datetime.fromtimestamp(latest_ts, tz=datetime.timezone.utc)

    def _get_schema_response(self, request, last_modified=None):
        # version specified as parameter to the view always takes precedence. after
        # that we try to source version through the schema view's own versioning_class.
        version = self.api_version or request.version or self._get_version_parameter(request)
        generator = self.generator_class(urlconf=self.urlconf, api_version=version, patterns=self.patterns)
        headers = {"Content-Disposition": f'inline; filename="{self._get_filename(request, version)}"'}
        if last_modified is None:
            last_modified = self._get_schema_last_modified()
        if last_modified is not None:
            headers['Last-Modified'] = formatdate(last_modified.timestamp(), usegmt=True)
        return Response(
            data=generator.get_schema(request=request, public=self.serve_public),
            headers=headers
        )

    def _get_filename(self, request, version):
        return "{title}{version}.{suffix}".format(
            title=spectacular_settings.TITLE or 'schema',
            version=f' ({version})' if version else '',
            suffix=self.perform_content_negotiation(request, force=True)[0].format
        )

    def _get_version_parameter(self, request):
        version = request.GET.get('version')
        if not api_settings.ALLOWED_VERSIONS or version in api_settings.ALLOWED_VERSIONS:
            return version
        return None


class SpectacularYAMLAPIView(SpectacularAPIView):
    renderer_classes = [OpenApiYamlRenderer, OpenApiYamlRenderer2]


class SpectacularJSONAPIView(SpectacularAPIView):
    renderer_classes = [OpenApiJsonRenderer, OpenApiJsonRenderer2]


def _get_sidecar_url(filepath):
    return static(f'drf_spectacular_sidecar/{filepath}')


class SpectacularSwaggerView(APIView):
    renderer_classes = [TemplateHTMLRenderer]
    permission_classes = spectacular_settings.SERVE_PERMISSIONS
    authentication_classes = AUTHENTICATION_CLASSES
    url_name: str = 'schema'
    url: Optional[str] = None
    template_name: str = 'drf_spectacular/swagger_ui.html'
    template_name_js: str = 'drf_spectacular/swagger_ui.js'
    title: str = spectacular_settings.TITLE

    @extend_schema(exclude=True)
    def get(self, request, *args, **kwargs):
        return Response(
            data={
                'title': self.title,
                'swagger_ui_css': self._swagger_ui_resource('swagger-ui.css'),
                'swagger_ui_bundle': self._swagger_ui_resource('swagger-ui-bundle.js'),
                'swagger_ui_standalone': self._swagger_ui_resource('swagger-ui-standalone-preset.js'),
                'favicon_href': self._swagger_ui_favicon(),
                'schema_url': self._get_schema_url(request),
                'settings': self._dump(spectacular_settings.SWAGGER_UI_SETTINGS),
                'oauth2_config': self._dump(spectacular_settings.SWAGGER_UI_OAUTH2_CONFIG),
                'template_name_js': self.template_name_js,
                'script_url': None,
                'csrf_header_name': self._get_csrf_header_name(),
                'schema_auth_names': self._dump(self._get_schema_auth_names()),
            },
            template_name=self.template_name,
            headers={
                "Cross-Origin-Opener-Policy": "unsafe-none",
            }
        )

    def _dump(self, data):
        return data if isinstance(data, str) else json.dumps(data, indent=2)

    def _get_schema_url(self, request):
        schema_url = self.url or get_relative_url(reverse(self.url_name, request=request))
        return set_query_parameters(
            url=schema_url,
            lang=request.GET.get('lang'),
            version=request.GET.get('version')
        )

    def _get_csrf_header_name(self):
        csrf_header_name = settings.CSRF_HEADER_NAME
        if csrf_header_name.startswith('HTTP_'):
            csrf_header_name = csrf_header_name[5:]
        return csrf_header_name.replace('_', '-')

    def _get_schema_auth_names(self):
        from drf_spectacular.extensions import OpenApiAuthenticationExtension
        if spectacular_settings.SERVE_PUBLIC:
            return []
        auth_extensions = [
            OpenApiAuthenticationExtension.get_match(klass)
            for klass in self.authentication_classes
        ]
        return [auth.name for auth in auth_extensions if auth]

    @staticmethod
    def _swagger_ui_resource(filename):
        if spectacular_settings.SWAGGER_UI_DIST == 'SIDECAR':
            return _get_sidecar_url(f'swagger-ui-dist/{filename}')
        return f'{spectacular_settings.SWAGGER_UI_DIST}/{filename}'

    @staticmethod
    def _swagger_ui_favicon():
        if spectacular_settings.SWAGGER_UI_FAVICON_HREF == 'SIDECAR':
            return _get_sidecar_url('swagger-ui-dist/favicon-32x32.png')
        return spectacular_settings.SWAGGER_UI_FAVICON_HREF


class SpectacularSwaggerSplitView(SpectacularSwaggerView):
    """
    Alternate Swagger UI implementation that separates the html request from the
    javascript request to cater to web servers with stricter CSP policies.
    """
    url_self: Optional[str] = None

    @extend_schema(exclude=True)
    def get(self, request, *args, **kwargs):
        if request.GET.get('script') is not None:
            return Response(
                data={
                    'schema_url': self._get_schema_url(request),
                    'settings': self._dump(spectacular_settings.SWAGGER_UI_SETTINGS),
                    'oauth2_config': self._dump(spectacular_settings.SWAGGER_UI_OAUTH2_CONFIG),
                    'csrf_header_name': self._get_csrf_header_name(),
                    'schema_auth_names': self._dump(self._get_schema_auth_names()),
                },
                template_name=self.template_name_js,
                content_type='application/javascript',
            )
        else:
            script_url = self.url_self or request.get_full_path()
            return Response(
                data={
                    'title': self.title,
                    'swagger_ui_css': self._swagger_ui_resource('swagger-ui.css'),
                    'swagger_ui_bundle': self._swagger_ui_resource('swagger-ui-bundle.js'),
                    'swagger_ui_standalone': self._swagger_ui_resource('swagger-ui-standalone-preset.js'),
                    'favicon_href': self._swagger_ui_favicon(),
                    'script_url': set_query_parameters(
                        url=script_url,
                        lang=request.GET.get('lang'),
                        script=''  # signal to deliver init script
                    )
                },
                template_name=self.template_name,
            )


class SpectacularRedocView(APIView):
    renderer_classes = [TemplateHTMLRenderer]
    permission_classes = spectacular_settings.SERVE_PERMISSIONS
    authentication_classes = AUTHENTICATION_CLASSES
    url_name: str = 'schema'
    url: Optional[str] = None
    template_name: str = 'drf_spectacular/redoc.html'
    title: Optional[str] = spectacular_settings.TITLE

    @extend_schema(exclude=True)
    def get(self, request, *args, **kwargs):
        return Response(
            data={
                'title': self.title,
                'redoc_standalone': self._redoc_standalone(),
                'schema_url': self._get_schema_url(request),
                'settings': self._dump(spectacular_settings.REDOC_UI_SETTINGS),
            },
            template_name=self.template_name
        )

    def _dump(self, data):
        if not data:
            return None
        elif isinstance(data, str):
            return data
        else:
            return json.dumps(data, indent=2)

    @staticmethod
    def _redoc_standalone():
        if spectacular_settings.REDOC_DIST == 'SIDECAR':
            return _get_sidecar_url('redoc/bundles/redoc.standalone.js')
        return f'{spectacular_settings.REDOC_DIST}/bundles/redoc.standalone.js'

    def _get_schema_url(self, request):
        schema_url = self.url or get_relative_url(reverse(self.url_name, request=request))
        return set_query_parameters(
            url=schema_url,
            lang=request.GET.get('lang'),
            version=request.GET.get('version')
        )


class SpectacularSwaggerOauthRedirectView(RedirectView):
    """
    A view that serves the SwaggerUI oauth2-redirect.html file so that SwaggerUI can authenticate itself using Oauth2

    This view should be served as ``./oauth2-redirect.html`` relative to the SwaggerUI itself.
    If that is not possible, this views absolute url can also be set via the
    ``SPECTACULAR_SETTINGS.SWAGGER_UI_SETTINGS.oauth2RedirectUrl`` django settings.
    """
    def get_redirect_url(self, *args, **kwargs):
        return _get_sidecar_url("swagger-ui-dist/oauth2-redirect.html") + "?" + self.request.GET.urlencode()
