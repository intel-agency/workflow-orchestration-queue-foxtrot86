# workflow-orchestration-queue-zulu48 — Forensic Report

> **Date:** 2026-03-28
>
> **Scope:** Repository-wide — all workflows across all runs since repo creation
>
> **Affected targets:** `intel-agency/workflow-orchestration-queue-zulu48`, workflows: `orchestrator-agent`, `python-ci`
>
> **Pattern confirmed:** Yes — two distinct, independent failure classes identified

---

## 1. Executive Summary

The repository exhibits two independent, unresolved failure classes.

**Class A — Orchestrator Idle Timeout (1 run, still blocking):** The orchestrator run triggered by the `orchestration:epic-implemented` label on issue #4 stalled during the `review-epic-prs` sub-workflow and was killed by the watchdog after 15 minutes of inactivity. The root cause is a permission policy conflict: the delegated `code-reviewer` subagent attempted to execute `gh` bash commands to inspect PR #5, but the opencode permission ruleset evaluates all `bash` commands as `action: ask` in subagent context. In a headless CI run, no human is available to approve these prompts. The subagent entered a permanent passive wait, and the 15-minute idle watchdog fired. The pipeline is now stuck: issue #4 carries `orchestration:epic-implemented` but not `orchestration:epic-reviewed`, meaning the 4-step orchestration sequence cannot advance to step 3 (report-progress) or step 4 (debrief-and-document) without manual intervention.

