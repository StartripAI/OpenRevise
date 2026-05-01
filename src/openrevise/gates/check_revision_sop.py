#!/usr/bin/env python3
"""
SOP-level gate for revision candidates.

This script classifies claim-level revision proposals into:
- PASS_AUTO_REVISE
- NEEDS_MANUAL_REVIEW
- BLOCKED

It is designed to be used after source gate, but can also run standalone.
"""

from __future__ import annotations

import argparse
import csv
import difflib
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Sequence


MATERIAL_CHANGE_INTENTS = {
    "data_metric_update",
    "threshold_update",
    "endpoint_definition_change",
    "regulatory_conclusion_update",
    "risk_language_update",
    "recommendation_grade_update",
    "definition_change",
}

RISK_TERMS = {"risk", "toxicity", "adverse", "safety", "warning", "严重", "风险", "毒性", "不良"}
REGULATORY_TERMS = {"fda", "nmpa", "ema", "approval", "approved", "认定", "批准", "监管"}
RECOMMENDATION_TERMS = {"grade", "level", "recommend", "优先推荐", "证据级别", "推荐级别"}


@dataclass(frozen=True)
class SourceState:
    source_id: str
    ok: bool
    detail: str
    evidence_excerpt: str


@dataclass(frozen=True)
class ClaimResult:
    claim_id: str
    gate_status: str
    confidence: str
    material_gate_pass: bool
    required_sources_passed: bool
    double_check_passed: bool
    convergence: str
    blocking_reason: str
    original_sentence: str
    proposed_revision: str
    change_intent: str
    source_refs: str
    source_locations: str
    evidence_excerpt: str
    reason: str


def _maybe_reexec_runtime_python() -> None:
    if os.environ.get("REVISE_NO_REEXEC") == "1":
        return
    repo_root = Path(__file__).resolve().parents[3]
    override = os.environ.get("REVISE_RUNTIME_PYTHON", "").strip()
    preferred = Path(override) if override else (repo_root / ".venv311" / "bin" / "python")
    if not preferred.exists():
        return
    try:
        current = Path(sys.executable).resolve()
        target = preferred.resolve()
    except OSError:
        return
    if current == target:
        return
    os.environ["REVISE_NO_REEXEC"] = "1"
    os.execv(str(preferred), [str(preferred), str(Path(__file__).resolve()), *sys.argv[1:]])


def _as_list(value: object) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x) for x in value if str(x).strip()]
    return [str(value)]


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _numeric_tokens(text: str) -> List[str]:
    return re.findall(r"\d+(?:\.\d+)?%?", text or "")


def _token_set(text: str) -> set[str]:
    normalized = _normalize_text(text)
    if not normalized:
        return set()
    return set(re.findall(r"[a-zA-Z0-9\u4e00-\u9fff]+", normalized))


def _jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    set_a = set(a)
    set_b = set(b)
    if not set_a and not set_b:
        return 1.0
    union = set_a | set_b
    if not union:
        return 1.0
    return len(set_a & set_b) / len(union)


def _present_terms(text: str, terms: set[str]) -> set[str]:
    low = _normalize_text(text)
    return {term for term in terms if term in low}


def _has_term_presence_delta(original: str, proposed: str, terms: set[str]) -> bool:
    return _present_terms(original, terms) != _present_terms(proposed, terms)


def _is_material_update(
    *,
    original_sentence: str,
    proposed_revision: str,
    change_intent: str,
) -> tuple[bool, str]:
    original = _normalize_text(original_sentence)
    proposed = _normalize_text(proposed_revision)
    if not proposed:
        return False, "missing_proposed_revision"
    if original == proposed:
        return False, "cosmetic_rewrite_blocked"

    intent = (change_intent or "").strip().lower()
    similarity = _jaccard(_token_set(original_sentence), _token_set(proposed_revision))
    char_ratio = difflib.SequenceMatcher(a=original_sentence.strip(), b=proposed_revision.strip()).ratio()
    has_numeric_change = _numeric_tokens(original_sentence) != _numeric_tokens(proposed_revision)
    has_risk_delta = _has_term_presence_delta(original_sentence, proposed_revision, RISK_TERMS)
    has_regulatory_delta = _has_term_presence_delta(original_sentence, proposed_revision, REGULATORY_TERMS)
    has_recommendation_delta = _has_term_presence_delta(
        original_sentence,
        proposed_revision,
        RECOMMENDATION_TERMS,
    )
    substantive_signal = has_numeric_change or has_risk_delta or has_regulatory_delta or has_recommendation_delta

    if not substantive_signal and (similarity >= 0.9 or char_ratio >= 0.80):
        return False, "cosmetic_rewrite_blocked"

    if intent in MATERIAL_CHANGE_INTENTS:
        # Some definition-level updates may not carry obvious numeric/term deltas.
        # For intent-declared material updates, require clear lexical distance to
        # avoid passing near-cosmetic rewrites.
        if substantive_signal or similarity <= 0.75 or char_ratio <= 0.70:
            return True, ""
        return False, "cosmetic_rewrite_blocked"

    if substantive_signal:
        return True, ""

    return False, "non_material_change"


