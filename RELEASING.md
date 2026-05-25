## Releasing

Prerequisites: maintainers with PyPI trusted publishing access.

### Version bump

1. Update `version` in `pyproject.toml` following SemVer.
2. Update `CHANGELOG.md`: move Unreleased items to a new dated section.
3. Regenerate the lock file: `uv lock`
4. Open a pull request titled `release: vX.Y.Z`.
5. After CI passes, merge to `main`.

### Tag and publish

```bash
git checkout main
git pull
git tag vX.Y.Z
git push origin vX.Y.Z
```

The `Release` workflow will:

- build the package
- generate SLSA provenance attestation
- publish to PyPI via trusted publishing
- create a GitHub Release with auto-generated notes and build artifacts

### Supply chain artifacts

- `uv.lock` is committed to the repo for reproducible dependency resolution.
- CI generates a CycloneDX SBOM on every run (available as an artifact).
- Releases include SLSA provenance attestations for build integrity.

### Hotfix release

For urgent fixes on the latest release:

1. Branch from the release tag: `git checkout -b hotfix/vX.Y.Z+1 vX.Y.Z`
2. Apply fix, update version and changelog.
3. Regenerate lock file: `uv lock`
4. Tag `vX.Y.Z+1` and push.
