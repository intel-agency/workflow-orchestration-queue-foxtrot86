# Workflow Execution Plan: project-setup

**Generated:** 2026-03-28
**Workflow:** project-setup
**Repository:** intel-agency/workflow-orchestration-queue-foxtrot86
**Triggering Issue:** #1

---

## 1. Overview

This document outlines the execution plan for the `project-setup` dynamic workflow. This workflow initializes a fresh repository created from the `workflow-orchestration-queue-foxtrot86` template and prepares it for development of the workflow-orchestration-queue system.

**Workflow File:** `ai_instruction_modules/ai-workflow-assignments/dynamic-workflows/project-setup.md`

**Total Assignments:** 6 main assignments + 2 post-assignment events per assignment + 1 pre-script event + 1 post-script event

**High-level Goal:** Initialize the repository, create application plan, establish project structure, create documentation, and merge the setup PR.

---

## 2. Project Context Summary

### Application Overview
**workflow-orchestration-queue** is a headless agentic orchestration platform that transforms GitHub Issues into automated Execution Orders. It shifts AI from a passive co-pilot to an autonomous background production service.

### Technology Stack
- **Language:** Python 3.12+
- **Web Framework:** FastAPI + Uvicorn
- **Validation:** Pydantic
- **HTTP Client:** HTTPX (async)
- **Package Manager:** uv (Rust-based)
- **Containerization:** Docker, DevContainers
- **Shell Scripts:** PowerShell Core (pwsh), Bash

### Key Components
1. **The Ear (Notifier):** FastAPI webhook receiver for GitHub events
2. **The State (Work Queue):** GitHub Issues as distributed state management
3. **The Brain (Sentinel):** Async polling orchestrator service
4. **The Hands (Worker):** DevContainer-based AI execution environment

### Repository Details
- **Repository:** intel-agency/workflow-orchestration-queue-foxtrot86
- **Template Source:** intel-agency/workflow-orchestration-queue-foxtrot86
- **Pre-built Image:** ghcr.io/intel-agency/workflow-orchestration-prebuild/devcontainer:main-latest

### Key Constraints
- All GitHub Actions MUST be pinned to specific commit SHAs (not version tags)
- Python 3.12+ with uv package manager
- Follow the "Script-First Integration" principle using devcontainer-opencode.sh
- Security: HMAC signature validation, credential scrubbing, network isolation

---

## 3. Assignment Execution Plan

### Pre-script-begin Event

| Field | Content |
|---|---|
| **Assignment** | `create-workflow-plan`: Create Workflow Plan |
| **Goal** | Create a comprehensive workflow execution plan before any other assignments begin |
| **Key Acceptance Criteria** | - Dynamic workflow file read and understood<br>- All assignments traced and read<br>- All plan_docs/ files read<br>- Workflow execution plan produced<br>- Stakeholder approval obtained<br>- Committed to plan_docs/workflow-plan.md |
| **Project-Specific Notes** | This assignment creates the plan you are reading now. The plan_docs/ directory already contains detailed specifications for the workflow-orchestration-queue system. |
| **Prerequisites** | Dynamic workflow file accessible, plan_docs/ directory exists |
| **Dependencies** | None (first step) |
| **Risks / Challenges** | None - this is a planning exercise |
| **Events** | None |

---

### Main Assignment 1: init-existing-repository

| Field | Content |
|---|---|
| **Assignment** | `init-existing-repository`: Initialize Existing Repository |
| **Goal** | Initialize the repository with proper configuration, labels, milestones, and create the setup branch/PR |
| **Key Acceptance Criteria** | - New branch created (dynamic-workflow-project-setup)<br>- Branch protection ruleset imported<br>- GitHub Project created for issue tracking<br>- Labels imported from .github/.labels.json<br>- Workspace/devcontainer files renamed<br>- PR created to main |
| **Project-Specific Notes** | The repository is a fresh template clone. The AGENTS.md already exists with template content. Need to rename workspace file to match repo name. |
| **Prerequisites** | GitHub authentication with repo, project, read:org scopes |
| **Dependencies** | create-workflow-plan (pre-script event) |
| **Risks / Challenges** | - Branch protection import requires `administration: write` scope<br>- GitHub Project creation requires org permissions<br>- Must use GH_ORCHESTRATION_AGENT_TOKEN (not GITHUB_TOKEN) |
| **Events** | None within assignment; post-assignment-complete fires after |

**Output Reference:** `#initiate-new-repository.init-existing-repository`
**PR Number:** Will be extracted for use in pr-approval-and-merge

---

### Main Assignment 2: create-app-plan