**Class B — Python-CI Build Failure (6 runs, PR #2 still open):** The `dynamic-workflow-project-setup` branch (PR #2) has 6 consecutive `python-ci` failures caused by a hatchling build configuration error. The package source directory is not registered correctly, so hatchling cannot find any files to ship in the wheel. Multiple fix attempts failed; PR #2 is still open.

**Recommended next steps:**
1. For Class A: Expand the bash permission allowlist in the code-reviewer (or subagent) permission ruleset so `gh` CLI read operations are auto-approved in headless mode, then re-trigger by re-applying `orchestration:epic-implemented` to issue #4.
2. For Class B: Fix `pyproject.toml` to declare `[tool.hatch.build.targets.wheel] packages = ["src/sentinel"]` (or the correct package name), then push to the `dynamic-workflow-project-setup` branch.

---

## 2. Forensic Evidence

### 2.1 Failure Inventory

| # | Workflow | Run ID | Date (UTC) | Branch / Event | Stage Reached | Last Meaningful Output | Duration / Idle Gap | Conclusion |
|---|----------|--------|------------|----------------|---------------|------------------------|---------------------|------------|
| 1 | `orchestrator-agent` | 23673934864 | 2026-03-28 01:03:37Z | `main` / `issues labeled` | `Execute orchestrator agent` — delegated to `code-reviewer` subagent step 0 | `permission.asked` — 4 bash blocker events at 01:08:35Z | 20 min 27s total; 15 min idle gap (01:08:35Z → 01:23:48Z) | `failure` (exit 143 / SIGTERM) |
| 2 | `python-ci` | 23673413056 | 2026-03-28 00:38:17Z | `dynamic-workflow-project-setup` / `pull_request` | `lint` job — `uv pip install -e .` | `ValueError: Unable to determine which files to ship inside the wheel` | ~13s | `failure` (exit 1) |
| 3 | `python-ci` | 23673399362 | 2026-03-28 00:37:38Z | `dynamic-workflow-project-setup` / `pull_request` | `lint` job | Same ValueError | ~12s | `failure` (exit 1) |
| 4 | `python-ci` | 23673398844 | 2026-03-28 00:37:37Z | `dynamic-workflow-project-setup` / `push` | `lint` job | Same ValueError | ~13s | `failure` (exit 1) |
| 5 | `python-ci` | 23673364164 | 2026-03-28 00:35:53Z | `dynamic-workflow-project-setup` / `pull_request` | `lint` job | Same ValueError | ~16s | `failure` (exit 1) |
| 6 | `python-ci` | 23673363456 | 2026-03-28 00:35:51Z | `dynamic-workflow-project-setup` / `push` | `lint` job | Same ValueError | ~13s | `failure` (exit 1) |
| 7 | `python-ci` | 23673339904 | 2026-03-28 00:34:44Z | `dynamic-workflow-project-setup` / `pull_request` | `lint` / `typecheck` jobs | Same ValueError | ~15s | `failure` (exit 1) |

### 2.2 Exceptions / Non-Matching Cases

**Orchestrator runs that succeeded (Class A context):**
- Run 23673566782 (00:45:39Z, 8s) — quick successful `orchestrator-agent` run on issue #4, matched the `orchestration:epic-ready` clause and launched `implement-epic`.
- Run 23673566806 (00:45:39Z, 3min) — successful orchestrator run, labeled trigger processing.
- Run 23673604298 (00:47:29Z, 17min) — successful `implement-epic` execution for issue #4. The developer subagent ran without hitting the bash permission blocker because `implement-epic` uses the `developer` agent which has different permission context (or the commands it ran were pre-approved in the ruleset).
- Run 23673407688 (00:38:02Z, ~11min) — successful initial orchestrator run for the application plan issue.

**Python-CI vs. Validate on same PRs:**
- On every PR that had a `python-ci` failure, the `validate` workflow on the same PR **succeeded**. The `validate` workflow runs different checks (lint, scan, shell tests) and does not invoke `uv pip install` or the hatchling build chain.

**PR #5 (`issues/4-standardized-work-item-interface`):**
- No `python-ci` run was triggered for PR #5. Either the `python-ci` workflow does not trigger on that branch, or the workflow path filter excludes it. Run 23673911459 (`validate`: success) and run 23673910611 (`CodeQL`: success) were the only checks.

### 2.3 Success / Baseline Context

- **Orchestrator runs:** 4 successes out of 5 orchestrator-agent runs (80% success rate). The single failure is the most recent and is a novel failure mode (permission blocker) not seen in prior runs.
- **Python-CI:** 0 successes out of 6 runs (0% success rate) across 3 fix attempts on the `dynamic-workflow-project-setup` branch. This class shows no improvement between attempts.
- **PR #2 state:** Still open. The branch `dynamic-workflow-project-setup` has a blocking python-ci failure that prevents the PR from being confidently merged.
- **Issue #4 state:** Open. Carries labels `epic`, `implementation:ready`, `orchestration:epic-ready`, `orchestration:epic-implemented`. Missing `orchestration:epic-reviewed` — the 4-step orchestration pipeline is paused at step 2.

---

## 3. Root Cause Analysis

### 3.1 Immediate Cause

**Class A:** The opencode permission ruleset contains the entry `{"permission":"bash","pattern":"*","action":"ask"}` which routes all bash tool invocations to a human confirmation gate. The `code-reviewer` subagent (session `ses_2ce0401afffe8czdSjEG7V3FqT`) simultaneously queued four bash commands:

```
gh pr view 5 --repo intel-agency/workflow-orchestration-queue-zulu48 --json ...
gh pr diff 5 --repo intel-agency/workflow-orchestration-queue-zulu48
gh api repos/intel-agency/workflow-orchestration-queue-zulu48/pulls/5/reviews
gh api repos/intel-agency/workflow-orchestration-queue-zulu48/pulls/5/comments
```

All four were evaluated as `action: ask` and placed in a `permission.asked` queue. In headless workflow mode, no human is present to answer. The subagent produced no further output. Fifteen minutes later the watchdog — which tracks "no output from client or server" — fired and sent SIGTERM (exit 143).

**Class B:** The hatchling build system in `python-ci` could not find a package directory:

```
ValueError: Unable to determine which files to ship inside the wheel using the following heuristics
The most likely cause of this is that there is no directory that matches the name of your project (workflow_orchestration_queue).
```

The Python package source is under `src/sentinel/`, but the project name in `pyproject.toml` resolves to `workflow_orchestration_queue`, and no explicit `packages = [...]` directive was added to `[tool.hatch.build.targets.wheel]`.

### 3.2 Mechanism

**Class A:**

1. Orchestrator matched the `orchestration:epic-implemented` + `epic` labels on issue #4 (correct match, correct clause 4).
2. Orchestrator completed required pre-work: read memory graph, posted status updates, fetched `review-epic-prs` workflow instructions, found PR #5.
3. Orchestrator delegated "Review and merge PR #5" to the `code-reviewer` subagent at 01:08:11Z.
4. `code-reviewer` used `sequential_thinking` (6 thoughts), planned to gather PR data in parallel, then issued 4 concurrent bash commands at 01:08:35Z.
5. All 4 bash commands were evaluated against the ruleset, matched `{"permission":"bash","pattern":"*","action":"ask"}`, and published `permission.asked` events.
6. No subsequent tool calls or outputs were produced. Server bus continued emitting `message.part.delta` and `message.part.updated` events at 01:08:35Z — then nothing for 15 minutes.
7. Watchdog evaluated at 01:23:48Z: "opencode idle for 15m (no output from client or server); terminating." Process sent SIGTERM; exit code 143.

**Class B:**

1. The `dynamic-workflow-project-setup` branch added a `pyproject.toml` with project name `workflow-orchestration-queue` (hyphens → underscores → `workflow_orchestration_queue`).
2. Source code lives in `src/sentinel/` — not `src/workflow_orchestration_queue/`.
3. When `python-ci` runs `uv pip install -e .`, hatchling tries to build the wheel, cannot find `workflow_orchestration_queue/` directory, raises `ValueError` on file selection.
4. All three fix commit messages address different symptoms ("pin pydantic", "configure hatch to find packages in src/") but none reached the correct fix (declaring `packages = ["src/sentinel"]` or renaming the package directory).

### 3.3 Why This Area Is Fragile

**Class A:** The opencode permission model has a dual-source problem:
- The top-level permission config allows `bash/*` globally (`action: allow`), but the subagent-level config overrides this to `action: ask`.
- The `code-reviewer` subagent's bash commands were classified as requiring human confirmation — a sensible default in interactive mode, but fatal in headless CI.
- The watchdog measures *output absence* as its proxy for idleness. A subagent waiting silently for a permission gate looks identical to a frozen process. There is no distinct signal that separates "waiting for permission" from "stuck in a loop" or "crashed silently."
- This pattern will recur any time any subagent that needs to run `bash` reaches this permission gate in a new run, until the policy is updated.

**Class B:** The project structure chosen by the AI-generated setup code (`src/sentinel/`) does not align with the project discovery name (`workflow_orchestration_queue`). Hatchling's auto-discovery relies on matching the project name string, and the mismatch is silent until build time. Each fix attempt diagnosed a secondary symptom rather than the structural mismatch.

### 3.4 Confidence / Uncertainty Notes

- **Directly observed in Class A logs:** Last real output at `01:08:35Z` was the four `permission.asked` events. Server log shows `message.part.delta` events up to `01:08:29Z`, a 5-second gap to `01:08:35Z`, then silence. Watchdog fires at `01:23:48Z`. This is `15m 13s` of silence, consistent with the 15-minute threshold. Exit code 143 = SIGTERM.
- **Directly observed in Class B logs:** `ValueError` across all 6 runs with identical traceback root. The error is reproducible and deterministic.
- **Strongly inferred:** The earlier `implement-epic` run (23673604298) succeeded because the `developer` agent's bash commands were either pre-approved in the global ruleset or did not trigger the `ask` policy. Direct comparison of the permission rulesets between sessions was not available in the retrieved logs, but the behavior difference is consistent with agent-scoped permission inheritance.
- **Not yet proven:** Whether the `code-reviewer` subagent's bash policy is governed by the subagent-level permission block `{"permission":"bash","pattern":"*","action":"ask"}` or inherited from a different scope. The evidence strongly implies the subagent scope.

---

## 4. Solutions with Pros/Cons

### Solution A: Expand bash allowlist for `gh` read operations in subagent context

**Change:** Add a policy entry before the catch-all `ask` rule that pre-approves `gh` CLI read operations (e.g., `gh pr view`, `gh pr diff`, `gh api .../reviews`, `gh api .../comments`) in all subagent permission rulesets. Specifically, insert `{"permission":"bash","pattern":"gh pr *","action":"allow"}` and `{"permission":"bash","pattern":"gh api *","action":"allow"}` before the current wildcard `ask` rule in the permission configuration that governs the `code-reviewer` (and by extension all subagents).

| Pros | Cons |
|------|------|
| Directly fixes the exact blocked commands | Requires knowing which bash patterns are needed up-front; new bash patterns might still hit `ask` |
| Minimal change, low risk of broader side-effects | Pattern-matching on bash strings can be fragile if commands are parameterized differently |
| Unblocks the pipeline immediately — re-trigger by reapplying `orchestration:epic-implemented` | Does not fix the underlying design issue of using bash for read operations rather than MCP/API calls |
| Consistent with how the `developer` agent already works (read operations allowed) | |

**Implementation notes:**

The allowlist entries should be placed in the workflow-level permission config that generates subagent permission arrays (visible in the server logs as the `ruleset=` parameter). The relevant pattern additions before the `{"permission":"bash","pattern":"*","action":"ask"}` entry are:

```json
{"permission":"bash","pattern":"gh pr view *","action":"allow"},
{"permission":"bash","pattern":"gh pr diff *","action":"allow"},
{"permission":"bash","pattern":"gh api *","action":"allow"},
{"permission":"bash","pattern":"gh issue *","action":"allow"}
```

After the change, re-trigger by removing and re-applying `orchestration:epic-implemented` to issue #4.

---

### Solution B: Raise the idle timeout from 15 minutes to 30+ minutes

**Change:** Increase the opencode idle watchdog threshold from the current 15 minutes to 30 or 45 minutes. This gives subagents more time to receive permission grants in interactive-adjacent scenarios, without changing the permission policy.

| Pros | Cons |
|------|------|
| Zero configuration change to the permission system | Does not fix the root cause — the agent is still blocked, just killed later |
| Reduces false-positive kills for legitimately slow subagents | Doubles or triples wall-clock cost of a stalled run before diagnosis |
| Easy single-parameter change | In a headless run, nobody is granting permissions — the wait is infinite; timeout just delays the failure |
| | Does nothing for the deterministic `python-ci` failure (Class B) |

**Implementation notes:**

The watchdog threshold is configured in `scripts/devcontainer-opencode.sh`. Locate the `IDLE_TIMEOUT` or equivalent variable and increase it. This is a band-aid, not a fix.

---

### Solution C: Refactor code-reviewer to use MCP/API tools instead of bash for PR data gathering

**Change:** Update the `code-reviewer` agent definition to use MCP GitHub tools (`mcp_github_pull_request_read`, `mcp_github_get_file_contents`, etc.) for reading PR data instead of shelling out to `gh`. The MCP tools are already allowed in the permission ruleset (`{"permission":"mcp_tool","pattern":"*","action":"allow"}`) across all agent contexts, and do not require bash.

| Pros | Cons |
|------|------|
| Eliminates the permission conflict entirely for read operations | Requires modifying the agent instruction file for `code-reviewer` |
| MCP tool calls are already unconditionally permitted — no policy change needed | Not all `gh` functionality is available via MCP (e.g., `gh pr diff` requires a custom formulation) |
| Makes the agent work the same in interactive and headless modes | More implementation work than Solution A |
| Consistent with the spirit of MCP-first tool use | Agent instructions must be tested after the change |

**Implementation notes:**

Edit `.opencode/agents/code-reviewer.md` (or the remote instruction source `agent-instructions/code-reviewer.md`) to prefer `mcp_github_pull_request_read` for PR metadata, `mcp_github_get_file_contents` for file diffs, and `mcp_github_search_code` for code inspection. `gh pr diff` can be replaced by fetching file contents from the PR head commit via MCP. This is the medium-term structural fix.

---

### Solution D: Fix python-ci hatchling config (for Class B)

**Change:** Add explicit package declaration to `pyproject.toml` in the `dynamic-workflow-project-setup` branch so hatchling finds the correct source directory.

| Pros | Cons |
|------|------|
| Directly resolves all 6 `python-ci` failures | Small change, but requires identifying the correct package name / directory in the src/ layout |
| Unblocks PR #2 merge | PR #2 may not be required to proceed with the epic-level work — the failure is in a setup branch |
| Needed regardless of Classes A/B fix status | |

**Implementation notes:**

In `pyproject.toml`, under `[tool.hatch.build.targets.wheel]`:

```toml
[tool.hatch.build.targets.wheel]
packages = ["src/sentinel"]
```

Or, if the package was intended to be named `workflow_orchestration_queue`, rename `src/sentinel/` to `src/workflow_orchestration_queue/`. Coordinating with Class A resolution: the package structure should already be decided by the `implement-epic` output (which succeeded) — check `src/` directory on the `issues/4-standardized-work-item-interface` branch for the authoritative layout.

---

## 5. Recommendation

### Recommended Path

1. **Immediate (Class A unblock):** Apply Solution A — add `gh pr`, `gh api`, and `gh issue` patterns to the subagent bash allowlist. This has the lowest risk and is a one-line-per-pattern change. After the change, re-trigger the orchestration by removing `orchestration:epic-implemented` from issue #4 and reapplying it.

2. **Short-term (Class A hardening):** Apply Solution C in parallel with or shortly after Solution A — move `code-reviewer`'s PR data gathering to MCP tools. This is the structurally correct fix and prevents future bash permission blockers for any new `gh` command patterns not yet in the allowlist.

3. **Concurrent (Class B fix):** Apply Solution D — fix `pyproject.toml` to declare `packages = ["src/sentinel"]`. This is an independent failure class that has no interaction with Class A. It should be done regardless, as PR #2 cannot merge cleanly with python-ci failing.

4. **Do not pursue Solution B (timeout increase) as a standalone fix** — it defers diagnosis without resolving anything.

### Why This Recommendation

**Solution A is best immediately** because:
- The exact commands that are blocked are known from the log (`gh pr view`, `gh pr diff`, `gh api .../reviews`, `gh api .../comments`). A targeted allowlist eliminates the exact blocker with zero functional change to security posture for read-only `gh` calls.
- It unblocks the stalled pipeline in minutes. Issue #4 is paused mid-sequence; the epic cannot be closed, and the next epic cannot begin, until this is resolved.
- It does not touch the agent instruction files, which is a lower-risk change surface.

**Solution A alone is insufficient long-term** because:
- The pattern-allowlist approach requires maintenance every time a new `gh` read command pattern is used. Solution C eliminates the maintenance burden by using MCP tools that are already fully allowed.
- If a future agent uses a slightly different `gh` invocation (e.g., different flags or arguments outside the approved patterns), the blocker reappears silently.

**Solution D (Class B) is independent** and should be done regardless of Class A:
- PR #2 is the project setup PR. While the epic-level work can proceed via the main branch, having the setup PR stalled with 0% CI pass rate is a hygiene issue that will compound if other developers or workflows depend on it.
- The fix is a one-line `pyproject.toml` change. Risk is minimal.

**What this leaves unresolved:**
- The watchdog still measures *output silence* as its proxy for idleness, meaning it cannot distinguish "waiting for permission" from "crashed." A future improvement would be to emit a heartbeat or a distinct "waiting for permission" signal that the watchdog can recognize differently.

---

## 6. Appendix

### 6.1 Raw Error Signatures

**Class A — Permission blocked / idle timeout:**

```text
INFO  2026-03-28T01:08:35 +0ms service=permission permission=bash pattern=gh pr view 5 --repo intel-agency/workflow-orchestration-queue-zulu48 --json ... action={"permission":"bash","pattern":"*","action":"ask"} evaluated
INFO  2026-03-28T01:08:35 +0ms service=bus type=permission.asked publishing
...
##[error]opencode idle for 15m (no output from client or server); terminating
opencode exit code: 143
```

**Class B — Hatchling build error:**

```text
File ".../hatchling/builders/wheel.py", line 258, in default_file_selection_options
    raise ValueError(message)
ValueError: Unable to determine which files to ship inside the wheel using the following heuristics:
https://hatch.pypa.io/latest/plugins/builder/wheel/#default-file-selection

The most likely cause of this is that there is no directory that matches
the name of your project (workflow_orchestration_queue).
```

### 6.2 Representative Last-Known-Good / Last-Known-Bad Output

**Class A — Last meaningful activity before freeze (01:08:35Z):**

```text
orchestrate  Execute orchestrator agent in devcontainer  2026-03-28T01:08:24Z
[server] Thought 1/6
[server] Task: Execute PR review, approval, and merge workflow for PR #5...
[server] Planning the approach:
[server] 1. First, gather PR information - details, files changed, CI status, review comments
[server] ...Let me start by gathering all the PR information in parallel.

orchestrate  Execute orchestrator agent in devcontainer  2026-03-28T01:08:35Z
INFO service=permission permission=bash pattern=gh pr view 5 ...
action={"permission":"bash","pattern":"*","action":"ask"} evaluated
INFO service=bus type=permission.asked publishing
[... 4 permission.asked events at 01:08:35Z ...]
[... silence for 15 minutes ...]
```

**Class A — Watchdog trigger (01:23:48Z):**

```text
2026-03-28T01:23:48.4274316Z ##[error]opencode idle for 15m (no output from client or server); terminating
2026-03-28T01:23:58.4310214Z opencode exit code: 143
```

**Class B — Last line before error:**

```text
lint  2026-03-28T00:34:53.2097328Z     val = self.func(instance)
lint  2026-03-28T00:34:53.2097599Z           ^^^^^^^^^^^^^^^^^^^
lint  2026-03-28T00:34:53.2097838Z File ".../hatchling/builders/wheel.py", line 258, in default_file_selection_options
lint  2026-03-28T00:34:53.2099347Z     raise ValueError(message)
lint  2026-03-28T00:34:53.2100077Z ValueError: Unable to determine which files to ship inside the wheel
```

### 6.3 Sources Consulted

- Workflow runs: 23673934864 (Class A, failing), 23673604298 (successful `implement-epic` baseline), 23673566806, 23673566782, 23673407688 (successful orchestrator runs)
- Workflow runs (Class B): 23673339904, 23673363456, 23673364164, 23673398844, 23673399362, 23673413056
- Validate runs (passing baselines): 23673413068, 23673399363, 23673364172, 23673339909, 23673911459
- Issues: #4 (Epic: Phase 1 — Task 1.1 — Standardized Work Item Interface) — state open, labels checked
- PRs: #2 (dynamic-workflow-project-setup, state OPEN), #5 (feat(sentinel): implement standardized work item interface, validate/CodeQL passing)
- Log analysis: `gh run view --log-failed` for runs 23673934864 and 23673339904
- Server-side logs: embedded in the orchestrator step log for run 23673934864
- Repo: `intel-agency/workflow-orchestration-queue-zulu48` — created 2026-03-28T00:10:22Z, branch `main`
