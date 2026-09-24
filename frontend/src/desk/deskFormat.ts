import type { AgentRun, DraftEdit } from "../api/client";
import { displayLabel, displayValue } from "../presentation";

export type Row = Record<string, unknown>;
export type DeskDraft = {
  id: string;
  version: number;
  current: boolean;
  sent: boolean;
  approved: boolean;
  returned: boolean;
  review_required: boolean;
  recipient: string;
  body: string;
  candidate: Pick<
    DraftEdit,
    "response_type" | "claims" | "concerns" | "attachment_ids"
  > & { sender?: string };
  findings: { message: string }[];
};
export const isActive = (run?: AgentRun) =>
  !!run && ["queued", "running"].includes(run.status);
export const titleCase = (value: unknown) => {
  const label = displayLabel(value);
  return label ? label[0].toUpperCase() + label.slice(1) : "Not recorded";
};
export const dateTime = (value: unknown, time = false) => {
  if (!value || Number.isNaN(new Date(String(value)).valueOf()))
    return "Not recorded";
  return new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    ...(time
      ? ({ hour: "numeric", minute: "2-digit", second: "2-digit" } as const)
      : ({ month: "short", day: "numeric", year: "numeric" } as const)),
  }).format(new Date(String(value)));
};
export const money = (value: number) =>
  new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(
    value / 100,
  );
export const fact = (value: unknown) =>
  value === null || value === undefined || value === ""
    ? "Not recorded"
    : typeof value === "boolean"
      ? value
        ? "Yes"
        : "No"
      : displayValue(value);
export const caseStatus = (status: string) =>
  ({
    under_review: "Under review",
    waiting_for_review: "Under review",
    waiting_for_borrower: "Waiting for borrower",
    waiting_on_department: "With specialist",
    in_progress: "In progress",
    ready: "Ready",
  })[status] ?? titleCase(status);
const eastern = (value: unknown, options: Intl.DateTimeFormatOptions) =>
  new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    ...options,
  }).format(new Date(String(value)));
const valid = (value: unknown) =>
  !!value && !Number.isNaN(new Date(String(value)).valueOf());
/** "Sep 18, 10:30 AM" (Eastern). */
export const shortDateTime = (value: unknown) =>
  valid(value)
    ? eastern(value, {
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
      })
    : "Not recorded";
/** "10:30 AM" (Eastern, no seconds). */
export const shortTime = (value: unknown) =>
  valid(value)
    ? eastern(value, { hour: "numeric", minute: "2-digit" })
    : "Not recorded";
const easternDate = (value: Date) => {
  const [m, d, y] = eastern(value, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).split("/");
  return Date.UTC(Number(y), Number(m) - 1, Number(d));
};
/** Eastern Monday–Friday workdays after the receipt date (receipt day is day 0). */
export const workdayAge = (received: unknown, now = new Date()) => {
  if (!valid(received)) return null;
  const first = easternDate(new Date(String(received)));
  const last = easternDate(now);
  if (last < first) return null;
  const day = 86400000;
  let count = 0;
  for (let t = first + day; t <= last; t += day) {
    const weekday = new Date(t).getUTCDay();
    if (weekday !== 0 && weekday !== 6) count++;
  }
  return count;
};
/** Service-level tone for a workday age out of 20. */
export const ageTone = (age: number | null | undefined) =>
  age === null || age === undefined
    ? "unknown"
    : age >= 15
      ? "late"
      : age >= 10
        ? "warn"
        : "ok";
