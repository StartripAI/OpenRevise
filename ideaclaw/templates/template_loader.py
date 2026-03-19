"""Template loader for deliverable templates.

Loads templates, review forms, and section structures mapped to each
IdeaClaw profile via ``template_registry.json``.  This sits between the
profile system and the pack builder, providing the *deliverable skeleton*
that the pipeline fills in section-by-section.

Architecture position:
    Profile YAML → TemplateLoader → PackBuilder/Exporter
    (top layer)    (this module)    (bottom layer)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Default location relative to the OpenRevise root
_DEFAULT_TEMPLATE_DIR = Path(__file__).resolve().parents[2] / "deliverable_templates"


class TemplateLoader:
    """Load and resolve deliverable templates for any profile."""

    def __init__(self, template_dir: Optional[Path] = None):
        self.template_dir = Path(template_dir) if template_dir else _DEFAULT_TEMPLATE_DIR
        self._registry: Dict[str, Dict] = {}
        self._review_forms: Dict[str, Dict] = {}
        self._load_registry()
        self._load_review_forms()

    # ------------------------------------------------------------------
    # Registry loading
    # ------------------------------------------------------------------

    def _load_registry(self) -> None:
        """Load template_registry.json mapping profiles → templates."""
        registry_path = self.template_dir / "template_registry.json"
        if not registry_path.exists():
            logger.warning("template_registry.json not found at %s", registry_path)
            return

        with open(registry_path, encoding="utf-8") as f:
            data = json.load(f)

        # Flatten tier→profile into a single profile→config map
        for tier_key, profiles in data.items():
            if tier_key.startswith("_"):
                continue
            if isinstance(profiles, dict):
                for profile_id, config in profiles.items():
                    config = {**config, "_tier": tier_key}  # defensive copy
                    self._registry[profile_id] = config

        logger.info("Loaded %d profile→template mappings", len(self._registry))

    def _load_review_forms(self) -> None:
        """Load all review form JSONs."""
        forms_dir = self.template_dir / "review_forms"
        if not forms_dir.exists():
            return
        for fp in forms_dir.glob("*.json"):
            with open(fp, encoding="utf-8") as f:
                self._review_forms[fp.stem] = json.load(f)
        logger.info("Loaded %d review forms", len(self._review_forms))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def has_template(self, profile_id: str) -> bool:
        """Check if a deliverable template exists for the given profile."""
        return profile_id in self._registry

    def get_config(self, profile_id: str) -> Dict[str, Any]:
        """Get the template configuration for a profile.

        Returns dict with keys: template, format, review, _tier, etc.
        """
        return self._registry.get(profile_id, {})

    def get_template_path(self, profile_id: str) -> Optional[Path]:
        """Get the absolute path to the template directory for a profile."""
        cfg = self._registry.get(profile_id)
        if not cfg:
            return None
        tpl_rel = cfg.get("template", "")
        tpl_path = self.template_dir / tpl_rel
        return tpl_path if tpl_path.exists() else None

    def get_template_content(self, profile_id: str) -> Optional[str]:
        """Read the main template file content for a profile.

        Looks for template.tex, template.md, or template.fountain
        in the template directory.
        """
        tpl_path = self.get_template_path(profile_id)
        if not tpl_path:
            return None

        for ext in [".tex", ".md", ".fountain"]:
            candidate = tpl_path / f"template{ext}"
            if candidate.exists():
                return candidate.read_text(encoding="utf-8")

        # Fallback: try any .tex or .md file in the directory (skip subdirs)
        for fp in sorted(tpl_path.iterdir()):
            if fp.is_file() and fp.suffix in (".tex", ".md"):
                return fp.read_text(encoding="utf-8")

        return None

    def get_sections(self, profile_id: str) -> List[str]:
        """Get the list of section names for a profile's template."""
        tpl_path = self.get_template_path(profile_id)
        if not tpl_path:
            return []

        sections_dir = tpl_path / "sections"
        if sections_dir.exists():
            return sorted(
                fp.stem for fp in sections_dir.iterdir()
                if fp.suffix in (".tex", ".md")
            )

        # Parse sections from main template
        content = self.get_template_content(profile_id)
        if not content:
            return []

        sections = []
        for line in content.split("\n"):
            line = line.strip()
            if line.startswith("\\section{") or line.startswith("\\subsection{"):
                # Extract section name from LaTeX
                name = line.split("{", 1)[1].rsplit("}", 1)[0]
                sections.append(name)
            elif line.startswith("## "):
                # Extract from Markdown
                sections.append(line[3:].strip())
        return sections

    def get_section_content(self, profile_id: str, section_name: str) -> Optional[str]:
        """Get the template content for a specific section."""
        tpl_path = self.get_template_path(profile_id)
        if not tpl_path:
            return None

        sections_dir = tpl_path / "sections"
        if sections_dir.exists():
            for ext in (".tex", ".md"):
                fp = sections_dir / f"{section_name}{ext}"
                if fp.exists():
                    return fp.read_text(encoding="utf-8")
        return None

    def get_review_form(self, profile_id: str) -> Optional[Dict]:
        """Get the review form for the given profile.

        Resolves the review field from the registry to a loaded form.
        """
        cfg = self._registry.get(profile_id, {})
        review_key = cfg.get("review", "content")
        return self._review_forms.get(review_key)

    def get_format(self, profile_id: str) -> str:
        """Get the output format for a profile: 'latex', 'markdown', or 'fountain'."""
        cfg = self._registry.get(profile_id, {})
        return cfg.get("format", "markdown")

    def get_tier(self, profile_id: str) -> str:
        """Get the tier for a profile."""
        cfg = self._registry.get(profile_id, {})
        return cfg.get("_tier", "unknown")

    def get_prompt(self, profile_id: str) -> Optional[Dict]:
        """Get the LLM writing prompt/instructions for a profile's tier.

        Loads the tier-level prompt.json which contains section-by-section
        writing instructions for the LLM.
        """
        tier = self.get_tier(profile_id)
        if tier == "unknown":
            return None

        prompt_path = self.template_dir / tier / "prompt.json"
        if not prompt_path.exists():
            return None

        with open(prompt_path, encoding="utf-8") as f:
            return json.load(f)

    def list_profiles(self, tier: Optional[str] = None) -> List[str]:
        """List all profiles, optionally filtered by tier."""
        if tier:
            return [p for p, c in self._registry.items() if c.get("_tier") == tier]
        return list(self._registry.keys())

    def summary(self) -> Dict[str, int]:
        """Return a summary of profiles per tier."""
        from collections import Counter
        tiers = Counter(c.get("_tier", "unknown") for c in self._registry.values())
        return dict(tiers)
