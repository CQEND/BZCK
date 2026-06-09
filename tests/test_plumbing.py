import collections
import json
import re
import sys
import typing
from datetime import datetime
from enum import Enum
from unittest import mock

if sys.version_info >= (3, 8):
    from typing import TypedDict
else:
    from typing_extensions import TypedDict

import pytest
from django import __version__ as DJANGO_VERSION
from django.db import models
from django.urls import include, path
from django.utils.functional import lazystr
from rest_framework import generics, serializers

from drf_spectacular.openapi import AutoSchema
from drf_spectacular.plumbing import (
    _apply_content_type_overrides, _build_media_type_examples, _get_media_type_schema,
    _resolve_media_type_encoding, analyze_named_regex_pattern, build_basic_type,
    build_choice_field, build_media_type_object, detype_pattern, follow_field_source,
    force_instance, get_doc, get_list_serializer, get_relative_url, is_field, is_serializer,
    resolve_type_hint, safe_ref, set_query_parameters,
)
from drf_spectacular.utils import OpenApiExample
from drf_spectacular.validation import validate_schema
from tests import generate_schema


def test_get_list_serializer_preserves_context():
    serializer = serializers.Serializer(context={"foo": "bar"})
    list_serializer = get_list_serializer(serializer)
    assert list_serializer.context == {"foo": "bar"}


def test_is_serializer():
    assert not is_serializer(serializers.SlugField)
    assert not is_serializer(serializers.SlugField())

    assert not is_serializer(models.CharField)
    assert not is_serializer(models.CharField())

    assert is_serializer(serializers.Serializer)
    assert is_serializer(serializers.Serializer())


def test_is_field():
    assert is_field(serializers.SlugField)
    assert is_field(serializers.SlugField())

    assert not is_field(models.CharField)
    assert not is_field(models.CharField())

    assert not is_field(serializers.Serializer)
    assert not is_field(serializers.Serializer())


def test_force_instance():
    assert isinstance(force_instance(serializers.CharField), serializers.CharField)
    assert force_instance(5) == 5
    assert force_instance(dict) == dict


def test_follow_field_source_forward_reverse(no_warnings):
    class FFS1(models.Model):
        id = models.UUIDField(primary_key=True)
        field_bool = models.BooleanField()

    class FFS2(models.Model):
        ffs1 = models.ForeignKey(FFS1, on_delete=models.PROTECT)

    class FFS3(models.Model):
        id = models.CharField(primary_key=True, max_length=3)
        ffs2 = models.ForeignKey(FFS2, on_delete=models.PROTECT)
        field_float = models.FloatField()

    forward_field = follow_field_source(FFS3, ['ffs2', 'ffs1', 'field_bool'])
    reverse_field = follow_field_source(FFS1, ['ffs2', 'ffs3', 'field_float'])
    forward_model = follow_field_source(FFS3, ['ffs2', 'ffs1'])
    reverse_model = follow_field_source(FFS1, ['ffs2', 'ffs3'])

    assert isinstance(forward_field, models.BooleanField)
    assert isinstance(reverse_field, models.FloatField)
    assert isinstance(forward_model, models.UUIDField)
    assert isinstance(reverse_model, models.CharField)

    auto_schema = AutoSchema()
    assert auto_schema._map_model_field(forward_field, None)['type'] == 'boolean'
    assert auto_schema._map_model_field(reverse_field, None)['type'] == 'number'
    assert auto_schema._map_model_field(forward_model, None)['type'] == 'string'
    assert auto_schema._map_model_field(reverse_model, None)['type'] == 'string'


def test_detype_patterns_with_module_includes(no_warnings):
    detype_pattern(
        pattern=path('', include('tests.test_fields'))
    )


NamedTupleA = collections.namedtuple("NamedTupleA", "a, b")


class NamedTupleB(typing.NamedTuple):
    a: int
    b: str


class LanguageEnum(str, Enum):
    EN = 'en'
    DE = 'de'


# Make sure we can deal with plain Enums that are not handled by DRF.
# The second base class makes this work for DRF.
class InvalidLanguageEnum(Enum):
    EN = 'en'
    DE = 'de'


class TD1(TypedDict):
    foo: int
    bar: typing.List[str]


class TD2(TypedDict):
    foo: str
    bar: typing.Dict[str, int]


