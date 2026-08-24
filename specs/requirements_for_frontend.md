# 009 - Core Library Split

> **Superseded in part by [011](011-tool-orchestration-and-agent-workflows.md).**
> The string *formula* encoding (`formulas.py` / `safe_formula.py`) has been
> removed; the structured `ToolCall` is now the canonical durable encoding of a
> tool invocation. References to formulas below should be read as `ToolCall`.

## 1. Overview
This specification defines how Simple Steps will be separated into two repositories:

- `simple-steps-core`: the reusable Python library containing the stable execution model, operation registry, formula system, pack loading, and optional agent runtime primitives.
- `simple-steps`: the product/application repository containing the FastAPI host, React frontend, desktop/local launchers, deployment configuration, and product-specific persistence/integration code.

The goal is to make development, testing, and production rollout simpler by separating stable tool execution from product delivery concerns.

This spec treats operations as approved production tools. The workflow formula is the durable representation of a tool invocation. Agents may assist in composing workflows, but production execution must remain constrained to reviewed, registered operations.

## 2. Scope

**In Scope:**
- Define repository boundaries between core library code and app-host code.
- Define the required package structure for `simple-steps-core`.
- Define the architectural relationship between sessions, operations, formulas, packs, and agent tooling.
- Define testing and release expectations for the new core library.
- Define migration requirements so existing behavior can be moved with minimal breakage.

**Out of Scope:**
- Full implementation of the repo split.
- Final deployment manifests for the application repo.
- Detailed frontend redesign work.
- New operation behavior unrelated to the repo boundary.

## 3. Architecture Intent

### 3.1 Core Principle
The system shall be structured around a tool-first production model:

- Humans author and harden stable Python operations.
- Operations are registered as production-safe tools.
- Agents and users compose workflows by selecting and configuring those tools.
- Workflow formulas are persisted as the editable, auditable representation of those tool calls.
- Production runtime executes approved operations only; it does not execute arbitrary agent-authored Python source.

### 3.2 Repository Roles

#### `simple-steps-core`
The core repository shall contain reusable Python library code that is valuable independent of any specific UI or deployment target.

#### `simple-steps`
The application repository shall import `simple-steps-core` and provide product-specific hosting concerns, including API transport, static asset serving, desktop/window wrappers, environment-specific config, and deployment tooling.

## 4. Functional Requirements

### 4.1 Repository Boundary
- **REQ-CORE-001:** The `simple-steps-core` repository shall be installable as a standalone Python package using a standard `src/` layout.
- **REQ-CORE-002:** The `simple-steps-core` repository shall not contain React, Vite, bundled frontend assets, or frontend build scripts.
- **REQ-CORE-003:** The `simple-steps-core` repository shall not require static asset serving, browser launch behavior, or deployment-specific runtime code.
- **REQ-CORE-004:** The `simple-steps` repository shall depend on `simple-steps-core` through a package dependency rather than copying core source files.

### 4.2 Tool / Operation Model
- **REQ-CORE-005:** A registered operation shall be treated as the canonical production tool abstraction.
- **REQ-CORE-006:** The structured `ToolCall` shall be the canonical durable encoding of a tool invocation.
- **REQ-CORE-007:** The core library shall provide a structured, serializable representation of a tool call (`ToolCall`: `operation_id` + `arguments`).
- **REQ-CORE-008:** Tool calls shall serialize to and from JSON and be validatable against the operation registry.
- **REQ-CORE-009:** Production execution shall be constrained to registered operations and validated arguments.

### 4.3 Session and Execution Context
- **REQ-CORE-010:** Core execution shall support session-scoped result isolation so independent users or browser contexts do not collide in shared runtime state.
- **REQ-CORE-011:** The core library shall expose a session-aware execution context abstraction that can be used by API hosts, tests, and agent flows.
- **REQ-CORE-012:** Session-scoped references for prior step outputs shall remain resolvable across workflow execution.

### 4.4 Operation Registry and Packs
- **REQ-CORE-013:** The core library shall own the operation registration system, operation metadata, and operation lookup behavior.
- **REQ-CORE-014:** The core library shall own pack discovery, pack loading, and pack management behavior that is not tied to a specific frontend or deployment target.
- **REQ-CORE-015:** Pack and operation metadata shall remain accessible to downstream hosts for API exposure, UI rendering, and agent context building.

### 4.5 Agent Integration
- **REQ-CORE-016:** Agent functionality in the core library shall be optional and installable through extras rather than mandatory runtime dependencies.
- **REQ-CORE-017:** The reusable agent subsystem shall operate on structured workflow/tool context rather than product-specific HTTP request objects.
- **REQ-CORE-018:** The reusable agent subsystem shall be able to reason over available operations, current workflow state, and session-aware references.
- **REQ-CORE-019:** FastAPI routers, WebSocket transport, and persisted UI-facing agent config storage shall remain outside the reusable core agent subsystem.
- **REQ-CORE-020:** The agent runtime shall facilitate workflow composition and diagnosis, but shall not define new production runtime behavior via arbitrary source generation.

