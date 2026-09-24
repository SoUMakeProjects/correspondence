import type { components } from "./schema";
import { REVIEWER } from "../auth/reviewer";

export type Case = components["schemas"]["CaseRead"];
export type CaseCreate = components["schemas"]["CaseCreate"];
export type CasePatch = components["schemas"]["CasePatch"];
export type Configuration = components["schemas"]["ConfigurationRead"];
export type CaseEvent = components["schemas"]["EventRead"];
export type Scenario = components["schemas"]["ScenarioRead"];
export type Evidence = components["schemas"]["EvidenceRead"];
export type Knowledge = components["schemas"]["KnowledgeRead"];
export type Task = components["schemas"]["TaskRead"];
export type Assessment = components["schemas"]["AssessmentReport"];
export type Validation = components["schemas"]["ValidationReport"];
export type AgentRun = components["schemas"]["RunRead"];
export type Artifacts = components["schemas"]["ArtifactsRead"];
export type Workflow = components["schemas"]["WorkflowRead"];
export type CaseInput = components["schemas"]["CaseInput"];
export type DraftEdit = components["schemas"]["DraftEdit"];
export type RunSummary = components["schemas"]["SummaryRead"];
export type MailTemplate = components["schemas"]["MailTemplate"];
export type MailMessage = components["schemas"]["MailMessageRead"];
export type MailUpload = components["schemas"]["MailAttachmentRead"];
export type MailThread = components["schemas"]["ThreadRead"];
export type ThreadDetail = components["schemas"]["ThreadDetail"];
export type Operations = components["schemas"]["OperationsRead"];
export type SystemCase = components["schemas"]["SystemCaseRead"];
export type ResetState = components["schemas"]["ResetState"];
export type RunFault = NonNullable<components["schemas"]["RunStart"]["fault"]>;
type SavedAssessment = components["schemas"]["SavedAssessment"];
type Simulation = components["schemas"]["SimulationInspection"];
type CaseList = components["schemas"]["CaseList"];
type EventPage = components["schemas"]["EventPage"];
export type IntakeReview = {
  signal_id: string;
  detail: string;
  message: MailMessage;
  classification: { request_type: string } | null;
};
export type IntakeReviews = {
  reviews: IntakeReview[];
  loans: { id: string; borrower: string; recipient: string }[];
};

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const detail = body?.error;
    throw new ApiError(
      response.status,
      detail?.code ?? "request_failed",
      detail?.message ??
        "The workspace could not complete this request. Please try again.",
    );
  }
  return response.json() as Promise<T>;
}

