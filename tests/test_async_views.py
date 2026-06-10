from django.db import models
from rest_framework import generics, serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from drf_spectacular.plumbing import is_async_callable, is_view_method_async
from drf_spectacular.utils import extend_schema, extend_schema_view
from tests import generate_schema, get_response_schema


class ItemModel(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField()

    class Meta:
        app_label = 'tests'


class ItemSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField()
    description = serializers.CharField()


class SyncAPIView(APIView):
    serializer_class = ItemSerializer

    def get(self, request):
        return Response({'id': 1, 'name': 'test', 'description': 'desc'})

    def post(self, request):
        return Response({'id': 1, 'name': 'test', 'description': 'desc'})


class AsyncAPIView(APIView):
    serializer_class = ItemSerializer

    async def get(self, request):
        return Response({'id': 1, 'name': 'test', 'description': 'desc'})

    async def post(self, request):
        return Response({'id': 1, 'name': 'test', 'description': 'desc'})


def test_async_api_view_schema_matches_sync(no_warnings):
    sync_schema = generate_schema('/items', view=SyncAPIView)
    async_schema = generate_schema('/items', view=AsyncAPIView)
    assert sync_schema == async_schema


def test_async_api_view_with_extend_schema(no_warnings):
    @extend_schema_view(
        get=extend_schema(responses=ItemSerializer),
        post=extend_schema(request=ItemSerializer, responses=ItemSerializer),
    )
    class AsyncViewWithSchema(APIView):
        async def get(self, request):
            return Response({'id': 1, 'name': 'test', 'description': 'desc'})

        async def post(self, request):
            return Response({'id': 1, 'name': 'test', 'description': 'desc'})

    schema = generate_schema('/items', view=AsyncViewWithSchema)
    assert 'Item' in schema['components']['schemas']
    operation_get = schema['paths']['/items']['get']
    operation_post = schema['paths']['/items']['post']
    assert get_response_schema(operation_get) == {'$ref': '#/components/schemas/Item'}
    assert get_response_schema(operation_post) == {'$ref': '#/components/schemas/Item'}


def test_async_api_view_with_extend_schema_on_method(no_warnings):
    class AsyncViewMethodSchema(APIView):
        serializer_class = ItemSerializer

        @extend_schema(responses=ItemSerializer)
        async def get(self, request):
            return Response({'id': 1, 'name': 'test', 'description': 'desc'})

        @extend_schema(request=ItemSerializer, responses=ItemSerializer)
        async def post(self, request):
            return Response({'id': 1, 'name': 'test', 'description': 'desc'})

    schema = generate_schema('/items', view=AsyncViewMethodSchema)
    assert 'Item' in schema['components']['schemas']
    operation_get = schema['paths']['/items']['get']
    assert get_response_schema(operation_get) == {'$ref': '#/components/schemas/Item'}


def test_async_api_view_description(no_warnings):
    class AsyncViewWithDoc(APIView):
        serializer_class = ItemSerializer

        async def get(self, request):
            """Async GET description"""
            return Response({})

    schema = generate_schema('/items', view=AsyncViewWithDoc)
    assert schema['paths']['/items']['get']['description'] == 'Async GET description'


def test_async_generic_api_view(no_warnings):
    class AsyncGenericView(generics.GenericAPIView):
        serializer_class = ItemSerializer
        queryset = ItemModel.objects.none()

        async def get(self, request):
            return Response({'id': 1, 'name': 'test', 'description': 'desc'})

    schema = generate_schema('/items', view=AsyncGenericView)
    assert 'Item' in schema['components']['schemas']
    operation = schema['paths']['/items']['get']
    assert get_response_schema(operation) == {'$ref': '#/components/schemas/Item'}


def test_async_api_view_with_async_get_serializer_class(warnings):
    class ViewWithAsyncGetSerializer(APIView):
        async def get_serializer_class(self):
            return ItemSerializer

        async def get(self, request):
            return Response({})

    schema = generate_schema('/items', view=ViewWithAsyncGetSerializer)
    assert 'schemas' not in schema.get('components', {}) or 'Item' not in schema['components']['schemas']


def test_async_api_view_with_async_get_serializer(warnings):
    class ViewWithAsyncGetSerializer(APIView):
        serializer_class = ItemSerializer

        async def get_serializer(self, *args, **kwargs):
            return ItemSerializer(*args, **kwargs)

        async def get(self, request):
            return Response({})

    schema = generate_schema('/items', view=ViewWithAsyncGetSerializer)
    assert 'Item' in schema['components']['schemas']
    operation = schema['paths']['/items']['get']
    assert get_response_schema(operation) == {'$ref': '#/components/schemas/Item'}


def test_async_api_view_with_serializer_class_fallback(warnings):
    class ViewWithAsyncGetSerializerButClassAttr(APIView):
        serializer_class = ItemSerializer

        async def get_serializer(self, *args, **kwargs):
            return ItemSerializer(*args, **kwargs)

        async def get(self, request):
            return Response({})

    schema = generate_schema('/items', view=ViewWithAsyncGetSerializerButClassAttr)
    assert 'Item' in schema['components']['schemas']
    operation = schema['paths']['/items']['get']
    assert get_response_schema(operation) == {'$ref': '#/components/schemas/Item'}


def test_async_api_view_with_extend_schema_overrides_async(no_warnings):
    @extend_schema(responses=ItemSerializer)
    class FullyAsyncView(APIView):
        async def get(self, request):
            return Response({})

    schema = generate_schema('/items', view=FullyAsyncView)
    assert 'Item' in schema['components']['schemas']
    operation = schema['paths']['/items']['get']
    assert get_response_schema(operation) == {'$ref': '#/components/schemas/Item'}


def test_is_async_callable():
    async def async_func():
        pass

    def sync_func():
        pass

    assert is_async_callable(async_func)
    assert not is_async_callable(sync_func)


def test_is_async_callable_with_bound_method():
    class MyView:
        async def get(self, request):
            pass

        def post(self, request):
            pass

    view = MyView()
    assert is_async_callable(view.get)
    assert not is_async_callable(view.post)


def test_is_view_method_async():
    class MyView:
        async def get(self, request):
            pass

        def post(self, request):
            pass

    view = MyView()
    assert is_view_method_async(view, 'get')
    assert not is_view_method_async(view, 'post')
    assert not is_view_method_async(view, 'nonexistent')


def test_async_api_view_schema_valid(no_warnings):
    class AsyncView(APIView):
        serializer_class = ItemSerializer

        async def get(self, request):
            """Retrieve items asynchronously"""
            return Response({'id': 1, 'name': 'test', 'description': 'desc'})

        async def post(self, request):
            """Create item asynchronously"""
            return Response({'id': 1, 'name': 'test', 'description': 'desc'})

    schema = generate_schema('/items', view=AsyncView)

    assert 'Item' in schema['components']['schemas']
    item_schema = schema['components']['schemas']['Item']
    assert item_schema['type'] == 'object'
    assert 'name' in item_schema['properties']
    assert 'description' in item_schema['properties']

    get_op = schema['paths']['/items']['get']
    assert get_op['description'] == 'Retrieve items asynchronously'
    assert get_op['operationId'] == 'items_retrieve'

    post_op = schema['paths']['/items']['post']
    assert post_op['description'] == 'Create item asynchronously'
