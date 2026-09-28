"""Write a new bundle without replacing any existing destination."""

from pathlib import Path


class EmitBlocked(Exception):
    """Inputs or output destinations are not safe to emit."""


def write_bundle(directory: Path, documents: dict[str, str]) -> list[Path]:
    paths = [directory / name for name in documents]
    for path in paths:
        if path.exists() or path.is_symlink():
            raise EmitBlocked(f"{path}: already exists; use a fresh output directory")
    written: list[Path] = []
    try:
        directory.mkdir(parents=True, exist_ok=True)
        for path, content in zip(paths, documents.values(), strict=True):
            # Exclusive creation also protects against a collision after preflight.
            with path.open("x", encoding="utf-8") as handle:
                written.append(path)
                handle.write(content)
    except OSError as exc:
        for path in written:
            path.unlink()
        raise EmitBlocked(f"could not write bundle: {exc}") from exc
    return written