| Field | Content |
|---|---|
| **Assignment** | `create-app-plan`: Create Application Plan |
| **Goal** | Create a comprehensive application plan based on the plan_docs/ specifications |
| **Key Acceptance Criteria** | - Application template analyzed<br>- Plan documented in GitHub issue using template<br>- Milestones created and linked<br>- Issue added to GitHub Project<br>- Appropriate labels applied |
| **Project-Specific Notes** | Plan docs already exist with detailed specifications (Development Plan v4.2, Architecture Guide v3.2, Implementation Spec v1.2). Need to synthesize into a single planning issue. |
| **Prerequisites** | init-existing-repository completed, plan_docs/ analyzed |
| **Dependencies** | init-existing-repository (for labels, project) |
| **Risks / Challenges** | - Planning issue template must be used<br>- Must NOT implement any code - planning only |
| **Events** | pre-assignment-begin: gather-context<br>on-assignment-failure: recover-from-error<br>post-assignment-complete: report-progress |

**Output Reference:** `#initiate-new-repository.create-app-plan`
**Plan Issue Number:** Will be used for post-script-complete label application

---

### Main Assignment 3: create-project-structure

| Field | Content |
|---|---|
| **Assignment** | `create-project-structure`: Create Project Structure |
| **Goal** | Create the actual project scaffolding based on the application plan |
| **Key Acceptance Criteria** | - Solution/project structure created<br>- Docker/Compose configurations created<br>- CI/CD foundation established<br>- Documentation structure created<br>- Repository summary created<br>- All GitHub Actions pinned to SHAs |
| **Project-Specific Notes** | Python project using uv. Structure should include:<br>- pyproject.toml, uv.lock<br>- src/notifier_service.py, src/orchestrator_sentinel.py<br>- src/models/work_item.py, src/queue/github_queue.py<br>- Dockerfile, docker-compose.yml<br>- .github/workflows/ with SHA-pinned actions |
| **Prerequisites** | create-app-plan completed, tech stack defined |
| **Dependencies** | create-app-plan (for structure decisions) |
| **Risks / Challenges** | - Must use uv for Python package management<br>- All workflow actions must be SHA-pinned<br>- Docker healthchecks must not use curl (use Python stdlib) |
| **Events** | None within assignment; post-assignment-complete fires after |

**Output Reference:** `#initiate-new-repository.create-project-structure`

---

### Main Assignment 4: create-agents-md-file

| Field | Content |
|---|---|
| **Assignment** | `create-agents-md-file`: Create AGENTS.md File |
| **Goal** | Create comprehensive AGENTS.md file for AI coding agents |
| **Key Acceptance Criteria** | - AGENTS.md exists at repository root<br>- Contains project overview, setup commands<br>- Contains project structure, code style<br>- Commands validated by running them<br>- Committed and pushed |
| **Project-Specific Notes** | AGENTS.md already exists from template. Need to update it with project-specific content for the workflow-orchestration-queue system, including Python/uv commands, Docker commands, and project-specific conventions. |
| **Prerequisites** | create-project-structure completed |
| **Dependencies** | create-project-structure (for commands to validate) |
| **Risks / Challenges** | - Must validate all commands work<br>- Must not duplicate README.md content |
| **Events** | None within assignment; post-assignment-complete fires after |

**Output Reference:** `#initiate-new-repository.create-agents-md-file`

---

### Main Assignment 5: debrief-and-document

| Field | Content |
|---|---|
| **Assignment** | `debrief-and-document`: Debrief and Document Learnings |
| **Goal** | Capture lessons learned, create debrief report |
| **Key Acceptance Criteria** | - Detailed report created using template<br>- All deviations documented<br>- Stakeholder approval obtained<br>- Report committed and pushed<br>- Execution trace saved |
| **Project-Specific Notes** | Document all deviations from assignments, any issues encountered, and recommendations for future improvements to the workflow system. |
| **Prerequisites** | All previous assignments completed |
| **Dependencies** | All main assignments |
| **Risks / Challenges** | - Must include all deviations<br>- Must capture execution trace |
| **Events** | None within assignment; post-assignment-complete fires after |

**Output Reference:** `#initiate-new-repository.debrief-and-document`

---

### Main Assignment 6: pr-approval-and-merge

