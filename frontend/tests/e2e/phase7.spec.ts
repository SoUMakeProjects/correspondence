import { expect, test } from "./fixtures";
import type { APIRequestContext, Page } from "@playwright/test";

async function load(request: APIRequestContext, scenario: string) {
  const response = await request.post(`/api/scenarios/${scenario}/instances`, {
    data: { request_id: crypto.randomUUID(), variant: "base" },
  });
  expect(response.ok()).toBeTruthy();
  return response.json();
}

async function action(
  request: APIRequestContext,
  item: any,
  operation: string,
  args: object = {},
) {
  const current = await (await request.get(`/api/cases/${item.id}`)).json();
  const assessment = await (
    await request.get(`/api/cases/${item.id}/assessment`)
  ).json();
  const response = await request.post(
    `/api/simulations/${item.simulation_id}/cases/${item.id}/tools`,
    {
      data: {
        loan_identifier: item.loan_identifier,
        client_code: item.client_code,
        command: {
          operation,
          action_id: crypto.randomUUID(),
          expected_revision: current.revision,
          evidence_versions: assessment.evidence_versions,
          input_hash: assessment.input_hash,
          ...args,
        },
      },
    },
  );
  const result = await response.json();
  expect(result.status, JSON.stringify(result)).toBe("simulated_complete");
  return result;
}

async function open(page: Page, caseId: string) {
  await page.addInitScript(
    (id) => localStorage.setItem("correspondence.selectedCase", id),
    caseId,
  );
  await page.goto("/?workspace=classic");
  return page.getByRole("region", {
    name: "Review and case inputs",
    exact: true,
  });
}

