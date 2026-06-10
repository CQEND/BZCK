"""Direct unit tests for ``drf_spectacular.plumbing.build_parameter_type``.

These tests exercise each branch of ``build_parameter_type`` by inspecting the
returned dictionary directly, without relying on snapshot files.
"""

import pytest

from drf_spectacular.plumbing import build_parameter_type
from drf_spectacular.utils import OpenApiParameter


# ---------------------------------------------------------------------------
# Basic structure / location variations
# ---------------------------------------------------------------------------


def test_query_parameter_basic():
    param = build_parameter_type(
        name='q',
        schema={'type': 'string'},
        location=OpenApiParameter.QUERY,
    )
    assert param['in'] == 'query'
    assert param['name'] == 'q'
    assert param['schema'] == {'type': 'string'}
    # ``required`` is omitted when not required and not a path parameter
    assert 'required' not in param


def test_path_parameter_implies_required_and_strips_default_and_nullable():
    param = build_parameter_type(
        name='id',
        schema={'type': 'integer', 'nullable': True, 'default': 1, 'readOnly': True},
        location=OpenApiParameter.PATH,
    )
    assert param['in'] == 'path'
    assert param['required'] is True
    # PATH parameters strip ``nullable`` and ``default``
    assert 'nullable' not in param['schema']
    assert 'default' not in param['schema']
    # ``readOnly`` is always stripped from parameter schemas
    assert 'readOnly' not in param['schema']


def test_header_and_cookie_locations_accepted():
    header = build_parameter_type(
        name='X-Token', schema={'type': 'string'}, location=OpenApiParameter.HEADER,
    )
    cookie = build_parameter_type(
        name='session', schema={'type': 'string'}, location=OpenApiParameter.COOKIE,
    )
    assert header['in'] == 'header'
    assert cookie['in'] == 'cookie'


# ---------------------------------------------------------------------------
# ``required`` / ``description`` / ``deprecated``
# ---------------------------------------------------------------------------


def test_explicit_required_flag_is_honored():
    param = build_parameter_type(
        name='q', schema={'type': 'string'}, location=OpenApiParameter.QUERY, required=True,
    )
    assert param['required'] is True


def test_description_is_set_only_when_truthy():
    with_desc = build_parameter_type(
        name='q', schema={'type': 'string'}, location=OpenApiParameter.QUERY, description='a query',
    )
    without_desc = build_parameter_type(
        name='q', schema={'type': 'string'}, location=OpenApiParameter.QUERY, description=None,
    )
    assert with_desc['description'] == 'a query'
    assert 'description' not in without_desc


def test_deprecated_flag():
    param = build_parameter_type(
        name='old', schema={'type': 'string'}, location=OpenApiParameter.QUERY, deprecated=True,
    )
    assert param['deprecated'] is True


# ---------------------------------------------------------------------------
# ``explode`` / ``style`` combinations, including ``deepObject`` style
# ---------------------------------------------------------------------------


def test_deep_object_style_for_query_sets_explode_true():
    param = build_parameter_type(
        name='filter',
        schema={'type': 'object'},
        location=OpenApiParameter.QUERY,
        style='deepObject',
    )
    assert param['style'] == 'deepObject'
    assert param['explode'] is True


def test_deep_object_style_is_ignored_for_non_query_locations():
    # OpenAPI does not allow ``deepObject`` outside the query location; the
    # implementation should silently not set the style in that case.
    param = build_parameter_type(
        name='filter',
        schema={'type': 'object'},
        location=OpenApiParameter.HEADER,
        style='deepObject',
    )
    assert param['in'] == 'header'
    assert 'style' not in param
    assert 'explode' not in param


def test_explode_true_without_style():
    param = build_parameter_type(
        name='tags', schema={'type': 'string'}, location=OpenApiParameter.QUERY, explode=True,
    )
    assert param['explode'] is True
    assert 'style' not in param


def test_explode_false_without_style():
    param = build_parameter_type(
        name='tags', schema={'type': 'string'}, location=OpenApiParameter.QUERY, explode=False,
    )
    assert param['explode'] is False


