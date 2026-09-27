"""The curated corpus and retrieval (init.md §8.2).

Every paragraph carries its document's classification. `retrieve` drops paragraphs the caller may not see
BEFORE scoring, so an unauthorised paragraph can never reach a model context or an answer. Retrieval is a
small deterministic keyword ranking; no vector index over mixed-classification material exists."""
import math
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

CORPUS_DIR = Path(os.getenv("AI_CORPUS_DIR", "/srv/ai-corpus"))
OFFICE_ROLES = ("fo.", "zo.", "do.", "ho.caiu")
STOP = set(("a an and are as at be by can do does for from how i if in is it its me my of on or the this to was what when "
            "where which who why will with you your").split())


@dataclass(frozen=True)
class Paragraph:
    doc_id: str
    title: str
    version: str
    classification: str
    verified: bool
    number: int
    text: str

    @property
    def ref(self) -> str:
        return f"{self.doc_id} §{self.number}"


def _front_matter(raw: str) -> tuple[dict[str, str], str]:
    head, body = raw.split("---", 2)[1:]
    meta = {k.strip(): v.strip() for k, v in (line.split(":", 1) for line in head.strip().splitlines())}
    return meta, body


@lru_cache(maxsize=1)
def load() -> tuple[Paragraph, ...]:
    folder = CORPUS_DIR if CORPUS_DIR.exists() else Path(__file__).resolve().parents[4] / "config" / "ai-corpus"
    out = []
    for path in sorted(folder.glob("*.md")):
        if path.name == "README.md":
            continue
        meta, body = _front_matter(path.read_text(encoding="utf-8"))
        blocks = [b.strip() for b in re.split(r"\n\s*\n", body) if b.strip()]
        for n, text in enumerate(blocks, start=1):
            out.append(Paragraph(meta["doc_id"], meta["title"], meta["version"], meta["classification"],
                                 meta.get("verified", "").lower().startswith("checked"), n, text))
    return tuple(out)


def may_read(stakeholder: str, classification: str) -> bool:
    if classification == "public":
        return True
    if classification == "officer-restricted":
        return stakeholder.startswith(OFFICE_ROLES)
    return False                                     # confidential and anything unknown: never via the assistant


def tokens(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9₹]+", text.lower()) if w not in STOP and len(w) > 1]


def retrieve(question: str, stakeholder: str, limit: int = 4) -> list[Paragraph]:
    allowed = [p for p in load() if may_read(stakeholder, p.classification)]      # authorise first
    q = set(tokens(question))
    if not q or not allowed:
        return []
    df: dict[str, int] = {}
    for p in allowed:
        for w in set(tokens(p.text + " " + p.title)):
            df[w] = df.get(w, 0) + 1
    scored = []
    for p in allowed:
        words = tokens(p.text + " " + p.title)
        score = sum(words.count(w) * math.log(1 + len(allowed) / df[w]) for w in q if w in df)
        if score > 0:
            scored.append((score + (0.5 if p.verified else 0), p))
    return [p for _, p in sorted(scored, key=lambda s: (-s[0], s[1].ref))[:limit]]
