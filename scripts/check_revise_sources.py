#!/usr/bin/env python3
"""
Source gate for revise workflows.

Gate rule:
- Required sources must be reachable and contain required evidence tokens.
- Optional sources are checked and reported, but do not block the run.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import ssl
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

def _maybe_reexec_runtime_python() -> None:
    if os.environ.get("REVISE_NO_REEXEC") == "1":
        return
    repo_root = Path(__file__).resolve().parents[1]
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

from pypdf import PdfReader

from evidence_extractors import extract_local_source_text
from run_artifact_utils import is_valid_run_id


@dataclass
class CheckResult:
    source_id: str
    tier: str
    ok: bool
    reachable: bool
    matched_tokens: int
    total_tokens: int
    detail: str
    evidence_excerpt: str = ""
    extraction_detail: str = ""


def _fetch_url_text(
    url: str,
    timeout: int = 25,
    ca_bundle: str | None = None,
    allow_insecure_tls: bool = False,
) -> str:
    return _fetch_url_bytes(
        url,
        timeout=timeout,
        ca_bundle=ca_bundle,
        allow_insecure_tls=allow_insecure_tls,
    ).decode("utf-8", errors="ignore")


def _fetch_url_bytes(
    url: str,
    timeout: int = 25,
    ca_bundle: str | None = None,
    allow_insecure_tls: bool = False,
) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "revise-source-check/1.0"})
    if allow_insecure_tls:
        context = ssl._create_unverified_context()
    elif ca_bundle:
        context = ssl.create_default_context(cafile=ca_bundle)
    else:
        context = None
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=context) as resp:
            return resp.read()
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        # Fallback for environments where Python's trust store is out of sync
        # with system certificates while curl can still validate TLS properly.
        curl_cmd = ["curl", "-fsSL", "--max-time", str(timeout), "--retry", "1"]
        if ca_bundle:
            curl_cmd.extend(["--cacert", ca_bundle])
        if allow_insecure_tls:
            curl_cmd.append("-k")
        curl_cmd.append(url)
        proc = subprocess.run(curl_cmd, check=False, capture_output=True)
        if proc.returncode != 0:
            stderr = proc.stderr.decode("utf-8", errors="ignore").strip()
            raise urllib.error.URLError(stderr or f"curl failed with exit code {proc.returncode}")
        return proc.stdout


def _fetch_remote_pdf_text(
    url: str,
    timeout: int = 30,
    ca_bundle: str | None = None,
    allow_insecure_tls: bool = False,
) -> str:
    payload = _fetch_url_bytes(
        url,
        timeout=timeout,
        ca_bundle=ca_bundle,
        allow_insecure_tls=allow_insecure_tls,
    )

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=True) as tmp:
        tmp.write(payload)
        tmp.flush()
        reader = PdfReader(tmp.name)
        return "\n".join((page.extract_text() or "") for page in reader.pages)


def _normalize_for_match(text: str) -> str:
    # Join words split by line-wrap hyphenation in PDF text extraction,
    # e.g. "inde- pendent" -> "independent".
    merged = re.sub(r"([A-Za-z])-\s+([A-Za-z])", r"\1\2", text)
    return re.sub(r"\s+", " ", merged).strip().lower()


def _make_excerpt(text: str, limit: int = 320) -> str:
    flat = " ".join((text or "").split())
    if len(flat) <= limit:
        return flat
    return flat[: limit - 3].rstrip() + "..."


def _check_one(
    source_id: str,
    spec: Dict[str, object],
    tier: str,
    ca_bundle: str | None = None,
    allow_insecure_tls: bool = False,
) -> CheckResult:
    must_include = [str(x) for x in spec.get("must_include", [])]
    must_include_any = [str(x) for x in spec.get("must_include_any", [])]
    source_type = str(spec.get("type", "")).strip()
    extract_mode = str(spec.get("extract_mode", "auto"))
    ocr_mode = str(spec.get("ocr_mode", "dual"))
    location_hints = [str(x) for x in spec.get("location_hints", []) if str(x).strip()]
    body = ""
    extraction_detail = ""

    try:
        if source_type == "url_text":
            body = _fetch_url_text(
                str(spec["url"]),
                ca_bundle=ca_bundle,
                allow_insecure_tls=allow_insecure_tls,
            )
        elif source_type == "remote_pdf":
            body = _fetch_remote_pdf_text(
                str(spec["url"]),
                ca_bundle=ca_bundle,
                allow_insecure_tls=allow_insecure_tls,
            )
        elif source_type == "local_pdf":
            path = Path(str(spec["path"]))
            extracted = extract_local_source_text(
                source_type=source_type,
                path=path,
                extract_mode=extract_mode,
                ocr_mode=ocr_mode,
                location_hints=location_hints,
            )
            body = extracted.text
            extraction_detail = extracted.detail
        elif source_type in {"local_docx", "local_pptx", "local_image"}:
            path = Path(str(spec["path"]))
            extracted = extract_local_source_text(
                source_type=source_type,
                path=path,
                extract_mode=extract_mode,
                ocr_mode=ocr_mode,
                location_hints=location_hints,
            )
            body = extracted.text
            extraction_detail = extracted.detail
        else:
            return CheckResult(
                source_id=source_id,
                tier=tier,
                ok=False,
                reachable=False,
                matched_tokens=0,
                total_tokens=len(must_include) + (1 if must_include_any else 0),
                detail=f"Unsupported source type: {source_type}",
            )
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, RuntimeError, FileNotFoundError) as exc:
        return CheckResult(
            source_id=source_id,
            tier=tier,
            ok=False,
            reachable=False,
            matched_tokens=0,
            total_tokens=len(must_include) + (1 if must_include_any else 0),
            detail=f"Fetch/parse failed: {exc}",
        )

    normalized_body = _normalize_for_match(body)
    missing_tokens = [tok for tok in must_include if _normalize_for_match(tok) not in normalized_body]
    matched_required = len(must_include) - len(missing_tokens)

    matched_any = 0
    missing_any: List[str] = []
    if must_include_any:
        any_matches = [tok for tok in must_include_any if _normalize_for_match(tok) in normalized_body]
        if any_matches:
            matched_any = 1
        else:
            missing_any = must_include_any

    total_tokens = len(must_include) + (1 if must_include_any else 0)
    matched = matched_required + matched_any
    ok = matched_required == len(must_include) and (not must_include_any or matched_any == 1)
    detail_parts: List[str] = []
    if missing_tokens:
        detail_parts.append("missing evidence tokens: " + "; ".join(missing_tokens[:3]))
    if missing_any:
        detail_parts.append("must_include_any not matched: " + "; ".join(missing_any[:3]))
    if not detail_parts:
        detail_parts.append("all tokens matched")
    if extraction_detail:
        detail_parts.append(f"extractor={extraction_detail}")

    return CheckResult(
        source_id=source_id,
        tier=tier,
        ok=ok,
        reachable=True,
        matched_tokens=matched,
        total_tokens=total_tokens,
        detail="; ".join(detail_parts),
        evidence_excerpt=_make_excerpt(body),
        extraction_detail=extraction_detail,
    )


def run_check(
    config_path: Path,
    ca_bundle: str | None = None,
    allow_insecure_tls: bool = False,
) -> Dict[str, object]:
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    required = cfg.get("required_sources", {})
    optional = cfg.get("optional_sources", {})
    if not isinstance(required, dict) or not isinstance(optional, dict):
        raise ValueError("Config fields required_sources and optional_sources must be objects")
    if len(required) == 0:
        return {
            "all_required_passed": False,
            "required_failed_count": 1,
            "config_error": "required_sources is empty; configure at least one required source",
            "results": [],
        }

    results: List[CheckResult] = []
    for source_id, spec in required.items():
        results.append(
            _check_one(
                source_id,
                spec,
                "required",
                ca_bundle=ca_bundle,
                allow_insecure_tls=allow_insecure_tls,
            )
        )
    for source_id, spec in optional.items():
        results.append(
            _check_one(
                source_id,
                spec,
                "optional",
                ca_bundle=ca_bundle,
                allow_insecure_tls=allow_insecure_tls,
            )
        )

    required_failed = [r for r in results if r.tier == "required" and not r.ok]
    payload = {
        "all_required_passed": len(required_failed) == 0,
        "required_failed_count": len(required_failed),
        "results": [
            {
                "source_id": r.source_id,
                "tier": r.tier,
                "ok": r.ok,
                "reachable": r.reachable,
                "matched_tokens": r.matched_tokens,
                "total_tokens": r.total_tokens,
                "detail": r.detail,
                "evidence_excerpt": r.evidence_excerpt,
                "extraction_detail": r.extraction_detail,
            }
            for r in results
        ],
    }
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Run source gate checks for revise workflow.")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "config" / "revise_sources.json",
    )
    parser.add_argument("--output-json", type=Path, default=None)
    parser.add_argument(
        "--ca-bundle",
        type=Path,
        default=Path(os.environ["REVISE_CA_BUNDLE"]) if os.environ.get("REVISE_CA_BUNDLE") else None,
        help="Optional CA bundle PEM path for enterprise/private trust chains. "
        "Can also be set via REVISE_CA_BUNDLE env var.",
    )
    parser.add_argument(
        "--allow-insecure-tls",
        action="store_true",
        help="Disable TLS certificate verification for diagnostic use only.",
    )
    parser.add_argument(
        "--run-dir",
        type=Path,
        default=None,
        help="Run directory root. If set with --run-id and --output-json omitted, "
        "defaults to <run-dir>/reports/source_gate_report_<run_id>.json",
    )
    parser.add_argument("--run-id", type=str, default=None)
    args = parser.parse_args()

    if args.run_dir is not None and args.output_json is None:
        if not args.run_id:
            parser.error("--run-id is required when --run-dir is used without --output-json")
        if not is_valid_run_id(args.run_id):
            parser.error(f"Invalid --run-id format: {args.run_id}")
        args.output_json = args.run_dir / "reports" / f"source_gate_report_{args.run_id}.json"

    ca_bundle = str(args.ca_bundle) if args.ca_bundle else None
    try:
        payload = run_check(
            args.config,
            ca_bundle=ca_bundle,
            allow_insecure_tls=args.allow_insecure_tls,
        )
    except Exception as exc:
        payload = {
            "all_required_passed": False,
            "required_failed_count": 1,
            "config_error": f"{exc.__class__.__name__}: {exc}",
            "results": [],
        }
    out = json.dumps(payload, ensure_ascii=False, indent=2)
    print(out)
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(out + "\n", encoding="utf-8")

    return 0 if payload["all_required_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