def _load_source_states(path: Path | None) -> Dict[str, SourceState]:
    if path is None:
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    results = payload.get("results", [])
    out: Dict[str, SourceState] = {}
    for item in results:
        source_id = str(item.get("source_id", "")).strip()
        if not source_id:
            continue
        out[source_id] = SourceState(
            source_id=source_id,
            ok=bool(item.get("ok", False)),
            detail=str(item.get("detail", "")),
            evidence_excerpt=str(item.get("evidence_excerpt", "")),
        )
    return out


def _confidence_from_claim(
    *,
    claim: Dict[str, object],
    source_states: Dict[str, SourceState],
) -> tuple[str, bool, bool, str, str]:
    required_sources = _as_list(claim.get("required_sources"))
    double_sources = _as_list(claim.get("double_check_sources"))
    source_ids = _as_list(claim.get("source_ids"))
    if not source_ids:
        source_ids = sorted(set(required_sources + double_sources))

    def source_ok(source_id: str) -> bool:
        state = source_states.get(source_id)
        return bool(state.ok) if state else False

    source_ok_map = {sid: source_ok(sid) for sid in source_ids}
    has_any_evidence = any(source_ok_map.values())
    required_pass = (
        all(source_ok(sid) for sid in required_sources) if required_sources else has_any_evidence
    )

    convergence = str(claim.get("evidence_convergence", "unknown")).strip().lower()
    if convergence not in {"consistent", "conflict", "unknown"}:
        convergence = "unknown"
    if bool(claim.get("conflict")):
        convergence = "conflict"

    double_check_pass = all(source_ok(sid) for sid in double_sources) if double_sources else False

    passed_source_count = sum(1 for sid in source_ids if source_ok(sid))
    if convergence == "conflict":
        return "LOW", required_pass, double_check_pass, convergence, "evidence_conflict_needs_manual_review"

    if required_pass and double_check_pass and passed_source_count >= 2 and convergence == "consistent":
        return "HIGH", required_pass, double_check_pass, convergence, ""

    if required_pass and has_any_evidence:
        return "MEDIUM", required_pass, double_check_pass, convergence, ""

    return "LOW", required_pass, double_check_pass, convergence, "fulltext_missing"


def _candidate_status(material_pass: bool, confidence: str) -> str:
    if not material_pass:
        return "BLOCKED"
    if confidence == "HIGH":
        return "PASS_AUTO_REVISE"
    if confidence == "MEDIUM":
        return "NEEDS_MANUAL_REVIEW"
    return "BLOCKED"


def _join_source_locations(claim: Dict[str, object]) -> str:
    hints = _as_list(claim.get("source_locations")) or _as_list(claim.get("location_hints"))
    return ",".join(hints)


def _collect_excerpts(source_ids: Sequence[str], states: Dict[str, SourceState], limit: int = 420) -> str:
    parts: List[str] = []
    for sid in source_ids:
        state = states.get(sid)
        if not state or not state.evidence_excerpt:
            continue
        parts.append(f"[{sid}] {state.evidence_excerpt}")
    text = " | ".join(parts)
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def run_sop_gate(
    *,
    claim_spec_path: Path,
    gate_report_path: Path | None,
) -> tuple[List[ClaimResult], Dict[str, object]]:
    claim_payload = json.loads(claim_spec_path.read_text(encoding="utf-8"))
    claims = claim_payload.get("claims", [])
    if not isinstance(claims, list):
        raise ValueError("claim-spec field claims must be a list")
    source_states = _load_source_states(gate_report_path)

    rows: List[ClaimResult] = []
    for item in claims:
        if not isinstance(item, dict):
            continue
        claim_id = str(item.get("claim_id", "")).strip()
        original_sentence = str(item.get("original_sentence", "")).strip()
        proposed_revision = str(item.get("proposed_revision", "")).strip()
        change_intent = str(item.get("change_intent", "")).strip()
        reason = str(item.get("reason", "")).strip()

        material_pass, material_reason = _is_material_update(
            original_sentence=original_sentence,
            proposed_revision=proposed_revision,
            change_intent=change_intent,
        )
        confidence, required_pass, double_pass, convergence, confidence_reason = _confidence_from_claim(
            claim=item,
            source_states=source_states,
        )
        gate_status = _candidate_status(material_pass, confidence)
        blocking_reason = material_reason or confidence_reason

        source_ids = _as_list(item.get("source_ids")) or sorted(
            set(_as_list(item.get("required_sources")) + _as_list(item.get("double_check_sources")))
        )
        rows.append(
            ClaimResult(
                claim_id=claim_id,
                gate_status=gate_status,
                confidence=confidence,
                material_gate_pass=material_pass,
                required_sources_passed=required_pass,
                double_check_passed=double_pass,
                convergence=convergence,
                blocking_reason=blocking_reason,
                original_sentence=original_sentence,
                proposed_revision=proposed_revision,
                change_intent=change_intent,
                source_refs=",".join(source_ids),
                source_locations=_join_source_locations(item),
                evidence_excerpt=_collect_excerpts(source_ids, source_states),
                reason=reason,
            )
        )

    auto = [r for r in rows if r.gate_status == "PASS_AUTO_REVISE"]
    manual = [r for r in rows if r.gate_status == "NEEDS_MANUAL_REVIEW"]
    blocked = [r for r in rows if r.gate_status == "BLOCKED"]
    pass_rate = (len(auto) / len(rows)) if rows else 0.0
    missing_rate = (
        len([r for r in rows if r.blocking_reason in {"fulltext_missing", "missing_proposed_revision"}]) / len(rows)
        if rows
        else 0.0
    )
    summary = {
        "claim_count": len(rows),
        "auto_revise_count": len(auto),
        "manual_review_count": len(manual),
        "blocked_count": len(blocked),
        "pass_rate": round(pass_rate, 4),
        "missing_rate": round(missing_rate, 4),
        "blocking_reason_counts": {
            reason: sum(1 for r in rows if r.blocking_reason == reason)
            for reason in sorted(set(r.blocking_reason for r in rows if r.blocking_reason))
        },
    }
    return rows, summary


