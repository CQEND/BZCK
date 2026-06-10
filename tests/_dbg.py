def test_debug_async_api_view():
    from rest_framework import serializers
    from rest_framework.decorators import api_view
    from rest_framework.response import Response

    class S(serializers.Serializer):
        a = serializers.IntegerField()

    @extend_schema_schema = lambda x: x  # dummy

    from drf_spectacular.utils import extend_schema

    @extend_schema(request=S, responses=S)
    @api_view(['POST'])
    async def async_hello(request):
        return Response({'a': 1})

    schema = generate_schema('hello', view_function=async_hello)
    import json
    print(json.dumps(schema['paths'], indent=2, default=str))
    assert False, 'intentionally'