TYPE_HINT_TEST_PARAMS = [
    (
        typing.Optional[int],
        {'type': 'integer', 'nullable': True}
    ), (
        typing.List[int],
        {'type': 'array', 'items': {'type': 'integer'}}
    ), (
        typing.List[typing.Dict[str, int]],
        {'type': 'array', 'items': {'type': 'object', 'additionalProperties': {'type': 'integer'}}}
    ), (
        list,
        {'type': 'array', 'items': {}}
    ), (
        typing.Tuple[int, int, int],
        {'type': 'array', 'items': {'type': 'integer'}, 'minLength': 3, 'maxLength': 3}
    ), (
        typing.Set[datetime],
        {'type': 'array', 'items': {'type': 'string', 'format': 'date-time'}}
    ), (
        typing.FrozenSet[datetime],
        {'type': 'array', 'items': {'type': 'string', 'format': 'date-time'}}
    ), (
        typing.Dict[str, int],
        {'type': 'object', 'additionalProperties': {'type': 'integer'}}
    ), (
        typing.Dict[str, str],
        {'type': 'object', 'additionalProperties': {'type': 'string'}}
    ), (
        typing.Dict[str, typing.List[int]],
        {'type': 'object', 'additionalProperties': {'type': 'array', 'items': {'type': 'integer'}}}
    ), (
        dict,
        {'type': 'object', 'additionalProperties': {}}
    ), (
        typing.Union[int, str],
        {'oneOf': [{'type': 'integer'}, {'type': 'string'}]}
    ), (
        typing.Union[int, str, None],
        {'oneOf': [{'type': 'integer'}, {'type': 'string'}], 'nullable': True}
    ), (
        typing.Optional[typing.Union[str, int]],
        {'oneOf': [{'type': 'string'}, {'type': 'integer'}], 'nullable': True}
    ), (
        LanguageEnum,
        {'enum': ['en', 'de'], 'type': 'string'}
    ), (
        InvalidLanguageEnum,
        {'enum': ['en', 'de']}
    ), (
        NamedTupleB,
        {
            'type': 'object',
            'properties': {'a': {'type': 'integer'}, 'b': {'type': 'string'}},
            'required': ['a', 'b']
        }
    )
]


if DJANGO_VERSION > '3':
    from django.db.models.enums import TextChoices  # only available in Django>3

    class LanguageChoices(TextChoices):
        EN = 'en'
        DE = 'de'

    TYPE_HINT_TEST_PARAMS.append((
        LanguageChoices,
        {
            'enum': ['en', 'de'],
            'type': 'string',
            'description': '* `en` - En\n* `de` - De',
            'x-spec-enum-id': '982ab9eaa2725610'
        }
    ))

TYPE_HINT_TEST_PARAMS.append((
    typing.Iterable[NamedTupleA],
    {
        'type': 'array',
        'items': {'type': 'object', 'properties': {'a': {}, 'b': {}}, 'required': ['a', 'b']}
    }
))

if sys.version_info >= (3, 8):
    # Literal only works for python >= 3.8 despite typing_extensions, because it
    # behaves slightly different w.r.t. __origin__
    TYPE_HINT_TEST_PARAMS.append((
        typing.Literal['x', 'y'],
        {'enum': ['x', 'y'], 'type': 'string'}
    ))

    class TD3(TypedDict, total=False):
        """a test description"""
        a: str
    TYPE_HINT_TEST_PARAMS.append((
        TD3,
        {
            'type': 'object',
            'description': 'a test description',
            'properties': {
                'a': {'type': 'string'},
            }
        }
    ))

if sys.version_info >= (3, 9):
    TYPE_HINT_TEST_PARAMS.append((
        dict[str, int],
        {'type': 'object', 'additionalProperties': {'type': 'integer'}}
    ))


# typing.TypedDict for py==3.8 is missing the __required_keys__ feature.
# below that we use typing_extensions.TypedDict, which does contain it.
if sys.version_info >= (3, 9) or sys.version_info < (3, 8):
    class TD4Optional(TypedDict, total=False):
        a: str

    class TD4(TD4Optional):
        """A test description2"""
        b: bool
    TYPE_HINT_TEST_PARAMS.append((
        TD1,
        {
            'type': 'object',
            'properties': {
                'foo': {'type': 'integer'},
                'bar': {'type': 'array', 'items': {'type': 'string'}}
            },
            'required': ['bar', 'foo']
        }
    ))
    TYPE_HINT_TEST_PARAMS.append((
        typing.List[TD2],
        {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'foo': {'type': 'string'},
                    'bar': {'type': 'object', 'additionalProperties': {'type': 'integer'}}
                },
                'required': ['bar', 'foo'],
            }
        }
    ))
    TYPE_HINT_TEST_PARAMS.append((
        TD4,
        {
            'type': 'object',
            'description': 'A test description2',
            'properties': {
                'a': {'type': 'string'},
                'b': {'type': 'boolean'}
            },
            'required': ['b'],
        })
    )
