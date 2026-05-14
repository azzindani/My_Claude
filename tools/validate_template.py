#!/usr/bin/env python3
"""Validate that a settings.json template renders to valid JSON and uses only
known placeholders.

Usage:
    python tools/validate_template.py <path-to-template>
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ALLOWED_PLACEHOLDERS = {
    "{{CLAUDE_HOME}}",
    "{{PYTHON}}",
    "{{HOOK_COMMAND}}",
    "{{HOOK_SHELL}}",
}

# Stub values used to render the template before parsing.
STUB_VALUES = {
    "{{CLAUDE_HOME}}":  "/tmp/claude",
    "{{PYTHON}}":       "/usr/bin/python3",
    "{{HOOK_COMMAND}}": "bash /tmp/claude/hooks/h.sh",
    "{{HOOK_SHELL}}":   "bash",
}


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(f"usage: {sys.argv[0]} <template-path>")

    template_path = Path(sys.argv[1])
    raw = template_path.read_text(encoding="utf-8")

    found = set(re.findall(r"\{\{[^}]+\}\}", raw))
    unknown = found - ALLOWED_PLACEHOLDERS
    if unknown:
        sys.exit(f"unknown placeholders in {template_path}: {sorted(unknown)}")

    rendered = raw
    for ph, val in STUB_VALUES.items():
        rendered = rendered.replace(ph, val)

    try:
        json.loads(rendered)
    except json.JSONDecodeError as e:
        sys.exit(f"{template_path} does not render to valid JSON: {e}")

    print(f"{template_path}: template OK (placeholders: {sorted(found)})")


if __name__ == "__main__":
    main()
