"""Git-driven incremental compile helper tests."""

from __future__ import annotations

import subprocess
from pathlib import Path

from intent_engine.core.git_incremental import git_changed_design_paths


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    return proc.stdout.strip()


def test_git_changed_design_paths_classifies_changed_markdown_docs(tmp_path: Path):
    repo = tmp_path / "repo"
    docs = repo / "docs"
    docs.mkdir(parents=True)
    (docs / "changed.md").write_text("before\n")
    (docs / "renamed.md").write_text("rename before\n")
    (docs / "deleted.md").write_text("delete me\n")
    (docs / "unchanged.md").write_text("same\n")
    (docs / "notes.txt").write_text("before\n")
    _git(repo, "init")
    _git(repo, "add", ".")
    _git(repo, "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "base")
    base_ref = _git(repo, "rev-parse", "HEAD")

    (docs / "changed.md").write_text("after\n")
    (docs / "added.md").write_text("new\n")
    _git(repo, "add", "docs/added.md")
    _git(repo, "mv", "docs/renamed.md", "docs/renamed-new.md")
    (docs / "deleted.md").unlink()
    (docs / "notes.txt").write_text("after\n")

    result = git_changed_design_paths(base_ref, docs)

    changed = {item["relativePath"] for item in result["changedDocuments"]}
    skipped = {item["repoRelativePath"]: item["reason"] for item in result["skippedDocuments"]}
    assert changed == {"added.md", "changed.md", "renamed-new.md"}
    assert skipped == {"docs/notes.txt": "not-markdown"}
    assert "deleted.md" not in changed
    assert "unchanged.md" not in changed
