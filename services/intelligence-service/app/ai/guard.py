"""Guards around the model (init.md §8.3, Journey E4). Enforced by code, whatever the model or a retrieved
document says: injection-looking text is flagged and kept out of quotes, identifiers are redacted from
every answer, and structured outputs are validated with no extra fields allowed."""
import re

from pydantic import BaseModel, ConfigDict, Field

INJECTION = re.compile(r"ignore (all |any )?(previous|prior|above|system)|system (prompt|restrictions)|administrator mode|"
                       r"reveal (all|every)|disregard (the|your) (rules|instructions)|you are now", re.I)
IDENTIFIERS = [
    (re.compile(r"\b\d{12}\b"), "[number withheld]"),                         # UAN-like
    (re.compile(r"\b[6-9]\d{9}\b"), "[number withheld]"),                     # mobile-like
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b"), "[email withheld]"),
    (re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b"), "[PAN withheld]"),
    (re.compile(r"CONFIDENTIAL-MARKER-\d+"), "[withheld]"),
]
OTHER_MEMBER = re.compile(r"\b(all|every|other|another|someone else'?s?)\s+(members?|uans?|people|users|accounts)\b|"
                          r"\buan (of|for) \w+|\b\d{12}\b", re.I)


def looks_like_injection(text: str) -> bool:
    return bool(INJECTION.search(text))


def redact(text: str) -> str:
    for pattern, replacement in IDENTIFIERS:
        text = pattern.sub(replacement, text)
    return text


def asks_for_other_members(question: str) -> bool:
    return bool(OTHER_MEMBER.search(question))


class Citation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ref: str
    title: str
    excerpt: str
    verified: bool


class KnowledgeAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answer: str
    citations: list[Citation]
    uncertainty: str
    mode: str                         # llm | extractive | refused
    model_id: str
    advisory_only: bool = True
    ignored_instructions: list[str] = Field(default_factory=list)


class ClaimAnalysis(BaseModel):
    """The init.md §8.3 advisory schema. extra="forbid": an unexpected field (say an "action") is rejected."""
    model_config = ConfigDict(extra="forbid")
    analysis_type: str
    advisory_only: bool
    summary: str
    evidence_references: list[str]
    uncertainties: list[str]
    suggested_next_step: str
    model_id: str
    policy_version: str


class ModelSummary(BaseModel):
    """What the model is allowed to return for a claim analysis: prose only, no actions, no fields to act on."""
    model_config = ConfigDict(extra="forbid")
    summary: str = Field(max_length=800)
    uncertainties: list[str] = Field(default_factory=list, max_length=5)
