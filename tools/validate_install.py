#!/usr/bin/env python3
"""Validate a Claude Code install directory produced by install.sh / install.ps1.

Usage:
    python tools/validate_install.py <claude_home> <expected_shell>

  expected_shell is "powershell" on Windows, "bash" on Linux/macOS.

Exits 0 on success, non-zero with a message on failure.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

EXPECTED_FILES = [
    "settings.json",
    "statusline.py",
    "statusline.bat",
    "statusline.ps1",
    "statusline-command.sh",
    "statusline_test.py",
    "hooks/ask-user-question-reminder.ps1",
    "hooks/ask-user-question-reminder.sh",
]


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    if len(sys.argv) != 3:
        fail(f"usage: {sys.argv[0]} <claude_home> <expected_shell>")
    claude_home = Path(sys.argv[1])
    expected_shell = sys.argv[2]

    if expected_shell not in {"bash", "powershell"}:
        fail(f"expected_shell must be 'bash' or 'powershell', got {expected_shell!r}")

    if not claude_home.is_dir():
        fail(f"claude_home does not exist: {claude_home}")

    # 1) All expected files present
    for rel in EXPECTED_FILES:
        if not (claude_home / rel).is_file():
            fail(f"missing file: {rel}")
    print("[ok] all expected files present")

    # 2) settings.json parses, no unresolved placeholders, hook matches OS
    settings_path = claude_home / "settings.json"
    raw = settings_path.read_text(encoding="utf-8")
    if "{{" in raw or "}}" in raw:
        fail(f"unresolved placeholders in settings.json:\n{raw}")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        fail(f"settings.json is not valid JSON: {e}")
    print("[ok] settings.json parses and has no placeholders")

    try:
        hook = data["hooks"]["PreToolUse"][0]["hooks"][0]
    except (KeyError, IndexError, TypeError) as e:
        fail(f"settings.json missing PreToolUse hook entry: {e}")

    if hook.get("shell") != expected_shell:
        fail(f"hook.shell = {hook.get('shell')!r}, expected {expected_shell!r}")

    cmd = hook.get("command", "")
    if expected_shell == "bash":
        if not cmd.startswith("bash "):
            fail(f"bash hook command should start with 'bash ', got: {cmd!r}")
    else:
        if "powershell" not in cmd.lower():
            fail(f"powershell hook command should mention powershell, got: {cmd!r}")
    print(f"[ok] hook configured for {expected_shell}: {cmd}")

    # 3) statusline command resolved
    sl_cmd = data.get("statusLine", {}).get("command", "")
    if "statusline.py" not in sl_cmd:
        fail(f"statusLine.command should reference statusline.py, got: {sl_cmd!r}")
    print(f"[ok] statusline configured: {sl_cmd}")

    # 4) Plugins declared
    enabled = data.get("enabledPlugins", {})
    for plugin in (
        "rust-analyzer-lsp@claude-plugins-official",
        "ui-ux-pro-max@ui-ux-pro-max-skill",
    ):
        if not enabled.get(plugin):
            fail(f"missing enabled plugin: {plugin}")
    print("[ok] expected plugins enabled")

    # 5) Bash hook should be executable on Unix-likes
    if expected_shell == "bash":
        hook_sh = claude_home / "hooks/ask-user-question-reminder.sh"
        if not os.access(hook_sh, os.X_OK):
            fail(f"hook script not executable: {hook_sh}")
        print("[ok] bash hook is executable")

    print("\nALL CHECKS PASSED")


if __name__ == "__main__":
    main()
