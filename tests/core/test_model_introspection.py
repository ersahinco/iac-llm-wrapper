"""Tests for model introspection utilities (generic core)."""

from __future__ import annotations

from enum import StrEnum

import pytest
from pydantic import BaseModel

from intent_engine.core.model_introspection import (
    append_to_list_field,
    coerce_value,
    derive_target_type,
    discover_model_fields,
    field_exists,
    list_annotation_item_model,
    resolve_field_info,
)


class Color(StrEnum):
    RED = "red"
    BLUE = "blue"


class NestedModel(BaseModel):
    name: str = "default"
    count: int = 0


class ItemModel(BaseModel):
    name: str = "item"
    value: str = ""


class SampleModel(BaseModel):
    __test__ = False
    name: str = "test"
    color: Color = Color.RED
    nested: NestedModel = NestedModel()
    items: list[ItemModel] = []
    tags: list[str] = []
    optional_field: str | None = None


class TestResolveFieldInfo:
    def test_resolve_top_level_field(self):
        field_info, annotation = resolve_field_info(SampleModel, "name")
        assert annotation is str

    def test_resolve_nested_field(self):
        field_info, annotation = resolve_field_info(SampleModel, "nested.name")
        assert annotation is str

    def test_resolve_enum_field(self):
        field_info, annotation = resolve_field_info(SampleModel, "color")
        from typing import get_args, get_origin

        if get_origin(annotation) is not None:
            args = get_args(annotation)
            annotation = next((a for a in args if a is not type(None)), annotation)
        assert annotation is Color

    def test_resolve_list_field(self):
        field_info, annotation = resolve_field_info(SampleModel, "items")
        from typing import get_origin

        assert get_origin(annotation) is list

    def test_missing_field_raises(self):
        with pytest.raises(AttributeError):
            resolve_field_info(SampleModel, "nonexistent")

    def test_resolve_union_optional(self):
        field_info, annotation = resolve_field_info(SampleModel, "optional_field")
        assert annotation is str | None or annotation == str | None


class TestDeriveTargetType:
    def test_string(self):
        assert derive_target_type(str) == "string"

    def test_int(self):
        assert derive_target_type(int) == "int"

    def test_bool(self):
        assert derive_target_type(bool) == "bool"

    def test_optional_str(self):
        assert derive_target_type(str | None) == "string"

    def test_list_str(self):
        assert derive_target_type(list[str]) == "cidr_list"

    def test_strenum(self):
        assert derive_target_type(Color) == "Color"


class TestCoerceValue:
    def test_coerce_str(self):
        assert coerce_value("hello", str) == "hello"

    def test_coerce_int(self):
        assert coerce_value("42", int) == 42

    def test_coerce_bool(self):
        assert coerce_value("true", bool) is True
        assert coerce_value("false", bool) is False

    def test_coerce_optional_str(self):
        assert coerce_value("hello", str | None) == "hello"

    def test_coerce_cidr_list(self):
        assert coerce_value("10.0.0.0/16,192.168.0.0/24", list[str]) == [
            "10.0.0.0/16",
            "192.168.0.0/24",
        ]

    def test_coerce_strenum(self):
        assert coerce_value("red", Color) == Color.RED

    def test_coerce_none(self):
        assert coerce_value(None, str) is None


class TestFieldExists:
    def test_existing_field(self):
        assert field_exists(SampleModel, "name")

    def test_nested_field(self):
        assert field_exists(SampleModel, "nested.name")

    def test_missing_field(self):
        assert not field_exists(SampleModel, "nonexistent")


class TestListAnnotationItemModel:
    def test_list_of_models(self):
        model = list_annotation_item_model(list[ItemModel])
        assert model is ItemModel

    def test_non_list_returns_none(self):
        assert list_annotation_item_model(str) is None

    def test_list_of_primitives_returns_none(self):
        assert list_annotation_item_model(list[str]) is None


class TestDiscoverModelFields:
    def test_discovers_leaf_fields(self):
        fields = discover_model_fields(SampleModel)
        assert "name" in fields
        assert "nested_name" in fields
        assert "nested_count" in fields

    def test_skips_nested_models(self):
        fields = discover_model_fields(SampleModel)
        assert "nested" not in fields

    def test_skips_list_of_models(self):
        fields = discover_model_fields(SampleModel)
        assert "items" not in fields


class TestAppendToListField:
    def test_appends_to_list_field(self):
        intent = SampleModel()
        ok = append_to_list_field(intent, "items", {"name": "first", "value": "v1"})
        assert ok is True
        assert len(intent.items) == 1
        assert intent.items[0].name == "first"
        assert intent.items[0].value == "v1"

    def test_appends_multiple(self):
        intent = SampleModel()
        append_to_list_field(intent, "items", {"name": "a"})
        append_to_list_field(intent, "items", {"name": "b"})
        assert len(intent.items) == 2

    def test_non_list_returns_false(self):
        intent = SampleModel()
        ok = append_to_list_field(intent, "name", {"name": "x"})
        assert ok is False

    def test_primitive_list_returns_false(self):
        intent = SampleModel()
        ok = append_to_list_field(intent, "tags", "new-tag")
        assert ok is False