def test_explode_with_explicit_form_style():
    param = build_parameter_type(
        name='tags',
        schema={'type': 'string'},
        location=OpenApiParameter.QUERY,
        style='form',
        explode=False,
    )
    assert param['style'] == 'form'
    assert param['explode'] is False


def test_form_style_without_explode_does_not_set_explode():
    # If the caller provides only a ``style`` but no ``explode`` value, we
    # should not invent one and leave it up to OpenAPI defaults.
    param = build_parameter_type(
        name='tags',
        schema={'type': 'string'},
        location=OpenApiParameter.QUERY,
        style='form',
    )
    assert param['style'] == 'form'
    assert 'explode' not in param


# ---------------------------------------------------------------------------
# Array schema + explode interaction
# ---------------------------------------------------------------------------


def test_array_schema_without_style_or_explode_defaults_to_form_and_explode_true():
    param = build_parameter_type(
        name='ids',
        schema={'type': 'array', 'items': {'type': 'integer'}},
        location=OpenApiParameter.QUERY,
    )
    assert param['schema']['type'] == 'array'
    assert param['style'] == 'form'
    assert param['explode'] is True


def test_array_schema_with_explode_false_explicit():
    param = build_parameter_type(
        name='ids',
        schema={'type': 'array', 'items': {'type': 'integer'}},
        location=OpenApiParameter.QUERY,
        explode=False,
    )
    assert param['style'] == 'form'
    assert param['explode'] is False


def test_array_schema_with_explode_true_explicit():
    param = build_parameter_type(
        name='ids',
        schema={'type': 'array', 'items': {'type': 'integer'}},
        location=OpenApiParameter.QUERY,
        explode=True,
    )
    assert param['style'] == 'form'
    assert param['explode'] is True


def test_array_schema_with_existing_style_keeps_style_intact():
    # If a caller already provided a style, we should not overwrite it with
    # the array default.
    param = build_parameter_type(
        name='ids',
        schema={'type': 'array', 'items': {'type': 'integer'}},
        location=OpenApiParameter.QUERY,
        style='spaceDelimited',
        explode=True,
    )
    assert param['style'] == 'spaceDelimited'
    assert param['explode'] is True


# ---------------------------------------------------------------------------
# ``enum`` / ``pattern`` handling: value goes onto ``items`` for arrays
# ---------------------------------------------------------------------------


def test_enum_on_scalar_schema():
    param = build_parameter_type(
        name='status', schema={'type': 'string'},
        location=OpenApiParameter.QUERY, enum=['b', 'a', 'c'],
    )
    assert param['schema']['enum'] == ['a', 'b', 'c']


def test_enum_on_array_schema_attaches_to_items():
    param = build_parameter_type(
        name='status',
        schema={'type': 'array', 'items': {'type': 'string'}},
        location=OpenApiParameter.QUERY,
        enum=['b', 'a'],
    )
    assert param['schema']['items']['enum'] == ['a', 'b']
    assert 'enum' not in param['schema']


def test_pattern_on_scalar_schema():
    param = build_parameter_type(
        name='code', schema={'type': 'string'},
        location=OpenApiParameter.QUERY, pattern=r'\d{3}',
    )
    assert param['schema']['pattern'] == r'\d{3}'


def test_pattern_on_array_schema_attaches_to_items():
    param = build_parameter_type(
        name='codes',
        schema={'type': 'array', 'items': {'type': 'string'}},
        location=OpenApiParameter.QUERY,
        pattern=r'\d{3}',
    )
    assert param['schema']['items']['pattern'] == r'\d{3}'
    assert 'pattern' not in param['schema']


# ---------------------------------------------------------------------------
# ``default``, ``allow_blank`` / ``allowEmptyValue``
# ---------------------------------------------------------------------------


def test_default_is_set_for_non_path_parameters():
    param = build_parameter_type(
        name='limit', schema={'type': 'integer'},
        location=OpenApiParameter.QUERY, default=10,
    )
    assert param['schema']['default'] == 10


