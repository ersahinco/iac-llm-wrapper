"""Portable path rules for registered artifact and fixture references."""

from __future__ import annotations

from pathlib import PurePosixPath, PureWindowsPath


def relative_path_error(value: str) -> str | None:
    """Return why a path is unsafe, or None for a portable relative path."""
    if not value:
        return "path must not be empty"
    if "\x00" in value:
        return "path must not contain a null byte"
    if "\\" in value:
        return "path must use forward slashes"
    if PurePosixPath(value).is_absolute() or PureWindowsPath(value).drive:
        return "path must be relative"
    if any(part in {"", ".", ".."} for part in value.split("/")):
        return "path must not contain empty, dot, or parent segments"
    return None
