"""Citation enrichment loop.

Ported from AI-Scientist's `get_citation_aider_prompt()`.
Iteratively adds citations to a draft by:
1. LLM identifies where a citation is needed
2. Search Semantic Scholar for the paper
3. LLM selects the best match
4. Insert citation into draft
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from ideaclaw.sources.scholar import PaperResult, search_for_papers

logger = logging.getLogger(__name__)

__all__ = ["CitationManager", "CitationRound"]


@dataclass
class CitationRound:
    """Record of a single citation enrichment round."""

    round_num: int
    query: str
    description: str
    selected_papers: List[PaperResult]
    inserted: bool = False


CITATION_SYSTEM_MSG = """\
You are an ambitious AI PhD student looking to publish a paper that will contribute
significantly to the field. You have already written an initial draft and now you are
looking to add missing citations to related papers throughout the paper.

Focus on completing the existing write-up and do not add entirely new elements unless necessary.
Ensure every point in the paper is substantiated with sufficient evidence.
Feel free to add more cites to a particular point if there is only one or two references.
Aim to discuss a broad range of relevant papers, not just the most popular ones.
Make sure not to copy verbatim from prior literature to avoid plagiarism.

You will have {total_rounds} rounds to add references, but do not need to use them all.
DO NOT ADD A CITATION THAT ALREADY EXISTS!
"""

CITATION_IDENTIFY_PROMPT = '''\
Round {current_round}/{total_rounds}:

You have written this draft so far:

"""
{draft}
"""

Identify the most important citation that you still need to add, and the query to find the paper.

Respond in JSON format:
```json
{{
    "Description": "A precise description of where and how to add the citation",
    "Query": "The search query to find the paper"
}}
```

If no more citations are needed, respond with:
```json
{{
    "Description": "No more citations needed",
    "Query": ""
}}
```
'''

CITATION_SELECT_PROMPT = """\
Search has recovered the following articles:

{papers}

Select the most relevant paper(s) for this citation. Respond in JSON:
```json
{{
    "Selected": [0],
    "Description": "Updated description of how to insert the citation"
}}
```

Select [] if none are appropriate. Indices are 0-based.
"""


class CitationManager:
    """Manages iterative citation enrichment of a draft.

    In IDE-agent mode, the agent itself acts as the LLM.
    In API mode, calls are made via LLMClient.
    """

    def __init__(self, max_rounds: int = 20, engine: str = "semanticscholar"):
        self.max_rounds = max_rounds
        self.engine = engine
        self.rounds: List[CitationRound] = []

    def identify_missing_citation(
        self, draft: str, current_round: int
    ) -> Dict[str, str]:
        """Build the prompt for identifying a missing citation.

        Returns:
            Dict with system_prompt and user_prompt keys.
        """
        return {
            "system": CITATION_SYSTEM_MSG.format(total_rounds=self.max_rounds),
            "user": CITATION_IDENTIFY_PROMPT.format(
                current_round=current_round,
                total_rounds=self.max_rounds,
                draft=draft[:8000],  # Truncate to fit context
            ),
        }

    def search_and_format(self, query: str, limit: int = 10) -> Tuple[str, List[PaperResult]]:
        """Search for papers and format results for LLM selection.

        Returns:
            Tuple of (formatted_string, paper_results).
        """
        papers = search_for_papers(query, limit=limit, engine=self.engine)
        if not papers:
            return "No papers found.", []

        formatted = []
        for i, paper in enumerate(papers):
            formatted.append(
                f"{i}: {paper.title}. {paper.authors}. "
                f"{paper.venue}, {paper.year}.\n"
                f"   Abstract: {paper.abstract[:200]}..."
            )
        return "\n\n".join(formatted), papers

    def build_selection_prompt(self, papers_str: str) -> Dict[str, str]:
        """Build the prompt for selecting papers from search results."""
        return {
            "system": CITATION_SYSTEM_MSG.format(total_rounds=self.max_rounds),
            "user": CITATION_SELECT_PROMPT.format(papers=papers_str),
        }

    def insert_citation(
        self, draft: str, paper: PaperResult, description: str
    ) -> str:
        """Insert a citation into the draft based on the description.

        This is a simple heuristic insertion — the LLM should handle
        actual placement in IDE-agent mode.

        Args:
            draft: Current draft text.
            paper: Selected paper to cite.
            description: Description of where to insert.

        Returns:
            Updated draft with citation reference appended to sources.
        """
        # Add to sources section if it exists
        cite_text = f"- {paper.to_citation_string()}"
        if "## Sources" in draft or "## References" in draft:
            # Find the sources/references section and append
            for header in ["## Sources", "## References", "## 📚 Sources"]:
                if header in draft:
                    parts = draft.split(header, 1)
                    parts[1] = parts[1] + f"\n{cite_text}"
                    return header.join(parts)

        # Fallback: append at end
        return draft + f"\n\n## References\n{cite_text}\n"

    def run_citation_loop(
        self,
        draft: str,
        llm_call_fn=None,
    ) -> Tuple[str, List[CitationRound]]:
        """Run the full citation enrichment loop.

        Args:
            draft: The initial draft text.
            llm_call_fn: Optional function(system, user) -> str for LLM calls.
                If None, returns prompts for manual/agent execution.

        Returns:
            Tuple of (enriched_draft, citation_rounds).
        """
        if llm_call_fn is None:
            logger.info("No LLM function provided. Use identify_missing_citation() "
                       "and build_selection_prompt() for manual citation enrichment.")
            return draft, []

        enriched = draft
        for round_num in range(1, self.max_rounds + 1):
            # Step 1: Identify missing citation
            prompt = self.identify_missing_citation(enriched, round_num)
            response = llm_call_fn(prompt["system"], prompt["user"])

            # Parse response
            try:
                json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
                if json_match:
                    parsed = json.loads(json_match.group(1))
                else:
                    parsed = json.loads(response)
            except (json.JSONDecodeError, AttributeError):
                logger.warning(f"Round {round_num}: Failed to parse citation response")
                continue

            if not parsed.get("Query") or "no more" in parsed.get("Description", "").lower():
                logger.info(f"Citation loop converged after {round_num} rounds")
                break

            query = parsed["Query"]
            description = parsed["Description"]

            # Step 2: Search
            papers_str, papers = self.search_and_format(query)
            if not papers:
                continue

            # Step 3: Select
            sel_prompt = self.build_selection_prompt(papers_str)
            sel_response = llm_call_fn(sel_prompt["system"], sel_prompt["user"])

            try:
                json_match = re.search(r'```json\s*(.*?)\s*```', sel_response, re.DOTALL)
                if json_match:
                    sel_parsed = json.loads(json_match.group(1))
                else:
                    sel_parsed = json.loads(sel_response)
            except (json.JSONDecodeError, AttributeError):
                continue

            selected_indices = sel_parsed.get("Selected", [])
            if isinstance(selected_indices, str):
                selected_indices = json.loads(selected_indices) if selected_indices != "[]" else []

            selected_papers = []
            for idx in selected_indices:
                if 0 <= idx < len(papers):
                    selected_papers.append(papers[idx])

            # Step 4: Insert
            for paper in selected_papers:
                enriched = self.insert_citation(enriched, paper, description)

            self.rounds.append(
                CitationRound(
                    round_num=round_num,
                    query=query,
                    description=description,
                    selected_papers=selected_papers,
                    inserted=bool(selected_papers),
                )
            )

        return enriched, self.rounds