else:
    TYPE_HINT_TEST_PARAMS.append((
        TD1,
        {
            'type': 'object',
            'properties': {
                'foo': {'type': 'integer'},
                'bar': {'type': 'array', 'items': {'type': 'string'}}
            },
        }
    ))
    TYPE_HINT_TEST_PARAMS.append((
        typing.List[TD2],
        {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'foo': {'type': 'string'},
                    'bar': {'type': 'object', 'additionalProperties': {'type': 'integer'}}
                }
            },
        }
    ))
# New X | Y union syntax in Python 3.10+ (PEP 604)
if sys.version_info >= (3, 10):
    TYPE_HINT_TEST_PARAMS.extend([
        (
            int | None,
            {'type': 'integer', 'nullable': True}
        ),
        (
            int | str,
            {'oneOf': [{'type': 'integer'}, {'type': 'string'}]}
        ), (
            int | str | None,
            {'oneOf': [{'type': 'integer'}, {'type': 'string'}], 'nullable': True}
        ), (
            list[int | str],
            {"type": "array", "items": {"oneOf": [{"type": "integer"}, {"type": "string"}]}}
        )
    ])

if sys.version_info >= (3, 12):
    exec("type MyAlias = typing.Literal['x', 'y']")
    exec("type MyAliasNested = MyAlias | list[int | str]")

    TYPE_HINT_TEST_PARAMS.extend([
        (
            MyAlias,  # noqa: F821
            {'enum': ['x', 'y'], 'type': 'string'}
        ),
        (
            MyAliasNested,  # noqa: F821
            {
                'oneOf': [
                    {'enum': ['x', 'y'], 'type': 'string'},
                    {"type": "array", "items": {"oneOf": [{"type": "integer"}, {"type": "string"}]}}
                ]
            }
        )
    ])


@pytest.mark.parametrize(['type_hint', 'ref_schema'], TYPE_HINT_TEST_PARAMS)
def test_type_hint_extraction(no_warnings, type_hint, ref_schema):
    def func() -> type_hint:
        pass  # pragma: no cover

    # check expected resolution
    schema = resolve_type_hint(typing.get_type_hints(func).get('return'))
    assert json.dumps(schema) == json.dumps(ref_schema)

    # check schema validity
    class XSerializer(serializers.Serializer):
        x = serializers.SerializerMethodField()
    XSerializer.get_x = func

    class XView(generics.RetrieveAPIView):
        serializer_class = XSerializer

    validate_schema(generate_schema('/x', view=XView))


@pytest.mark.parametrize(['pattern', 'output'], [
    ('(?P<t1><,()(())(),)', {'t1': '<,()(())(),'}),
    (r'(?P<t1>.\\)', {'t1': r'.\\'}),
    (r'(?P<t1>.\\\\)', {'t1': r'.\\\\'}),
    (r'(?P<t1>.\))', {'t1': r'.\)'}),
    (r'(?P<t1>)', {'t1': r''}),
    (r'(?P<t1>.[\(]{2})', {'t1': r'.[\(]{2}'}),
    (r'(?P<t1>(.))/\(t/(?P<t2>\){2}()\({2}().*)', {'t1': '(.)', 't2': r'\){2}()\({2}().*'}),
])
def test_analyze_named_regex_pattern(no_warnings, pattern, output):
    re.compile(pattern)  # check validity of regex
    assert analyze_named_regex_pattern(pattern) == output


def test_unknown_basic_type(capsys):
    build_basic_type(object)
    assert 'could not resolve type for "<class \'object\'>' in capsys.readouterr().err