test("reviewer returns, validates an edit, approves the exact version and invalidates it with new evidence", async ({
  page,
  request,
}, testInfo) => {
  const item = await load(request, "DEMO-03");
  await action(request, item, "cct.apply_plan");
  const current = await (await request.get(`/api/cases/${item.id}`)).json();
  const assessment = await (
    await request.get(`/api/cases/${item.id}/assessment`)
  ).json();
  const evidence = await (
    await request.get(`/api/cases/${item.id}/evidence`)
  ).json();
  const record = evidence.find((e: any) => e.details.kind === "record");
  const config = record.details.facts.client_configuration;
  await action(request, item, "csp.prepare", {
    candidate: {
      case_revision: current.content_revision,
      version: 1,
      response_type: "final_resolution",
      client_code: item.client_code,
      client_version: config.version,
      sender: config.sender_email,
      recipient: assessment.authorized_recipient,
      evidence_versions: assessment.evidence_versions,
      attachment_ids: [],
      disclosure_ids: config.disclosure_keys,
      concerns: assessment.concerns.map((c: any) => ({
        concern_id: c.concern_id,
        disposition: c.disposition,
      })),
      claims: ["tax_status", "tax_scheduled_date", "tax_bill_received_at"].map(
        (field) => ({
          field,
          value: record.details.facts[field],
          evidence_id: record.id,
        }),
      ),
    },
  });
  const view = await open(page, item.id);
  await expect(
    view.getByText("Review required", { exact: true }),
  ).toBeVisible();
  await view
    .getByLabel("Review note", { exact: true })
    .fill("Confirm scheduled wording and preserve the dates.");
  await view
    .getByRole("button", { name: "Return for changes", exact: true })
    .click();
  await expect(
    view.getByText("Returned for changes", { exact: true }),
  ).toBeVisible();
  await view.getByText("Edit the supported response", { exact: true }).click();
  await view.getByLabel("Claim 1 value", { exact: true }).fill("paid");
  await view.getByRole("button", { name: "Save validated revision" }).click();
  await expect(view.getByRole("alert")).toContainText(
    "Evidence does not establish",
  );
  await view.getByLabel("Claim 1 value", { exact: true }).fill("scheduled");
  await view.getByRole("button", { name: "Save validated revision" }).click();
  await expect(
    view.getByRole("heading", { name: "Response review · version 2" }),
  ).toBeVisible();
  await view.getByRole("button", { name: "Approve this version" }).click();
  await expect(
    view.getByText("Approved current version", { exact: true }),
  ).toBeVisible();
  await page.reload();
  await expect(
    view.getByText("Approved current version", { exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath("phase7-review.png"),
    fullPage: true,
  });
  const approved = await (
    await request.get(`/api/cases/${item.id}/workflow`)
  ).json();
  expect(approved.reviews).toHaveLength(2);
  expect(approved.drafts).toHaveLength(2);
  expect(approved.drafts[1].approved).toBe(true);
  await view
    .getByLabel("Input to supply")
    .selectOption("tax_specialist_result");
  await view
    .getByRole("button", { name: "Receive input", exact: true })
    .click();
  await expect(
    view.getByText("Inputs changed — prepare a current response", {
      exact: true,
    }),
  ).toBeVisible();
  const updated = await (
    await request.get(`/api/cases/${item.id}/workflow`)
  ).json();
  expect(updated.drafts[1].approved).toBe(false);
  expect(
    await (await request.get(`/api/cases/${item.id}/tasks`)).json(),
  ).toHaveLength(1);
});

test("same-case input persists and Resume uses the selected paused run without repeat submission", async ({
  page,
  request,
}) => {
  const item = await load(request, "DEMO-01");
  // Only model transport is stubbed. Evidence input and persistence use the real services.
  const prior = {
    id: crypto.randomUUID(),
    case_id: item.id,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    case_revision: item.revision,
    status: "waiting_for_input",
    checkpoint: { steps: 0, history: [], reason: "verified_outcome" },
    model_configuration: {
      source: "test_double",
      configuration_id: "phase7-browser-only",
      protocol: "test",
      tool_contract: 7,
    },
  };
  const runs = [prior];
  let starts = 0;
  await page.route("**/api/config", async (route) => {
    const config = await (await route.fetch()).json();
    await route.fulfill({ json: { ...config, agent_available: true } });
  });
  await page.route(`**/api/cases/${item.id}/runs`, async (route) => {
    if (route.request().method() === "POST") {
      starts++;
      expect(route.request().postDataJSON().resume_from).toBe(prior.id);
      const next = { ...prior, id: crypto.randomUUID() };
      runs.push(next);
      await route.fulfill({ status: 202, json: next });
    } else await route.fulfill({ json: runs });
  });
  const view = await open(page, item.id);
  await view.getByLabel("Input to supply").selectOption("name_legal_document");
  await view
    .getByRole("button", { name: "Receive input", exact: true })
    .click();
  await expect(view.getByRole("status")).toContainText(
    "Input saved to this case",
  );
  const updated = await (await request.get(`/api/cases/${item.id}`)).json();
  expect(updated.id).toBe(item.id);
  expect(updated.original_received_at).toBe(item.original_received_at);
  expect(updated.revision).toBeGreaterThan(item.revision);
  await page.getByRole("button", { name: "Resume agent", exact: true }).click();
  await expect.poll(() => starts).toBe(1);
  await page.reload();
  await expect(
    page.getByRole("button", { name: "Resume agent", exact: true }),
  ).toBeVisible();
  expect(starts).toBe(1);
  const persisted = await (
    await request.get(`/api/cases/${item.id}/workflow`)
  ).json();
  expect(persisted.contacts).toHaveLength(1);
  expect(
    (await (await request.get(`/api/cases/${item.id}/evidence`)).json()).some(
      (e: any) =>
        e.details.key === "legal-document" &&
        e.details.availability === "available",
    ),
  ).toBe(true);
});

test("acknowledged specialist responsibility persists as a transfer", async ({
  page,
  request,
}, testInfo) => {
  const item = await load(request, "DEMO-04");
  await action(request, item, "cct.apply_plan");
  await action(request, item, "cct.handoff");
  const view = await open(page, item.id);
  await expect(view.getByLabel("Acting reviewer")).toHaveValue("Admin");
  await expect(view.getByLabel("Acting reviewer")).not.toBeEditable();
  await view
    .getByRole("button", { name: "Acknowledge specialist receipt" })
    .click();
  await expect(
    view.getByText("acknowledged by Admin", {
      exact: true,
    }),
  ).toBeVisible();
  await page.reload();
  await expect(
    view.getByText("acknowledged by Admin", {
      exact: true,
    }),
  ).toBeVisible();
  const current = await (await request.get(`/api/cases/${item.id}`)).json();
  expect(current.status).toBe("transferred");
  const result = await (
    await request.get(`/api/cases/${item.id}/completion-check`)
  ).json();
  expect(result.valid).toBe(false);
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(page.viewportSize()!.width + 1);
  await page.screenshot({
    path: testInfo.outputPath("phase7-handoff.png"),
    fullPage: true,
  });
});
