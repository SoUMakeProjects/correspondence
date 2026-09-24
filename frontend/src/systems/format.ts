/** Shared display formatting for the CCT, ILS and OnBase system views. */
import { displayLabel, displayValue } from "../presentation";

export type Row = Record<string, unknown>;

const TZ = "America/New_York";
const isIsoDate = (v: unknown) =>
  typeof v === "string" && /^\d{4}-\d{2}-\d{2}$/.test(v);
const isIsoInstant = (v: unknown) =>
  typeof v === "string" && /^\d{4}-\d{2}-\d{2}T/.test(v);

/** "Mar 27, 2020" for a calendar date (no timezone shift). */
export function calendarDate(value: unknown): string {
  if (!isIsoDate(value)) return String(value ?? "");
  const [y, m, d] = String(value).split("-").map(Number);
  return new Intl.DateTimeFormat("en-US", {
    timeZone: "UTC",
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(new Date(Date.UTC(y, m - 1, d)));
}

/** "Sep 18, 2026, 10:30 AM ET". */
export function instant(value: unknown, withYear = true): string {
  if (!value || Number.isNaN(new Date(String(value)).valueOf()))
    return "Not recorded";
  return (
    new Intl.DateTimeFormat("en-US", {
      timeZone: TZ,
      month: "short",
      day: "numeric",
      ...(withYear ? { year: "numeric" as const } : {}),
      hour: "numeric",
      minute: "2-digit",
    }).format(new Date(String(value))) + " ET"
  );
}

/** "10:30:05 AM". */
export function clock(value: unknown): string {
  if (!value || Number.isNaN(new Date(String(value)).valueOf())) return "";
  return new Intl.DateTimeFormat("en-US", {
    timeZone: TZ,
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(String(value)));
}

export const money = (minor: number) =>
  new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(
    minor / 100,
  );

export const sentence = (value: unknown) => {
  const text = displayLabel(value);
  return text ? text[0].toUpperCase() + text.slice(1) : "Not recorded";
};

/** Human labels for known servicing-record keys. */
const LABELS: Record<string, string> = {
  product: "Product",
  requester_role: "Requester role",
  authorized_recipient: "Authorized recipient",
  communication_restriction: "Communication restriction",
  borrower_email: "Email",
  borrower_phone: "Phone",
  mailing_address: "Mailing address",
  property_address: "Property address",
  occupancy: "Occupancy",
  original_principal_minor: "Original principal",
  note_date: "Note date",
  term_months: "Loan term",
  annual_rate_basis_points: "Interest rate",
  principal_interest_minor: "Monthly principal & interest",
  remaining_payments: "Remaining payments",
  first_payment_date: "Next payment due",
  maturity_date: "Scheduled maturity",
  last_payment_received: "Last payment received",
  escrow_included: "Escrow in schedule",
  current_legal_name: "Current legal name",
  requested_legal_name: "Requested legal name",
  profile_update_result: "Profile update reference",
  representative_email: "Representative email",
  representation_verified: "Representation verified",
  servicing_bankruptcy_status: "Bankruptcy status (servicing)",
  specialist_determination: "Specialist determination",
  escrow_monthly_deposit_minor: "Monthly escrow deposit",
  escrow_analysis_date: "Escrow analysis",
  escrow_surplus_minor: "Escrow surplus",
  escrow_refund_method: "Surplus refund method",
  payment_method: "Payment method",
  new_payment_minor: "New monthly payment",
  new_payment_effective_date: "New payment effective",
  recurring_payment_enrollment: "Automatic payments",
  draw_authorization: "Draw authorization",
  escrow_balance_minor: "Escrow balance",
  tax_escrow_responsibility: "Taxes paid from escrow",
  tax_period: "Tax bill",
  tax_payee: "Tax payee",
  tax_bill_number: "Tax bill number",
  tax_parcel_id: "Parcel ID",
  tax_schedule_verified_by: "Tax Team review reference",
  tax_payment_reference: "Tax payment reference",
  confirmed_status: "Confirmed payment status",
  scheduled_date: "Scheduled disbursement date",
  paid_at: "Disbursed",
  reviewed_at: "Reviewed",
  reviewed_by: "Reviewed by",
  tax_status: "Tax payment status",
  tax_amount_minor: "Tax amount",
  tax_due_date: "Tax due date",
  tax_scheduled_date: "Tax payment scheduled",
  tax_bill_received_at: "Tax bill received",
  tax_paid_at: "Tax disbursed",
  eft_intent: "EFT purpose",
  refund_authorization: "Refund authorization",
};

export const fieldLabel = (key: string) =>
  LABELS[key] ??
  sentence(key.replace(/_minor$/, "").replace(/_basis_points$/, ""));

/** Formats a servicing value according to its key and shape. */
export function fieldValue(key: string, value: unknown): string {
  if ((key === "paid_at" || key === "tax_paid_at") && !value)
    return "Not yet disbursed";
  if (value === null || value === undefined || value === "")
    return "Not recorded";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "number") {
    if (key.endsWith("_minor")) return money(value);
    if (key.endsWith("_basis_points")) return `${(value / 100).toFixed(3)}%`;
    if (key === "term_months") return `${value} months`;
    return value.toLocaleString("en-US");
  }
  if (isIsoDate(value)) return calendarDate(value);
  if (isIsoInstant(value)) return instant(value);
  if (typeof value === "string" && /^[a-z]+(_[a-z]+)+$|^[a-z]+$/.test(value))
    return sentence(value);
  return displayValue(value);
}

/** Short, copyable form of a long identifier. */
export const shortId = (value: unknown) => {
  const text = String(value ?? "");
  const match = text.match(/[0-9a-f]{8}(?=-[0-9a-f]{4}-)/i);
  return match ? match[0].toUpperCase() : text;
};

const ACTORS: Record<string, string> = {
  azure_agent: "AI agent",
  "test double": "AI agent",
  test_double: "AI agent",
  local_presenter: "System",
  system: "System",
  "Demo reviewer": "Reviewer",
  "Demo evaluation reviewer": "Reviewer",
};
export const actorName = (value: unknown) => {
  const text = String(value ?? "");
  return ACTORS[text] ?? displayValue(text);
};

const REF_PREFIX: Record<string, string> = {
  outbox: "DELIVERY",
  package: "PKG",
  note: "NOTE",
  draft: "DRAFT",
  case: "CASE",
  task: "TASK",
  handoff: "HANDOFF",
};
/** Consistent short reference label, e.g. "PKG-F05BEA45". */
export const refLabel = (kind: unknown, id: unknown) =>
  `${REF_PREFIX[String(kind)] ?? String(kind).toUpperCase()}-${shortId(id)}`;
