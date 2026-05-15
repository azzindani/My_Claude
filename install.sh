#!/usr/bin/env bash
# Install personal Claude Code config into the current user's ~/.claude directory.
# Works on Linux, macOS, and Windows under Git Bash / WSL / MSYS2.
#
# Usage:
#   ./install.sh
#   ./install.sh --python /path/to/python
#   ./install.sh --claude-home /custom/.claude
#   ./install.sh --force      # overwrite without backing up
#   ./install.sh --dry-run    # show what would happen

set -euo pipefail

PYTHON=""
CLAUDE_HOME="${HOME}/.claude"
FORCE=0
DRY_RUN=0

while [ $# -gt 0 ]; do
    case "$1" in
        --python)      PYTHON="$2"; shift 2 ;;
        --claude-home) CLAUDE_HOME="$2"; shift 2 ;;
        --force)       FORCE=1; shift ;;
        --dry-run)     DRY_RUN=1; shift ;;
        -h|--help)
            grep '^#' "$0" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *) echo "Unknown arg: $1" >&2; exit 1 ;;
    esac
done

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
SOURCE="${REPO_ROOT}/home/.claude"

if [ ! -d "$SOURCE" ]; then
    echo "Source directory not found: $SOURCE" >&2
    exit 1
fi

# --- OS detection ---------------------------------------------------------
case "$(uname -s)" in
    MINGW*|MSYS*|CYGWIN*) IS_WINDOWS=1 ;;
    *)                    IS_WINDOWS=0 ;;
esac

# --- Python detection -----------------------------------------------------
if [ -z "$PYTHON" ]; then
    PYTHON="$(command -v python3 || command -v python || true)"
fi
if [ -z "$PYTHON" ]; then
    echo "Could not find python3/python on PATH. Pass --python <path>." >&2
    exit 1
fi

# --- Hook command (per-OS) ------------------------------------------------
if [ "$IS_WINDOWS" -eq 1 ]; then
    HOOK_SCRIPT="${CLAUDE_HOME}/hooks/ask-user-question-reminder.ps1"
    HOOK_COMMAND="powershell -NoProfile -ExecutionPolicy Bypass -File \"${HOOK_SCRIPT}\""
    HOOK_SHELL="powershell"
else
    HOOK_SCRIPT="${CLAUDE_HOME}/hooks/ask-user-question-reminder.sh"
    HOOK_COMMAND="bash \"${HOOK_SCRIPT}\""
    HOOK_SHELL="bash"
fi

echo "Repo source : $SOURCE"
echo "Target dir  : $CLAUDE_HOME"
echo "Python      : $PYTHON"
echo "Hook shell  : $HOOK_SHELL"
[ "$DRY_RUN" -eq 1 ] && echo "DRY RUN -- no changes will be made"
echo

# Files where we substitute placeholders. All other files are copied verbatim.
TEMPLATED=("settings.json" "statusline.bat" "statusline.ps1")

is_templated() {
    local rel="$1"
    for t in "${TEMPLATED[@]}"; do
        [ "$t" = "$rel" ] && return 0
    done
    return 1
}

# sed-safe escaping for replacement strings (escape /, &, and the delimiter)
sed_escape_repl() {
    printf '%s' "$1" | sed -e 's/[\/&]/\\&/g'
}

# JSON: every backslash and double quote in the substituted value must be
# escaped so the result is still valid JSON. Backslashes first (otherwise we'd
# escape the backslashes we just added).
json_escape() {
    printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g'
}

# Compose the four substitutions, both in raw and JSON-escaped flavors.
CLAUDE_HOME_RAW_ESC="$(sed_escape_repl "$CLAUDE_HOME")"
PYTHON_RAW_ESC="$(sed_escape_repl "$PYTHON")"
HOOK_COMMAND_RAW_ESC="$(sed_escape_repl "$HOOK_COMMAND")"
HOOK_SHELL_RAW_ESC="$(sed_escape_repl "$HOOK_SHELL")"

CLAUDE_HOME_JSON_ESC="$(sed_escape_repl "$(json_escape "$CLAUDE_HOME")")"
PYTHON_JSON_ESC="$(sed_escape_repl "$(json_escape "$PYTHON")")"
HOOK_COMMAND_JSON_ESC="$(sed_escape_repl "$(json_escape "$HOOK_COMMAND")")"
HOOK_SHELL_JSON_ESC="$(sed_escape_repl "$(json_escape "$HOOK_SHELL")")"

backup_existing() {
    local path="$1"
    if [ -e "$path" ]; then
        local stamp
        stamp="$(date +%Y%m%d-%H%M%S)"
        local backup="${path}.bak-${stamp}"
        [ "$DRY_RUN" -eq 0 ] && cp -a "$path" "$backup"
        echo "  backup : $backup"
    fi
}

install_file() {
    local src="$1"
    local rel="${src#"$SOURCE"/}"
    local dest="${CLAUDE_HOME}/${rel}"
    local dest_dir
    dest_dir="$(dirname "$dest")"

    [ "$DRY_RUN" -eq 0 ] && mkdir -p "$dest_dir"

    if [ -e "$dest" ] && [ "$FORCE" -ne 1 ]; then
        backup_existing "$dest"
    fi

    if is_templated "$rel"; then
        echo "  template : $rel"
        if [ "$DRY_RUN" -eq 0 ]; then
            case "$rel" in
                *.json)
                    sed -e "s/{{CLAUDE_HOME}}/${CLAUDE_HOME_JSON_ESC}/g" \
                        -e "s/{{PYTHON}}/${PYTHON_JSON_ESC}/g" \
                        -e "s/{{HOOK_COMMAND}}/${HOOK_COMMAND_JSON_ESC}/g" \
                        -e "s/{{HOOK_SHELL}}/${HOOK_SHELL_JSON_ESC}/g" \
                        "$src" > "$dest"
                    ;;
                *)
                    sed -e "s/{{CLAUDE_HOME}}/${CLAUDE_HOME_RAW_ESC}/g" \
                        -e "s/{{PYTHON}}/${PYTHON_RAW_ESC}/g" \
                        -e "s/{{HOOK_COMMAND}}/${HOOK_COMMAND_RAW_ESC}/g" \
                        -e "s/{{HOOK_SHELL}}/${HOOK_SHELL_RAW_ESC}/g" \
                        "$src" > "$dest"
                    ;;
            esac
        fi
    else
        echo "  copy     : $rel"
        if [ "$DRY_RUN" -eq 0 ]; then
            cp -a "$src" "$dest"
            case "$rel" in
                *.sh) chmod +x "$dest" ;;
            esac
        fi
    fi
}

while IFS= read -r -d '' f; do
    install_file "$f"
done < <(find "$SOURCE" -type f -print0)

echo
if [ "$DRY_RUN" -eq 1 ]; then
    echo "Dry run complete. Re-run without --dry-run to apply."
else
    echo "Install complete."
    echo "Restart Claude Code so it picks up the new settings."
    echo
    echo "Plugins (declared in settings.json) will install on first launch:"
    echo "  - rust-analyzer-lsp@claude-plugins-official"
    echo "  - ui-ux-pro-max@ui-ux-pro-max-skill"
    echo "If they don't auto-install, run /plugin inside Claude Code."
fi
