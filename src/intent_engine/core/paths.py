"""Portable path rules for registered artifact and fixture references."""

from __future__ import annotations

from pathlib import Path, PurePosixPath, PureWindowsPath


class BundleFileError(ValueError):
    """A bundle member is missing or unsafe to read."""

    def __init__(self, message: str, *, reason: str) -> None:
        super().__init__(message)
        self.reason = reason


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


def resolve_bundle_file(
    bundle: Path,
    relative_name: str,
    *,
    required: bool = True,
) -> Path | None:
    """Resolve a regular bundle file without following member symlinks."""
    path_error = relative_path_error(relative_name)
    if path_error:
        raise BundleFileError(
            f"Bundle file '{relative_name}' has an invalid path: {path_error}.",
            reason="invalid-path",
        )
    if bundle.is_symlink():
        raise BundleFileError(f"Bundle root is a symlink: {bundle}", reason="symlink")
    try:
        bundle_root = bundle.resolve(strict=True)
    except OSError as exc:
        raise BundleFileError(
            f"Bundle root is not readable: {bundle}: {exc}", reason="root"
        ) from exc
    if not bundle_root.is_dir():
        raise BundleFileError(f"Bundle root is not a directory: {bundle}", reason="root")

    candidate = bundle
    for part in PurePosixPath(relative_name).parts:
        candidate /= part
        if candidate.is_symlink():
            raise BundleFileError(
                f"Bundle file '{relative_name}' must not be a symlink or have symlink parents.",
                reason="symlink",
            )
    if not candidate.exists():
        if required:
            raise BundleFileError(
                f"Missing required bundle file: {relative_name}",
                reason="missing",
            )
        return None
    if not candidate.is_file():
        raise BundleFileError(
            f"Bundle file '{relative_name}' must be a regular file.",
            reason="not-file",
        )
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(bundle_root)
    except (OSError, ValueError) as exc:
        raise BundleFileError(
            f"Bundle file '{relative_name}' resolves outside the bundle.",
            reason="containment",
        ) from exc
    return resolved
