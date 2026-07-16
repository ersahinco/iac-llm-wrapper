"""Resolve Pydantic fields and coerce graph decisions to model values."""

from __future__ import annotations

import importlib
from enum import StrEnum
from typing import Any, get_args, get_origin

from pydantic import BaseModel


def resolve_field_info(
    model: type[BaseModel],
    dotted_path: str,
) -> tuple[Any, Any]:
    """Resolve a dotted path to (field_info, annotation) on a model.

    Returns (field_info, annotation) where field_info may be None for nested
    model attributes that are not Pydantic fields.
    """
    parts = dotted_path.split(".")
    current_model: type[Any] = model
    field_info: Any = None
    annotation: Any = None

    for i, part in enumerate(parts):
        if not issubclass(current_model, BaseModel):
            # We've reached a non-model attribute; try getattr
            annotation = getattr(current_model, "__annotations__", {}).get(part, Any)
            field_info = None
            break

        if part not in current_model.model_fields:
            raise AttributeError(
                f"Field '{part}' not found on {current_model.__name__}. "
                f"Available: {list(current_model.model_fields.keys())}"
            )
        field_info = current_model.model_fields[part]
        annotation = field_info.annotation

        # If there are more parts, descend into the annotation
        if i < len(parts) - 1:
            origin = get_origin(annotation)
            if origin is not None:
                # Unwrap Optional, list, etc.
                args = get_args(annotation)
                if origin is list and args:
                    annotation = args[0]
                elif type(None) in args:
                    # Optional[X] -> X
                    annotation = next(a for a in args if a is not type(None))
                else:
                    annotation = args[0] if args else Any
            current_model = annotation

    return field_info, annotation


def _unwrap_optional(annotation: Any) -> tuple[Any, Any]:
    origin = get_origin(annotation)
    if origin is not None:
        args = get_args(annotation)
        if type(None) in args:
            annotation = next(a for a in args if a is not type(None))
            origin = get_origin(annotation)
    return annotation, origin


def _coerce_int(raw: Any) -> int | None:
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float):
        return int(raw) if raw.is_integer() else None
    try:
        return int(raw)
    except (ValueError, TypeError, OverflowError):
        try:
            number = float(raw)
        except (ValueError, TypeError, OverflowError):
            return None
        return int(number) if number.is_integer() else None


def _coerce_float(raw: Any) -> float | None:
    try:
        return float(raw)
    except (ValueError, TypeError):
        return None


def _coerce_bool(raw: Any) -> bool | None:
    if isinstance(raw, bool):
        return raw
    normalized = str(raw).strip().lower()
    if normalized in ("true", "yes", "1"):
        return True
    if normalized in ("false", "no", "0"):
        return False
    return None


def _coerce_string_list(raw: Any) -> list[str] | None:
    if isinstance(raw, list):
        return [str(item) for item in raw]
    if isinstance(raw, str):
        return [part.strip() for part in raw.split(",") if part.strip()]
    return None


def coerce_value(raw: Any, annotation: Any) -> Any:
    """Coerce a raw value to an annotation, returning None on invalid input."""
    if raw is None:
        return None

    annotation, origin = _unwrap_optional(annotation)

    if annotation is str:
        return str(raw)
    if annotation is int:
        return _coerce_int(raw)
    if annotation is bool:
        return _coerce_bool(raw)
    if annotation is float:
        return _coerce_float(raw)

    if origin is list:
        args = get_args(annotation)
        if args and args[0] is str:
            return _coerce_string_list(raw)
        return None

    if isinstance(annotation, type) and issubclass(annotation, StrEnum):
        try:
            return annotation(raw)
        except (TypeError, ValueError):
            return None

    return str(raw)


def coerce_requirement_value(
    raw: Any,
    *,
    model: type[BaseModel] | None,
    target_field: str | None,
    target_type: str,
) -> Any:
    """Coerce one graph requirement through its model annotation or metadata."""
    if model is not None and target_field is not None:
        try:
            _, annotation = resolve_field_info(model, target_field)
        except (AttributeError, TypeError):
            pass
        else:
            return coerce_value(raw, annotation)

    fallback_annotations = {
        "string": str,
        "int": int,
        "bool": bool,
        "float": float,
        "cidr_list": list[str],
        "string_list": list[str],
    }
    annotation = fallback_annotations.get(target_type)
    if annotation is not None:
        return coerce_value(raw, annotation)

    if model is not None:
        enum_type = getattr(model, target_type, None)
        if enum_type is None:
            module = importlib.import_module(model.__module__)
            enum_type = getattr(module, target_type, None)
        if isinstance(enum_type, type):
            return coerce_value(raw, enum_type)
    return str(raw)


def validate_requirement_against_model(
    req: Any,
    model: type[BaseModel],
) -> list[str]:
    """Validate that a Requirement's target_field maps to an existing model field.

    Returns a list of error messages (empty if valid).
    """
    errors: list[str] = []
    if not req.target_field:
        return errors
    try:
        resolve_field_info(model, req.target_field)
    except (AttributeError, TypeError) as e:
        errors.append(f"Requirement '{req.key}': target_field '{req.target_field}' invalid: {e}")
    return errors