def _write_csv(path: Path, rows: Sequence[ClaimResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "claim_id",
                "gate_status",
                "confidence",
                "material_gate_pass",
                "required_sources_passed",
                "double_check_passed",
                "convergence",
                "blocking_reason",
                "change_intent",
                "source_refs",
                "source_locations",
                "reason",
                "original_sentence",
                "proposed_revision",
                "evidence_excerpt",
            ],
        )
        writer.writeheader()
        for r in rows:
            writer.writerow(
                {
                    "claim_id": r.claim_id,
                    "gate_status": r.gate_status,
                    "confidence": r.confidence,
                    "material_gate_pass": "YES" if r.material_gate_pass else "NO",
                    "required_sources_passed": "YES" if r.required_sources_passed else "NO",
                    "double_check_passed": "YES" if r.double_check_passed else "NO",
                    "convergence": r.convergence,
                    "blocking_reason": r.blocking_reason,
                    "change_intent": r.change_intent,
                    "source_refs": r.source_refs,
                    "source_locations": r.source_locations,
                    "reason": r.reason,
                    "original_sentence": r.original_sentence,
                    "proposed_revision": r.proposed_revision,
                    "evidence_excerpt": r.evidence_excerpt,
                }
            )


def main() -> int:
    _maybe_reexec_runtime_python()
    parser = argparse.ArgumentParser(description="Run SOP gate for claim-level revision candidates.")
    parser.add_argument("--claim-spec", type=Path, required=True)
    parser.add_argument(
        "--gate-report",
        type=Path,
        default=None,
        help="Optional source gate report JSON from check_revise_sources.py",
    )
    parser.add_argument("--output-csv", type=Path, required=True, help="Full claim matrix output.")
    parser.add_argument(
        "--output-candidates-csv",
        type=Path,
        default=None,
        help="Auto-revise candidates output. Default: <output-csv-dir>/revise_candidates.csv",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="SOP gate summary JSON. Default: <output-csv-dir>/sop_qc_report.json",
    )
    args = parser.parse_args()

    if not args.claim_spec.exists():
        parser.error(f"claim spec not found: {args.claim_spec}")
    if args.gate_report is not None and not args.gate_report.exists():
        parser.error(f"gate report not found: {args.gate_report}")

    rows, summary = run_sop_gate(
        claim_spec_path=args.claim_spec,
        gate_report_path=args.gate_report,
    )

    candidates_csv = args.output_candidates_csv or (args.output_csv.parent / "revise_candidates.csv")
    summary_json = args.output_json or (args.output_csv.parent / "sop_qc_report.json")
    auto_candidates = [r for r in rows if r.gate_status == "PASS_AUTO_REVISE"]

    _write_csv(args.output_csv, rows)
    _write_csv(candidates_csv, auto_candidates)
    summary_json.parent.mkdir(parents=True, exist_ok=True)
    summary_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Claim matrix: {args.output_csv}")
    print(f"Auto-revise candidates: {candidates_csv}")
    print(f"SOP QC report: {summary_json}")
    print(
        "Counts:",
        f"claims={summary['claim_count']}",
        f"auto={summary['auto_revise_count']}",
        f"manual={summary['manual_review_count']}",
        f"blocked={summary['blocked_count']}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
