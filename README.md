# My_Claude

[![CI](https://github.com/azzindani/My_Claude/actions/workflows/ci.yml/badge.svg)](https://github.com/azzindani/My_Claude/actions/workflows/ci.yml)

My personal [Claude Code](https://claude.com/claude-code) setup — settings, hooks, and statusline — versioned so I can re-install on any machine in one command.

Cross-platform: tested on **Linux**, **macOS**, and **Windows** in CI.

## What's in here

```
home/.claude/
  settings.json                     main config (templated)
  hooks/
    ask-user-question-reminder.ps1  PreToolUse hook (Windows)
    ask-user-question-reminder.sh   PreToolUse hook (Linux/macOS)
  statusline.py                     custom Python statusline (multi-line, cost/budget aware)
  statusline.bat                    Windows wrapper (templated)
  statusline.ps1                    PowerShell wrapper (templated)
  statusline-command.sh             POSIX statusline wrapper
  statusline_test.py                statusline smoke test
install.ps1                         installer (Windows / PowerShell 7 anywhere)
install.sh                          installer (Linux / macOS / Git Bash / WSL)
tools/
  validate_install.py               post-install validator (used by CI and locally)
.github/workflows/ci.yml            CI: lint + install matrix on Linux/macOS/Windows
```

The repo is **config only**. Runtime artefacts (caches, sessions, history, credentials, telemetry, project state) are intentionally not tracked.

## Install

### Windows

```powershell
git clone https://github.com/azzindani/My_Claude.git
cd My_Claude
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

Optional flags:

| Flag                       | Purpose                                                     |
| -------------------------- | ----------------------------------------------------------- |
| `-Python <path>`           | Use a specific Python (default: first `python` on PATH)     |
| `-ClaudeHome <path>`       | Install into a different `.claude` dir                      |
| `-Force`                   | Overwrite existing files without backing them up            |
| `-DryRun`                  | Print what would happen without writing anything            |

### macOS / Linux

```bash
git clone https://github.com/azzindani/My_Claude.git
cd My_Claude
chmod +x install.sh
./install.sh
```

Same flags, lowercase: `--python`, `--claude-home`, `--force`, `--dry-run`.

### What the installer does

1. Detects the current OS to pick the right hook script (`.ps1` on Windows, `.sh` on Linux/macOS).
2. Walks `home/.claude/` and copies each file to `~/.claude/`.
3. For templated files (`settings.json`, `statusline.bat`, `statusline.ps1`) it substitutes:
   - `{{CLAUDE_HOME}}` → resolved `.claude` path on this machine
   - `{{PYTHON}}` → resolved Python interpreter (`python3` preferred, falls back to `python`)
   - `{{HOOK_COMMAND}}` → `powershell -File ...` on Windows, `bash ...` on Linux/macOS
   - `{{HOOK_SHELL}}` → `powershell` on Windows, `bash` on Linux/macOS
   - JSON values are properly escaped (`\` → `\\`, `"` → `\"`).
4. Marks `*.sh` files executable on Linux/macOS.
5. Existing files are backed up to `<file>.bak-YYYYMMDD-HHMMSS` unless `--force` / `-Force` is set.
6. Restart Claude Code afterwards so it reloads settings.

### Verifying an install

```bash
python tools/validate_install.py ~/.claude bash         # Linux/macOS
python tools\validate_install.py %USERPROFILE%\.claude powershell   # Windows
```

Validates that all expected files exist, `settings.json` parses with no leftover placeholders, the hook is configured for the right shell, and expected plugins are enabled.

## Plugins

`settings.json` declares two plugins via `enabledPlugins`:

- `rust-analyzer-lsp@claude-plugins-official` — official marketplace
- `ui-ux-pro-max@ui-ux-pro-max-skill` — added marketplace `nextlevelbuilder/ui-ux-pro-max-skill`

Claude Code will pick these up on first launch. If they don't auto-install, run `/plugin` inside Claude Code and install them manually.

## Updating the repo from your live config

When you change settings on a working machine and want to push them back:

1. Diff your live `~/.claude/settings.json` against `home/.claude/settings.json`.
2. Re-template any new hardcoded paths back to `{{CLAUDE_HOME}}` / `{{PYTHON}}`.
3. Copy any new hooks, statusline tweaks, etc. into `home/.claude/`.
4. Commit and push.

## CI

`.github/workflows/ci.yml` runs on every push / PR:

| Job              | Runs on                                  | Checks                                                                                              |
| ---------------- | ---------------------------------------- | --------------------------------------------------------------------------------------------------- |
| `lint`           | `ubuntu-latest`                          | `shellcheck` on all `.sh` files, `PSScriptAnalyzer` on all `.ps1` files, settings.json template renders to valid JSON |
| `install-test`   | `ubuntu-latest`, `macos-latest`, `windows-latest` | Dry-run, real install, validator script, hook smoke test, statusline smoke test, idempotent re-install with `--force` |

## Notes

- The statusline (`statusline.py`) is self-contained — it reads `~/.claude/usage_log.json` for token/cost tracking and discovers `git` itself. No template substitution needed.
- The `AskUserQuestion` hook references memory entries (`feedback_no_clarifying_questions.md`, `feedback_stop_asking_deliver.md`) by name. Those are personal memory files, not shipped here — the hook still runs fine without them; the reminder text just lists the names it expects.
- Plugin install state (`~/.claude/plugins/installed_plugins.json` etc.) is **not** versioned — Claude Code rebuilds it from `enabledPlugins` and `extraKnownMarketplaces`.
