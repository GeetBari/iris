# Iris development checkpoint

## Submitted Codex task integration — local, not committed

New iris_agents.py generates quoted Codex exec launch plans and renders JSONL
activity. Prompt files are sent through stdin, not interpolated into shell code.
Agent jobs persist request/mode/result path and expose streamed activity plus
final text. read-only and workspace-write only; no permission bypass.

Voice: ask Codex for PROJECT to INSTRUCTIONS -> five-minute pending review;
approve agent task submits a single read-only review. Write access requires
dashboard approval. Cancel agent task removes pending reviews. Last-job status
and stop controls work for submitted tasks. Dashboard has draft/review/cancel
controls plus final-result cards. Approval payload is immutable and one-use.

26 local tests and browser JS syntax validation passed. After the initial
automatic approval block, the user explicitly authorized the live read-only
Codex smoke test. It passed through Iris's draft/approve/job/result flow:
job 4bf4928c36b44d2f86e4cf8ff6226f1f finished with exit code 0 and final text
IRIS_AGENT_READY. Captured events show an agent response and completed turn,
without tool-execution events. No file-editing agent task has been tested.

Remaining: multi-step workflow execution, richer disambiguation/readiness checks,
reviewed generated shell commands, administrator/UAC tasks, full adapters for
other agents. No claim that the entire six-stage roadmap is complete.

## Voice task milestone — verified for publication

User confirmed voice-driven tests, result reporting and VS Code + Codex launch.
20 regression tests pass, including the codecs/Codex speech alias and exclusive
Windows task-service port binding. Concurrent service requests also passed.

Shared task owner: iris_task_service.py on loopback port 8766. Dashboard and
assistant use iris_task_client.py with a private runtime token in ignored data/.
The service starts on demand and survives dashboard/voice-worker restarts.
Restarting the task service itself still leaves old jobs untracked; Windows
restart also ends runtime context. No PID-based reattachment is attempted.

iris_tasks.py owns server-side project profiles, current project, recent job
IDs, structured voice actions and project-name clarification. Default profile
iris uses this checkout, VS Code, Codex, and unittest discovery. Dashboard
Project profiles editor persists approved commands to data/projects.json.
Requests supported: start coding on PROJECT with EDITOR and AGENT, run tests
for PROJECT, start development server, build project, check port NUMBER, list
tasks, task status/did they pass, stop last task/server, cancel pending request.
Unknown projects/tools are rejected; arbitrary speech never becomes shell code.
Speech matching currently uses explicit intent rules, not an LLM planner.

Validated: actual shared-service job survived dashboard restart and could be
stopped; voice-task request ran saved Iris tests. Unit coverage includes profile
persistence, project clarification, follow-up context, port input validation,
owned-job cancellation, accurate failure reporting, terminal fixes and HTTP
request protection. Browser script syntax checked. Microphone end-to-end check
still requires user speech. Restart Iris worker to load voice integration.

Natural phrasing fallback is now implemented in iris_intents.py using local
Qwen JSON interpretation into validated actions/projects/tools only. Tested
against the running E: Ollama installation with a coding-session paraphrase.
No model-generated shell text is executed. Exact common commands still work
without Ollama. Active project/recent task IDs persist in data/task-context.json;
dated voice request/reply events persist in data/task-events.jsonl and are shown
in the developer workspace. Original personal commands bypass this routing.

Remaining stages from the plan: broader multi-step planning, reviewed generated
commands, richer job disambiguation, UAC workflows and full agent task adapters.
Agent integration currently launches interactive terminals, not task submission.

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