def test_default_is_stripped_for_path_parameters():
    param = build_parameter_type(
        name='id', schema={'type': 'integer'},
        location=OpenApiParameter.PATH, default=1,
    )
    assert 'default' not in param['schema']


def test_allow_blank_false_sets_minlength_for_string():
    param = build_parameter_type(
        name='name', schema={'type': 'string'},
        location=OpenApiParameter.QUERY, allow_blank=False,
    )
    assert param['schema']['minLength'] == 1


def test_allow_blank_false_preserves_existing_minlength():
    param = build_parameter_type(
        name='name', schema={'type': 'string', 'minLength': 2},
        location=OpenApiParameter.QUERY, allow_blank=False,
    )
    assert param['schema']['minLength'] == 2


def test_allow_blank_false_on_query_string_sets_allow_empty_value_false():
    param = build_parameter_type(
        name='name', schema={'type': 'string'},
        location=OpenApiParameter.QUERY, allow_blank=False,
    )
    assert param['allowEmptyValue'] is False


def test_allow_blank_false_does_not_set_allow_empty_value_for_non_query():
    # ``allowEmptyValue`` is only meaningful for query parameters per OpenAPI.
    param = build_parameter_type(
        name='name', schema={'type': 'string'},
        location=OpenApiParameter.HEADER, allow_blank=False,
    )
    assert param['schema']['minLength'] == 1
    assert 'allowEmptyValue' not in param


def test_allow_blank_false_has_no_effect_on_non_string_types():
    param = build_parameter_type(
        name='age', schema={'type': 'integer'},
        location=OpenApiParameter.QUERY, allow_blank=False,
    )
    assert 'minLength' not in param['schema']
    assert 'allowEmptyValue' not in param


# ---------------------------------------------------------------------------
# ``examples`` and ``extensions``
# ---------------------------------------------------------------------------


def test_examples_are_attached_when_provided():
    examples = {'first': {'value': 'a'}}
    param = build_parameter_type(
        name='q', schema={'type': 'string'},
        location=OpenApiParameter.QUERY, examples=examples,
    )
    assert param['examples'] == examples


def test_extensions_are_sanitized_and_attached():
    extensions = {'x-foo': 'bar', 'x-baz': 1}
    param = build_parameter_type(
        name='q', schema={'type': 'string'},
        location=OpenApiParameter.QUERY, extensions=extensions,
    )
    assert param['x-foo'] == 'bar'
    assert param['x-baz'] == 1


def test_extensions_none_leaves_no_extra_fields():
    param = build_parameter_type(
        name='q', schema={'type': 'string'},
        location=OpenApiParameter.QUERY, extensions=None,
    )
    assert not any(k.startswith('x-') for k in param.keys())


# ---------------------------------------------------------------------------
# Misc / combined scenarios
# ---------------------------------------------------------------------------


def test_irrelevant_meta_is_stripped_from_schema():
    schema = {
        'type': 'integer',
        'readOnly': True,
        'writeOnly': True,
        'example': 1,
    }
    param = build_parameter_type(name='id', schema=schema, location=OpenApiParameter.QUERY)
    assert 'readOnly' not in param['schema']
    assert 'writeOnly' not in param['schema']
    assert param['schema']['example'] == 1


def test_full_fledged_parameter_with_all_options():
    param = build_parameter_type(
        name='tags',
        schema={'type': 'array', 'items': {'type': 'string'}},
        location=OpenApiParameter.QUERY,
        required=True,
        description='List of tags',
        enum=['a', 'b'],
        default=['a'],
        deprecated=True,
        examples={'first': {'value': ['a']}},
        extensions={'x-visible': True},
    )
    assert param['name'] == 'tags'
    assert param['in'] == 'query'
    assert param['required'] is True
    assert param['deprecated'] is True
    assert param['description'] == 'List of tags'
    assert param['schema']['items']['enum'] == ['a', 'b']
    assert param['schema']['default'] == ['a']
    assert param['style'] == 'form'
    assert param['explode'] is True
    assert param['examples'] == {'first': {'value': ['a']}}
    assert param['x-visible'] is True
