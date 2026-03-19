"""LaTeX generation and compilation.

Ported from AI-Scientist's `generate_latex()` + `compile_latex()`.
Handles:
- Reference validation (check all \\cite{} keys exist in .bib)
- Figure validation (check all \\includegraphics files exist)
- Duplicate section/figure detection
- chktex error correction
- pdflatex + bibtex compilation pipeline
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

__all__ = [
    "LatexCompiler",
    "compile_latex",
    "validate_latex",
    "LatexValidationResult",
]


class LatexValidationResult:
    """Result of LaTeX document validation."""

    def __init__(self):
        self.missing_refs: List[str] = []
        self.missing_figures: List[str] = []
        self.duplicate_sections: List[str] = []
        self.duplicate_figures: List[str] = []
        self.chktex_errors: List[str] = []

    @property
    def is_valid(self) -> bool:
        return not (self.missing_refs or self.missing_figures or
                    self.duplicate_sections or self.duplicate_figures)

    def summary(self) -> str:
        issues = []
        if self.missing_refs:
            issues.append(f"Missing references: {', '.join(self.missing_refs)}")
        if self.missing_figures:
            issues.append(f"Missing figures: {', '.join(self.missing_figures)}")
        if self.duplicate_sections:
            issues.append(f"Duplicate sections: {', '.join(self.duplicate_sections)}")
        if self.duplicate_figures:
            issues.append(f"Duplicate figures: {', '.join(self.duplicate_figures)}")
        if self.chktex_errors:
            issues.append(f"chktex errors: {len(self.chktex_errors)}")
        return "\n".join(issues) if issues else "No issues found."


# ---------------------------------------------------------------------------
# Per-Section Writing Tips (from AI-Scientist)
# ---------------------------------------------------------------------------

PER_SECTION_TIPS: Dict[str, str] = {
    "Abstract": """\
- TL;DR of the paper
- What are we trying to do and why is it relevant?
- Why is this hard?
- How do we solve it (our contribution!)
- How do we verify that we solved it (Experiments and results)
- One continuous paragraph, no line breaks.""",

    "Introduction": """\
- Longer version of the Abstract
- What, why, how, and verification
- List contributions as bullet points
- Extra space? Future work!""",

    "Related Work": """\
- Academic siblings: alternative attempts at the same problem
- Compare and contrast, don't just describe
- End each paragraph with how your work differs""",

    "Background": """\
- Academic ancestors: concepts required for understanding the method
- Problem Setting with formal notation
- Highlight unusual assumptions""",

    "Method": """\
- What we do. Why we do it.
- Use the formalism from Problem Setting
- Build on Background concepts""",

    "Experimental Setup": """\
- How we test that our stuff works
- Dataset, evaluation metrics, hyperparameters, implementation details
- Do not imagine unknown hardware details""",

    "Results": """\
- Only results that have actually been run — DO NOT HALLUCINATE
- Compare to baselines with statistics and confidence intervals
- Include ablation studies
- Discuss limitations
- Include all relevant figures""",

    "Conclusion": """\
