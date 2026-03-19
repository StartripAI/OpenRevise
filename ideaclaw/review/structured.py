"""Structured review forms and prompts.

Ported from AI-Scientist's `perform_review.py` — NeurIPS review form
with 14 evaluation fields, scoring rubrics, and response format.
"""

from __future__ import annotations

__all__ = [
    "NEURIPS_REVIEW_FORM",
    "REVIEW_FIELDS",
    "REVIEWER_SYSTEM_PROMPT",
    "REVIEWER_SYSTEM_PROMPT_STRICT",
    "REVIEWER_SYSTEM_PROMPT_LENIENT",
    "TEMPLATE_INSTRUCTIONS",
    "REVIEWER_REFLECTION_PROMPT",
    "META_REVIEWER_SYSTEM_PROMPT",
]


# ---------------------------------------------------------------------------
# Review Fields Definition
# ---------------------------------------------------------------------------

REVIEW_FIELDS = {
    "Summary": {"type": "text", "description": "A summary of the paper content and its contributions"},
    "Strengths": {"type": "list", "description": "A list of strengths of the paper"},
    "Weaknesses": {"type": "list", "description": "A list of weaknesses of the paper"},
    "Originality": {"type": "score", "min": 1, "max": 4, "labels": ["low", "medium", "high", "very high"]},
    "Quality": {"type": "score", "min": 1, "max": 4, "labels": ["low", "medium", "high", "very high"]},
    "Clarity": {"type": "score", "min": 1, "max": 4, "labels": ["low", "medium", "high", "very high"]},
    "Significance": {"type": "score", "min": 1, "max": 4, "labels": ["low", "medium", "high", "very high"]},
    "Questions": {"type": "list", "description": "Clarifying questions for the authors"},
    "Limitations": {"type": "list", "description": "Limitations and potential negative societal impacts"},
    "Ethical Concerns": {"type": "bool", "description": "Whether there are ethical concerns"},
    "Soundness": {"type": "score", "min": 1, "max": 4, "labels": ["poor", "fair", "good", "excellent"]},
    "Presentation": {"type": "score", "min": 1, "max": 4, "labels": ["poor", "fair", "good", "excellent"]},
    "Contribution": {"type": "score", "min": 1, "max": 4, "labels": ["poor", "fair", "good", "excellent"]},
    "Overall": {"type": "score", "min": 1, "max": 10, "labels": [
        "very strong reject", "strong reject", "reject",
        "borderline reject", "borderline accept", "weak accept",
        "accept", "strong accept", "very strong accept", "award quality"
    ]},
    "Confidence": {"type": "score", "min": 1, "max": 5, "labels": [
        "low", "medium", "high", "very high", "absolute"
    ]},
    "Decision": {"type": "enum", "values": ["Accept", "Reject"]},
}


# ---------------------------------------------------------------------------
# System Prompts
# ---------------------------------------------------------------------------

REVIEWER_SYSTEM_PROMPT = (
    "You are an AI researcher who is reviewing a paper submitted to a prestigious ML venue. "
    "Be critical and cautious in your decision."
)

REVIEWER_SYSTEM_PROMPT_STRICT = (
    REVIEWER_SYSTEM_PROMPT
    + " If a paper is bad or you are unsure, give it bad scores and reject it."
)

REVIEWER_SYSTEM_PROMPT_LENIENT = (
    REVIEWER_SYSTEM_PROMPT
    + " If a paper is good or you are unsure, give it good scores and accept it."
)


# ---------------------------------------------------------------------------
# Response Format Instructions
# ---------------------------------------------------------------------------

