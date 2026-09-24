import { expect, test } from "@playwright/test";

test("admin signs in immediately as the fixed reviewer, refresh keeps the session and sign out clears it", async ({
  page,
}, testInfo) => {
  const requests: string[] = [];
  page.on("request", (request) => {
    if (new URL(request.url()).pathname.startsWith("/api/"))
      requests.push(request.url());
  });
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Sign in", exact: true }),
  ).toBeVisible();
  await expect(page.getByLabel("Username", { exact: true })).toBeFocused();
  await expect(
    page.getByRole("button", { name: "SSO login", exact: true }),
  ).toBeVisible();
  await expect(page.getByLabel("Username", { exact: true })).toHaveAttribute(
    "type",
    "password",
  );
  await expect(page.locator('input[type="password"], select')).toHaveCount(1);
  await expect(
    page.getByText(/Register|Create account|Create role|Sign up/i),
  ).toHaveCount(0);
  for (const [width, height] of [
    [1280, 720],
    [1366, 768],
    [1100, 650],
  ]) {
    await page.setViewportSize({ width, height });
    const card = await page.locator(".login-card").boundingBox();
    expect(card!.x).toBeGreaterThanOrEqual(0);
    expect(card!.y + card!.height).toBeLessThanOrEqual(height);
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth),
    ).toBeLessThanOrEqual(width);
    await page.screenshot({ path: testInfo.outputPath(`login-${width}.png`) });
  }
  expect(requests).toHaveLength(0);
  await page.getByLabel("Username", { exact: true }).fill("guest");
  await page.getByRole("button", { name: "SSO login", exact: true }).click();
  await expect(page.getByRole("alert")).toHaveText(
    "This username is not authorised to access the dashboard.",
  );
  await expect(page.getByLabel("Username", { exact: true })).toHaveValue("");
  await expect(
    page.getByRole("heading", { name: "Case dashboard", exact: true }),
  ).toHaveCount(0);
  await page.getByLabel("Username", { exact: true }).fill("");
  await page.getByLabel("Username", { exact: true }).pressSequentially("admin");
  await expect(
    page.getByRole("heading", { name: "Case dashboard", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".desk-profile")).toContainText("Admin");
  await expect(page.locator(".desk-profile")).toContainText("Reviewer");
  // Sign out lives in the account menu under the reviewer's name.
  await page.locator(".desk-profile").click();
  await expect(
    page.getByRole("menuitem", { name: "Sign out", exact: true }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Case dashboard", exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath("reviewer-dashboard.png"),
  });
  await page.locator(".desk-profile").click();
  await page.getByRole("menuitem", { name: "Sign out", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Sign in", exact: true }),
  ).toBeVisible();
  await expect(page.getByLabel("Username", { exact: true })).toHaveValue("");
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Sign in", exact: true }),
  ).toBeVisible();
});

test("case and diagnostics URLs require the login screen while Mailbox stays independent", async ({
  page,
  context,
}) => {
  await page.goto("/cases/00000000-0000-0000-0000-000000000001");
  await expect(
    page.getByRole("heading", { name: "Sign in", exact: true }),
  ).toBeVisible();
  await page.getByLabel("Username", { exact: true }).fill("admin");
  await expect(page).toHaveURL("http://127.0.0.1:5174/");
  await expect(
    page.getByRole("heading", { name: "Case dashboard", exact: true }),
  ).toBeVisible();
  await page.locator(".desk-profile").click();
  await page.getByRole("menuitem", { name: "Sign out", exact: true }).click();
  await page.goto("/?workspace=classic");
  await expect(
    page.getByRole("heading", { name: "Sign in", exact: true }),
  ).toBeVisible();
  const mailbox = await context.newPage();
  await mailbox.goto("http://127.0.0.1:5177");
  await expect(
    mailbox.getByRole("button", { name: "New mail", exact: true }),
  ).toBeVisible();
  await expect(mailbox.getByLabel("Username", { exact: true })).toHaveCount(0);
});
