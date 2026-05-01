#!/usr/bin/env python3
"""
Label-value consistency gate for high-risk subgroup metrics.

Current hard rule:
- If an opioid-related replacement sentence contains both ITT and mITT metric tuples,
  verify label-to-value binding against extracted source text before revise.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Tuple


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


_maybe_reexec_runtime_python()

from openrevise.sources.evidence_extractors import extract_local_source_text
from openrevise.artifacts.run_artifact_utils import is_valid_run_id


FOOTNOTE_KEY_PATTERN = re.compile(r"\[\[fn:([A-Za-z0-9_]+)\]\]")
LABEL_MARKER_PATTERN = re.compile(r"(?<![a-z])(m?itt)(?![a-z])\s*[:：]", re.IGNORECASE)
PAIR_VS_PATTERN = re.compile(
    r"(?P<a>\d+(?:\.\d+)?)\s*(?:个月|month|months|mo)?\s*(?:vs|/|v)\s*(?P<b>\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
PAIR_MEDIAN_PATTERN = re.compile(
    r"(?:median|中位数)\s*(?:\(\s*\d+%?\s*ci[^)]*\)\s*)?"
    r"(?P<a>\d+(?:\.\d+)?)\s*(?:\([^)]{0,80}\))?\s*"
    r"(?P<b>\d+(?:\.\d+)?)\s*(?:\([^)]{0,80}\))?",
    re.IGNORECASE,
)
HR_PATTERN = re.compile(r"hr[^0-9]{0,12}(?P<hr>\d+(?:\.\d+)?)", re.IGNORECASE)
P_PATTERN = re.compile(r"p(?:值)?[^0-9]{0,12}(?P<p>\d+(?:\.\d+)?)", re.IGNORECASE)
SOURCE_TUPLE_PATTERN = re.compile(
    r"(?:median|中位数)\s*(?:\(\s*\d+%?\s*ci[^)]*\)\s*)?"
    r"(?P<a>\d+(?:\.\d+)?)\s*(?:\([^)]{0,80}\))?\s*"
    r"(?P<b>\d+(?:\.\d+)?)\s*(?:\([^)]{0,80}\))?"
    r".{0,260}?"
    r"hr[^0-9]{0,20}(?P<hr>\d+(?:\.\d+)?)"
    r".{0,220}?"
    r"p(?:值)?[^0-9]{0,20}(?P<p>\d+(?:\.\d+)?)",
    re.IGNORECASE | re.DOTALL,
)
OPIOID_ITT_ANCHOR_PATTERN = re.compile(
    r"(?:opioid\s*use|使用阿片类药物)\s*\(\s*itt\s*\)",
    re.IGNORECASE,
)
ITT_PATTERN = re.compile(r"(?<![a-z])itt(?![a-z])", re.IGNORECASE)
MITT_PATTERN = re.compile(r"(?<![a-z])mitt(?![a-z])", re.IGNORECASE)


@dataclass(frozen=True)
class MetricTuple:
    left: str
    right: str
    hr: str
    p: str | None

    def key(self) -> str:
        return "|".join([self.left, self.right, self.hr, self.p or "na"])

    def core_key(self) -> str:
        return "|".join([self.left, self.right, self.hr])


@dataclass(frozen=True)
class SourceInference:
    source_id: str
    label_map: Dict[str, MetricTuple]
    detail: str


def _normalize_text(text: str) -> str:
    normalized = (
        text.replace("：", ":")
        .replace("；", ";")
        .replace("，", ",")
        .replace("（", "(")
        .replace("）", ")")
        .replace("＝", "=")
        .replace("　", " ")
    )
    return re.sub(r"\s+", " ", normalized).strip()


def _normalize_number(raw: str) -> str:
    value = float(raw)
    formatted = f"{value:.6f}".rstrip("0").rstrip(".")
    if not formatted:
        return "0"
    return formatted


def _metric_tuple(
    *,
    left: str,
    right: str,
    hr: str,
    p: str | None,
) -> MetricTuple:
    return MetricTuple(
        left=_normalize_number(left),
        right=_normalize_number(right),
        hr=_normalize_number(hr),
        p=_normalize_number(p) if p is not None else None,
    )


def _canonical_label(raw: str) -> str:
    clean = re.sub(r"\s+", "", raw).lower()
    if clean == "itt":
        return "ITT"
    if clean == "mitt":
        return "mITT"
    return raw


def _find_metric_in_segment(segment: str) -> MetricTuple | None:
    pair_match = PAIR_VS_PATTERN.search(segment)
    if pair_match is None:
        pair_match = PAIR_MEDIAN_PATTERN.search(segment)
    if pair_match is None:
        return None
    hr_match = HR_PATTERN.search(segment)
    if hr_match is None:
        return None
    p_match = P_PATTERN.search(segment)
    return _metric_tuple(
        left=pair_match.group("a"),
        right=pair_match.group("b"),
        hr=hr_match.group("hr"),
        p=(p_match.group("p") if p_match is not None else None),
    )


def _extract_patch_label_map(replacement: str) -> Dict[str, MetricTuple]:
    text = _normalize_text(replacement)
    markers = list(LABEL_MARKER_PATTERN.finditer(text))
    if len(markers) < 2:
        return {}

    out: Dict[str, MetricTuple] = {}
    for idx, marker in enumerate(markers):
        label = _canonical_label(marker.group(1))
        next_start = markers[idx + 1].start() if idx + 1 < len(markers) else len(text)
        segment = text[marker.end() : next_start]
        metric = _find_metric_in_segment(segment)
        if metric is None:
            continue
        out[label] = metric
    return out


def _extract_source_ids_from_replacement(replacement: str) -> List[str]:
    keys = [m.group(1) for m in FOOTNOTE_KEY_PATTERN.finditer(replacement)]
    dedup: List[str] = []
    seen = set()
    for key in keys:
        if key in seen:
            continue
        seen.add(key)
        dedup.append(key)
    return dedup


def _is_opioid_context(text: str) -> bool:
    low = text.lower()
    return ("opioid" in low) or ("阿片" in text)


def _window_for_endpoint(text: str) -> str:
    normalized = _normalize_text(text)
    anchor = OPIOID_ITT_ANCHOR_PATTERN.search(normalized)
    if anchor is not None:
        start = anchor.start()
        return normalized[start : start + 7000]

    low = normalized.lower()
    anchor_positions: List[int] = []
    for term in ["opioid", "阿片"]:
        idx = low.find(term.lower())
        if idx >= 0:
            anchor_positions.append(idx)
    if not anchor_positions:
        return normalized
    start = min(anchor_positions)
    return normalized[start : start + 9000]


def _extract_source_metric_tuples(window_text: str) -> List[MetricTuple]:
    out: List[MetricTuple] = []
    for m in SOURCE_TUPLE_PATTERN.finditer(window_text):
        try:
            metric = _metric_tuple(
                left=m.group("a"),
                right=m.group("b"),
                hr=m.group("hr"),
                p=m.group("p"),
            )
        except ValueError:
            continue
        out.append(metric)
    return out


def _infer_label_order(window_text: str) -> List[str]:
    itt_match = ITT_PATTERN.search(window_text)
    mitt_match = MITT_PATTERN.search(window_text)
    if itt_match is None or mitt_match is None:
        return []
    if itt_match.start() < mitt_match.start():
        return ["ITT", "mITT"]
    return ["mITT", "ITT"]


def _infer_source_label_map(text: str) -> Dict[str, MetricTuple]:
    window = _window_for_endpoint(text)
    tuples = _extract_source_metric_tuples(window)
    if len(tuples) < 2:
        return {}
    label_order = _infer_label_order(window)
    if len(label_order) != 2:
        return {}
    return {
        label_order[0]: tuples[0],
        label_order[1]: tuples[1],
    }


def _load_source_specs(path: Path | None) -> Dict[str, Dict[str, object]]:
    if path is None or not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    out: Dict[str, Dict[str, object]] = {}
    for block in ["required_sources", "optional_sources"]:
        source_block = payload.get(block, {})
        if isinstance(source_block, dict):
            for source_id, spec in source_block.items():
                if isinstance(spec, dict):
                    out[str(source_id)] = spec
    return out


def _iter_local_fallback_source_ids(specs: Dict[str, Dict[str, object]]) -> List[str]:
    local_types = {"local_pdf", "local_docx", "local_pptx", "local_txt", "local_text"}
    out: List[str] = []
    for source_id, spec in specs.items():
        source_type = str(spec.get("type", "")).strip()
        if source_type in local_types:
            out.append(source_id)
    return out


def _extract_source_text(
    *,
    source_id: str,
    spec: Dict[str, object],
) -> Tuple[str, str]:
    source_type = str(spec.get("type", "")).strip()
    if source_type in {"local_txt", "local_text"}:
        path = Path(str(spec.get("path", "")).strip())
        if not path.exists():
            raise FileNotFoundError(f"Local file not found: {path}")
        return path.read_text(encoding="utf-8", errors="ignore"), "native_text"
    if source_type not in {"local_pdf", "local_docx", "local_pptx"}:
        raise RuntimeError(f"unsupported_source_type:{source_type}")
    path = Path(str(spec.get("path", "")).strip())
    extract_mode = str(spec.get("extract_mode", "auto")).strip() or "auto"
    ocr_mode = str(spec.get("ocr_mode", "dual")).strip() or "dual"
    location_hints = [str(x) for x in spec.get("location_hints", []) if str(x).strip()]
    result = extract_local_source_text(
        source_type=source_type,
        path=path,
        extract_mode=extract_mode,
        ocr_mode=ocr_mode,
        location_hints=location_hints,
    )
    return result.text, result.detail


def _build_expected_map(
    *,
    source_ids: Iterable[str],
    source_specs: Dict[str, Dict[str, object]],
    cache: Dict[str, Tuple[str, str]],
) -> Tuple[Dict[str, Dict[str, int]], List[SourceInference], List[str]]:
    expected_counts: Dict[str, Dict[str, int]] = {"ITT": {}, "mITT": {}}
    inferences: List[SourceInference] = []
    warnings: List[str] = []

    for source_id in source_ids:
        spec = source_specs.get(source_id)
        if spec is None:
            warnings.append(f"source_spec_missing:{source_id}")
            continue
        if source_id not in cache:
            try:
                cache[source_id] = _extract_source_text(source_id=source_id, spec=spec)
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"source_extract_failed:{source_id}:{exc}")
                continue
        text, detail = cache[source_id]
        inferred = _infer_source_label_map(text)
        if not inferred:
            warnings.append(f"source_infer_failed:{source_id}")
            continue
        inferences.append(SourceInference(source_id=source_id, label_map=inferred, detail=detail))
        for label, metric in inferred.items():
            bucket = expected_counts.setdefault(label, {})
            key = metric.key()
            bucket[key] = bucket.get(key, 0) + 1

    return expected_counts, inferences, warnings


def run_gate(
    *,
    patch_spec_path: Path,
    source_config_path: Path | None,
) -> Dict[str, object]:
    payload = json.loads(patch_spec_path.read_text(encoding="utf-8"))
    patch_items = payload.get("patches", [])
    if not isinstance(patch_items, list):
        raise ValueError("patch-spec field patches must be a list")

    source_specs = _load_source_specs(source_config_path)
    fallback_sources = _iter_local_fallback_source_ids(source_specs)
    source_cache: Dict[str, Tuple[str, str]] = {}

    results: List[Dict[str, object]] = []
    fail_count = 0
    checked_count = 0

    for item in patch_items:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label", "")).strip() or "<no_label>"
        replacement = str(item.get("replacement", ""))
        patch_map = _extract_patch_label_map(replacement)
        if not _is_opioid_context(replacement):
            continue
        if not ({"ITT", "mITT"} <= set(patch_map.keys())):
            continue

        checked_count += 1
        source_ids = [
            sid for sid in _extract_source_ids_from_replacement(replacement) if sid in source_specs
        ]
        if not source_ids:
            source_ids = fallback_sources

        expected_counts, inferences, warnings = _build_expected_map(
            source_ids=source_ids,
            source_specs=source_specs,
            cache=source_cache,
        )
        expected_keys = {k: sorted(v.keys()) for k, v in expected_counts.items() if v}

        status = "PASS"
        reason = "ok"

        if not expected_counts.get("ITT") or not expected_counts.get("mITT"):
            status = "FAIL"
            reason = "unverifiable_label_binding"
        else:
            for metric_label in ["ITT", "mITT"]:
                proposed_key = patch_map[metric_label].key()
                proposed_core_key = patch_map[metric_label].core_key()
                expected_for_label = set(expected_counts.get(metric_label, {}).keys())
                expected_for_label_core = {
                    "|".join(value.split("|")[:3]) for value in expected_counts.get(metric_label, {}).keys()
                }
                opposite = "mITT" if metric_label == "ITT" else "ITT"
                expected_for_opposite = set(expected_counts.get(opposite, {}).keys())
                expected_for_opposite_core = {
                    "|".join(value.split("|")[:3]) for value in expected_counts.get(opposite, {}).keys()
                }

                if proposed_key in expected_for_label or proposed_core_key in expected_for_label_core:
                    continue
                if proposed_key in expected_for_opposite or proposed_core_key in expected_for_opposite_core:
                    status = "FAIL"
                    reason = f"swapped_label_binding:{metric_label}->{opposite}"
                    break
                status = "FAIL"
                reason = f"label_value_mismatch:{metric_label}"
                break

            if status == "PASS":
                for metric_label in ["ITT", "mITT"]:
                    if len(expected_counts.get(metric_label, {})) > 1:
                        status = "FAIL"
                        reason = f"source_value_conflict:{metric_label}"
                        break

        if status == "FAIL":
            fail_count += 1

        results.append(
            {
                "patch_label": label,
                "status": status,
                "reason": reason,
                "source_ids": source_ids,
                "warnings": warnings,
                "replacement_map": {k: v.key() for k, v in patch_map.items()},
                "expected_map": expected_keys,
                "source_inference": [
                    {
                        "source_id": x.source_id,
                        "detail": x.detail,
                        "label_map": {k: v.key() for k, v in x.label_map.items()},
                    }
                    for x in inferences
                ],
            }
        )

    return {
        "status": "PASS" if fail_count == 0 else "FAIL",
        "candidate_patch_count": checked_count,
        "fail_count": fail_count,
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check label-value consistency for high-risk subgroup metrics.")
    parser.add_argument("--patch-spec", type=Path, required=True)
    parser.add_argument("--source-config", type=Path, default=None)
    parser.add_argument("--output-json", type=Path, default=None)
    parser.add_argument(
        "--run-dir",
        type=Path,
        default=None,
        help="Run directory root. If used with --run-id and --output-json omitted, "
        "defaults to <run-dir>/reports/label_value_consistency_<run_id>.json",
    )
    parser.add_argument("--run-id", type=str, default=None)
    args = parser.parse_args()

    if not args.patch_spec.exists():
        parser.error(f"patch spec not found: {args.patch_spec}")
    if args.source_config is not None and not args.source_config.exists():
        parser.error(f"source config not found: {args.source_config}")

    if args.run_dir is not None and args.output_json is None:
        if not args.run_id:
            parser.error("--run-id is required when --run-dir is used without --output-json")
        if not is_valid_run_id(args.run_id):
            parser.error(f"Invalid --run-id format: {args.run_id}")
        args.output_json = args.run_dir / "reports" / f"label_value_consistency_{args.run_id}.json"

    payload = run_gate(
        patch_spec_path=args.patch_spec,
        source_config_path=args.source_config,
    )
    out = json.dumps(payload, ensure_ascii=False, indent=2)
    print(out)
    if args.output_json is not None:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(out + "\n", encoding="utf-8")

    return 0 if payload["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
