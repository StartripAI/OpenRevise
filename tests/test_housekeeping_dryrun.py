"""Regression test: housekeeping --dry-run must not mutate run_index.tsv."""

import os
import time
from pathlib import Path

from openrevise.pipeline import housekeeping


def test_dry_run_does_not_mutate_run_index(tmp_path: Path):
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
    old_ts = time.time() - 60 * 24 * 3600
    old_struct = time.gmtime(old_ts)
    run_id = time.strftime("%Y%m%dT%H%M%SZ", old_struct) + "_ABCDEF"
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
        "dry-run must not mutate run-index"
    )
