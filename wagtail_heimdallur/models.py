"""Core data models for Wagtail-Heimdallur proofreading results."""

from dataclasses import dataclass, field
from typing import List
import json


@dataclass
class DiffAnnotation:
    """A single correction annotation with character positions.

    Attributes:
        orig_start_idx: Start index in the original text.
        orig_end_idx: End index in the original text.
        orig_string: The original substring being annotated.
        changed_start_idx: Start index in the corrected text.
        changed_end_idx: End index in the corrected text.
        changed_string: The corrected substring.
        change_type: Category of the change (e.g., "spelling", "grammar", "style").
    """

    orig_start_idx: int
    orig_end_idx: int
    orig_string: str
    changed_start_idx: int
    changed_end_idx: int
    changed_string: str
    change_type: str

    def to_dict(self) -> dict:
        """Serialize this annotation to a plain dictionary."""
        return {
            "orig_start_idx": self.orig_start_idx,
            "orig_end_idx": self.orig_end_idx,
            "orig_string": self.orig_string,
            "changed_start_idx": self.changed_start_idx,
            "changed_end_idx": self.changed_end_idx,
            "changed_string": self.changed_string,
            "change_type": self.change_type,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DiffAnnotation":
        """Deserialize a DiffAnnotation from a plain dictionary."""
        return cls(
            orig_start_idx=data["orig_start_idx"],
            orig_end_idx=data["orig_end_idx"],
            orig_string=data["orig_string"],
            changed_start_idx=data["changed_start_idx"],
            changed_end_idx=data["changed_end_idx"],
            changed_string=data["changed_string"],
            change_type=data["change_type"],
        )


@dataclass
class ProofreadingResult:
    """Complete proofreading result with original, corrected text and annotations.

    Attributes:
        original_text: The original text that was proofread.
        corrected_text: The corrected version of the text.
        annotations: List of DiffAnnotation objects describing individual changes.
    """

    original_text: str
    corrected_text: str
    annotations: List[DiffAnnotation] = field(default_factory=list)

    def to_json(self) -> str:
        """Serialize this result to a JSON string."""
        return json.dumps({
            "original_text": self.original_text,
            "corrected_text": self.corrected_text,
            "annotations": [a.to_dict() for a in self.annotations],
        })

    @classmethod
    def from_json(cls, json_str: str) -> "ProofreadingResult":
        """Deserialize a ProofreadingResult from a JSON string."""
        data = json.loads(json_str)
        return cls(
            original_text=data["original_text"],
            corrected_text=data["corrected_text"],
            annotations=[
                DiffAnnotation.from_dict(a) for a in data["annotations"]
            ],
        )