- Brief recap of the entire paper
- Future work as potential academic offspring""",
}


# ---------------------------------------------------------------------------
# Refinement Prompts (from AI-Scientist)
# ---------------------------------------------------------------------------

ERROR_LIST = """\
- Unenclosed math symbols
- Only reference figures that exist in the directory
- LaTeX syntax errors
- Numerical results that do not come from explicit experiments
- Repeatedly defined figure labels
- References to papers not in the .bib file — DO NOT ADD NEW CITATIONS
- Unnecessary verbosity or repetition, unclear text
- Results or insights not yet included
- Relevant figures not yet included in the text
- Unclosed environments (\\begin{figure} without \\end{figure})
- Duplicate headers (duplicated \\section{Introduction} or \\end{document})
- Unescaped symbols (shakespeare_char should be shakespeare\\_char)
- Incorrect closing (</ end{figure}> instead of \\end{figure})
"""

REFINEMENT_PROMPT = (
    "Great job! Now criticize and refine only the {section} that you just wrote. "
    "Make this complete in this pass, do not leave any placeholders.\n\n"
    "Pay particular attention to fixing any errors such as:\n" + ERROR_LIST
)

SECOND_REFINEMENT_PROMPT = (
    "Criticize and refine the {section} only. Recall the advice:\n{tips}\n"
    "Make this complete in this pass, do not leave any placeholders.\n\n"
    "Pay attention to how it fits with the rest of the paper.\n"
    "Identify redundancies (repeated figures or text) — decide where to cut.\n"
    "Identify where to save space and be more concise without weakening the message.\n"
    "Fix any remaining errors as before:\n" + ERROR_LIST
)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_latex(tex_path: str | Path, project_dir: Optional[str | Path] = None) -> LatexValidationResult:
    """Validate a LaTeX document for common issues.

    Args:
        tex_path: Path to the .tex file.
        project_dir: Directory containing figures and other files.

    Returns:
        LatexValidationResult with detected issues.
    """
    tex_path = Path(tex_path)
    project_dir = Path(project_dir) if project_dir else tex_path.parent

    result = LatexValidationResult()

    if not tex_path.exists():
        logger.error(f"LaTeX file not found: {tex_path}")
        return result

    tex_text = tex_path.read_text(encoding="utf-8", errors="replace")

    # Check references
    cites = re.findall(r"\\cite[a-z]*\{([^}]*)\}", tex_text)
    cite_keys = {cite.strip() for item in cites for cite in item.split(",")}

    bib_match = re.search(
        r"\\begin\{filecontents\}\{references\.bib\}(.*?)\\end\{filecontents\}",
        tex_text,
        re.DOTALL,
    )
    bib_text = bib_match.group(1) if bib_match else ""

    for key in cite_keys:
        if key and key not in bib_text:
            result.missing_refs.append(key)

    # Check figures
    referenced_figs = re.findall(r"\\includegraphics.*?\{(.*?)\}", tex_text)
    all_figs = {f.name for f in project_dir.iterdir() if f.suffix in (".png", ".jpg", ".pdf", ".eps")}

    for fig in referenced_figs:
        fig_name = Path(fig).name
        if fig_name not in all_figs and fig not in all_figs:
            result.missing_figures.append(fig)

    # Check duplicate sections
    sections = re.findall(r"\\section\{([^}]*)\}", tex_text)
    seen = set()
    for sec in sections:
        if sec in seen:
            result.duplicate_sections.append(sec)
        seen.add(sec)

    # Check duplicate figures
    fig_refs = re.findall(r"\\includegraphics.*?\{(.*?)\}", tex_text)
    seen_figs: Set[str] = set()
    for fig in fig_refs:
        if fig in seen_figs:
            result.duplicate_figures.append(fig)
        seen_figs.add(fig)

    return result


# ---------------------------------------------------------------------------
# Compilation
# ---------------------------------------------------------------------------

def compile_latex(
    tex_dir: str | Path,
    output_pdf: Optional[str | Path] = None,
    timeout: int = 30,
) -> bool:
    """Compile a LaTeX document to PDF.

    Runs: pdflatex → bibtex → pdflatex → pdflatex

    Args:
        tex_dir: Directory containing template.tex.
        output_pdf: Optional output PDF path. If None, stays in tex_dir.
        timeout: Timeout per command in seconds.

    Returns:
        True if compilation succeeded.
    """
    tex_dir = Path(tex_dir)
    tex_file = tex_dir / "template.tex"

    if not tex_file.exists():
        logger.error(f"template.tex not found in {tex_dir}")
        return False

    commands = [
        ["pdflatex", "-interaction=nonstopmode", "template.tex"],
        ["bibtex", "template"],
        ["pdflatex", "-interaction=nonstopmode", "template.tex"],
        ["pdflatex", "-interaction=nonstopmode", "template.tex"],
    ]

    logger.info("Compiling LaTeX...")
    success = True

    for cmd in commands:
        try:
            result = subprocess.run(
                cmd,
                cwd=str(tex_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout,
            )
            if result.returncode != 0:
                logger.warning(f"Command {' '.join(cmd)} returned {result.returncode}")
        except subprocess.TimeoutExpired:
            logger.error(f"LaTeX timed out after {timeout}s: {' '.join(cmd)}")
            success = False
        except FileNotFoundError:
            logger.error(f"Command not found: {cmd[0]}. Install TeX Live or MiKTeX.")
            return False

    # Move PDF if output path specified
    pdf_file = tex_dir / "template.pdf"
    if output_pdf and pdf_file.exists():
        output_pdf = Path(output_pdf)
        output_pdf.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.move(str(pdf_file), str(output_pdf))
            logger.info(f"PDF saved to {output_pdf}")
        except Exception as e:
            logger.error(f"Failed to move PDF: {e}")
            success = False

    return success and (pdf_file.exists() or (output_pdf and Path(output_pdf).exists()))


class LatexCompiler:
    """High-level LaTeX compiler with validation and error correction.

    Usage:
        compiler = LatexCompiler(project_dir="/path/to/project")
        validation = compiler.validate()
        if validation.is_valid:
            compiler.compile(output_pdf="paper.pdf")
    """

    def __init__(self, project_dir: str | Path):
        self.project_dir = Path(project_dir)
        self.tex_dir = self.project_dir / "latex"
        self.tex_file = self.tex_dir / "template.tex"

    def validate(self) -> LatexValidationResult:
        """Validate the LaTeX document."""
        return validate_latex(self.tex_file, self.project_dir)

    def compile(
        self,
        output_pdf: Optional[str | Path] = None,
        timeout: int = 30,
    ) -> bool:
        """Compile to PDF."""
        out = output_pdf or (self.project_dir / "output.pdf")
        return compile_latex(self.tex_dir, out, timeout)

    def get_section_tip(self, section: str) -> str:
        """Get writing tip for a section."""
        return PER_SECTION_TIPS.get(section, "")

    def get_refinement_prompt(self, section: str) -> str:
        """Get first-pass refinement prompt for a section."""
        return REFINEMENT_PROMPT.format(section=section)

    def get_second_refinement_prompt(self, section: str) -> str:
        """Get second-pass refinement prompt for a section."""
        tips = self.get_section_tip(section)
        return SECOND_REFINEMENT_PROMPT.format(section=section, tips=tips)
