"""Git helpers for explicit incremental design-doc compilation."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any


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


def git_changed_design_paths(base_ref: str, doc_root: Path) -> dict[str, Any]:
    """Return git-changed paths under doc_root, split into Markdown docs and skips."""
    doc_root = doc_root.resolve()
    repo_root = git_repo_root(doc_root)
    relative_doc_root = doc_root.relative_to(repo_root)
    proc = subprocess.run(
        [
            "git",
            "-C",
            str(repo_root),
            "diff",
            "-M",
            "--name-only",
            "--diff-filter=ACMRT",
            base_ref,
            "--",
            relative_doc_root.as_posix(),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        message = (proc.stderr or proc.stdout).strip()
        raise RuntimeError(f"git diff failed for {base_ref}: {message}")

    changed_documents: list[dict[str, str]] = []
    skipped_documents: list[dict[str, str]] = []
    for raw in proc.stdout.splitlines():
        if not raw.strip():
            continue
        repo_relative = Path(raw.strip())
        absolute = repo_root / repo_relative
        try:
            doc_relative = absolute.relative_to(doc_root)
        except ValueError:
            skipped_documents.append(
                {
                    "path": str(absolute),
                    "repoRelativePath": repo_relative.as_posix(),
                    "reason": "outside-doc-root",
                }
            )
            continue
        if absolute.suffix.lower() != ".md":
            skipped_documents.append(
                {
                    "path": str(absolute),
                    "repoRelativePath": repo_relative.as_posix(),
                    "reason": "not-markdown",
                }
            )
            continue
        changed_documents.append(
            {
                "path": str(absolute),
                "relativePath": doc_relative.as_posix(),
                "repoRelativePath": repo_relative.as_posix(),
            }
        )

    return {
        "repoRoot": str(repo_root),
        "docRoot": str(doc_root),
        "baseRef": base_ref,
        "changedDocuments": changed_documents,
        "skippedDocuments": skipped_documents,
    }


def git_show_text(repo_root: Path, base_ref: str, repo_relative_path: str) -> str | None:
    proc = subprocess.run(
        ["git", "-C", str(repo_root), "show", f"{base_ref}:{repo_relative_path}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return None
    return proc.stdout


def bundle_path_for_doc(root: Path, relative_doc_path: str) -> Path:
    relative = Path(relative_doc_path)
    return root / relative.with_suffix("")
