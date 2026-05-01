"""Regression test: revise_docx must report a friendly error when DOCX is missing required parts."""
from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path

FIXTURE = Path(__file__).parent / "fixtures" / "docx_no_footnotes.docx"


def test_missing_footnotes_returns_friendly_error(tmp_path: Path):
    out = tmp_path / "out.docx"
    spec = tmp_path / "patch.json"
    # Need a non-empty patches list to get past load_patch_spec; the patch
    # itself never gets evaluated because load_xml_from_docx fails first on
    # the missing word/footnotes.xml part.
    spec.write_text(json.dumps({
        "footnote_sources": {},
        "patches": [{"label": "P1", "anchor": "placeholder body", "replacement": "x", "reason": "r"}],
    }))

    proc = subprocess.run(
        [
            sys.executable, "-m", "openrevise.revise.revise_docx",
            "--input-docx", str(FIXTURE),
            "--output-docx", str(out),
            "--patch-spec", str(spec),
        ],
        capture_output=True, text=True,
    )
    assert proc.returncode != 0, f"expected non-zero exit; got 0. stderr={proc.stderr}"
    assert "footnotes.xml" in proc.stderr, f"expected friendly error mentioning footnotes.xml; got stderr={proc.stderr}"
    # Friendly handler must avoid surfacing a raw Python traceback.
    assert "Traceback" not in proc.stderr, (
        f"expected friendly error, got raw traceback. stderr={proc.stderr}"
    )
    assert "KeyError" not in proc.stderr, (
        f"expected friendly error, got raw KeyError. stderr={proc.stderr}"
    )
