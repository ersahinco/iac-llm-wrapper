"""Model introspection utilities.

The Pydantic data model is the single source of truth. This module provides
tools to inspect models, resolve dotted field paths, derive target_type from
annotations, and coerce values generically.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, cast, get_args, get_origin

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


def derive_target_type(annotation: Any) -> str:
    """Derive a target_type string from a Python type annotation.

    Returns one of: 'string', 'int', 'bool', 'float', 'cidr_list',
    or the class name for enums / StrEnum.
    """
    origin = get_origin(annotation)
    if origin is not None:
        args = get_args(annotation)
        if type(None) in args:
            annotation = next(a for a in args if a is not type(None))
            origin = get_origin(annotation)

    if origin is list:
        args = get_args(annotation)
        if args and args[0] is str:
            return "cidr_list"
        return "list"

    if annotation is str:
        return "string"
    if annotation is int:
        return "int"
    if annotation is bool:
        return "bool"
    if annotation is float:
        return "float"

    if isinstance(annotation, type) and issubclass(annotation, StrEnum):
        return annotation.__name__
    if isinstance(annotation, type) and issubclass(annotation, str):
        return "string"
    if isinstance(annotation, type) and issubclass(annotation, int):
        return "int"
    if isinstance(annotation, type) and issubclass(annotation, bool):
        return "bool"

    return "string"


def coerce_value(raw: Any, annotation: Any) -> Any:
    """Coerce a raw value to match a Python type annotation.

    Handles str, int, bool, float, list[str], and StrEnum subclasses.
    Returns None if coercion fails.
    """
    if raw is None:
        return None

    origin = get_origin(annotation)
    if origin is not None:
        args = get_args(annotation)
        if type(None) in args:
            annotation = next(a for a in args if a is not type(None))
            origin = get_origin(annotation)

    if annotation is str:
        return str(raw)
    if annotation is int:
        try:
            return int(float(raw))
        except (ValueError, TypeError):
            return None
    if annotation is bool:
        if isinstance(raw, bool):
            return raw
        return str(raw).lower() in ("true", "yes", "1")
    if annotation is float:
        try:
            return float(raw)
        except (ValueError, TypeError):
            return None

    # list[str] / cidr_list
    if origin is list:
        args = get_args(annotation)
        if args and args[0] is str:
            if isinstance(raw, list):
                return [str(x) for x in raw]
            if isinstance(raw, str):
                return [c.strip() for c in raw.split(",") if c.strip()]
            return None
        return None

    # StrEnum
    if isinstance(annotation, type) and issubclass(annotation, StrEnum):
        try:
            return annotation(raw)
        except ValueError:
            return None

    # Fallback
    return str(raw)


def field_exists(model: type[BaseModel], dotted_path: str) -> bool:
    """Check whether a dotted path exists on a model."""
    try:
        resolve_field_info(model, dotted_path)
        return True
    except (AttributeError, TypeError):
        return False


def list_annotation_item_model(annotation: Any) -> type[BaseModel] | None:
    """If annotation is list[SomeModel], return SomeModel."""
    origin = get_origin(annotation)
    if origin is list:
        args = get_args(annotation)
        if args and isinstance(args[0], type) and issubclass(args[0], BaseModel):
            return args[0]
    return None


def discover_model_fields(
    model: type[BaseModel],
    prefix: str = "",
) -> dict[str, tuple[str, Any]]:
    """Discover all leaf fields on a model suitable for graph requirements.

    Returns a dict of key -> (dotted_path, annotation).
    Skips nested BaseModel fields (they are not leafs) and list[BaseModel].
    """
    result: dict[str, tuple[str, Any]] = {}
    for name, field_info in model.model_fields.items():
        annotation = field_info.annotation
        path = f"{prefix}{name}" if not prefix else f"{prefix}.{name}"

        origin = get_origin(annotation)
        args = get_args(annotation)

        if origin is not None and type(None) in args:
            annotation = next(a for a in args if a is not type(None))
            origin = get_origin(annotation)
            args = get_args(annotation)

        # Skip list[BaseModel] — handled separately
        if origin is list:
            item_type = args[0] if args else Any
            if isinstance(item_type, type):
                item_cls = cast(type[Any], item_type)
                try:
                    if issubclass(item_cls, BaseModel):
                        continue
                except TypeError:
                    pass

        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            result.update(discover_model_fields(annotation, path))
            continue

        key = path.replace(".", "_")
        result[key] = (path, annotation)

    return result


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
        _, annotation = resolve_field_info(model, req.target_field)
        derived = derive_target_type(annotation)
        if req.target_type and req.target_type != derived:
            # Allow explicit overrides, but warn
            pass
    except (AttributeError, TypeError) as e:
        errors.append(f"Requirement '{req.key}': target_field '{req.target_field}' invalid: {e}")
    return errors


def append_to_list_field(
    intent: BaseModel,
    dotted_path: str,
    item_data: Any,
) -> bool:
    """Append a model instance to a list[Model] field on an intent.

    Returns True if successful, False if the field is not a list[Model].
    """
    try:
        _, annotation = resolve_field_info(type(intent), dotted_path)
        item_model = list_annotation_item_model(annotation)
        if item_model is None or not isinstance(item_data, dict):
            return False
        instance = item_model(**item_data)
        # Navigate to the list and append
        parts = dotted_path.split(".")
        obj = intent
        for part in parts[:-1]:
            obj = getattr(obj, part)
        lst = getattr(obj, parts[-1])
        lst.append(instance)
        return True
    except Exception:
        return False


def merge_into_list_field(
    intent: BaseModel,
    dotted_path: str,
    item_data: dict[str, Any],
    dedupe_key: str = "name",
) -> bool:
    """Append or backfill a list[Model] field on an intent.

    If an existing item with the same `dedupe_key` exists, only fields explicitly
    provided by `item_data` are merged, and only when the current item did not
    explicitly set them or currently holds an empty value.
    """
    try:
        _, annotation = resolve_field_info(type(intent), dotted_path)
        item_model = list_annotation_item_model(annotation)
        if item_model is None:
            return False

        instance = item_model(**item_data)
        parts = dotted_path.split(".")
        obj = intent
        for part in parts[:-1]:
            obj = getattr(obj, part)
        lst = getattr(obj, parts[-1])

        if dedupe_key not in item_data:
            lst.append(instance)
            return True

        dedupe_value = item_data[dedupe_key]
        for idx, existing in enumerate(lst):
            if getattr(existing, dedupe_key, None) != dedupe_value:
                continue

            explicit_existing = set(getattr(existing, "model_fields_set", set()))
            updates: dict[str, Any] = {}
            for field_name in getattr(instance, "model_fields_set", set()):
                if field_name == dedupe_key:
                    continue
                current_value = getattr(existing, field_name, None)
                if field_name not in explicit_existing or current_value in (None, "", [], {}):
                    updates[field_name] = getattr(instance, field_name)

            if updates:
                lst[idx] = existing.model_copy(update=updates)
            return True

        lst.append(instance)
        return True
    except Exception:
        return False
