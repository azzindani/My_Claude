# Hook: PreToolUse on AskUserQuestion
# Injects a reminder citing the CLAUDE.md Core Principle and matching memory entries.
# Does NOT block — emits hookSpecificOutput.additionalContext and exits 0.

# Drain stdin (hook payload not needed — reminder is unconditional)
$null = [Console]::In.ReadToEnd()

$reminder = "REMINDER: CLAUDE.md Core Principle -- DO NOT call AskUserQuestion when CLAUDE.md/prompt/memory already resolves the ambiguity. Matching memory entries: feedback_no_clarifying_questions.md, feedback_stop_asking_deliver.md. CHECKLIST before proceeding: (1) Does CLAUDE.md answer this? (2) Does the current prompt answer this? (3) Does loaded memory answer this? If any of the three resolves it, CANCEL this AskUserQuestion call and EXECUTE the work instead. Reserve AskUserQuestion for genuinely undetermined choices (irreversible action, destructive scope, conflicting instructions)."

$payload = @{
    hookSpecificOutput = @{
        hookEventName     = "PreToolUse"
        additionalContext = $reminder
    }
} | ConvertTo-Json -Compress -Depth 4

[Console]::Out.WriteLine($payload)
exit 0
