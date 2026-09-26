FROM ghcr.io/astral-sh/uv:0.11.8 AS uv
FROM openpolicyagent/opa:1.21.0-static AS opa
FROM python:3.12-slim

COPY --from=uv /uv /usr/local/bin/uv
COPY --from=opa /opa /usr/local/bin/opa
WORKDIR /opt/app
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src
RUN uv sync --locked --no-dev --no-editable --extra graphrag

ENV PATH="/opt/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
WORKDIR /workspace
ENTRYPOINT ["iac-llm-wrapper"]
CMD ["--help"]
