import os, sys
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tests.settings')

import django
django.setup()

from django.db import models
from rest_framework import serializers, viewsets
from django_filters.rest_framework import DjangoFilterBackend, FilterSet, ChoiceFilter
from drf_spectacular.generators import SchemaGenerator

# Define models inline
class Color(models.Model):
    name = models.CharField(max_length=10, choices=(('red', 'Red'), ('blue', 'Blue'), ('green', 'Green')))

    class Meta:
        app_label = 'tests'

class ColorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Color
        fields = '__all__'


# Test 1: ChoiceFilter with explicit choices
class Filter1(FilterSet):
    color = ChoiceFilter(choices=(('x', 'X'), ('y', 'Y')))

    class Meta:
        model = Color
        fields = []

class View1(viewsets.ReadOnlyModelViewSet):
    queryset = Color.objects.all()
    serializer_class = ColorSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = Filter1

gen = SchemaGenerator(patterns=None)
schema = gen.get_schema(request=None, public=True, patterns=None)

# Find the endpoint
for path, methods in schema.get('paths', {}).items():
    for method, info in methods.items():
        if method == 'get':
            params = info.get('parameters', [])
            for p in params:
                if p['name'] == 'color':
                    print("Test 1 - ChoiceFilter with explicit choices:")
                    print(f"  Schema: {p['schema']}")
                    enum = p['schema'].get('enum')
                    print(f"  Enum: {enum}")
                    assert enum == ['x', 'y'], f"Expected ['x', 'y'], got {enum}"
                    print("  PASS")