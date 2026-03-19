"""Peer review engine — single, ensemble, and meta-review.

Ported from AI-Scientist's `perform_review()`.
Supports:
- Single reviewer with multi-reflection
- Ensemble of N reviewers with score averaging
- Meta-reviewer aggregation
- Few-shot examples (optional)
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from ideaclaw.review.structured import (
    NEURIPS_REVIEW_FORM,
    REVIEW_FIELDS,
    REVIEWER_SYSTEM_PROMPT,
    REVIEWER_SYSTEM_PROMPT_STRICT,
    REVIEWER_REFLECTION_PROMPT,
    META_REVIEWER_SYSTEM_PROMPT,
)

logger = logging.getLogger(__name__)

__all__ = ["perform_review", "ReviewResult", "PeerReviewer"]


@dataclass
class ReviewResult:
    """Structured review output."""

    summary: str = ""
    strengths: List[str] = field(default_factory=list)
    weaknesses: List[str] = field(default_factory=list)
    originality: int = 0
    quality: int = 0
    clarity: int = 0
    significance: int = 0
    questions: List[str] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)
    ethical_concerns: bool = False
    soundness: int = 0
    presentation: int = 0
    contribution: int = 0
    overall: int = 0
    confidence: int = 0
    decision: str = ""
    thought: str = ""

    @classmethod
    def from_json(cls, data: Dict[str, Any]) -> "ReviewResult":
        """Create ReviewResult from parsed JSON."""
        return cls(
            summary=data.get("Summary", ""),
            strengths=data.get("Strengths", []),
            weaknesses=data.get("Weaknesses", []),
            originality=data.get("Originality", 0),
            quality=data.get("Quality", 0),
            clarity=data.get("Clarity", 0),
            significance=data.get("Significance", 0),
            questions=data.get("Questions", []),
            limitations=data.get("Limitations", []),
            ethical_concerns=data.get("Ethical Concerns", False),
            soundness=data.get("Soundness", 0),
            presentation=data.get("Presentation", 0),
            contribution=data.get("Contribution", 0),
            overall=data.get("Overall", 0),
            confidence=data.get("Confidence", 0),
            decision=data.get("Decision", ""),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "Summary": self.summary,
            "Strengths": self.strengths,
            "Weaknesses": self.weaknesses,
            "Originality": self.originality,
            "Quality": self.quality,
            "Clarity": self.clarity,
            "Significance": self.significance,
            "Questions": self.questions,
            "Limitations": self.limitations,
            "Ethical Concerns": self.ethical_concerns,
            "Soundness": self.soundness,
            "Presentation": self.presentation,
            "Contribution": self.contribution,
            "Overall": self.overall,
            "Confidence": self.confidence,
            "Decision": self.decision,
        }

    @property
    def is_accept(self) -> bool:
        return self.decision.lower() == "accept"

    @property
    def score_summary(self) -> str:
        """One-line score summary."""
        return (
            f"Overall={self.overall}/10, "
            f"Soundness={self.soundness}/4, "
            f"Originality={self.originality}/4, "
            f"Clarity={self.clarity}/4, "
            f"Significance={self.significance}/4, "
            f"Decision={self.decision}"
        )


def _extract_json(text: str) -> Optional[Dict]:
    """Extract JSON from LLM output (between ```json markers)."""
    match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    # Try parsing the whole text
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None


class PeerReviewer:
    """Full peer review engine with ensemble and reflection support."""

    def __init__(
        self,
        llm_call_fn: Optional[Callable] = None,
        system_prompt: str = REVIEWER_SYSTEM_PROMPT_STRICT,
        num_reflections: int = 5,
        num_ensemble: int = 1,
    ):
        """Initialize the reviewer.

        Args:
            llm_call_fn: Function(system, user) -> str for LLM calls.
                If None, builds prompts for manual/agent execution.
            system_prompt: System prompt for the reviewer.
            num_reflections: Number of reflection rounds per review.
            num_ensemble: Number of independent reviews for ensemble.
        """
        self.llm_call_fn = llm_call_fn
        self.system_prompt = system_prompt
        self.num_reflections = num_reflections
        self.num_ensemble = num_ensemble

    def build_review_prompt(self, text: str) -> Dict[str, str]:
        """Build the initial review prompt.

        Args:
            text: Paper/draft text to review.

        Returns:
            Dict with system and user prompt keys.
        """
        user_prompt = NEURIPS_REVIEW_FORM + f"\n\nHere is the paper you are asked to review:\n```\n{text}\n```"
        return {
            "system": self.system_prompt,
            "user": user_prompt,
        }

    def build_reflection_prompt(self, round_num: int) -> Dict[str, str]:
        """Build a reflection prompt for iterative review improvement."""
        return {
            "system": self.system_prompt,
            "user": REVIEWER_REFLECTION_PROMPT.format(
                current_round=round_num,
                num_reflections=self.num_reflections,
            ),
        }

    def review(self, text: str) -> ReviewResult:
        """Perform a full review with reflection.

        If ensemble > 1, runs multiple independent reviews and aggregates.

        Args:
            text: Paper/draft text to review.

        Returns:
            ReviewResult with scores and feedback.
        """
        if self.llm_call_fn is None:
            raise RuntimeError(
                "No LLM function provided. Use build_review_prompt() for manual review."
            )

        if self.num_ensemble > 1:
            return self._ensemble_review(text)
        return self._single_review(text)

    def _single_review(self, text: str) -> ReviewResult:
        """Run a single review with multi-reflection."""
        prompt = self.build_review_prompt(text)
        response = self.llm_call_fn(prompt["system"], prompt["user"])
        review_json = _extract_json(response)

        if review_json is None:
            logger.error("Failed to parse initial review")
            return ReviewResult()

        # Multi-reflection loop
        if self.num_reflections > 1:
            msg_context = response  # Keep context for reflection
            for j in range(1, self.num_reflections):
                ref_prompt = self.build_reflection_prompt(j + 1)
                ref_response = self.llm_call_fn(
                    ref_prompt["system"],
                    f"Previous review:\n{msg_context}\n\n{ref_prompt['user']}",
                )
                new_json = _extract_json(ref_response)
                if new_json is not None:
                    review_json = new_json
                    msg_context = ref_response

                if "I am done" in ref_response:
                    logger.info(f"Review converged after {j + 1} reflections")
                    break

        result = ReviewResult.from_json(review_json)
        # Extract thought if present
        thought_match = re.search(r'THOUGHT:\s*(.*?)(?:REVIEW JSON:|$)', response, re.DOTALL)
        if thought_match:
            result.thought = thought_match.group(1).strip()

        return result

    def _ensemble_review(self, text: str) -> ReviewResult:
        """Run multiple reviews and aggregate via meta-review."""
        reviews = []
        for i in range(self.num_ensemble):
            logger.info(f"Ensemble review {i + 1}/{self.num_ensemble}")
            review = self._single_review(text)
            if review.overall > 0:
                reviews.append(review)

        if not reviews:
            return ReviewResult()

        if len(reviews) == 1:
            return reviews[0]

        # Aggregate scores
        aggregated = self._aggregate_reviews(reviews)
        return aggregated

    def _aggregate_reviews(self, reviews: List[ReviewResult]) -> ReviewResult:
        """Aggregate multiple reviews by averaging scores and merging text."""
        if not reviews:
            return ReviewResult()

        # Average numerical scores
        score_fields = [
            ("originality", 1, 4),
            ("quality", 1, 4),
            ("clarity", 1, 4),
            ("significance", 1, 4),
            ("soundness", 1, 4),
            ("presentation", 1, 4),
            ("contribution", 1, 4),
            ("overall", 1, 10),
            ("confidence", 1, 5),
        ]

        result = ReviewResult()
        for field_name, lo, hi in score_fields:
            scores = [getattr(r, field_name) for r in reviews if lo <= getattr(r, field_name) <= hi]
            if scores:
                setattr(result, field_name, round(sum(scores) / len(scores)))

        # Merge text fields
        all_strengths = []
        all_weaknesses = []
        all_questions = []
        all_limitations = []
        for r in reviews:
            all_strengths.extend(r.strengths)
            all_weaknesses.extend(r.weaknesses)
            all_questions.extend(r.questions)
            all_limitations.extend(r.limitations)

        # Deduplicate (simple)
        result.strengths = list(dict.fromkeys(all_strengths))
        result.weaknesses = list(dict.fromkeys(all_weaknesses))
        result.questions = list(dict.fromkeys(all_questions))
        result.limitations = list(dict.fromkeys(all_limitations))

        # Summary from first review
        result.summary = reviews[0].summary

        # Decision by majority
        accept_votes = sum(1 for r in reviews if r.is_accept)
        result.decision = "Accept" if accept_votes > len(reviews) / 2 else "Reject"

        # Ethical concerns if any reviewer flagged
        result.ethical_concerns = any(r.ethical_concerns for r in reviews)

        return result


def perform_review(
    text: str,
    llm_call_fn: Optional[Callable] = None,
    num_reflections: int = 5,
    num_ensemble: int = 1,
    strict: bool = True,
) -> ReviewResult:
    """Convenience function to perform a full peer review.

    Args:
        text: Paper/draft text to review.
        llm_call_fn: Function(system, user) -> str for LLM calls.
        num_reflections: Number of reflection rounds.
        num_ensemble: Number of independent reviewers for ensemble.
        strict: If True, use strict reviewer prompt.

    Returns:
        ReviewResult with scores and feedback.
    """
    system_prompt = REVIEWER_SYSTEM_PROMPT_STRICT if strict else REVIEWER_SYSTEM_PROMPT
    reviewer = PeerReviewer(
        llm_call_fn=llm_call_fn,
        system_prompt=system_prompt,
        num_reflections=num_reflections,
        num_ensemble=num_ensemble,
    )
    return reviewer.review(text)
