def test_debug_async():
    import json
    from rest_framework import serializers
    from rest_framework.decorators import api_view
    from rest_framework.response import Response
    from drf_spectacular.utils import extend_schema

    class S(serializers.Serializer):
        a = serializers.IntegerField()

    @extend_schema(request=S, responses=S)
    @api_view(['POST'])
    async def async_hello(request):
        return Response({'a': 1})

    from tests import generate_schema
    schema = generate_schema('dbg', view_function=async_hello)
    print(json.dumps(schema['paths'], indent=2, default=str))
    assert False, 'debug stop'
