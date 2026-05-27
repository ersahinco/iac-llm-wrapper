"""Tests for model introspection with LZA models."""

from __future__ import annotations

import pytest

from intent_engine.core.model_introspection import (
    append_to_list_field,
    coerce_value,
    derive_target_type,
    discover_model_fields,
    field_exists,
    list_annotation_item_model,
    merge_into_list_field,
    resolve_field_info,
)
from intent_engine.patterns.lza.models import RawIntent, Topology, Workload


class TestResolveFieldInfo:
    def test_resolve_top_level_field(self):
        field_info, annotation = resolve_field_info(RawIntent, "primary_region")
        assert annotation is str

    def test_resolve_nested_field(self):
        field_info, annotation = resolve_field_info(RawIntent, "network.cidr")
        assert annotation is str

    def test_resolve_enum_field(self):
        field_info, annotation = resolve_field_info(RawIntent, "topology")
        from typing import get_args, get_origin

        if get_origin(annotation) is not None:
            args = get_args(annotation)
            annotation = next((a for a in args if a is not type(None)), annotation)
        assert annotation.__name__ == "Topology"

    def test_resolve_list_field(self):
        field_info, annotation = resolve_field_info(RawIntent, "workloads")
        from typing import get_origin

        assert get_origin(annotation) is list

    def test_missing_field_raises(self):
        with pytest.raises(AttributeError):
            resolve_field_info(RawIntent, "nonexistent")


class TestDeriveTargetType:
    def test_strenum(self):
        assert derive_target_type(Topology) == "Topology"


class TestCoerceValue:
    def test_coerce_strenum(self):
        assert coerce_value("hub-spoke", Topology) == Topology.HUB_SPOKE


class TestFieldExists:
    def test_existing_field(self):
        assert field_exists(RawIntent, "primary_region")

    def test_nested_field(self):
        assert field_exists(RawIntent, "network.cidr")

    def test_missing_field(self):
        assert not field_exists(RawIntent, "nonexistent")


class TestListAnnotationItemModel:
    def test_workloads(self):
        model = list_annotation_item_model(list[Workload])
        assert model is Workload


class TestDiscoverModelFields:
    def test_discovers_leaf_fields(self):
        fields = discover_model_fields(RawIntent)
        assert "primary_region" in fields
        assert "network_cidr" in fields
        assert "security_audit_retention_days" in fields

    def test_skips_nested_models(self):
        fields = discover_model_fields(RawIntent)
        assert "network" not in fields

    def test_skips_list_of_models(self):
        fields = discover_model_fields(RawIntent)
        assert "workloads" not in fields


class TestAppendToListField:
    def test_appends_workload(self):
        intent = RawIntent()
        ok = append_to_list_field(intent, "workloads", {"name": "api", "target_account": "Prod"})
        assert ok is True
        assert len(intent.workloads) == 1
        assert intent.workloads[0].name == "api"
        assert intent.workloads[0].target_account == "Prod"

    def test_non_list_returns_false(self):
        intent = RawIntent()
        ok = append_to_list_field(intent, "primary_region", {"name": "x"})
        assert ok is False


class TestMergeIntoListField:
    def test_appends_when_name_missing(self):
        intent = RawIntent()

        ok = merge_into_list_field(intent, "workloads", {"name": "api", "target_account": "Prod"})

        assert ok is True
        assert len(intent.workloads) == 1
        assert intent.workloads[0].target_account == "Prod"

    def test_backfills_only_missing_fields(self):
        intent = RawIntent()
        append_to_list_field(intent, "workloads", {"name": "api"})

        ok = merge_into_list_field(
            intent,
            "workloads",
            {
                "name": "api",
                "target_account": "Prod",
                "network_mode": "public",
                "port": 9000,
            },
        )

        assert ok is True
        assert len(intent.workloads) == 1
        assert intent.workloads[0].target_account == "Prod"
        assert intent.workloads[0].network_mode.value == "public"
        assert intent.workloads[0].port == 9000

    def test_preserves_explicit_existing_fields(self):
        intent = RawIntent()
        append_to_list_field(
            intent,
            "workloads",
            {"name": "api", "target_account": "Prod", "network_mode": "private"},
        )

        merge_into_list_field(
            intent,
            "workloads",
            {"name": "api", "target_account": "Shadow", "network_mode": "public"},
        )

        assert len(intent.workloads) == 1
        assert intent.workloads[0].target_account == "Prod"
        assert intent.workloads[0].network_mode.value == "private"
