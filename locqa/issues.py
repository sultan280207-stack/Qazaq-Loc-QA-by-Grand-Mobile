from __future__ import annotations

from dataclasses import dataclass, asdict, field

ISSUE_TYPES = [
    "untranslated", "same_as_source", "placeholder_mismatch", "plural_mismatch",
    "glossary_violation", "length_overflow", "machine_translation_suspect",
    "inconsistent_term", "suffix_harmony", "orthography", "wrong_language",
]
SEVERITIES = ["high", "medium", "low"]


@dataclass
class Issue:
    key: str
    issue_type: str
    severity: str
    source: str | None
    target: str | None
    evidence: str
    suggestion: str | None = None
    confidence: float = 0.5
    reviewed_by_human: bool = False
    line: int | None = None
    detector: str = ""
    origin: str = "auto"          # auto | review
    extra: dict = field(default_factory=dict, repr=False)

    def __post_init__(self):
        assert self.issue_type in ISSUE_TYPES, self.issue_type
        assert self.severity in SEVERITIES, self.severity
        self.confidence = round(max(0.0, min(1.0, float(self.confidence))), 2)

    def to_json(self) -> dict:
        d = {
            "key": self.key, "issue_type": self.issue_type, "severity": self.severity,
            "source": self.source, "target": self.target, "evidence": self.evidence,
            "suggestion": self.suggestion, "confidence": self.confidence,
            "reviewed_by_human": self.reviewed_by_human,
            "line": self.line, "detector": self.detector, "origin": self.origin,
        }
        return d

    @property
    def ident(self) -> tuple[str, str]:
        return (self.key, self.issue_type)