def test_choicefield_choices_enum():
    schema = build_choice_field(serializers.ChoiceField(['bluepill', 'redpill']))
    assert schema['enum'] == ['bluepill', 'redpill']
    assert schema['type'] == 'string'

    schema = build_choice_field(serializers.ChoiceField(
        ['bluepill', 'redpill'], allow_null=True, allow_blank=True
    ))
    assert schema['enum'] == ['bluepill', 'redpill', '', None]
    assert schema['type'] == 'string'

    schema = build_choice_field(serializers.ChoiceField(
        choices=['bluepill', 'redpill', '', None], allow_null=True, allow_blank=True
    ))
    assert schema['enum'] == ['bluepill', 'redpill', '', None]
    assert 'type' not in schema

    schema = build_choice_field(serializers.ChoiceField(
        choices=[1, 2], allow_blank=True
    ))
    assert schema['enum'] == [1, 2, '']
    assert 'type' not in schema


def test_choicefield_empty_choices():
    schema = build_choice_field(serializers.ChoiceField(choices=[]))
    assert schema['enum'] == []
    assert 'type' not in schema

    schema = build_choice_field(serializers.ChoiceField(choices=[], allow_null=True))
    assert schema['enum'] == [None]
    assert 'type' not in schema

    schema = build_choice_field(serializers.ChoiceField(choices=[], allow_blank=True))
    assert schema['enum'] == ['']
    assert schema['type'] == 'string'

    schema = build_choice_field(serializers.ChoiceField(choices=[], allow_blank=True, allow_null=True))
    assert schema['enum'] == ['', None]
    assert schema['type'] == 'string'


def test_safe_ref():
    schema = build_basic_type(str)
    schema['$ref'] = '#/components/schemas/Foo'

    schema = safe_ref(schema)
    assert schema == {
        'allOf': [{'$ref': '#/components/schemas/Foo'}],
        'type': 'string'
    }

    del schema['type']
    schema = safe_ref(schema)
    assert schema == {'$ref': '#/components/schemas/Foo'}
    assert safe_ref(schema) == safe_ref(schema)


def test_url_tooling_with_lazy_url():
    some_url = "http://api.example.org/accounts/"

    assert get_relative_url(some_url) == "/accounts/"
    assert set_query_parameters(some_url, foo=123) == some_url + "?foo=123"

    assert get_relative_url(lazystr(some_url)) == "/accounts/"
    assert set_query_parameters(lazystr(some_url), foo=123) == some_url + "?foo=123"


def test_get_doc():
    T = typing.TypeVar('T')

    class MyClass(typing.Generic[T]):
        pass

    doc = get_doc(MyClass)
    assert doc == ""


@pytest.mark.parametrize('disable', [False, True])
def test_get_doc_with_class_docstring(disable):
    class MyClass:
        """a docstring"""

    with mock.patch(
        "drf_spectacular.settings.spectacular_settings.DISABLE_DOCSTRING_DESCRIPTIONS",
        disable,
    ):
        doc = get_doc(MyClass)
        if disable:
            assert doc == ""
        else:
            assert doc == "a docstring"


@pytest.mark.parametrize('disable', [False, True])
def test_get_doc_with_function_docstring(disable):
    def my_func():
        """a docstring"""

    with mock.patch(
        "drf_spectacular.settings.spectacular_settings.DISABLE_DOCSTRING_DESCRIPTIONS",
        disable,
    ):
        doc = get_doc(my_func)
        if disable:
            assert doc == ""
        else:
            assert doc == "a docstring"


@pytest.mark.parametrize('disable', [False, True])
def test_get_doc_with_method_docstring(disable):
    class MyClass:
        def my_method(self):
            """a docstring"""

    with mock.patch(
        "drf_spectacular.settings.spectacular_settings.DISABLE_DOCSTRING_DESCRIPTIONS",
        disable,
    ):
        doc = get_doc(MyClass().my_method)
        if disable:
            assert doc == ""
        else:
            assert doc == "a docstring"


# ---------------------------------------------------------------------------
# Tests for the media-type helper functions extracted from build_media_type_object.
# ---------------------------------------------------------------------------


def test_build_media_type_object_minimal():
    # Schema-only usage preserves the schema key (no optional fields emitted).
    schema = {'type': 'object', 'properties': {'name': {'type': 'string'}}}
    result = build_media_type_object(schema)
    assert result == {'schema': schema}
    assert 'examples' not in result
    assert 'encoding' not in result


def test_build_media_type_object_with_examples_dict():
    schema = {'type': 'string'}
    examples = {'default': {'value': 'hello'}}
    result = build_media_type_object(schema, examples=examples)
    assert result['examples'] == examples


