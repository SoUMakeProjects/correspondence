import { expect, test } from "./fixtures";

test("business assessment explains pending work and persists decision evidence", async ({
  page,
}, testInfo) => {
  await page.goto("/?workspace=classic");
  await page.getByRole("button", { name: "New case", exact: true }).click();
  await page.getByLabel("Case type", { exact: true }).selectOption("DEMO-04");
  await page.getByRole("button", { name: "Create case", exact: true }).click();
  const assessment = page.getByRole("region", {
    name: "Business assessment",
    exact: true,
  });
  await expect(
    assessment.getByText("Compliance", { exact: true }),
  ).toBeVisible();
  await expect(
    assessment.getByText("classification mapping missing", { exact: true }),
  ).toBeVisible();
  await expect(
    assessment.getByText("monica.ferrante@ferrantehale.example.com", { exact: false }),
  ).toBeVisible();
  await assessment
    .getByRole("button", { name: "Record assessment", exact: true })
    .click();
  await expect(
    assessment.getByText("Decision evidence · 1 recorded assessment", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByText("Business assessment recorded", { exact: true }),
  ).toBeVisible();
  await assessment
    .getByText("Decision evidence · 1 recorded assessment", { exact: true })
    .click();
  await expect(
    assessment.getByText("Calendar: eastern-mon-fri-v1", { exact: true }),
  ).toBeVisible();
  await assessment
    .getByText("Completion check: Prerequisites outstanding", { exact: true })
    .click();
  await expect(
    assessment.getByText(
      "The final ILS note must be recorded for this response.",
      { exact: true },
    ),
  ).toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath("phase3.png"),
    fullPage: true,
  });
  const width = await page.evaluate(() =>
    Math.max(innerWidth, document.documentElement.scrollWidth),
  );
  expect(width).toBeLessThanOrEqual(page.viewportSize()!.width + 1);
});
