# Iris development checkpoint

## October 6, 2026

Validation: four tests passed covering actual PowerShell output and failure exit
codes, stopping a running job, literal path quoting, C: workspace rejection, and
HTTP rejection of foreign-origin or missing-token execution requests.

User constraints: keep installs and project data on E: or D:. Commit or push only
when explicitly requested. User authorized publishing this upgrade on October 6.

Implemented developer workspace at http://127.0.0.1:8765/dev, linked from the
existing dashboard. Standard library only; no new dependencies installed.

- Discovery via PATH for VS Code, Cursor, Windsurf, Codex CLI, Claude Code,
  Gemini CLI, Aider, Ollama, Git, Python, Node.js and npm. Ollama also checked
  at the existing E: installation. Tools without PATH launchers may show missing.
- Project validation requires an existing directory on D: or E:.
- Coding sessions open an installed editor and/or interactive agent terminal.
  These are generic executable launch adapters, not autonomous agent APIs.
- Reviewed PowerShell jobs with exit codes, bounded output reads, history, and
  stop controls targeting only processes owned by this dashboard instance.
- Session selections saved in browser storage. Job records/scripts/output in
  ignored data/dev. Dashboard restarts mark old running jobs untracked;
  those jobs may still run and need closing in their terminal or Task Manager.
- Local host/origin checks plus per-process token for developer mutations.
- Voice phrase 'start a coding session' opens the workspace for user selection.
- Fixed assistant --command handling used by the older dashboard console.

Remaining capabilities: richer voice planning with reviewed execution, named
multi-step profiles, full agent protocol integrations, interactive terminal
embedding, Windows administrator/UAC task workflows. No automatic agent
installation, authentication, elevation or unattended destructive operations.

Launch using run_iris_dashboard.bat, then open /dev. The PowerShell launcher
starts a hidden server, waits for readiness, reuses a running dashboard, and
records startup errors under data. It does not kill other port listeners.
Stop the existing dashboard process before launching after code edits.
The workspace page and developer API both returned HTTP 200 in the live check.
