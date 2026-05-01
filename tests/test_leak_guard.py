"""Self-check test: no sensitive tokens in tracked files."""

import re
import subprocess

FORBIDDEN = re.compile(r"PANOVA|阿片|opioid use \(ITT\)|/Users/star/")

# These two files necessarily contain the forbidden tokens because they
# define the leak-guard pattern. Exclude them from the scan; they're
# allow-listed by their exact paths.
SELF_REFERENCE_FILES = frozenset({
    "tests/test_leak_guard.py",
    ".github/workflows/leak-guard.yml",
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
