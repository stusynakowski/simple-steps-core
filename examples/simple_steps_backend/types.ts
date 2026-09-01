// TypeScript types for the simple-steps React frontend.
// These mirror the simple-steps-core models and the backend API in `app.py`.
// Keep them in sync with the Python models (domain/models.py).

// ── Tool palette (GET /operations) ───────────────────────────────────────
export type ParamKind = "data" | "resource";

export interface OperationParam {
  name: string;
  type_name: string;
  required: boolean;
  default: unknown | null;
  kind: ParamKind;
}

/** JSON Schema (draft 2020-12 subset) for a tool's inputs/outputs. */
export type JSONSchema = Record<string, unknown>;

export interface ArgGuardrail {
  enum?: unknown[] | null;
  minimum?: number | null;
  maximum?: number | null;
  min_length?: number | null;
  max_length?: number | null;
  pattern?: string | null;
  note?: string;
}

export interface Guardrails {
  usage: string;
  rules: string[];
  arguments: Record<string, ArgGuardrail>;
  read_only: boolean;
  destructive: boolean;
  requires_confirmation: boolean;
}

/** prefab-ui protocol document: { view: <component tree>, state: {...} }. */
export type PrefabUI = Record<string, unknown>;

export interface OperationDefinition {
  operation_id: string;
  description: string;
  category: string;
  type: "source" | "map" | "filter" | "dataframe" | "expand" | "raw_output" | "orchestrator";
  params: OperationParam[];
  input_schema: JSONSchema;      // data params only — render forms from this
  output_schema: JSONSchema | null;
  dependencies: string[];        // resource param names (injected, not user-supplied)
  ui: PrefabUI | null;           // prefab-ui protocol (default auto-built; overridable)
  guardrails: Guardrails | null; // usage policy + enforced argument constraints
}

// ── Step authoring (StepSpec) ─────────────────────────────────────────────
export type OrchestrationMode = "single" | "map" | "filter" | "expand" | "collapse";
export type OnError = "collect" | "fail_fast" | "skip";

export interface OrchestrationConfig {
  mode: OrchestrationMode;       // default "single"
  over?: string | null;          // step reference to the collection (required unless single)
  item_arg?: string | null;
  concurrency: number;           // default 1
  on_error?: OnError | null;
  retries: number;               // default 0
  initial?: unknown | null;      // seed for "collapse"
}

export interface ExecutionConfig {
  mode: "sync" | "async";        // default "sync"
  run: "auto" | "manual";        // default "manual"
  timeout?: number | null;
  retries: number;
  cache: boolean;
}

/** An argument is a literal JSON value, or a string reference to a step (starts with "step"). */
export type Argument = unknown;

export interface StepSpec {
  step_id: string;
  name: string;                  // operation_id of the tool to run
  stage?: number | string | null; // optional group for staged execution
  arguments: Record<string, Argument>;
  orchestration: OrchestrationConfig;
  execution: ExecutionConfig;
}

// Convenience for constructing a simple single step in the UI.
export const singleStep = (
  step_id: string,
  name: string,
  args: Record<string, Argument> = {},
): StepSpec => ({
  step_id,
  name,
  arguments: args,
  orchestration: { mode: "single", concurrency: 1, retries: 0 },
  execution: { mode: "sync", run: "manual", retries: 0, cache: false },
});

// ── Backend API shapes ────────────────────────────────────────────────────
export type StepStatus = "pending" | "running" | "completed" | "failed";

export interface StepView {
  step_id: string;
  name: string;
  mode: OrchestrationMode;
  stage: number | string | null;
  status: StepStatus;
  value: unknown;
  error: string | null;
}

export interface ReferenceIssue { step_id: string; argument: string; reason: string; }

export interface WorkflowOut {
  workflow_id: string;
  status: "created" | "running" | "completed" | "failed";
  steps: StepView[];
  reference_issues: ReferenceIssue[];   // static wiring checks (unknown step, ordering, type mismatch)
}

export interface CreateWorkflowIn {
  workflow_id: string;
  steps: StepSpec[];
}

export interface DagNode { id: string; status: StepStatus; }
export interface DagEdge { from: string; to: string; }
export interface Dag { nodes: DagNode[]; edges: DagEdge[]; }

// Agent
export interface ProposeIn {
  goal: string;
  workflow?: StepSpec[];         // current steps (for modify)
}
export interface InvalidStep { step_id: string; reason: string; }
export interface ProposeOut {
  steps: StepSpec[];
  invalid: InvalidStep[];
}

// ── Minimal typed client ──────────────────────────────────────────────────
export class SimpleStepsClient {
  constructor(private baseUrl: string) {}

  private async json<T>(path: string, init?: RequestInit): Promise<T> {
    const res = await fetch(`${this.baseUrl}${path}`, {
      headers: { "content-type": "application/json" },
      ...init,
    });
    if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
    return res.json() as Promise<T>;
  }

  operations() {
    return this.json<OperationDefinition[]>("/operations");
  }
  createWorkflow(body: CreateWorkflowIn) {
    return this.json<WorkflowOut>("/workflows", { method: "POST", body: JSON.stringify(body) });
  }
  getWorkflow(id: string) {
    return this.json<WorkflowOut>(`/workflows/${id}`);
  }
  runWorkflow(id: string) {
    return this.json<WorkflowOut>(`/workflows/${id}/run`, { method: "POST" });
  }
  runStep(id: string, stepId: string) {
    return this.json<WorkflowOut>(`/workflows/${id}/steps/${stepId}/run`, { method: "POST" });
  }
  runStage(id: string, stage: number | string) {
    return this.json<WorkflowOut>(`/workflows/${id}/stages/${stage}/run`, { method: "POST" });
  }
  dag(id: string) {
    return this.json<Dag>(`/workflows/${id}/dag`);
  }
  propose(body: ProposeIn) {
    return this.json<ProposeOut>("/agent/propose", { method: "POST", body: JSON.stringify(body) });
  }
}
