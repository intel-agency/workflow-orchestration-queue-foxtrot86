# Fix Plan: workflow-orchestration-queue-zulu48

**Companion to:** [docs/zulu48-forensic-report.md](zulu48-forensic-report.md)  
**Date:** 2026-07-03  
**Scope:** Both failure classes from the forensic report — Class A (orchestrator idle timeout) and Class B (python-ci hatchling build failure)

---

## Quick Reference

| Class | Failure | Affected File(s) | Fix Effort |
|-------|---------|------------------|-----------|
| A | Orchestrator blocks on `bash: ask` approvals in headless CI | `.opencode/agents/code-reviewer.md` (+ `cloud-infra-expert.md`, `database-admin.md`) | Low — single-line change per agent |
| B | Hatchling wheel build: no directory matching project name | `pyproject.toml` | Low — already partially fixed; verify CI |

---

## Class A: Orchestrator Idle Timeout — Permission Blocking

### Background

When the orchestrator delegated to the `code-reviewer` subagent to review PR #5 (run 23673934864), the agent attempted four parallel `gh` CLI commands:

```
gh pr view 5
gh pr diff 5
gh api .../reviews
gh api .../comments
```

All four were evaluated against permission ruleset entry `{"permission":"bash","pattern":"*","action":"ask"}`. Each produced a `permission.asked` Bus event, suspending the command and waiting for a human to respond via the UI. In headless CI, no human is present; the approvals never arrive. The idle watchdog at `IDLE_TIMEOUT_SECS=900` fired after 15 minutes and killed the process (`exit code: 143`).

### Root Cause

The `code-reviewer.md` agent definition has this in its YAML frontmatter:

```yaml
permission:
  edit: deny
  bash: ask
```

Per the opencode permissions documentation:

> *"Agent permissions are merged with the global config, and **agent rules take precedence**."*

This means that even adding `"bash": "allow"` to the global `opencode.json` would NOT fix this — the agent-level `bash: ask` wins. The fix MUST be in the agent definition itself.

### Affected Agents (Template Repo)

Three agent definitions in `.opencode/agents/` have `bash: ask`:

| Agent | File | Current Permission |
|-------|------|-------------------|
| Code Reviewer | `.opencode/agents/code-reviewer.md` | `bash: ask` |
| Cloud Infra Expert | `.opencode/agents/cloud-infra-expert.md` | `bash: ask` |
| Database Admin | `.opencode/agents/database-admin.md` | `bash: ask` |

All three also have `write: false` and `edit: false` in their `tools:` section, so they cannot write files. The `bash` permission blocks are purely defensive, but they are incompatible with non-interactive operation.

### Fix Options

#### Option A — Global Allow (Recommended for CI, Simplest)

Change `bash: ask` → `bash: allow` in each affected agent frontmatter.

**`code-reviewer.md` — Before:**
```yaml
permission:
  edit: deny
  bash: ask
```

**`code-reviewer.md` — After:**
```yaml
permission:
  edit: deny
  bash: allow
```

Apply the same `bash: ask` → `bash: allow` change to `cloud-infra-expert.md` and `database-admin.md`.

| Pro | Con |
|-----|-----|
| Fixes the blocking immediately | Allows the agent to run any bash command |
| Minimal diff; easy to review | Slightly reduced interactive-session safety |
| `write/edit: false` already prevents file modifications | |

**Rationale:** The `code-reviewer` already has `write: false`, `edit: false`, and `permission: edit: deny`. It cannot alter any files. The bash commands it actually uses are read-only `gh` and `git` CLI queries. Allowing all bash is safe in context.

---

#### Option B — Targeted Pattern Allowlist (Recommended for Production)

Replace `bash: ask` with a granular ruleset that allows only known-safe commands and denies everything else.

```yaml
permission:
  edit: deny
  bash:
    "gh pr *": allow
    "gh api *": allow
    "gh issue *": allow
    "gh repo *": allow
    "git log *": allow
    "git diff *": allow
    "git show *": allow
    "git status *": allow
    "git blame *": allow
    "*": deny
```

| Pro | Con |
|-----|-----|
| Least-privilege; only expected commands allowed | Must be kept in sync with agent behavior |
| Clear documentation of what the agent is allowed to do | Could block the agent if it tries a new command form |
| Denies `rm`, `curl`, etc. explicitly | More lines to review |

