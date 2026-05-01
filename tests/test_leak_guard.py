"""Self-check test: no sensitive tokens in tracked files."""

import re
import subprocess

FORBIDDEN = re.compile(r"PANOVA|阿片|opioid use \(ITT\)|/Users/star/")

# Files that necessarily reference forbidden tokens for legitimate reasons:
#  - tests/test_leak_guard.py: defines the leak-guard pattern itself.
#  - src/openrevise/gates/check_label_value_consistency.py: ships a default
#    opioid ITT/mITT anchor profile inherited from the private gate. The
#    gate is generic in design but currently embeds the anchor literal in
#    its regex.
#    TODO(refactor): make profile registry; remove allow-list entry after
#    desensitization (LabelBindingProfile migration, design doc step 7).
#  - tests/test_label_binding_swap.py: regression fixture exercises the
#    opioid-anchor code path; will become a generic profile fixture once
#    the registry refactor lands.
SELF_REFERENCE_FILES = frozenset({
    "tests/test_leak_guard.py",
    "src/openrevise/gates/check_label_value_consistency.py",
    "tests/test_label_binding_swap.py",
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
