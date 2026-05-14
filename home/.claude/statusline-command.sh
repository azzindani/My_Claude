#!/bin/sh
input=$(cat)
python - "$input" << 'PYEOF'
import sys, json

try:
    data = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
except Exception:
    data = {}

model = data.get("model", {}).get("display_name", "Unknown Model")
cwd = data.get("workspace", {}).get("current_dir") or data.get("cwd", "?")
dir_short = cwd.rstrip("/\\").split("/")[-1].split("\\")[-1] or cwd

ctx = data.get("context_window", {})
used_pct = ctx.get("used_percentage")
usage = ctx.get("current_usage", {})
input_tokens = usage.get("input_tokens")
output_tokens = usage.get("output_tokens")

# Token string
token_str = ""
if input_tokens is not None and output_tokens is not None:
    total = input_tokens + output_tokens
    token_str = f"{total/1000:.1f}k tokens" if total >= 1000 else f"{total} tokens"

# Progress bar
bar_str = ""
if used_pct is not None:
    filled = int(used_pct / 5)
    empty = 20 - filled
    bar = "#" * filled + "-" * empty
    bar_str = f"[{bar}] {int(used_pct)}%"

# ANSI colors
CYAN, YELLOW, WHITE, GREEN, RESET = "\033[36m", "\033[33m", "\033[37m", "\033[32m", "\033[0m"

parts = [f"{CYAN}{model}{RESET}", f"{YELLOW}{dir_short}{RESET}"]
if token_str:
    parts.append(f"{WHITE}{token_str}{RESET}")
if bar_str:
    parts.append(f"{GREEN}{bar_str}{RESET}")

print("  ".join(parts))
PYEOF