| Field | Content |
|---|---|
| **Assignment** | `pr-approval-and-merge`: PR Approval and Merge |
| **Goal** | Complete the PR approval process and merge the setup branch |
| **Key Acceptance Criteria** | - CI verification passes (up to 3 fix cycles)<br>- Code review completed<br>- PR comments resolved<br>- Stakeholder approval obtained<br>- Merge performed<br>- Branch deleted<br>- Related issues closed |
| **Project-Specific Notes** | This is an automated setup PR - self-approval is acceptable. The PR number comes from init-existing-repository output. |
| **Prerequisites** | All previous assignments completed, PR exists |
| **Dependencies** | init-existing-repository (for $pr_num) |
| **Risks / Challenges** | - CI may fail requiring fixes<br>- Must use GH_ORCHESTRATION_AGENT_TOKEN for merge |
| **Input** | `$pr_num` from #initiate-new-repository.init-existing-repository |
| **Output** | `result`: "merged" | "pending" | "failed" |
| **Events** | None within assignment; post-assignment-complete fires after |

**Output Reference:** `#initiate-new-repository.pr-approval-and-merge`

---

## 4. Post-Assignment-Complete Events

After each main assignment, the following events fire:

| Event Assignment | Goal |
|---|---|
| `validate-assignment-completion` | Verify all acceptance criteria met, create validation report |
| `report-progress` | Generate progress report, capture outputs, create checkpoint |

**Output References:** `#events.post-assignment-complete.validate-assignment-completion`, `#events.post-assignment-complete.report-progress`

---

## 5. Post-Script-Complete Event

| Field | Content |
|---|---|
| **Event** | Apply `orchestration:plan-approved` label |
| **Goal** | Signal that the application plan is ready for epic creation |
| **Action** | Locate the application plan issue (from create-app-plan) and apply label `orchestration:plan-approved` |
| **Output Reference** | `#events.post-script-complete.plan-approved` |

---

## 6. Sequencing Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        PROJECT-SETUP WORKFLOW                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  [pre-script-begin]                                                          │
│       │                                                                      │
│       ▼                                                                      │
│  create-workflow-plan ──────────────────────────────────────────────────────│
│       │                                                                      │
│       ▼                                                                      │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │ MAIN ASSIGNMENTS (with post-assignment events after each)              │ │
│  │                                                                         │ │
│  │  init-existing-repository                                               │ │
│  │       │                                                                 │ │
│  │       ├── validate-assignment-completion                                │ │
│  │       └── report-progress                                               │ │
│  │       │                                                                 │ │
│  │       ▼                                                                 │ │
│  │  create-app-plan                                                        │ │
│  │       │                                                                 │ │
│  │       ├── validate-assignment-completion                                │ │
│  │       └── report-progress                                               │ │
│  │       │                                                                 │ │
│  │       ▼                                                                 │ │
│  │  create-project-structure                                               │ │
│  │       │                                                                 │ │
│  │       ├── validate-assignment-completion                                │ │
│  │       └── report-progress                                               │ │
│  │       │                                                                 │ │
│  │       ▼                                                                 │ │
│  │  create-agents-md-file                                                  │ │
│  │       │                                                                 │ │
│  │       ├── validate-assignment-completion                                │ │
│  │       └── report-progress                                               │ │
│  │       │                                                                 │ │
│  │       ▼                                                                 │ │
│  │  debrief-and-document                                                   │ │
│  │       │                                                                 │ │
│  │       ├── validate-assignment-completion                                │ │
│  │       └── report-progress                                               │ │
│  │       │                                                                 │ │
│  │       ▼                                                                 │ │
│  │  pr-approval-and-merge (uses $pr_num from init-existing-repository)    │ │
│  │       │                                                                 │ │
│  │       ├── validate-assignment-completion                                │ │
│  │       └── report-progress                                               │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
│       │                                                                      │
│       ▼                                                                      │
│  [post-script-complete]                                                      │
│       │                                                                      │
│       ▼                                                                      │
│  Apply orchestration:plan-approved label to app plan issue                   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 7. Open Questions

1. **GitHub Project Creation:** Does the orchestrator have the necessary `project` scope to create organization-level projects?
2. **Branch Protection:** Does the PAT have `administration: write` scope for importing branch protection rulesets?
3. **Existing Files:** The plan_docs/ directory already contains Python source files (github_queue.py, work_item.py, etc.). Should these be used as-is or regenerated?

---

## 8. Execution Notes

**2026-03-28 Execution:**
- Branch protection ruleset imported successfully (ID: 14455928)
- GitHub Project #30 "workflow-orchestration-queue-foxtrot86" already exists in the organization

---

## 8. Stakeholder Approval

**Status:** ⏳ Pending Approval

**Approval Statement:** _To be recorded after stakeholder review_

**Approved By:** _To be recorded_

**Date:** _To be recorded_
