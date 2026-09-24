import { expect, test } from "./fixtures";

test("desktop shows the persisted result of the simulator workflow", async ({
  page,
  request,
}, testInfo) => {
  const loaded = await request.post("/api/scenarios/DEMO-02/instances", {
    data: { request_id: crypto.randomUUID(), variant: "base" },
  });
  expect(loaded.ok()).toBeTruthy();
  const item = await loaded.json();
  const owner = "Phase 4 desktop reviewer";
  await request.patch(`/api/cases/${item.id}`, {
    data: {
      mutation_id: crypto.randomUUID(),
      expected_revision: item.revision,
      owner,
    },
  });
  async function action(operation: string, args: Record<string, unknown> = {}) {
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
    expect(response.ok()).toBeTruthy();
    const result = await response.json();
    expect(result.status).toBe("simulated_complete");
    return result;
  }
  await action("cct.apply_plan");
  const current = await (await request.get(`/api/cases/${item.id}`)).json();
  const assessment = await (
    await request.get(`/api/cases/${item.id}/assessment`)
  ).json();
  const evidence = await (
    await request.get(`/api/cases/${item.id}/evidence`)
  ).json();
  const record = evidence.find(
    (e: { details: { kind: string } }) => e.details.kind === "record",
  );
  const document = evidence.find(
    (e: { details: { key: string } }) => e.details.key === "amortization",
  );
  const config = record.details.facts.client_configuration;
  const prepared = await action("csp.prepare", {
    candidate: {
      case_revision: current.content_revision,
      version: 1,
      response_type: "final_resolution",
      client_code: item.client_code,
      client_version: config.version,
      sender: config.sender_email,
      recipient: record.details.facts.authorized_recipient,
      evidence_versions: assessment.evidence_versions,
      attachment_ids: [document.id],
      disclosure_ids: config.disclosure_keys,
      concerns: assessment.concerns.map(
        (c: { concern_id: string; disposition: string }) => ({
          concern_id: c.concern_id,
          disposition: c.disposition,
        }),
      ),
      claims: [
        {
          field: "document_attached",
          evidence_id: document.id,
          value: document.title,
        },
      ],
    },
  });
  const draft_id = prepared.reference.id;
  for (const operation of [
    "csp.send",
    "onbase.index",
    "ils.final_note",
    "cct.close",
  ])
    await action(operation, { draft_id });
  await page.goto("/?workspace=classic");
  const row = page.getByRole("row").filter({ hasText: owner });
  await expect(row).toContainText("closed");
  await row
    .getByRole("button", {
      name: "Amortization schedule request – loan ending 0002",
      exact: true,
    })
    .click();
  const assessmentView = page.getByRole("region", {
    name: "Business assessment",
    exact: true,
  });
  await expect(
    assessmentView.getByText("Completion check: Prerequisites met", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByText("Send response · Completed", { exact: true }),
  ).toBeVisible();
  await page.reload();
  const saved = page.getByRole("region", {
    name: "Saved response and records",
  });
  await expect(
    saved.getByText(`Recipient: ${record.details.facts.authorized_recipient}`, {
      exact: true,
    }),
  ).toBeVisible();
  await expect(saved.getByRole("heading", { name: "Outbox" })).toBeVisible();
  await expect(
    saved.getByRole("heading", { name: "Final notes" }),
  ).toBeVisible();
  for (const preview of await saved.locator(".response-preview").all()) {
    await expect(preview).not.toContainText(/synthetic|software demonstration/i);
  }
  const packageLink = saved.getByRole("link", {
    name: "Open combined response PDF",
  });
  const packageResponse = await request.get(
    (await packageLink.getAttribute("href"))!,
  );
  expect(packageResponse.ok()).toBeTruthy();
  expect(packageResponse.headers()["content-type"]).toContain(
    "application/pdf",
  );
  await expect(page.getByRole("row").filter({ hasText: owner })).toContainText(
    "closed",
  );
  await page.screenshot({
    path: testInfo.outputPath("phase4-desktop.png"),
    fullPage: true,
  });
});
