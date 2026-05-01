"""Regression test: housekeeping --dry-run must not mutate run_index.tsv."""

import os
import time
from pathlib import Path

import pytest

from openrevise.pipeline import housekeeping


def _make_run_id(age_days: float) -> tuple[str, float]:
    """Build a valid run_id whose embedded timestamp is `age_days` in the past."""
    old_ts = time.time() - age_days * 24 * 3600
    old_struct = time.gmtime(old_ts)
    run_id = time.strftime("%Y%m%dT%H%M%SZ", old_struct) + "_ABCDEF"
    return run_id, old_ts


def test_dry_run_does_not_mutate_run_index(tmp_path: Path):
    """Cold-archive branch (line ~164 guard): hot < age <= cold."""
    runs_root = tmp_path / "runs"
    archive_dir = tmp_path / "archive"
    reports_dir = tmp_path / "reports"
    runs_root.mkdir()
    archive_dir.mkdir()
    reports_dir.mkdir()

    run_index = reports_dir / "run_index.tsv"
    initial = "marker\trun_id\tstatus\n"
    run_index.write_text(initial)
    before = run_index.read_bytes()

    # Construct a run dir old enough to trigger COLD_ARCHIVED handling.
    # is_valid_run_id expects the format YYYYMMDDTHHMMSSZ_AAAAAA where
    # the last component is 6 alphanumerics (uppercase hex by convention).
    # Pick a timestamp ~60 days ago so age_days falls between
    # --hot-days=1 and --cold-days=180.
    run_id, old_ts = _make_run_id(60)
    run_dir = runs_root / run_id
    run_dir.mkdir()
    os.utime(run_dir, (old_ts, old_ts))

    args_list = [
        "--runs-root", str(runs_root),
        "--archive-dir", str(archive_dir),
        "--reports-dir", str(reports_dir),
        "--hot-days", "1",
        "--cold-days", "180",
        "--dry-run",
    ]
    rc = housekeeping.main(args_list)
    assert rc == 0
    assert run_index.read_bytes() == before, (
        "dry-run must not mutate run-index (COLD_ARCHIVED branch)"
    )


def test_dry_run_expired_branch_does_not_mutate_run_index(tmp_path: Path):
    """Expired-purge branch (line ~231 guard): age > cold_days, with run_has_purge=True.

    `_purge_non_key_dirs` walks subdirs ('intake', 'sources_raw', 'sources_parsed',
    'scope', 'verify', 'tmp') and appends each existing one to its `removed` list
    even under --dry-run. The for-loop over `removed` then sets
    `run_has_purge = True`, so we trigger the EXPIRED_NONKEY_PURGED upsert path
    by simply creating one such non-key subdir under the run.
    """
    runs_root = tmp_path / "runs"
    archive_dir = tmp_path / "archive"
    reports_dir = tmp_path / "reports"
    runs_root.mkdir()
    archive_dir.mkdir()
    reports_dir.mkdir()

    run_index = reports_dir / "run_index.tsv"
    initial = "marker\trun_id\tstatus\n"
    run_index.write_text(initial)
    before = run_index.read_bytes()

    # 400 days old > --cold-days=180, so the EXPIRED branch fires.
    run_id, old_ts = _make_run_id(400)
    run_dir = runs_root / run_id
    run_dir.mkdir()
    # Create a non-key subdir so _purge_non_key_dirs records it as "removed",
    # which sets run_has_purge=True and would otherwise drive an
    # EXPIRED_NONKEY_PURGED upsert.
    (run_dir / "intake").mkdir()
    os.utime(run_dir, (old_ts, old_ts))

    args_list = [
        "--runs-root", str(runs_root),
        "--archive-dir", str(archive_dir),
        "--reports-dir", str(reports_dir),
        "--hot-days", "1",
        "--cold-days", "180",
        "--dry-run",
    ]
    rc = housekeeping.main(args_list)
    assert rc == 0
    assert run_index.read_bytes() == before, (
        "dry-run must not mutate run-index (EXPIRED_NONKEY_PURGED branch)"
    )
    # Sanity: dry-run must also not actually delete the non-key subdir.
    assert (run_dir / "intake").exists(), "dry-run must not delete files"
