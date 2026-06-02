# Developer Visuals

Use this workflow to inspect the project without adding a dashboard or service.
The generated artifacts are local development outputs under ignored
`tests/results/`.

## Generate Views

```bash
uv run python scripts/render-dev-views.py
```

Open:

- `tests/results/dev-views/index.html` for the generated index.
- `tests/results/dev-views/graphs/*-requirement-graph.mmd` for requirement
  graph Mermaid diagrams.
- `tests/results/dev-views/models/*-intent-model.mmd` for Pydantic intent model
  Mermaid class diagrams.
- `tests/results/dev-views/code/module-dependencies.mmd` for package dependency
  shape.
- `tests/results/dev-views/results/*.md` for local golden journey and model
  benchmark summaries.

## Editor Setup

VS Code should offer the recommended extensions from `.vscode/extensions.json`.
The important ones are Python/Pylance, Ruff, mypy, YAML, TOML, Dev Containers,
and Mermaid preview.

## Devcontainer

Open the repo in the included devcontainer to get Python, uv, AWS CLI, Node,
Graphviz, jq, pre-commit, and the same VS Code extensions. The devcontainer
mounts `~/.aws` into the container so Bedrock runs use the normal AWS SSO/CLI
session without storing credentials in the repo.

The devcontainer runs this after creation:

```bash
uv sync --extra dev
uv run pre-commit install
uv run python scripts/render-dev-views.py
```

## Existing Product Review Page

For generated handoff bundles, the most useful human-facing visual is still:

```bash
uv run python -m intent_engine review html \
  --input tests/results/golden-bedrock-nova-2-lite/ready \
  --output tests/results/golden-bedrock-nova-2-lite/ready/handoff-review.html
```

That page shows readiness, contracts, blockers, model conformance, raw LLM
coverage, graph exports, trace summary, and benchmark links in one static file.