def test_build_media_type_object_with_encoding():
    schema = {'type': 'object'}
    encoding = {'file': {'contentType': 'application/octet-stream'}}
    result = build_media_type_object(
        schema, encoding=encoding, media_type='multipart/form-data',
    )
    assert result['encoding'] == encoding


def test_get_media_type_schema_none_returns_none():
    assert _get_media_type_schema(None) is None


def test_get_media_type_schema_dict_passthrough():
    schema = {'type': 'object'}
    assert _get_media_type_schema(schema) is schema


def test_get_media_type_schema_basic_type():
    from drf_spectacular.types import OpenApiTypes
    result = _get_media_type_schema(OpenApiTypes.INT)
    assert result is not None
    assert result.get('type') in ('integer', 'number')


def test_resolve_media_type_encoding_empty_input():
    assert _resolve_media_type_encoding(None) is None
    assert _resolve_media_type_encoding({}) is None


def test_resolve_media_type_encoding_preserves_valid_encoding():
    encoding = {'file': {'contentType': 'application/octet-stream'}}
    assert _resolve_media_type_encoding(
        encoding, 'multipart/form-data') == encoding


def test_resolve_media_type_encoding_warns_on_incompatible_media_type():
    encoding = {'file': {'contentType': 'application/octet-stream'}}
    with mock.patch('drf_spectacular.drainage.warn') as mocked_warn:
        result = _resolve_media_type_encoding(encoding, 'application/json')
    mocked_warn.assert_called_once()
    assert result == encoding


def test_resolve_media_type_encoding_strips_none_values():
    encoding = {'file': {'contentType': 'image/png', 'headers': None}}
    result = _resolve_media_type_encoding(encoding, 'multipart/form-data')
    assert result == {'file': {'contentType': 'image/png'}}


def test_build_media_type_examples_none_and_empty():
    assert _build_media_type_examples(None) is None
    assert _build_media_type_examples([]) is None


def test_build_media_type_examples_dict_passthrough():
    examples = {'default': {'value': 'ok'}}
    assert _build_media_type_examples(examples) is examples


def test_build_media_type_examples_from_openapi_example_objects():
    examples = [
        OpenApiExample(name='example1', value='hello'),
    ]
    result = _build_media_type_examples(examples)
    assert result is not None
    assert 'Example1' in result
    assert result['Example1']['value'] == 'hello'


def test_apply_content_type_overrides_no_overrides_is_identity():
    obj = {'schema': {'type': 'string'}}
    assert _apply_content_type_overrides(obj, 'application/json') is obj
    assert obj == {'schema': {'type': 'string'}}


def test_apply_content_type_overrides_adds_key():
    obj = {'schema': {'type': 'string'}}
    result = _apply_content_type_overrides(
        obj, 'application/json', overrides={'description': 'raw string body'}
    )
    assert result['description'] == 'raw string body'


def test_apply_content_type_overrides_removes_key_when_value_is_none():
    obj = {
        'schema': {'type': 'object'},
        'examples': {'foo': {'value': 1}},
    }
    result = _apply_content_type_overrides(
        obj, 'text/plain', overrides={'schema': None}
    )
    assert 'schema' not in result
    assert 'examples' in result


def test_apply_content_type_overrides_override_value_takes_precedence():
    obj = {'schema': {'type': 'object'}}
    result = _apply_content_type_overrides(
        obj,
        'application/json', overrides={'schema': {'type': 'string'}}
    )
    assert result['schema'] == {'type': 'string'}


def test_build_media_type_object_accepts_media_type_and_overrides():
    # Verify that the combined path through helpers produces expected shape.
    result = build_media_type_object(
        {'type': 'object'},
        examples={'demo': {'value': 'ok'}},
        encoding={'file': {'contentType': 'application/octet-stream'}},
        media_type='multipart/form-data',
    )
    assert result['schema'] == {'type': 'object'}
    assert result['examples'] == {'demo': {'value': 'ok'}}
    assert result['encoding'] == {'file': {'contentType': 'application/octet-stream'}}


def test_build_media_type_object_overrides_override_existing_keys():
    result = build_media_type_object(
        {'type': 'object'},
        examples={'demo': {'value': 'ok'}},
        overrides={'schema': {'type': 'string'}},
    )
    assert result['schema'] == {'type': 'string'}
