"""Self-check test: no sensitive tokens in tracked files."""

import re
import subprocess

FORBIDDEN = re.compile(r"PANOVA|阿片|opioid use \(ITT\)|/Users/star/")

# This file necessarily contains the forbidden tokens because it
# defines the leak-guard pattern. Exclude it from the scan; it's
# allow-listed by its exact path.
SELF_REFERENCE_FILES = frozenset({
    "tests/test_leak_guard.py",
})


def test_no_sensitive_tokens_in_tracked_files():
    files = subprocess.check_output(["git", "ls-files"], text=True).splitlines()
    offenders = []
    for path in files:
        if path in SELF_REFERENCE_FILES:
            continue
        try:
            with open(path, encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except (FileNotFoundError, IsADirectoryError):
            continue
        if FORBIDDEN.search(content):
            offenders.append(path)
    assert not offenders, f"Sensitive tokens found in: {offenders}"
