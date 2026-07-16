"""Small YAML helpers shared by artifact writers."""

from __future__ import annotations

from io import StringIO
from pathlib import Path
from typing import Any

import ruamel.yaml
from ruamel.yaml.error import YAMLError

from .paths import resolve_bundle_file


def dump_yaml(data: Any, *, indent: bool = True) -> str:
    yaml = ruamel.yaml.YAML()
    yaml.default_flow_style = False
    if indent:
        yaml.indent(mapping=2, sequence=4, offset=2)
    buf = StringIO()
    yaml.dump(data, buf)
    return "\n".join(line.rstrip() for line in buf.getvalue().splitlines()) + "\n"


def write_yaml_artifact(path: Path, data: Any, header: str, *, indent: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(header + dump_yaml(data, indent=indent))


def load_yaml_mapping(path: Path) -> dict[str, Any]:
    """Load a required YAML mapping and reject other document shapes."""
    yaml = ruamel.yaml.YAML(typ="safe")
    try:
        data = yaml.load(path.read_text())
    except (OSError, UnicodeError, YAMLError) as exc:
        raise ValueError(f"{path}: invalid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected YAML mapping")
    return data


def read_yaml_mapping(path: Path) -> dict[str, Any]:
    """Load an optional YAML mapping, returning empty only when it is absent."""
    if not path.exists() and not path.is_symlink():
        return {}
    return load_yaml_mapping(path)


def load_bundle_yaml_mapping(
    bundle: Path,
    relative_name: str,
    *,
    required: bool = True,
) -> dict[str, Any]:
    """Load a bundle YAML mapping through the safe member resolver."""
    path = resolve_bundle_file(bundle, relative_name, required=required)
    return load_yaml_mapping(path) if path is not None else {}
