"""Small YAML helpers shared by artifact writers."""

from __future__ import annotations

from io import StringIO
from pathlib import Path
from typing import Any

import ruamel.yaml


def dump_yaml(data: Any) -> str:
    yaml = ruamel.yaml.YAML()
    yaml.default_flow_style = False
    yaml.indent(mapping=2, sequence=4, offset=2)
    buf = StringIO()
    yaml.dump(data, buf)
    return "\n".join(line.rstrip() for line in buf.getvalue().splitlines()) + "\n"


def write_yaml_artifact(path: Path, data: Any, header: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(header + dump_yaml(data))
