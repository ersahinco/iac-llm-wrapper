"""Tests for model introspection utilities (generic core)."""

from __future__ import annotations

from enum import StrEnum

import pytest
from pydantic import BaseModel

from intent_engine.core.model_introspection import (
    coerce_requirement_value,
    coerce_value,
    resolve_field_info,
)


class Color(StrEnum):
    RED = "red"
    BLUE = "blue"


class NestedModel(BaseModel):
    name: str = "default"
    count: int = 0


class SampleModel(BaseModel):
    __test__ = False
    name: str = "test"
    color: Color = Color.RED
    nested: NestedModel = NestedModel()
    tags: list[str] = []
    optional_field: str | None = None
    enabled: bool = True


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

    def test_missing_field_raises(self):
        with pytest.raises(AttributeError):
            resolve_field_info(SampleModel, "nonexistent")

    def test_resolve_union_optional(self):
        field_info, annotation = resolve_field_info(SampleModel, "optional_field")
        assert annotation is str | None or annotation == str | None


class TestCoerceValue:
    def test_coerce_str(self):
        assert coerce_value("hello", str) == "hello"

    def test_coerce_int(self):
        assert coerce_value("42", int) == 42
        assert coerce_value("42.0", int) == 42
        assert coerce_value("1.5", int) is None
        assert coerce_value(True, int) is None
        assert coerce_value("not-an-int", int) is None

    def test_coerce_bool(self):
        assert coerce_value("true", bool) is True
        assert coerce_value("false", bool) is False
        assert coerce_value("sometimes", bool) is None

    def test_coerce_optional_str(self):
        assert coerce_value("hello", str | None) == "hello"
        assert coerce_value("not-an-int", int | None) is None

    def test_coerce_cidr_list(self):
        assert coerce_value("10.0.0.0/16,192.168.0.0/24", list[str]) == [
            "10.0.0.0/16",
            "192.168.0.0/24",
        ]
        assert coerce_value(["eu-central-1", "eu-west-1"], list[str]) == [
            "eu-central-1",
            "eu-west-1",
        ]
        assert coerce_value({"region": "eu-central-1"}, list[str]) is None

    def test_coerce_strenum(self):
        assert coerce_value("red", Color) == Color.RED
        assert coerce_value("green", Color) is None

    def test_coerce_none(self):
        assert coerce_value(None, str) is None

    def test_requirement_coercion_uses_model_then_fail_closed_fallback(self):
        assert (
            coerce_requirement_value(
                "false",
                model=SampleModel,
                target_field="enabled",
                target_type="bool",
            )
            is False
        )
        assert (
            coerce_requirement_value(
                "sometimes",
                model=SampleModel,
                target_field="enabled",
                target_type="bool",
            )
            is None
        )
        assert (
            coerce_requirement_value(
                "red",
                model=SampleModel,
                target_field="missing",
                target_type="Color",
            )
            == Color.RED
        )
