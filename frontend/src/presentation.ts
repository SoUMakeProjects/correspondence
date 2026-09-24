// Presentation only: stored records, evidence, identifiers and approvals retain
// their original values. Match known fixture copy; never strip arbitrary words
// from borrower messages, names, email addresses or user-entered notes.
const labels: Record<string, string> = {
  simulated_complete: "Completed",
  "Borrower Correspondence (Demo)": "Borrower Correspondence",
  fixed_mortgage: "Fixed-rate mortgage",
  demo_profile_name_update: "Profile name update",
  demo_tax_schedule_review: "Tax schedule review",
  demo_bankruptcy_status_review: "Bankruptcy status review",
  "Demo reviewer": "Reviewer",
  "Demo presenter": "Caseworker",
  "Demo supervisor": "Supervisor",
  "Demo Servicing Team": "Servicing Team",
  "Demo Records Team": "Records Team",
  "Demo Tax Team": "Tax Team",
  "Demo Bankruptcy Team": "Bankruptcy Team",
  "Demo Compliance Team": "Compliance Team",
  "Demo alternate owner": "Alternate owner",
  "Synthetic servicing record": "Servicing record",
  "Synthetic legal name-change certificate": "Legal name-change certificate",
  fixture_loader: "Case intake",
  demo_presenter: "Caseworker",
  local_presenter: "Caseworker",
  "cct.read": "Read case",
  "cct.apply_plan": "Record case plan",
  "cct.handoff": "Refer to specialist",
  "cct.close": "Close case",
  "ils.read": "Read servicing record",
  "ils.create_task": "Create specialist task",
  "ils.update_name": "Update legal name",
  "ils.final_note": "Record final note",
  "csp.prepare": "Prepare response",
  "csp.send": "Send response",
  "onbase.index": "Index response package",
};

export function displayLabel(value: unknown): string {
  const text = String(value ?? "");
  return labels[text] ?? text.replaceAll("_", " ");
}

export function displayValue(value: unknown): string {
  const text = String(value ?? "");
  return labels[text] ?? text;
}

export function clientName(code: string): string {
  const clients: Record<string, string> = {
    "DEMO-NORTH": "Northstar Residential Servicing",
    "DEMO-HARBOR": "Harbor Point Mortgage Services",
  };
  return clients[code] ?? code;
}

const copy: [string, string][] = [
  [
    "This is a synthetic foundation sample; no borrower has been contacted.",
    "",
  ],
  [
    "Northstar Demo Servicing: this communication uses fictional records for a software demonstration. No real loan, payment, servicing change or borrower communication is involved.",
    "",
  ],
  [
    "Harbor Demo Servicing: this is synthetic demonstration correspondence. It has no effect on a real account and does not establish a payment or legal determination.",
    "",
  ],
  [
    "Northstar Demo Servicing | Synthetic correspondence only",
    "Northstar Residential Servicing",
  ],
  [
    "Harbor Demo Servicing | Synthetic correspondence only",
    "Harbor Point Mortgage Services",
  ],
  ["Synthetic MVP guidance only; not approved for operational use.", ""],
  [
    "Referenced historical attachments were not supplied; the fixture document is newly generated.",
    "",
  ],
  [
    "This item describes prerequisites; enforcement is implemented in later rule and simulator phases.",
    "",
  ],
  ["The simulated servicing record confirms", "The servicing record confirms"],
  [
    "The current synthetic amortization schedule",
    "The current amortization schedule",
  ],
  ["The synthetic tax record shows", "The tax record shows"],
  ["applicable curated demo text", "applicable guidance"],
  ["Simulated operation completed.", "Operation completed."],
  ["Scoped synthetic records retrieved.", "Case records retrieved."],
  [
    "The persisted simulated result was independently verified.",
    "The saved result was independently verified.",
  ],
  ["Simulated response delivered:", "Response delivered:"],
  [
    "Prepare the distinct authorized name update for the later simulator.",
    "Prepare the authorized name update.",
  ],
  [
    "Include the currently curated demo disclosures for this client.",
    "Include the required disclosures for this client.",
  ],
  [
    "Supplied synthetic evidence received; the agent must inspect it before continuing.",
    "Evidence received; the agent must inspect it before continuing.",
  ],
];

export function displayText(value: unknown): string {
  return tidy(cleanCopy(String(value ?? "")));
}

const cleanCopy = (text: string) =>
  copy.reduce((t, [from, to]) => t.replaceAll(from, to), text);
const tidy = (text: string) =>
  text.replace(/\n[ \t]*\n(?:[ \t]*\n)+/g, "\n\n").trim();

export type TextRun = { text: string; bold: boolean };

/**
 * displayText() split into bold/plain runs. `spans` are server-computed [start, end)
 * offsets into the raw body (see backend app/letter_emphasis.py); they are applied
 * before display cleanup so offsets stay valid. Invalid spans are ignored.
 */
export function displayRuns(value: unknown, spans: unknown): TextRun[] {
  const raw = String(value ?? "");
  const runs: TextRun[] = [];
  let cursor = 0;
  for (const span of Array.isArray(spans) ? spans : []) {
    const [a, b] = span as [number, number];
    if (!Number.isInteger(a) || !Number.isInteger(b)) continue;
    if (a < cursor || b <= a || b > raw.length) continue;
    if (a > cursor) runs.push({ text: raw.slice(cursor, a), bold: false });
    runs.push({ text: raw.slice(a, b), bold: true });
    cursor = b;
  }
  if (cursor < raw.length) runs.push({ text: raw.slice(cursor), bold: false });
  if (!runs.some((r) => r.bold))
    return [{ text: displayText(raw), bold: false }];
  // Same cleanup as displayText(): copy substitutions per run, then collapse/trim the ends.
  const cleaned = runs.map((r) => ({ ...r, text: cleanCopy(r.text) }));
  cleaned[0].text = cleaned[0].text.trimStart();
  cleaned[cleaned.length - 1].text = cleaned[cleaned.length - 1].text.trimEnd();
  return cleaned
    .map((r) => ({
      ...r,
      text: r.text.replace(/\n[ \t]*\n(?:[ \t]*\n)+/g, "\n\n"),
    }))
    .filter((r) => r.text);
}

export function isOperationalGuidance(item: {
  kind: string;
  source_references: string[];
}): boolean {
  return !(
    item.kind === "disclosure" &&
    item.source_references.includes("DEMO:client-configuration")
  );
}
