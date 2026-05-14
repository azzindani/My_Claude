# Install personal Claude Code config into the current user's ~/.claude directory.
# Works with Windows PowerShell 5.1, PowerShell 7+ on Windows, and PowerShell 7+ on Linux/macOS.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File .\install.ps1
#   pwsh ./install.ps1
#   ./install.ps1 -Python /usr/bin/python3
#   ./install.ps1 -Force      # overwrite without backing up
#   ./install.ps1 -DryRun     # show what would happen

[CmdletBinding()]
param(
    [string]$Python,
    [string]$ClaudeHome,
    [switch]$Force,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

# --- OS detection ---------------------------------------------------------
# $IsWindows / $IsLinux / $IsMacOS exist in PS 7+. On Windows PowerShell 5.1,
# they don't, so default $IsWindows to true and the others to false.
if (-not (Test-Path Variable:IsWindows)) {
    $script:IsWindows = $true
    $script:IsLinux   = $false
    $script:IsMacOS   = $false
}

if (-not $ClaudeHome) {
    if ($IsWindows) {
        $ClaudeHome = Join-Path $env:USERPROFILE ".claude"
    } else {
        $ClaudeHome = Join-Path $env:HOME ".claude"
    }
}

$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Source   = Join-Path $RepoRoot "home/.claude"
if (-not (Test-Path $Source)) {
    Write-Error "Source directory not found: $Source"
    exit 1
}

# --- Python detection -----------------------------------------------------
if (-not $Python) {
    foreach ($name in @("python3", "python")) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd) { $Python = $cmd.Source; break }
    }
}
if (-not $Python) {
    Write-Error "Could not find python/python3 on PATH. Pass -Python <path>."
    exit 1
}

# --- Hook command (per-OS) ------------------------------------------------
if ($IsWindows) {
    $HookScript  = Join-Path $ClaudeHome "hooks/ask-user-question-reminder.ps1"
    $HookCommand = "powershell -NoProfile -ExecutionPolicy Bypass -File `"$HookScript`""
    $HookShell   = "powershell"
} else {
    $HookScript  = Join-Path $ClaudeHome "hooks/ask-user-question-reminder.sh"
    $HookCommand = "bash `"$HookScript`""
    $HookShell   = "bash"
}

Write-Host "Repo source : $Source"
Write-Host "Target dir  : $ClaudeHome"
Write-Host "Python      : $Python"
Write-Host "Hook shell  : $HookShell"
if ($DryRun) { Write-Host "DRY RUN -- no changes will be made" -ForegroundColor Yellow }
Write-Host ""

# Files where we substitute placeholders. All other files are copied verbatim.
$Templated = @(
    "settings.json",
    "statusline.bat",
    "statusline.ps1"
)

function Backup-Existing($path) {
    if (Test-Path $path) {
        $stamp  = Get-Date -Format "yyyyMMdd-HHmmss"
        $backup = "$path.bak-$stamp"
        if (-not $DryRun) { Copy-Item $path $backup -Recurse -Force }
        Write-Host "  backup : $backup" -ForegroundColor DarkGray
    }
}

function Json-Escape($s) {
    # Escape backslashes first, then double quotes — order matters.
    ($s -replace '\\', '\\') -replace '"', '\"'
}

function Install-File($srcFile) {
    $rel     = $srcFile.Substring($Source.Length).TrimStart('\','/')
    $relFwd  = $rel.Replace('\','/')
    $dest    = Join-Path $ClaudeHome $rel
    $destDir = Split-Path $dest -Parent

    if (-not $DryRun -and -not (Test-Path $destDir)) {
        New-Item -ItemType Directory -Force -Path $destDir | Out-Null
    }

    $isTemplated = $Templated -contains $relFwd

    if (Test-Path $dest) {
        if (-not $Force) { Backup-Existing $dest }
    }

    if ($isTemplated) {
        $content = Get-Content $srcFile -Raw
        if ($relFwd.ToLower().EndsWith('.json')) {
            # JSON: every backslash in substituted values must be doubled.
            $homeRepl = Json-Escape $ClaudeHome
            $pyRepl   = Json-Escape $Python
            $hookCmd  = Json-Escape $HookCommand
            $hookSh   = Json-Escape $HookShell
        } else {
            $homeRepl = $ClaudeHome
            $pyRepl   = $Python
            $hookCmd  = $HookCommand
            $hookSh   = $HookShell
        }
        $content = $content.Replace('{{CLAUDE_HOME}}',  $homeRepl)
        $content = $content.Replace('{{PYTHON}}',       $pyRepl)
        $content = $content.Replace('{{HOOK_COMMAND}}', $hookCmd)
        $content = $content.Replace('{{HOOK_SHELL}}',   $hookSh)
        Write-Host "  template : $relFwd"
        if (-not $DryRun) {
            [System.IO.File]::WriteAllText($dest, $content, [System.Text.UTF8Encoding]::new($false))
        }
    } else {
        Write-Host "  copy     : $relFwd"
        if (-not $DryRun) {
            Copy-Item $srcFile $dest -Force
            # Mark *.sh files executable on Unix-likes
            if (-not $IsWindows -and $relFwd.EndsWith('.sh')) {
                & chmod +x $dest 2>$null
            }
        }
    }
}

Get-ChildItem -Path $Source -Recurse -File | ForEach-Object {
    Install-File $_.FullName
}

Write-Host ""
if ($DryRun) {
    Write-Host "Dry run complete. Re-run without -DryRun to apply." -ForegroundColor Yellow
} else {
    Write-Host "Install complete." -ForegroundColor Green
    Write-Host "Restart Claude Code so it picks up the new settings."
    Write-Host ""
    Write-Host "Plugins (declared in settings.json) will install on first launch:" -ForegroundColor Cyan
    Write-Host "  - rust-analyzer-lsp@claude-plugins-official"
    Write-Host "  - ui-ux-pro-max@ui-ux-pro-max-skill"
    Write-Host "If they don't auto-install, run /plugin inside Claude Code."
}
