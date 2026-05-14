# My_Claude

My personal [Claude Code](https://claude.com/claude-code) setup — settings, hooks, and statusline — versioned so I can re-install on any machine in one command.

## What's in here

```
home/.claude/
  settings.json                     main config (templated paths)
  hooks/
    ask-user-question-reminder.ps1  PreToolUse hook for AskUserQuestion
  statusline.py                     custom Python statusline (multi-line, cost/budget aware)
  statusline.bat                    Windows wrapper (templated)
  statusline.ps1                    PowerShell wrapper (templated)
  statusline-command.sh             POSIX statusline wrapper
  statusline_test.py                statusline smoke test
install.ps1                         Windows installer
install.sh                          macOS/Linux installer
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

1. Walks `home/.claude/` and copies each file to `~/.claude/`.
2. For templated files (`settings.json`, `statusline.bat`, `statusline.ps1`) it substitutes:
   - `{{CLAUDE_HOME}}` → resolved `.claude` path on this machine
   - `{{PYTHON}}` → resolved Python interpreter
3. Existing files are backed up to `<file>.bak-YYYYMMDD-HHMMSS` unless `--force` / `-Force` is set.
4. Restart Claude Code afterwards so it reloads settings.

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

## Notes

- The statusline (`statusline.py`) is self-contained — it reads `~/.claude/usage_log.json` for token/cost tracking and discovers `git` itself. No template substitution needed.
- The `AskUserQuestion` hook references memory entries (`feedback_no_clarifying_questions.md`, `feedback_stop_asking_deliver.md`) by name. Those are personal memory files, not shipped here — the hook still runs fine without them; the reminder text just lists the names it expects.
- Plugin install state (`~/.claude/plugins/installed_plugins.json` etc.) is **not** versioned — Claude Code rebuilds it from `enabledPlugins` and `extraKnownMarketplaces`.
