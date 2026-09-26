"""Knowledge-graph capture of requirements and architecture decisions.

Ingest a document, hold requirements and decisions in Neo4j, surface gaps and
conflicts deterministically, then emit configuration for an existing AWS
accelerator. Deployment stays with the owner's pipeline.
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.2.0"