> **Note on pattern syntax:** opencode pattern matching uses `*` for zero-or-more characters. `"gh pr *"` matches `gh pr view 5`, `gh pr diff 5`, etc. Commands with NO arguments (e.g., `git status`) also need the trailing ` *` if arguments might be added (i.e., `"git status *"` covers `git status --porcelain`).

---

#### Option C — Global opencode.json "Yolo" Mode (Not Recommended Here)

Set the project-level config to allow everything:

```json
{
  "permission": "allow"
}
```

This is the opencode equivalent of a `--yolo` or `--allow-all` flag (there is no such CLI flag — it must be set in config). It overrides all agent-level restrictions.

| Pro | Con |
|-----|-----|
| One-line fix; no need to touch agent files | Removes ALL permission guards for ALL agents |
| Works for any agent, including future ones | Prevents using `permission: deny` as a safety net |
| | Agent-level `bash: ask` would override this (agent rules take precedence) — so it does NOT actually fix the problem for agents with explicit `bash: ask` |

> **Important:** Due to "agent rules take precedence", Option C alone does **not** fix agents that have explicit `bash: ask` in their frontmatter. It only helps agents that have no bash permission entry at all. **Option A or B is required.**

---

### Implementation Plan (Class A)

1. **Apply to template repo** (this repo — `intel-agency/ai-new-workflow-app-template`):
   - Edit `.opencode/agents/code-reviewer.md`: change `bash: ask` → `bash: allow`
   - Edit `.opencode/agents/cloud-infra-expert.md`: same change
   - Edit `.opencode/agents/database-admin.md`: same change
   - Run `./scripts/validate.ps1 -All` (especially `test/validate-agents.ps1`)
   - Commit and push; confirm validate CI is green

2. **Apply to deployed zulu48 instance** (`intel-agency/workflow-orchestration-queue-zulu48`):
   - Open a PR against `main` with the same three agent file changes
   - After merge, re-trigger the orchestrator on issue #4 by re-applying the `orchestration:epic-implemented` label (which triggers the orchestrator-agent workflow)

3. **Verify fix** in the next orchestrator run:
   - Watch for `bash` tool calls in the log — they should now show `action=allow evaluated` instead of `action=ask evaluated`
   - Confirm no `permission.asked` Bus events appear in the server log
   - Confirm run completes without idle timeout

---

### Memory Tool Question

The failed run log showed:
```
⏱ memory_read_graph Unknown
```

The `Unknown` status is **not a JSON parse error**. It is opencode's display for an empty graph result (no entities or relations yet). The memory MCP server (`@modelcontextprotocol/server-memory`) starts with an empty JSONL file on first run; `read_graph` returns an empty result, which opencode renders as `Unknown`. This is expected behavior for a freshly-deployed repo.

No JSONL parse error was observed in the logs from run 23673934864. The memory tool worked normally; the current knowledge graph is empty because no prior orchestration run completed successfully to persist any entities.

---

## Class B: Python-CI Hatchling Build Failure

### Background

The `dynamic-workflow-project-setup` branch added a Python application at `src/` along with a `pyproject.toml` and GitHub Actions `python-ci.yml` workflow. The CI failed 6 consecutive times.

### Root Cause (Original)

Hatchling's automatic package discovery expects a directory matching the normalized project name (`workflow_orchestration_queue`) to exist. The actual source layout is:

```
src/
  __init__.py
  orchestrator_sentinel.py
  notifier_service.py
  models/
  queue/
```

No `src/workflow_orchestration_queue/` directory exists. Original `pyproject.toml` had no explicit `packages` setting, so discovery failed with:

```
ValueError: Unable to determine which files to ship inside the wheel using 
the following heuristics: ...
The most likely cause of this is that there is no directory that matches 
the name of your project (workflow_orchestration_queue).
```

### Current State (Partially Fixed)

A previous agent run added the following to `pyproject.toml`:

```toml
[tool.hatch.build.targets.wheel]
packages = ["src"]
```

And `src/__init__.py` now exists on the branch. This tells hatchling explicitly which Python package to bundle.

The resulting wheel installs `src` as a Python package, making `import src.orchestrator_sentinel` work — which aligns with the existing `[project.scripts]` entries:

```toml
[project.scripts]
sentinel = "src.orchestrator_sentinel:main"
notifier = "src.notifier_service:main"
```

### Verification Steps Required

The `packages = ["src"]` change should have fixed the hatchling wheel build error. However, CI may still show failures for other reasons:

1. **Check CI status** on the PR: `gh pr checks 2 --repo intel-agency/workflow-orchestration-queue-zulu48`
2. **If wheel build is failing** → the `packages = ["src"]` fix is either not committed or hatchling is caching the old config. Confirm the pyproject.toml on the branch.
3. **If tests are failing** → check `tests/` for import errors. Tests that import `from src.xxx` should work with `packages = ["src"]` but may need `src/__init__.py` to exist (it does).
4. **If ruff/mypy is failing** → check for lint/type errors introduced in the added source files.

### Recommended Alternative Fix (Cleaner Python Packaging)

Packaging `src` as a module is unconventional and risks namespace conflicts with any other `src` package. The standard `src/` layout for hatchling uses a sub-package:

```
src/
  workflow_orchestration_queue/
    __init__.py
    orchestrator_sentinel.py
    notifier_service.py
    models/
    queue/
```

With `pyproject.toml`:
```toml
[tool.hatch.build.targets.wheel]
packages = ["src/workflow_orchestration_queue"]

[project.scripts]
sentinel = "workflow_orchestration_queue.orchestrator_sentinel:main"
notifier = "workflow_orchestration_queue.notifier_service:main"
```

This is the correct long-term structure but requires renaming the directory and updating all imports. This is a larger change and should be deferred unless the `packages = ["src"]` approach is causing ongoing issues.

### Implementation Plan (Class B)

1. **Check current CI status** on PR #2 (`dynamic-workflow-project-setup`):
   ```bash
   gh pr checks 2 --repo intel-agency/workflow-orchestration-queue-zulu48
   ```

2. **If wheel build is still failing:**
   - Confirm `pyproject.toml` has `packages = ["src"]` on the branch
   - Confirm `src/__init__.py` exists on the branch
   - If missing either, add them and push

3. **If test failures remain (separate from wheel build):**
   - Run the tests locally to classify the failures:
     ```bash
     cd /workspaces/workflow-orchestration-queue-zulu48
     uv sync
     uv run pytest tests/ -v
     ```
   - Fix test-specific issues (e.g., missing mocks, fixture paths, import errors)

4. **After all checks green, merge PR #2:**
   ```bash
   gh pr merge 2 --squash --repo intel-agency/workflow-orchestration-queue-zulu48
   ```

---

## Sequencing and Dependencies

```
Class A fix (template repo) → commit/push → validate CI green
         ↓
Class A fix (zulu48 instance) → PR → merge
         ↓  
Re-trigger orchestrator on issue #4 (re-apply orchestration:epic-implemented label)
         ↓
Orchestrator completes code review of PR #5 successfully

Class B: Parallel track (independent of Class A)
Check python-ci status → if still failing, apply remaining fixes → merge PR #2
```

The two classes are independent. Class B (python-ci) can be fixed and merged concurrently with Class A.

---

## Risk Assessment

| Risk | Likelihood | Mitigation |
|------|-----------|-----------|
| `bash: allow` in code-reviewer allows unintended commands | Low | `write: false`, `edit: false`, `permission: edit: deny` still block file modifications |
| Other agents in zulu48 also block on `bash: ask` | Medium | Check `validate-agents.ps1` output; check all agent frontmatter before retriggering |
| Orchestrator re-run still fails for a different reason | Medium | Monitor run logs; next most likely issue is model context window or LLM quality |
| Python `src` package naming causes `pip` conflicts | Low | No known `src` package on PyPI; acceptable for private deployment |
| Class B CI failures are test-related, not wheel build | Medium | Run tests locally to classify before assuming wheel fix is sufficient |

---

## References

- [opencode Permissions Documentation](https://opencode.ai/docs/permissions)
- [docs/zulu48-forensic-report.md](zulu48-forensic-report.md) — Root cause evidence
- Failed run logs: workflow run ID `23673934864` in `intel-agency/workflow-orchestration-queue-zulu48`
- PR #2: `dynamic-workflow-project-setup` — Python project setup (Class B)
- Issue #4: Blocked at `orchestration:epic-implemented` stage (Class A)
