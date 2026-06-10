import pytest
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import serializers
from drf_spectacular.utils import extend_schema
from drf_spectacular.generators import SchemaGenerator
from django.urls import path

class MySerializer(serializers.Serializer):
    name = serializers.CharField()

class SyncView(APIView):
    @extend_schema(responses={200: MySerializer})
    def get(self, request):
        return Response({"name": "sync"})

try:
    from adrf.views import APIView as AsyncAPIView
except ImportError:
    try:
        from rest_framework.views import AsyncAPIView
    except ImportError:
        # mock it
        class AsyncAPIView(APIView):
            pass

class AsyncTestView(AsyncAPIView):
    @extend_schema(responses={200: MySerializer})
    async def get(self, request):
        return Response({"name": "async"})

def test_async_view():
    sync_generator = SchemaGenerator(patterns=[path('sync', SyncView.as_view())])
    sync_schema = sync_generator.get_schema(request=None, public=True)

    async_generator = SchemaGenerator(patterns=[path('async', AsyncTestView.as_view())])
    async_schema = async_generator.get_schema(request=None, public=True)

    sync_op = sync_schema['paths']['/sync']['get']
    async_op = async_schema['paths']['/async']['get']
    
    # remove operationId since they will be 'sync_retrieve' vs 'async_retrieve'
    del sync_op['operationId']
    del async_op['operationId']

    assert sync_op == async_op
