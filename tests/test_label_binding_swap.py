"""Regression test: SOP §Q15 — patch with swapped ITT/mITT must be blocked by the gate."""
from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path


def test_swapped_itt_mitt_blocks(tmp_path: Path):
    spec = tmp_path / "patch.json"
    src = tmp_path / "src.txt"

    # Patch claims ITT median 18 vs 12 HR=0.6, mITT 22 vs 14 HR=0.55.
    # Source places ITT with 22 vs 14 HR=0.55 (so the patch SWAPPED them).
    spec.write_text(json.dumps({
        "footnote_sources": {"src_demo": "Source: demo source"},
        "required_sources": {
            "src_demo": {
                "type": "local_txt",
                "path": str(src),
            }
        },
        "patches": [
            {
                "label": "Q15",
                "anchor": "opioid use (ITT)",
                "replacement": (
                    "opioid use (ITT) summary. "
                    "ITT: median 18 vs 12 HR 0.60 p 0.001 [[fn:src_demo]]; "
                    "mITT: median 22 vs 14 HR 0.55 p 0.001 [[fn:src_demo]]."
                ),
            }
        ],
    }))
    # Source uses "median A B" format (no "vs"); regex requires median prefix.
    # Source binds ITT -> (22, 14, HR 0.55, p 0.001); mITT -> (18, 12, HR 0.60, p 0.001).
    # Patch swapped them.
    src.write_text(
        "opioid use (ITT) summary. "
        "ITT analysis: median 22.0 14.0 HR 0.55 p 0.001. "
        "mITT analysis: median 18.0 12.0 HR 0.60 p 0.001."
    )
    out = tmp_path / "label_check_report.json"
    proc = subprocess.run(
        [
            sys.executable, "-m", "openrevise.gates.check_label_value_consistency",
            "--patch-spec", str(spec),
            "--source-config", str(spec),
            "--output-json", str(out),
        ],
        capture_output=True, text=True,
    )
    # Module must exist and run; "No module named ..." would mean the gate isn't ported.
    assert "No module named" not in proc.stderr, (
        f"gate module missing: {proc.stderr}"
    )
    assert proc.returncode != 0, f"expected non-zero exit when labels are swapped; stderr={proc.stderr}"
    assert out.exists(), f"gate must emit a report; stdout={proc.stdout}; stderr={proc.stderr}"
    report = out.read_text()
    assert "swapped_label_binding" in report or "swap" in report.lower(), (
        f"expected report to mention swapped binding; got {report[:500]}"
    )