TEMPLATE_INSTRUCTIONS = """
Respond in the following format:

THOUGHT:
<THOUGHT>

REVIEW JSON:
```json
<JSON>
```

In <THOUGHT>, first briefly discuss your intuitions and reasoning for the evaluation.
Detail your high-level arguments, necessary choices and desired outcomes of the review.
Do not make generic comments here, but be specific to your current paper.
Treat this as the note-taking phase of your review.

In <JSON>, provide the review in JSON format with the following fields in order:
- "Summary": A summary of the paper content and its contributions.
- "Strengths": A list of strengths of the paper.
- "Weaknesses": A list of weaknesses of the paper.
- "Originality": A rating from 1 to 4 (low, medium, high, very high).
- "Quality": A rating from 1 to 4 (low, medium, high, very high).
- "Clarity": A rating from 1 to 4 (low, medium, high, very high).
- "Significance": A rating from 1 to 4 (low, medium, high, very high).
- "Questions": A set of clarifying questions to be answered by the paper authors.
- "Limitations": A set of limitations and potential negative societal impacts.
- "Ethical Concerns": A boolean indicating whether there are ethical concerns.
- "Soundness": A rating from 1 to 4 (poor, fair, good, excellent).
- "Presentation": A rating from 1 to 4 (poor, fair, good, excellent).
- "Contribution": A rating from 1 to 4 (poor, fair, good, excellent).
- "Overall": A rating from 1 to 10 (very strong reject to award quality).
- "Confidence": A rating from 1 to 5 (low, medium, high, very high, absolute).
- "Decision": Either "Accept" or "Reject" only.

This JSON will be automatically parsed, so ensure the format is precise.
"""


# ---------------------------------------------------------------------------
# Full NeurIPS Review Form
# ---------------------------------------------------------------------------

NEURIPS_REVIEW_FORM = """\
Below is a description of the questions you will be asked on the review form for each
paper and some guidelines on what to consider when answering these questions.

1. Summary: Briefly summarize the paper and its contributions. This is not the place
   to critique the paper; the authors should generally agree with a well-written summary.

2. Strengths and Weaknesses: Provide a thorough assessment touching on:
   - Originality: Are the tasks or methods new? Novel combination of techniques?
   - Quality: Is the submission technically sound? Claims well supported?
   - Clarity: Is the submission clearly written and well organized?
   - Significance: Are the results important? Will others build on them?

3. Questions: List clarifying questions and suggestions for the authors.

4. Limitations: Have the authors adequately addressed limitations and potential
   negative societal impact?

5. Soundness (1-4): poor, fair, good, excellent

6. Presentation (1-4): poor, fair, good, excellent

7. Contribution (1-4): poor, fair, good, excellent

8. Overall (1-10):
   10: Award quality
   9: Very Strong Accept
   8: Strong Accept
   7: Accept
   6: Weak Accept
   5: Borderline accept
   4: Borderline reject
   3: Reject
   2: Strong Reject
   1: Very Strong Reject

9. Confidence (1-5):
   5: Absolutely certain, very familiar with related work
   4: Confident but not absolutely certain
   3: Fairly confident
   2: Willing to defend but likely missed parts
   1: Educated guess
""" + TEMPLATE_INSTRUCTIONS


# ---------------------------------------------------------------------------
# Reflection & Meta-Review Prompts
# ---------------------------------------------------------------------------

REVIEWER_REFLECTION_PROMPT = """\
Round {current_round}/{num_reflections}.
In your thoughts, first carefully consider the accuracy and soundness of the review
you just created. Include any other factors important in evaluating the paper.
Ensure the review is clear and concise, and the JSON is in the correct format.

In the next attempt, try to refine and improve your review.
Stick to the spirit of the original review unless there are glaring issues.

Respond in the same format as before:
THOUGHT:
<THOUGHT>

REVIEW JSON:
```json
<JSON>
```

If there is nothing to improve, repeat the previous JSON EXACTLY after the thought
and include "I am done" at the end of the thoughts but before the JSON.
ONLY INCLUDE "I am done" IF YOU ARE MAKING NO MORE CHANGES.
"""

META_REVIEWER_SYSTEM_PROMPT = """\
You are an Area Chair at a machine learning conference.
You are in charge of meta-reviewing a paper that was reviewed by {reviewer_count} reviewers.
Your job is to aggregate the reviews into a single meta-review in the same format.
Be critical and cautious in your decision, find consensus, and respect the opinion
of all the reviewers.
"""
