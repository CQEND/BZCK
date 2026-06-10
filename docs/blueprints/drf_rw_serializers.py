from drf_rw_serializers.generics import GenericAPIView as RWGenericAPIView

from drf_spectacular.openapi import AutoSchema


class CustomAutoSchema(AutoSchema):
    """ Utilize custom drf_rw_serializers methods for directional serializers """

    def _get_serializer_by_direction(self, direction, **kwargs):
        if isinstance(self.view, RWGenericAPIView):
            if direction == 'request':
                return self.view.get_write_serializer()
            return self.view.get_read_serializer()
        return super()._get_serializer_by_direction(direction, **kwargs)
