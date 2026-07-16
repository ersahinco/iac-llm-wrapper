"""Git-driven incremental compile helper tests."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from intent_engine.core.git_incremental import (
    bundle_path_for_doc,
    git_changed_design_paths,
    git_resolve_commit,
    git_show_text,
)


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
    assert result["baseRef"] == base_ref
    assert result["resolvedBaseCommit"] == base_ref


def test_git_ref_is_resolved_once_to_a_commit_for_diff_and_show(tmp_path: Path):
    repo = tmp_path / "repo"
    docs = repo / "docs"
    docs.mkdir(parents=True)
    tracked = docs / "service.md"
    tracked.write_text("before\n")
    _git(repo, "init")
    _git(repo, "add", ".")
    _git(repo, "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "base")
    commit = _git(repo, "rev-parse", "HEAD")
    branch = _git(repo, "branch", "--show-current")
    tracked.write_text("after\n")

    assert git_resolve_commit(repo, commit) == commit
    assert git_resolve_commit(repo, branch) == commit
    result = git_changed_design_paths(branch, docs)
    assert result["resolvedBaseCommit"] == commit
    assert git_show_text(repo, commit, "docs/service.md") == "before\n"


@pytest.mark.parametrize("base_ref", ["does-not-exist", "--help", "--output=/tmp/ref"])
def test_git_ref_must_resolve_to_a_commit(tmp_path: Path, base_ref: str):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")

    with pytest.raises(RuntimeError, match="git ref is not a commit"):
        git_resolve_commit(repo, base_ref)


def test_git_changed_paths_are_nul_delimited(tmp_path: Path):
    repo = tmp_path / "repo"
    docs = repo / "docs"
    docs.mkdir(parents=True)
    (docs / "base.md").write_text("base\n")
    _git(repo, "init")
    _git(repo, "add", ".")
    _git(repo, "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "base")
    base_ref = _git(repo, "rev-parse", "HEAD")
    unusual = docs / "line\nbreak.md"
    unusual.write_text("new\n")
    _git(repo, "add", "docs/line\nbreak.md")

    result = git_changed_design_paths(base_ref, docs)

    assert [item["relativePath"] for item in result["changedDocuments"]] == ["line\nbreak.md"]


def test_git_rejects_non_portable_changed_path(tmp_path: Path):
    repo = tmp_path / "repo"
    docs = repo / "docs"
    docs.mkdir(parents=True)
    (docs / "base.md").write_text("base\n")
    _git(repo, "init")
    _git(repo, "add", ".")
    _git(repo, "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "base")
    base_ref = _git(repo, "rev-parse", "HEAD")
    (docs / "bad\\name.md").write_text("new\n")
    _git(repo, "add", "docs/bad\\name.md")

    with pytest.raises(RuntimeError, match="git returned unsafe path"):
        git_changed_design_paths(base_ref, docs)


@pytest.mark.parametrize(
    "relative_path",
    ["../escape.md", "/tmp/escape.md", "nested\\escape.md", "./escape.md", "notes.txt"],
)
def test_bundle_path_rejects_unsafe_or_non_markdown_path(tmp_path: Path, relative_path: str):
    with pytest.raises(ValueError):
        bundle_path_for_doc(tmp_path, relative_path)


def test_bundle_path_preserves_nested_document_mapping(tmp_path: Path):
    assert bundle_path_for_doc(tmp_path, "team/service.md") == tmp_path / "team" / "service"
