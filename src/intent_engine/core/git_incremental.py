"""Git helpers for explicit incremental design-doc compilation."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any

from .paths import relative_path_error

_COMMIT_RE = re.compile(r"[0-9a-f]{40,64}")


def git_repo_root(path: Path) -> Path:
    proc = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        message = (proc.stderr or proc.stdout).strip()
        raise RuntimeError(f"not inside a git repository: {path}. {message}")
    return Path(proc.stdout.strip()).resolve()


def git_resolve_commit(repo_root: Path, base_ref: str) -> str:
    """Resolve a user-supplied ref once and require a commit object."""
    proc = subprocess.run(
        [
            "git",
            "-C",
            str(repo_root),
            "rev-parse",
            "--verify",
            "--end-of-options",
            f"{base_ref}^{{commit}}",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    commit = proc.stdout.strip()
    if proc.returncode != 0 or _COMMIT_RE.fullmatch(commit) is None:
        message = (proc.stderr or proc.stdout).strip()
        raise RuntimeError(f"git ref is not a commit: {base_ref}. {message}")
    return commit


def git_changed_design_paths(base_ref: str, doc_root: Path) -> dict[str, Any]:
    """Return git-changed paths under doc_root, split into Markdown docs and skips."""
    doc_root = doc_root.resolve(strict=True)
    repo_root = git_repo_root(doc_root)
    try:
        relative_doc_root = doc_root.relative_to(repo_root)
    except ValueError as exc:
        raise RuntimeError(f"document root is outside the git repository: {doc_root}") from exc
    resolved_base = git_resolve_commit(repo_root, base_ref)
    proc = subprocess.run(
        [
            "git",
            "-C",
            str(repo_root),
            "diff",
            "-M",
            "--name-only",
            "-z",
            "--diff-filter=ACMRT",
            resolved_base,
            "--",
            relative_doc_root.as_posix(),
        ],
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        message = (proc.stderr or proc.stdout).decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"git diff failed for {base_ref}: {message}")

    changed_documents: list[dict[str, str]] = []
    skipped_documents: list[dict[str, str]] = []
    for raw in proc.stdout.split(b"\0"):
        if not raw:
            continue
        try:
            repo_relative_text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise RuntimeError("git returned a path that is not valid UTF-8") from exc
        path_error = relative_path_error(repo_relative_text)
        if path_error:
            raise RuntimeError(f"git returned unsafe path {repo_relative_text!r}: {path_error}")
        repo_relative = PurePosixPath(repo_relative_text)
        absolute = (repo_root / Path(*repo_relative.parts)).resolve()
        try:
            absolute.relative_to(repo_root)
            doc_relative = absolute.relative_to(doc_root)
        except ValueError as exc:
            raise RuntimeError(
                f"git path escapes the document root: {repo_relative_text!r}"
            ) from exc
        if absolute.suffix.lower() != ".md":
            skipped_documents.append(
                {
                    "path": str(absolute),
                    "repoRelativePath": repo_relative_text,
                    "reason": "not-markdown",
                }
            )
            continue
        changed_documents.append(
            {
                "path": str(absolute),
                "relativePath": doc_relative.as_posix(),
                "repoRelativePath": repo_relative_text,
            }
        )

    return {
        "repoRoot": str(repo_root),
        "docRoot": str(doc_root),
        "baseRef": base_ref,
        "resolvedBaseCommit": resolved_base,
        "changedDocuments": changed_documents,
        "skippedDocuments": skipped_documents,
    }


def git_show_text(repo_root: Path, base_commit: str, repo_relative_path: str) -> str | None:
    if _COMMIT_RE.fullmatch(base_commit) is None:
        raise ValueError("base commit must be a full hexadecimal commit ID")
    path_error = relative_path_error(repo_relative_path)
    if path_error:
        raise ValueError(f"invalid git path: {path_error}")
    proc = subprocess.run(
        ["git", "-C", str(repo_root), "show", f"{base_commit}:{repo_relative_path}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return None
    return proc.stdout


def bundle_path_for_doc(root: Path, relative_doc_path: str) -> Path:
    path_error = relative_path_error(relative_doc_path)
    if path_error:
        raise ValueError(f"invalid document path: {path_error}")
    relative = PurePosixPath(relative_doc_path)
    if relative.suffix.lower() != ".md":
        raise ValueError("document path must have a .md suffix")
    candidate = root / Path(*relative.with_suffix("").parts)
    try:
        candidate.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError("document bundle path escapes the bundle root") from exc
    return candidate