### 4.6 Package Structure
- **REQ-CORE-021:** The core package shall be organized by concern rather than as a flat module list.
- **REQ-CORE-022:** The core package shall define a documented public API surface and treat other modules as internal unless explicitly exported.
- **REQ-CORE-023:** Domain models and formula logic shall not depend on API host code or frontend concerns.
- **REQ-CORE-024:** Execution logic may depend on domain abstractions, but domain abstractions shall not depend on execution modules.

### 4.7 Testing and Release
- **REQ-CORE-025:** The core repository shall provide unit tests for deterministic library behavior independent of the application host.
- **REQ-CORE-026:** The core repository shall provide integration tests for pack loading, workflow execution, and formula/tool-call flows.
- **REQ-CORE-027:** The core repository shall provide contract tests for the public API surface relied on by the application repo.
- **REQ-CORE-028:** The core repository shall be buildable as a wheel/sdist in CI without requiring frontend tooling.
- **REQ-CORE-029:** The application repo shall own end-to-end tests for HTTP routes, frontend integration, and deployment packaging.

## 5. Recommended Package Structure

The following package structure is the target for `simple-steps-core`:

```text
simple-steps-core/
├── pyproject.toml
├── README.md
├── src/
│   └── simple_steps_core/
│       ├── __init__.py
│       ├── api/
│       │   ├── __init__.py
│       │   ├── public.py
│       │   └── decorators.py
│       ├── domain/
│       │   ├── __init__.py
│       │   ├── models.py
│       │   ├── tool_calls.py
│       │   └── progress.py
│       ├── execution/
│       │   ├── __init__.py
│       │   ├── engine.py
│       │   ├── eval_engine.py
│       │   ├── orchestrators.py
│       │   ├── orchestration_ops.py
│       │   ├── context.py
│       │   └── step_proxy.py
│       ├── operations/
│       │   ├── __init__.py
│       │   ├── registry.py
│       │   └── builtin_operations.py
│       ├── packs/
│       │   ├── __init__.py
│       │   ├── models.py
│       │   ├── loader.py
│       │   ├── manager.py
│       │   └── discovery.py
│       ├── agent/
│       │   ├── __init__.py
│       │   ├── types.py
│       │   ├── prompts.py
│       │   ├── providers.py
│       │   ├── tools.py
│       │   ├── graph.py
│       │   └── service.py
│       ├── workspace/
│       │   ├── __init__.py
│       │   ├── session.py
│       │   ├── settings.py
│       │   └── state.py
│       └── py.typed
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── contract/
│   └── fixtures/
└── examples/
```

## 6. Ownership Rules

### 6.1 Core-Owned Concerns
The core repo should own:
- operation registration and metadata
- formula parsing and rendering
- structured tool-call types
- workflow execution engine
- session-aware result references
- pack loading and management
- reusable agent runtime primitives

### 6.2 App-Owned Concerns
The application repo should own:
- FastAPI route wiring
- WebSocket and REST transport shapes
- frontend API clients
- SPA/static asset serving
- browser/desktop launchers
- deployment configuration
- environment-specific config persistence for product UX

## 7. Migration Requirements

### 7.1 Extraction Order
- **REQ-MIG-001:** Migration shall begin by extracting reusable core modules before moving UI or deployment files.
- **REQ-MIG-002:** The first migration slice shall preserve existing runtime behavior through import-compatible wrappers or targeted rewrites.
- **REQ-MIG-003:** Frontend bundling into the Python package shall be removed from the core path during the split.
- **REQ-MIG-004:** API host code shall be updated to import core services and models from the new package rather than internal app-local copies.

### 7.2 Compatibility
- **REQ-MIG-005:** The split shall preserve the ability to enumerate available operations for frontend and agent consumers.
- **REQ-MIG-006:** The split shall preserve session-isolated step execution semantics.
- **REQ-MIG-007:** The split shall preserve formula parsing/building semantics for existing saved workflows unless a documented migration is introduced.

## 8. Testing Strategy

### 8.1 Core Repository
The core repository should validate the following in CI:
- editable install succeeds
- unit tests pass
- integration tests pass
- package builds as wheel/sdist
- optional agent extra can be installed in a separate CI job

### 8.2 Application Repository
The application repository should validate the following:
- API host boots against the pinned core version
- frontend can fetch operation/session/workflow metadata through app routes
- agent transport routes work against the core agent service
- packaged deployment artifacts include the frontend and run against the installed core library

## 9. Acceptance Criteria
- **AC-CORE-001:** A developer can install `simple-steps-core` independently and import the public execution and operation APIs without frontend dependencies.
- **AC-CORE-002:** A downstream app can enumerate operation metadata, parse/build formulas, and execute workflows using the installed core package.
- **AC-CORE-003:** Session-scoped execution remains isolated when multiple callers use the same app host.
- **AC-CORE-004:** The agent subsystem, when installed via extras, can reason over available operations and workflow context without depending on FastAPI route objects.
- **AC-CORE-005:** The application repo can host API routes and frontend assets without shipping those concerns inside the core package.

## 10. Open Questions
- Should workspace persistence helpers remain in core, or move fully into the application repo if they stay product-specific?
- Should the first migration preserve the existing `SIMPLE_STEPS.*` import paths via compatibility shims, or perform a single explicit namespace rewrite?
- Should structured tool-call objects become the canonical save format internally while formulas remain the UI-visible representation?