export const api = {
  uploadAttachment: (file: File, requestId: string) =>
    request<MailUpload>(
      `/mail/attachments?request_id=${encodeURIComponent(requestId)}&filename=${encodeURIComponent(file.name)}`,
      {
        method: "POST",
        headers: {
          "Content-Type":
            file.type ||
            ({
              pdf: "application/pdf",
              png: "image/png",
              jpg: "image/jpeg",
              jpeg: "image/jpeg",
              gif: "image/gif",
              webp: "image/webp",
            }[file.name.split(".").pop()?.toLowerCase() ?? ""] ??
              "application/octet-stream"),
        },
        body: file,
      },
    ),
  intakeReviews: (signal?: AbortSignal) =>
    request<IntakeReviews>("/mail/intake-reviews", { signal }),
  retryIntake: (id: string) =>
    request(`/mail/intake/${id}/retry`, { method: "POST" }),
  resolveIntake: (
    id: string,
    payload: components["schemas"]["IntakeResolution"],
  ) =>
    request(`/mail/intake/${id}/resolve`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  operations: (signal?: AbortSignal) =>
    request<Operations>("/operations", { signal }),
  /** Shared demo reset: the Desk and the Mailbox both watch its generation. */
  resetState: (signal?: AbortSignal) =>
    request<ResetState>("/workspace/reset", { signal }),
  resetWorkspace: () =>
    request<ResetState>("/workspace/reset", { method: "POST" }),
  systemCase: (id: string, signal?: AbortSignal) =>
    request<SystemCase>(`/systems/cases/${id}`, { signal }),
  mailTemplates: (signal?: AbortSignal) =>
    request<MailTemplate[]>("/mail/templates", { signal }),
  mailThread: (id: string, signal?: AbortSignal) =>
    request<ThreadDetail>(`/mail/threads/${id}`, { signal }),
  sendMail: (payload: components["schemas"]["MailSend"]) =>
    request<MailMessage>("/mail/messages", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  runSummary: (id: string, signal?: AbortSignal) =>
    request<RunSummary>(`/runs/${id}/summary`, { signal }),
  checkRecovery: (id: string, revision: number) =>
    request<{ blocked: boolean }>(`/cases/${id}/recovery/check`, {
      method: "POST",
      body: JSON.stringify({
        request_id: crypto.randomUUID(),
        expected_revision: revision,
        actor: REVIEWER.name,
      }),
    }),
  restoreStatus: (id: string, revision: number, action: string) =>
    request<Record<string, unknown>>(`/cases/${id}/recovery/restore-status`, {
      method: "POST",
      body: JSON.stringify({
        request_id: crypto.randomUUID(),
        expected_revision: revision,
        actor: REVIEWER.name,
        action_id: action,
      }),
    }),
  workflow: (id: string, signal?: AbortSignal) =>
    request<Workflow>(`/cases/${id}/workflow`, { signal }),
  supplyInput: (id: string, input: CaseInput) =>
    request<Case>(`/cases/${id}/inputs`, {
      method: "POST",
      body: JSON.stringify(input),
    }),
  editDraft: (id: string, input: DraftEdit) =>
    request<Record<string, unknown>>(`/cases/${id}/draft-edits`, {
      method: "POST",
      body: JSON.stringify(input),
    }),
  review: (id: string, input: components["schemas"]["ReviewCreate"]) =>
    request<components["schemas"]["ReviewRead"]>(`/cases/${id}/reviews`, {
      method: "POST",
      body: JSON.stringify(input),
    }),
  acknowledge: (
    id: string,
    input: components["schemas"]["HandoffAcknowledge"],
  ) =>
    request<Record<string, unknown>>(`/cases/${id}/handoff-acknowledgments`, {
      method: "POST",
      body: JSON.stringify(input),
    }),
  resumeRun: (id: string, revision: number, previous: string) =>
    request<AgentRun>(`/cases/${id}/runs`, {
      method: "POST",
      body: JSON.stringify({
        expected_revision: revision,
        resume_from: previous,
      }),
    }),
  resumeProcessing: (id: string, revision: number) =>
    request<components["schemas"]["SignalRead"]>(
      `/automation/cases/${id}/resume`,
      {
        method: "POST",
        body: JSON.stringify({
          request_id: crypto.randomUUID(),
          expected_revision: revision,
        }),
      },
    ),
  runs: (id: string, signal?: AbortSignal) =>
    request<AgentRun[]>(`/cases/${id}/runs`, { signal }),
  artifacts: (id: string, signal?: AbortSignal) =>
    request<Artifacts>(`/cases/${id}/artifacts`, { signal }),
  startRun: (
    id: string,
    revision: number,
    mode: "automatic" | "review_required",
    fault: RunFault = "none",
  ) =>
    request<AgentRun>(`/cases/${id}/runs`, {
      method: "POST",
      body: JSON.stringify({ expected_revision: revision, mode, fault }),
    }),
  stopRun: (id: string) =>
    request<AgentRun>(`/runs/${id}/stop`, { method: "POST" }),
  assessment: (id: string, signal?: AbortSignal) =>
    request<Assessment>(`/cases/${id}/assessment`, { signal }),
  completion: (id: string, signal?: AbortSignal) =>
    request<Validation>(`/cases/${id}/completion-check`, { signal }),
  assessmentHistory: (id: string, signal?: AbortSignal) =>
    request<SavedAssessment[]>(`/cases/${id}/assessments`, { signal }),
  recordAssessment: (id: string, revision: number) =>
    request<SavedAssessment>(`/cases/${id}/assessments`, {
      method: "POST",
      body: JSON.stringify({
        request_id: crypto.randomUUID(),
        expected_revision: revision,
      }),
    }),
  scenarios: (signal?: AbortSignal) =>
    request<Scenario[]>("/scenarios", { signal }),
  loadScenario: (
    scenario: Scenario["scenario_id"],
    variant: Scenario["variants"][number],
  ) =>
    request<Case>(`/scenarios/${scenario}/instances`, {
      method: "POST",
      body: JSON.stringify({ request_id: crypto.randomUUID(), variant }),
    }),
  evidence: (id: string, signal?: AbortSignal) =>
    request<Evidence[]>(`/cases/${id}/evidence`, { signal }),
  tasks: (id: string, signal?: AbortSignal) =>
    request<Task[]>(`/cases/${id}/tasks`, { signal }),
  simulation: (id: string, signal?: AbortSignal) =>
    request<Simulation>(`/simulations/${id}`, { signal }),
  knowledge: (scenario: string, client: string, signal?: AbortSignal) =>
    request<Knowledge[]>(
      `/knowledge?scenario_id=${encodeURIComponent(scenario)}&client_code=${encodeURIComponent(client)}`,
      { signal },
    ),
  configuration: (signal?: AbortSignal) =>
    request<Configuration>("/config", { signal }),
  cases: (offset: number, limit: number, signal?: AbortSignal) =>
    request<CaseList>(`/cases?offset=${offset}&limit=${limit}`, { signal }),
  case: (id: string, signal?: AbortSignal) =>
    request<Case>(`/cases/${id}`, { signal }),
  events: (id: string, signal?: AbortSignal) =>
    request<EventPage>(`/cases/${id}/events`, { signal }),
  create: (payload: CaseCreate) =>
    request<Case>("/cases", { method: "POST", body: JSON.stringify(payload) }),
  update: (id: string, payload: CasePatch) =>
    request<Case>(`/cases/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
};
