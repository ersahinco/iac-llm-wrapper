"""Typed objects shared by ingest, graph, analysis, and emit."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DecisionType = Literal["enum", "string", "string_list", "bool"]
FactOrigin = Literal["document", "default"]


class Gate(BaseModel):
    """A decision only applies when another decision holds a given value."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    decision: str
    equals: str


class Decision(BaseModel):
    """A question only a human can answer."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str
    label: str
    category: str
    type: DecisionType
    question: str
    options: list[str] = Field(default_factory=list)
    default: str | None = None
    hint: str | None = None
    gate: Gate | None = None
    requires: list[str] = Field(default_factory=list)


class Statement(BaseModel):
    """One prose line of the ingested document, with where it came from."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    text: str
    section: str
    line: int


class Document(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str
    sha256: str
    statements: list[Statement]


class Fact(BaseModel):
    """An answer to a decision, bound to its evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    decision_key: str
    value: str
    section: str
    line: int
    origin: FactOrigin = "document"
    statement_id: str | None = None


class Gap(BaseModel):
    """An applicable decision with no answer in the document."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    decision_key: str
    question: str
    category: str
    default: str | None = None
    blocks: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)


class Conflict(BaseModel):
    """A named, blocking input or policy finding."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str
    message: str
    decision_keys: list[str]
    evidence: list[str] = Field(default_factory=list)


class ArchitectureNode(BaseModel):
    """A sourced model proposal, never an accepted answer."""

    model_config = ConfigDict(extra="forbid")
    id: str
    label: Literal["System", "Candidate"]
    properties: dict[str, str]


class ArchitectureLink(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start_node_id: str
    end_node_id: str
    type: Literal["ABOUT", "CONNECTS_TO"]


class Architecture(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nodes: list[ArchitectureNode] = Field(default_factory=list)
    relationships: list[ArchitectureLink] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class Review(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    document: str
    sha256: str
    applicable: list[str]
    answered: list[str]
    gaps: list[Gap]
    conflicts: list[Conflict]
    facts: list[Fact] = Field(default_factory=list)
    architecture: Architecture = Field(default_factory=Architecture)
    organisation: Organisation | None = None
    assessments: list[Assessment] = Field(default_factory=list)
    integration_context: dict[str, object] = Field(default_factory=dict)

    @property
    def clean(self) -> bool:
        return not self.gaps and not self.conflicts


class Reference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    path: str
    kind: Literal["configuration", "context", "policy"]
    sha256: str = ""
    content: str = ""


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reference: str
    line: int = Field(ge=1)
    quote: str = Field(min_length=1)


class EstateSystem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    name: str
    lifecycle: Literal["existing", "planned"]
    evidence: Evidence


class Integration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    source: str
    target: str
    decision_keys: list[str] = Field(min_length=1)
    evidence: Evidence


class Policy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    decision_keys: list[str] = Field(min_length=1)
    evidence: Evidence


class Organisation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    references: list[Reference]
    systems: list[EstateSystem]
    integrations: list[Integration]
    questions: list[Decision]
    policies: list[Policy]


class Assessment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    policy_id: str
    status: Literal["passed", "warning", "conflict", "not-assessed"]
    message: str = Field(min_length=1)
    input_sha256: str = ""


Review.model_rebuild()
