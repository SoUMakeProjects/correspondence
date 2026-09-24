import { expect, test } from "./fixtures";

test("case records, assignments and history survive a browser reload", async ({
  page,
}, testInfo) => {
  await page.goto("/?workspace=classic");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await page.getByRole("button", { name: "New case", exact: true }).click();
  await page.getByRole("button", { name: "Create case", exact: true }).click();
  const details = page.getByRole("region", { name: "Selected case" });
  await expect(details.getByText("0099000002", { exact: true })).toBeVisible();
  const owner = `Reviewer ${testInfo.project.name}`;
  await page.getByLabel("Assigned owner").fill(owner);
  await page.getByRole("button", { name: "Save owner", exact: true }).click();
  await expect(
    page.getByRole("status").filter({ hasText: "Case updated" }),
  ).toBeVisible();
  await expect(page.getByLabel("Assigned owner")).toHaveValue(owner);
  await page
    .getByRole("button", { name: "Move to review", exact: true })
    .click();
  await expect(page.locator(".selected-row .status-pill")).toHaveText(
    "Under review",
  );
  await expect(details.getByText("Case updated", { exact: true })).toHaveCount(
    2,
  );
  await page.reload();
  const row = page.getByRole("row").filter({ hasText: owner });
  await expect(row).toContainText("Under review");
  await row
    .getByRole("button", {
      name: "Amortization schedule request – loan ending 0002",
      exact: true,
    })
    .click();
  await expect(page.getByLabel("Assigned owner")).toHaveValue(owner);
  await expect(details.getByText("Case updated", { exact: true })).toHaveCount(
    2,
  );
  await page.getByRole("button", { name: "Setup & status" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(
    page.getByText("AZURE_OPENAI_API_KEY", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Close setup", exact: true }).click();
  const widths = await page.evaluate(() => ({
    layout: innerWidth,
    document: document.documentElement.scrollWidth,
  }));
  const viewportWidth = page.viewportSize()!.width;
  expect(widths.layout).toBeLessThanOrEqual(viewportWidth + 1);
  expect(widths.document).toBeLessThanOrEqual(viewportWidth + 1);
  await page.screenshot({
    path: testInfo.outputPath("foundation.png"),
    fullPage: true,
  });
});

test("demo scenarios expose scoped documents, missing evidence and curated guidance", async ({
  page,
}, testInfo) => {
  await page.goto("/?workspace=classic");
  await page.getByRole("button", { name: "New case", exact: true }).click();
  await page.getByLabel("Case type", { exact: true }).selectOption("DEMO-02");
  await page.getByRole("button", { name: "Create case", exact: true }).click();
  const details = page.getByRole("region", { name: "Selected case" });
  await expect(details.getByText("0099000002", { exact: true })).toBeVisible();
  const resources = page.getByRole("region", {
    name: "Case evidence and guidance",
  });
  const pdf = resources.getByRole("link", { name: "Open PDF", exact: true });
  await expect(pdf).toBeVisible();
  const response = await page.request.get((await pdf.getAttribute("href"))!);
  expect(response.status()).toBe(200);
  expect(response.headers()["content-type"]).toContain("application/pdf");
  expect((await response.body()).subarray(0, 5).toString()).toBe("%PDF-");
  await expect(
    resources
      .locator("summary")
      .filter({ hasText: "Document fulfillment prerequisites" }),
  ).toBeVisible();

  await page.getByRole("button", { name: "New case", exact: true }).click();
  await page.getByLabel("Case type", { exact: true }).selectOption("DEMO-01");
  await page.getByRole("button", { name: "Create case", exact: true }).click();
  await expect(details.getByText("0099000001", { exact: true })).toBeVisible();
  await expect(
    resources.getByText("Document missing", { exact: true }),
  ).toBeVisible();
  const guidance = resources
    .locator(".knowledge-item")
    .filter({ hasText: "Evidence for an ordinary legal-name change" });
  await guidance.locator("summary").click();
  await expect(guidance.getByText(/S04:r115 · S04:r116 · P03/)).toBeVisible();
  await expect(
    resources
      .locator("summary")
      .filter({ hasText: "Document fulfillment prerequisites" }),
  ).toHaveCount(0);
  await page.screenshot({
    path: testInfo.outputPath("phase2.png"),
    fullPage: true,
  });
  const width = await page.evaluate(() =>
    Math.max(innerWidth, document.documentElement.scrollWidth),
  );
  expect(width).toBeLessThanOrEqual(page.viewportSize()!.width + 1);
});
