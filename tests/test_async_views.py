"""
Tests for drf-spectacular's support of DRF 3.12+ async views.

These tests cover both the low-level plumbing helpers that make async views
introspectable (``is_coroutine_function``, ``safe_call_view_method``) and the
end-to-end schema generation for function-style async views decorated with
``@api_view`` as well as for class-based views with async handler methods.
"""
import pytest

from rest_framework import serializers
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.views import APIView

from drf_spectacular.plumbing import (
    _resolve_coroutine, is_coroutine_function, safe_call_view_method,
)
from drf_spectacular.utils import extend_schema

from tests import generate_schema, get_request_schema, get_response_schema


def _resolve_schema_component(schema, ref):
    """drf-spectacular emits ``$ref`` references. Walk the components to
    resolve the referenced schema object so tests can introspect fields."""
    if not isinstance(ref, dict) or '$ref' not in ref:
        return ref
    path = ref['$ref'].split('/')
    obj = schema
    for part in path[1:]:
        obj = obj[part]
    return obj


# ---------------------------------------------------------------------------
# plumbing-level helpers
# ---------------------------------------------------------------------------
def test_is_coroutine_function_detects_async_and_sync():
    def sync_fn():
        return 'sync'

    async def async_fn():
        return 'async'

    assert is_coroutine_function(sync_fn) is False
    assert is_coroutine_function(async_fn) is True
    assert is_coroutine_function(None) is False
    assert is_coroutine_function(42) is False


def test_safe_call_view_method_sync_unchanged():
    class View:
        def get_serializer_class(self):
            return serializers.Serializer

    result = safe_call_view_method(View(), 'get_serializer_class')
    assert result is serializers.Serializer


def test_safe_call_view_method_missing_returns_default():
    result = safe_call_view_method(object(), 'get_serializer_class', default=42)
    assert result == 42


def test_safe_call_view_method_async_is_resolved_synchronously():
    class View:
        async def get_answer(self):
            return 42

    result = safe_call_view_method(View(), 'get_answer')
    assert result == 42


def test_safe_call_view_method_async_kwargs_are_passed_through():
    class View:
        async def get_item(self, key='default'):
            return key

    result = safe_call_view_method(View(), 'get_item', key='hello')
    assert result == 'hello'


def test_resolve_coroutine_handles_plain_values():
    # defensive: if something non-coroutine is passed we bail quietly
    assert _resolve_coroutine('not a coroutine') is None


# ---------------------------------------------------------------------------
# schema generation: function-style async views
# ---------------------------------------------------------------------------
class AsyncFunctionViewSerializer(serializers.Serializer):
    a = serializers.IntegerField()
    b = serializers.CharField(required=False)


def test_async_function_view_with_extend_schema():
    @extend_schema(
        request=AsyncFunctionViewSerializer,
        responses={200: AsyncFunctionViewSerializer},
    )
    @api_view(['POST'])
    async def async_hello(request):
        return Response({'a': 1, 'b': 'ok'})

    schema = generate_schema('async-hello', view_function=async_hello)
    operation = schema['paths']['/async-hello']['post']

    assert operation['operationId']
    request_schema = _resolve_schema_component(schema, get_request_schema(operation))
    assert request_schema['properties']['a']['type'] == 'integer'
    assert request_schema['properties']['b']['type'] == 'string'

    response_schema = _resolve_schema_component(
        schema, get_response_schema(operation, status='200')
    )
    assert response_schema['properties']['a']['type'] == 'integer'


# ---------------------------------------------------------------------------
# schema generation: class-based view with async handler
# ---------------------------------------------------------------------------
class AsyncClassSerializer(serializers.Serializer):
    name = serializers.CharField()
    count = serializers.IntegerField()


def test_class_view_with_async_get_handler():
    """A plain ``APIView`` subclass may expose async handlers without a
    dedicated ``AsyncAPIView`` base class. As long as the http-method handler
    is ``async def`` the schema generator should still be able to walk the
    view's configuration."""

    class AsyncHelloView(APIView):
        @extend_schema(
            request=AsyncClassSerializer,
            responses={200: AsyncClassSerializer},
        )
        async def post(self, request, *args, **kwargs):
            return Response({'name': 'x', 'count': 1})

    schema = generate_schema('async-class', view=AsyncHelloView)
    operation = schema['paths']['/async-class']['post']

    assert operation['operationId']
    request_schema = _resolve_schema_component(schema, get_request_schema(operation))
    assert request_schema['properties']['name']['type'] == 'string'
    assert request_schema['properties']['count']['type'] == 'integer'

    response_schema = _resolve_schema_component(
        schema, get_response_schema(operation, status='200')
    )
    assert response_schema['properties']['name']['type'] == 'string'


# ---------------------------------------------------------------------------
# schema generation: class-based view with async get_queryset/get_serializer_class
# ---------------------------------------------------------------------------
def test_class_view_with_async_get_serializer_class():
    """If a view overrides ``get_serializer_class`` with ``async def`` (for
    whatever reason), the schema generator should still be able to resolve
    the class without producing a broken schema."""

    class OverriddenSerializer(serializers.Serializer):
        title = serializers.CharField()

    class AsyncConfigView(APIView):
        async def get_serializer_class(self):
            return OverriddenSerializer

        @extend_schema(
            request=OverriddenSerializer,
            responses={200: OverriddenSerializer},
        )
        async def post(self, request, *args, **kwargs):
            return Response({'title': 'hello'})

    schema = generate_schema('async-cfg', view=AsyncConfigView)
    operation = schema['paths']['/async-cfg']['post']
    assert operation['operationId']
    request_schema = _resolve_schema_component(schema, get_request_schema(operation))
    assert request_schema['properties']['title']['type'] == 'string'


# ---------------------------------------------------------------------------
# consistency check: sync version of a view produces the same schema shape
# ---------------------------------------------------------------------------
def test_async_and_sync_view_schemas_are_equivalent():
    class SharedSerializer(serializers.Serializer):
        x = serializers.IntegerField()
        y = serializers.CharField()

    class SyncView(APIView):
        @extend_schema(
            request=SharedSerializer,
            responses={200: SharedSerializer},
        )
        def post(self, request, *args, **kwargs):
            return Response({'x': 1, 'y': 'a'})

    class AsyncView(APIView):
        @extend_schema(
            request=SharedSerializer,
            responses={200: SharedSerializer},
        )
        async def post(self, request, *args, **kwargs):
            return Response({'x': 1, 'y': 'a'})

    sync_schema = generate_schema('cmp-sync', view=SyncView)
    async_schema = generate_schema('cmp-async', view=AsyncView)

    sync_op = sync_schema['paths']['/cmp-sync']['post']
    async_op = async_schema['paths']['/cmp-async']['post']

    assert get_request_schema(sync_op) == get_request_schema(async_op)
    assert (
        get_response_schema(sync_op, status='200')
        == get_response_schema(async_op, status='200')
    )
