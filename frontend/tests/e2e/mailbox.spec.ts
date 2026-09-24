import { expect, test } from "./fixtures";
import type { Page, APIRequestContext } from "@playwright/test";
import { spawn, execFileSync } from "node:child_process";
import type { ChildProcess } from "node:child_process";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const workspace = fileURLToPath(new URL("../../..", import.meta.url));
const origin = "http://127.0.0.1:8026";
const mailboxOrigin = "http://127.0.0.1:5177";
test.setTimeout(90000);

test("prepared drafts are editable, compact and retain removed attachments through refresh and send", async ({
  page,
  request,
}, testInfo) => {
  let child: ChildProcess | undefined;
  try {
    child = await server(request, page);
    await page.setViewportSize({ width: 1280, height: 720 });
    await page.goto(mailboxOrigin);
    await page
      .getByRole("navigation", { name: "Folders", exact: true })
      .getByRole("button", { name: /^Drafts/ })
      .click();
    await expect(page.locator(".mail-draft-row")).toHaveCount(5);
    await expect(page.locator(".mail-draft-content p")).toHaveCount(0);
    const row = await page.locator(".mail-draft-row").first().boundingBox();
    expect(row!.height).toBeLessThan(90);
    for (let index = 0; index < 5; index++) {
      await page.locator(".mail-draft-content").nth(index).click();
      await expect(page.getByLabel("From", { exact: true })).toBeEditable();
      await expect(
        page.getByLabel("Message subject", { exact: true }),
      ).toBeEditable();
      await expect(
        page.getByLabel("Message body", { exact: true }),
      ).toBeEditable();
      await expect(page.locator(".mail-address-chip")).toHaveText(
        "correspondence@servicing.example.com",
      );
      await expect(page.getByRole("combobox")).toHaveCount(0);
      await page
        .getByRole("button", { name: "Close message", exact: true })
        .click();
    }
    await openDraft(page, /name/i);
    await page
      .getByLabel("From", { exact: true })
      .fill("marcus.j.delgado@outlook.com");
    await page
      .getByLabel("Message subject", { exact: true })
      .fill("Please send my loan schedule");
    const body = "Please email the amortization schedule for loan 0099000002.";
    await page.getByLabel("Message body", { exact: true }).fill(body);
    const removed = await page
      .locator(".mail-compose-attachments .mail-icon-button")
      .count();
    expect(removed).toBeGreaterThan(0);
    for (let index = 0; index < removed; index++)
      await page
        .locator(".mail-compose-attachments .mail-icon-button")
        .first()
        .click();
    await page.reload();
    await expect(page.getByLabel("From", { exact: true })).toHaveValue(
      "marcus.j.delgado@outlook.com",
    );
    await expect(page.getByLabel("Message body", { exact: true })).toHaveValue(
      body,
    );
    await expect(page.locator(".mail-compose-attachments")).toHaveCount(0);
    await expect(
      page.getByText("PDF only · 5 MB each · up to 5 files", { exact: true }),
    ).toHaveCount(0);
    await page.screenshot({
      path: testInfo.outputPath("editable-compact-drafts.png"),
    });
    const sent = page.waitForResponse(
      (response) =>
        response.url().endsWith("/api/mail/messages") &&
        response.request().method() === "POST",
    );
    await page
      .getByRole("button", { name: "Send message", exact: true })
      .click();
    const message = await (await sent).json();
    expect(message.sender).toBe("marcus.j.delgado@outlook.com");
    expect(message.subject).toBe("Please send my loan schedule");
    expect(message.body).toBe(body);
    expect(message.attachments).toEqual([]);
    // The confirmation toast is transient: it appears, then clears itself.
    const toast = page.locator(".mail-toast");
    await expect(toast).toContainText("Message sent.");
    await expect(toast).toHaveCount(0, { timeout: 6000 });
    await expect
      .poll(
        async () =>
          (
            await (
              await request.get(
                origin + `/api/mail/threads/${message.thread_id}`,
              )
            ).json()
          ).thread.case_id,
      )
      .toBeTruthy();
  } finally {
    for (const tab of page.context().pages()) await tab.close();
    await stop(child);
  }
});

test("images preview, remove and survive refresh and sending", async ({
  page,
  request,
}, testInfo) => {
  let child: ChildProcess | undefined;
  try {
    child = await server(request, page);
    await page.setViewportSize({ width: 1280, height: 720 });
    await page.goto(mailboxOrigin);
    await page.getByRole("button", { name: "New mail", exact: true }).click();
    await page
      .getByLabel("From", { exact: true })
      .fill("marcus.j.delgado@outlook.com");
    await page
      .getByLabel("Message subject", { exact: true })
      .fill("Schedule request with image");
    await page
      .getByLabel("Message body", { exact: true })
      .fill("Please send the amortization schedule for loan 0099000002.");
    const file = {
      name: "Supporting image.png",
      mimeType: "image/png",
      buffer: await fs.readFile(
        path.join(workspace, "frontend/tests/fixtures/attachment.png"),
      ),
    };
    await page.getByLabel("Add attachments").setInputFiles(file);
    const preview = page.getByRole("button", {
      name: "Preview Supporting image.png",
      exact: true,
    });
    await preview.click();
    const img = page.getByRole("img", { name: file.name, exact: true });
    await expect(img).toBeVisible();
    await expect(img).toHaveJSProperty("naturalWidth", 200);
    await expect(
      page.getByRole("link", { name: "Download", exact: true }),
    ).toHaveAttribute("download", file.name);
    await page.screenshot({ path: testInfo.outputPath("image-preview.png") });
    await page.keyboard.press("Escape");
    await page
      .getByRole("button", { name: "Remove Supporting image.png", exact: true })
      .click();
    await expect(preview).toHaveCount(0);
    await page.getByLabel("Add attachments").setInputFiles(file);
    await expect(preview).toBeVisible();
    await page.reload();
    await preview.click();
    await expect(img).toHaveJSProperty("naturalWidth", 200);
    await page.keyboard.press("Escape");
    await page
      .getByRole("button", { name: "Send message", exact: true })
      .click();
    await page
      .locator('.mail-letter[data-direction="outgoing"]')
      .getByRole("button", {
        name: "Preview Supporting image.png",
        exact: true,
      })
      .click();
    await expect(img).toHaveJSProperty("naturalWidth", 200);
  } finally {
    for (const tab of page.context().pages()) await tab.close();
    await stop(child);
  }
});

test("Drafts supports selection and filtering, and only Reset restores deleted drafts", async ({
  page,
  request,
}, testInfo) => {
  let child: ChildProcess | undefined;
  try {
    child = await server(request, page);
    await page.goto(mailboxOrigin);
    const folders = page.getByRole("navigation", {
      name: "Folders",
      exact: true,
    });
    await folders.getByRole("button", { name: /^Drafts/ }).click();
    await expect(page.locator(".mail-draft-row")).toHaveCount(5);
    await expect(
      page.getByRole("checkbox", { name: "Select all drafts" }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Filter drafts" }).click();
    await page
      .getByRole("button", { name: "With attachments", exact: true })
      .click();
    await expect(page.locator(".mail-draft-row")).toHaveCount(4);
    await page.getByRole("checkbox", { name: "Select all drafts" }).check();
    await expect(page.locator(".mail-draft-row input:checked")).toHaveCount(4);
    await page.getByRole("button", { name: "Delete", exact: true }).click();
    await expect(page.locator(".mail-draft-row")).toHaveCount(0);
    await page.getByRole("button", { name: "Undo", exact: true }).click();
    await expect(page.locator(".mail-draft-row")).toHaveCount(4);
    await page.getByRole("button", { name: "Clear", exact: true }).click();
    await expect(page.locator(".mail-draft-row")).toHaveCount(5);
    await page.locator(".mail-draft-row input").first().check();
    await expect(
      page.getByRole("checkbox", { name: "Select all drafts" }),
    ).toHaveJSProperty("indeterminate", true);
    await page.getByRole("button", { name: "Clear selection" }).click();
    for (const [width, height] of [
      [1280, 720],
      [1366, 768],
      [1100, 650],
    ]) {
      await page.setViewportSize({ width, height });
      await page.screenshot({
        path: testInfo.outputPath(`drafts-${width}.png`),
      });
      await page.getByRole("button", { name: "New mail", exact: true }).click();
      await expect(page.getByRole("combobox")).toHaveCount(0);
      await expect(page.getByLabel("From", { exact: true })).toHaveValue("");
      await expect(
        page.getByLabel("Message subject", { exact: true }),
      ).toHaveValue("");
      await expect(
        page.getByLabel("Message body", { exact: true }),
      ).toHaveValue("");
      await expect(page.getByLabel("Message body", { exact: true })).toHaveCSS(
        "font-size",
        "14px",
      );
      await expect(
        page.getByRole("button", { name: "Choose a message template" }),
      ).toHaveCount(0);
      const send = await page
        .getByRole("button", { name: "Send message", exact: true })
        .boundingBox();
      expect(send!.y + send!.height).toBeLessThanOrEqual(height);
      expect(send!.x + send!.width).toBeLessThanOrEqual(width);
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth),
      ).toBeLessThanOrEqual(width);
      await page.screenshot({
        path: testInfo.outputPath(`new-mail-${width}.png`),
      });
      await page.getByRole("button", { name: "Discard", exact: true }).click();
    }
    await page.getByRole("checkbox", { name: "Select all drafts" }).check();
    await page.getByRole("button", { name: "Delete", exact: true }).click();
    await expect(page.locator(".mail-draft-row")).toHaveCount(0);
    await page.reload();
    await expect(
      page.getByRole("heading", { name: "Drafts", exact: true }),
    ).toBeVisible();
    await expect(page.locator(".mail-draft-row")).toHaveCount(0);
    // Reset asks first; Cancel leaves the mailbox as it is.
    await page
      .getByRole("button", { name: "Reset mailbox", exact: true })
      .click();
    const confirm = page.getByRole("dialog", { name: "Reset mailbox?" });
    await expect(confirm).toContainText("deletes every case");
    await confirm.getByRole("button", { name: "Cancel", exact: true }).click();
    await expect(confirm).not.toBeVisible();
    await expect(page.locator(".mail-draft-row")).toHaveCount(0);
    await confirmReset(page);
    await folders.getByRole("button", { name: /^Drafts/ }).click();
    await expect(page.locator(".mail-draft-row")).toHaveCount(5);
    expect(
      (await (await request.get(origin + "/api/operations")).json()).cases,
    ).toHaveLength(0);
  } finally {
    for (const tab of page.context().pages()) await tab.close();
    await stop(child);
  }
});

test("refresh retains a pending conversation and Reset synchronizes across mailbox tabs", async ({
  page,
  request,
}) => {
  let child: ChildProcess | undefined;
  try {
    child = await server(request, page);
    await request.post(origin + "/test-only/require-review");
    const sender = await compose(page);
    await expect(
      page.getByRole("button", { name: "Approve and send" }),
    ).toBeEnabled({ timeout: 30000 });
    await sender.reload();
    await expect(sender.locator(".mail-message-row")).toHaveCount(1);
    await page.getByRole("button", { name: "Approve and send" }).click();
    await expect(
      sender.locator('.mail-letter[data-direction="incoming"]'),
    ).toBeVisible({ timeout: 30000 });
    await sender.reload();
    await expect(sender.locator(".mail-letter")).toHaveCount(2);
    const second = await page.context().newPage();
    await second.goto(mailboxOrigin);
    await expect(second.locator(".mail-letter")).toHaveCount(2);
    await confirmReset(second);
    for (const tab of [sender, second]) {
      await expect(tab.locator(".mail-message-row")).toHaveCount(0);
      await tab
        .getByRole("navigation", { name: "Folders", exact: true })
        .getByRole("button", { name: /^Drafts/ })
        .click();
      await expect(tab.locator(".mail-draft-row")).toHaveCount(5);
    }
    // The reset is shared: the workspace's cases return to the base state too.
    expect(
      (await (await request.get(origin + "/api/operations")).json()).cases,
    ).toHaveLength(0);
  } finally {
    for (const tab of page.context().pages()) await tab.close();
    await stop(child);
  }
});

async function renderedPdf(page: Page) {
  const canvas = page
    .locator('.mail-document-preview canvas[data-rendered="true"]')
    .first();
  await expect(canvas).toBeVisible({ timeout: 15000 });
  expect(
    await canvas.evaluate((element: HTMLCanvasElement) => {
      const pixels = element
        .getContext("2d")!
        .getImageData(0, 0, element.width, element.height).data;
      let ink = 0;
      for (let index = 0; index < pixels.length; index += 4)
        if (
          pixels[index] < 180 &&
          pixels[index + 1] < 180 &&
          pixels[index + 2] < 180
        )
          ink++;
      return ink;
    }),
  ).toBeGreaterThan(500);
}

test("EFT replies keep their payment choice across refresh without a template dropdown", async ({
  page,
  request,
}, testInfo) => {
  let child: ChildProcess | undefined;
  try {
    child = await server(request, page);
    await page.goto(mailboxOrigin);
    await openDraft(page, /EFT instead of checks/i);
    await page
      .getByRole("button", { name: "Send message", exact: true })
      .click();
    await page.getByRole("button", { name: "Reply", exact: true }).click();
    await expect(page.getByRole("combobox")).toHaveCount(0);
    await expect(
      page.getByRole("radio", { name: "Refund", exact: true }),
    ).toBeChecked();
    await page
      .getByRole("radio", { name: "Mortgage payment", exact: true })
      .check();
    await expect(page.getByLabel("Message body", { exact: true })).toHaveValue(
      /automatically each month/,
    );
    await page.reload();
    await expect(
      page.getByRole("radio", { name: "Mortgage payment", exact: true }),
    ).toBeChecked();
    await page.screenshot({ path: testInfo.outputPath("eft-reply.png") });
    await page
      .getByRole("button", { name: "Send message", exact: true })
      .click();
    await expect(
      page.locator('.mail-letter[data-direction="outgoing"]'),
    ).toHaveCount(2);
    const operations = await (
      await request.get(origin + "/api/operations")
    ).json();
    const thread = await (
      await request.get(
        origin + "/api/mail/threads/" + operations.threads[0].id,
      )
    ).json();
    expect(thread.messages[1].template_key).toBe("eft-incoming_payment");
  } finally {
    for (const tab of page.context().pages()) await tab.close();
    await stop(child);
  }
});

test("PDF attachments work in custom and prepared drafts, survive sending, and preview retries recover", async ({
  page,
  request,
}, testInfo) => {
  let child: ChildProcess | undefined;
  try {
    child = await server(request, page);
    await page.goto(mailboxOrigin);
    await openDraft(page, /amortization/i);
    const input = page.getByLabel("Add attachments");
    await input.setInputFiles({
      name: "notes.txt",
      mimeType: "text/plain",
      buffer: Buffer.from("not a PDF"),
    });
    await expect(
      page.getByText("Choose a PDF or a PNG, JPEG, GIF or WebP image.", {
        exact: true,
      }),
    ).toBeVisible();
    const file = path.join(
      workspace,
      "data/documents/v1/DEMO-02/base/amortization.pdf",
    );
    await input.setInputFiles(file);
    await expect(page.locator(".mail-upload-chip")).toHaveCount(1);
    await page
      .getByRole("button", { name: "Preview amortization.pdf", exact: true })
      .click();
    await renderedPdf(page);
    await page.screenshot({
      path: testInfo.outputPath("uploaded-pdf-preview.png"),
    });
    await page.keyboard.press("Escape");
    await page
      .getByRole("button", { name: "Remove amortization.pdf", exact: true })
      .click();
    await expect(page.locator(".mail-upload-chip")).toHaveCount(0);
    await input.setInputFiles(file);
    await expect(page.locator(".mail-upload-chip")).toHaveCount(1);
    await page
      .getByRole("button", { name: "Close message", exact: true })
      .click();
    await page.getByRole("button", { name: "New mail", exact: true }).click();
    await input.setInputFiles(file);
    await expect(page.locator(".mail-upload-chip")).toHaveCount(1);
    await page
      .getByLabel("From", { exact: true })
      .fill("marcus.j.delgado@outlook.com");
    await page
      .getByLabel("Message subject", { exact: true })
      .fill("My mortgage schedule");
    await page
      .getByLabel("Message body", { exact: true })
      .fill(
        "Please email the current amortization schedule for loan 0099000002.",
      );
    await page.reload();
    await expect(
      page.getByLabel("Message subject", { exact: true }),
    ).toHaveValue("My mortgage schedule");
    await expect(page.locator(".mail-upload-chip")).toHaveCount(1);
    await page
      .getByRole("button", { name: "Close message", exact: true })
      .click();
    await page
      .getByRole("navigation", { name: "Folders", exact: true })
      .getByRole("button", { name: /^Drafts/ })
      .click();
    await page
      .locator(".mail-draft-row")
      .filter({ hasText: "My mortgage schedule" })
      .click();
    await expect(page.locator(".mail-upload-chip")).toHaveCount(1);
    await page
      .getByRole("button", { name: "Send message", exact: true })
      .click();
    await expect(page.locator(".mail-letter")).toHaveCount(2, {
      timeout: 30000,
    });
    const latest = page.locator(".mail-letter").first();
    await expect(latest).toHaveAttribute("data-direction", "incoming");
    await expect(latest).toHaveCSS("background-color", "rgb(255, 255, 255)");
    await page.screenshot({
      path: testInfo.outputPath("light-newest-first-conversation.png"),
    });
    await page
      .getByRole("button", { name: "Preview amortization.pdf", exact: true })
      .click();
    await renderedPdf(page);
    await page.keyboard.press("Escape");
    let failPreview = true;
    await page.route(
      "**/api/mail/deliveries/*/attachments/0",
      async (route) => {
        if (failPreview) {
          await route.fulfill({
            status: 503,
            json: { error: { message: "Temporary document service failure." } },
          });
        } else await route.fallback();
      },
    );
    await latest.getByRole("button", { name: /^Preview / }).click();
    await expect(page.getByRole("alert")).toHaveText(
      "Temporary document service failure.",
    );
    failPreview = false;
    await page.getByRole("button", { name: "Try again", exact: true }).click();
    await renderedPdf(page);
    await page.keyboard.press("Escape");
    await latest
      .getByRole("button", { name: "Collapse message", exact: true })
      .click();
    await expect(latest.locator(".mail-letter-body")).toHaveCount(0);
    await latest
      .getByRole("button", { name: "Expand message", exact: true })
      .click();
    await expect(latest.locator(".mail-letter-body")).toBeVisible();
  } finally {
    for (const tab of page.context().pages()) await tab.close();
    await stop(child);
  }
});

test("Mailbox and Desk resets clear both apps and every case", async ({
  page,
  request,
}) => {
  let child: ChildProcess | undefined;
  try {
    child = await server(request, page);
    await request.post(origin + "/test-only/require-review");
    const sender = await compose(page);
    await expect(
      page.getByRole("button", { name: "Approve and send" }),
    ).toBeEnabled({ timeout: 30000 });
    const folders = sender.getByRole("navigation", {
      name: "Folders",
      exact: true,
    });
    // Mailbox reset: the open Desk case closes and the dashboard is empty.
    await confirmReset(sender);
    await expect(sender.locator(".mail-message-row")).toHaveCount(0);
    await folders.getByRole("button", { name: /^Drafts/ }).click();
    await expect(sender.locator(".mail-draft-row")).toHaveCount(5);
    await expect(
      page.getByRole("heading", { name: "Case dashboard", exact: true }),
    ).toBeVisible({ timeout: 10000 });
    await expect(page.getByRole("status").first()).toContainText(
      "reset from the Mailbox",
    );
    await expect(page.getByRole("table").locator("tbody tr")).toHaveCount(0);
    expect(
      (await (await request.get(origin + "/api/operations")).json()).cases,
    ).toHaveLength(0);
    for (const name of [/^Inbox/, /^Sent Items/, /^Deleted Items/]) {
      await folders.getByRole("button", { name }).click();
      await expect(sender.locator(".mail-message-row")).toHaveCount(0);
    }
    // Only explicit reset restores drafts: a discarded draft stays discarded.
    await folders.getByRole("button", { name: /^Drafts/ }).click();
    await sender.locator(".mail-draft-row").first().click();
    await sender.getByRole("button", { name: "Discard", exact: true }).click();
    await expect(sender.locator(".mail-draft-row")).toHaveCount(4);
    await sender.reload();
    await folders.getByRole("button", { name: /^Drafts/ }).click();
    await expect(sender.locator(".mail-draft-row")).toHaveCount(4);

    // Sending again works after a reset, and the Desk announces the new case.
    await openDraft(sender, /amortization/i);
    await sender
      .getByRole("button", { name: "Send message", exact: true })
      .click();
    await expect(page.getByRole("table").locator("tbody tr")).toHaveCount(1, {
      timeout: 15000,
    });

    // Desk reset (account menu, above Sign out) clears the Mailbox too.
    await page.locator(".desk-profile").click();
    const items = page.getByRole("menuitem");
    await expect(items).toHaveText([/Reset workspace/, /Sign out/]);
    await items.filter({ hasText: "Reset workspace" }).click();
    const dialog = page.getByRole("dialog").filter({
      has: page.getByRole("heading", { name: "Reset workspace?" }),
    });
    await dialog
      .getByRole("button", { name: "Reset workspace", exact: true })
      .click();
    await expect(dialog).not.toBeVisible();
    await expect(page.getByRole("table").locator("tbody tr")).toHaveCount(0);
    await expect(sender.locator(".mail-message-row")).toHaveCount(0, {
      timeout: 10000,
    });
    await folders.getByRole("button", { name: /^Drafts/ }).click();
    await expect(sender.locator(".mail-draft-row")).toHaveCount(5);
    await folders.getByRole("button", { name: /^Sent Items/ }).click();
    await expect(sender.locator(".mail-message-row")).toHaveCount(0);
    expect(
      (await (await request.get(origin + "/api/operations")).json()).cases,
    ).toHaveLength(0);
  } finally {
    for (const tab of page.context().pages()) await tab.close();
    await stop(child);
  }
});

test("custom mail is editable, automatically processed and previews draft and delivered documents", async ({
  page,
  request,
}, testInfo) => {
  let child: ChildProcess | undefined;
  try {
    child = await server(request, page);
    await page.goto(mailboxOrigin);
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    const folders = page.getByRole("navigation", {
      name: "Folders",
      exact: true,
    });
    await folders.getByRole("button", { name: /^Drafts/ }).click();
    await expect(page.locator(".mail-draft-row")).toHaveCount(5);
    await page.locator(".mail-draft-row").first().click();
    await page
      .getByRole("button", { name: /^Preview / })
      .first()
      .click();
    const preview = page.locator(".mail-document-preview");
    await expect(preview).toBeVisible();
    await expect(preview.locator("canvas").first()).toHaveAttribute(
      "data-rendered",
      "true",
      { timeout: 15000 },
    );
    await page.keyboard.press("Escape");
    await expect(preview).toHaveCount(0);
    await page
      .getByRole("button", { name: "Close message", exact: true })
      .click();
    await page.getByRole("button", { name: "New mail", exact: true }).click();
    await page
      .getByLabel("From", { exact: true })
      .fill("marcus.j.delgado@outlook.com");
    await page
      .getByLabel("Message subject", { exact: true })
      .fill("Please send my loan schedule");
    await page
      .getByLabel("Message body", { exact: true })
      .fill(
        "Hello, please send the amortization schedule for my loan 0099000002. Thank you.",
      );
    await expect(page.locator(".mail-address-chip")).toHaveText(
      "correspondence@servicing.example.com",
    );
    await expect(page.locator(".mail-compose-address select")).toHaveCount(0);
    await page.screenshot({ path: testInfo.outputPath("custom-compose.png") });
    await page
      .getByRole("button", { name: "Close message", exact: true })
      .click();
    await folders.getByRole("button", { name: /^Drafts/ }).click();
    await page
      .locator(".mail-draft-row")
      .filter({ hasText: "Please send my loan schedule" })
      .click();
    await expect(page.getByLabel("From", { exact: true })).toHaveValue(
      "marcus.j.delgado@outlook.com",
    );
    await page
      .getByRole("button", { name: "Send message", exact: true })
      .click();
    await expect(
      page.locator(".mail-letter[data-direction='incoming']"),
    ).toBeVisible({ timeout: 30000 });
    await page.getByRole("button", { name: /^Preview / }).click();
    await expect(preview.locator("canvas").first()).toHaveAttribute(
      "data-rendered",
      "true",
      { timeout: 15000 },
    );
    expect(
      await preview
        .locator("canvas")
        .first()
        .evaluate((canvas) => {
          const surface = canvas as HTMLCanvasElement;
          const pixels = surface
            .getContext("2d")!
            .getImageData(0, 0, surface.width, surface.height).data;
          let ink = 0;
          for (let index = 0; index < pixels.length; index += 4) {
            if (pixels[index + 3] > 0 && pixels[index] < 200) ink++;
          }
          return ink;
        }),
    ).toBeGreaterThan(1000);
    await page.screenshot({
      path: testInfo.outputPath("document-preview.png"),
    });
    await page.getByRole("button", { name: "Close document preview" }).click();
    const state = await (await request.get(origin + "/api/operations")).json();
    expect(state.cases).toHaveLength(1);
    expect(state.cases[0].subject).toBe("Please send my loan schedule");
    expect(errors).toEqual([]);
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth),
    ).toBeLessThanOrEqual(page.viewportSize()!.width);
  } finally {
    for (const tab of page.context().pages()) await tab.close();
    await stop(child);
  }
});

test("a reviewer resolves an unknown custom sender and the agent continues", async ({
  page,
  request,
}) => {
  let child: ChildProcess | undefined;
  try {
    child = await server(request, page);
    const sender = await page.context().newPage();
    await sender.goto(mailboxOrigin);
    await sender.getByRole("button", { name: "New mail", exact: true }).click();
    await sender
      .getByLabel("From", { exact: true })
      .fill("new-address@example.com");
    await sender
      .getByLabel("Message subject", { exact: true })
      .fill("Request for schedule");
    await sender
      .getByLabel("Message body", { exact: true })
      .fill("Please send the amortization schedule for loan 0099000002.");
    await sender
      .getByRole("button", { name: "Send message", exact: true })
      .click();
    await page.goto("/");
    const review = page.getByRole("region", {
      name: "Incoming requests needing review",
    });
    await expect(review).toBeVisible({ timeout: 30000 });
    await review
      .getByRole("button", { name: "Review request", exact: true })
      .click();
    await review.getByLabel("Verified loan").selectOption("0099000002");
    await expect(review.getByLabel("Reviewer", { exact: true })).toHaveValue(
      "Admin",
    );
    await expect(
      review.getByLabel("Reviewer", { exact: true }),
    ).not.toBeEditable();
    await review
      .getByLabel("Review note")
      .fill(
        "Verified the sender with the borrower and confirmed the intended loan.",
      );
    await review.getByRole("checkbox").check();
    await review.getByRole("button", { name: "Confirm and continue" }).click();
    await expect(review).toHaveCount(0);
    await expect(page.getByRole("table").locator("tbody tr")).toHaveCount(1);
    await expect(
      sender.locator(".mail-letter[data-direction='incoming']"),
    ).toBeVisible({ timeout: 30000 });
    await expect(sender.locator(".mail-letter").first()).toHaveAttribute(
      "data-direction",
      "incoming",
    );
    await expect(
      sender.locator(".mail-card-recipient span").first(),
    ).toHaveAttribute("title", "marcus.j.delgado@outlook.com");
  } finally {
    for (const tab of page.context().pages()) await tab.close();
    await stop(child);
  }
});

async function server(request: APIRequestContext, page: Page) {
  const data = path.join(
    workspace,
    ".local",
    "mailbox-browser",
    crypto.randomUUID(),
  );
  await fs.mkdir(data, { recursive: true });
  const child = spawn(
    path.join(
      workspace,
      ".venv",
      process.platform === "win32" ? "Scripts/python.exe" : "bin/python",
    ),
    [
      "-m",
      "uvicorn",
      "backend.tests.mailbox_server:app",
      "--host",
      "127.0.0.1",
      "--port",
      "8026",
      "--no-access-log",
    ],
    {
      cwd: workspace,
      windowsHide: true,
      stdio: "ignore",
      env: {
        ...process.env,
        APP_DATA_DIR: data,
        AZURE_OPENAI_BASE_URL: "",
        AZURE_OPENAI_API_KEY: "",
        AZURE_OPENAI_DEPLOYMENT: "",
      },
    },
  );
  await expect
    .poll(
      async () => {
        try {
          return (await request.get(origin + "/api/health")).ok();
        } catch {
          return false;
        }
      },
      { timeout: 30000 },
    )
    .toBe(true);
  await page.context().route(
    (url) => url.pathname.startsWith("/api/"),
    async (route) => {
      const url = new URL(route.request().url());
      try {
        const response = await route.fetch({
          url: origin + url.pathname + url.search,
        });
        if (url.pathname === "/api/config")
          await route.fulfill({
            response,
            json: { ...(await response.json()), agent_available: true },
          });
        else await route.fulfill({ response });
      } catch {
        await route.abort().catch(() => undefined);
      }
    },
  );
  return child;
}
// Waits for the test server to exit, so the next test's server can bind the
// same port and its health check cannot reach a server that is shutting down.
async function stop(child?: ChildProcess) {
  if (!child?.pid || child.exitCode !== null || child.signalCode !== null)
    return;
  const exited = new Promise<void>((resolve) => child.once("exit", () => resolve()));
  if (process.platform === "win32") {
    try {
      execFileSync("taskkill", ["/PID", String(child.pid), "/T", "/F"], {
        windowsHide: true,
        stdio: "ignore",
      });
    } catch {
      /* Already exited. */
    }
  } else child.kill("SIGTERM");
  const timeout = new Promise<"timeout">((resolve) =>
    setTimeout(() => resolve("timeout"), 15000),
  );
  if ((await Promise.race([exited, timeout])) === "timeout") {
    child.kill("SIGKILL");
    await exited;
  }
}
async function confirmReset(tab: Page) {
  await tab
    .getByRole("button", { name: "Reset mailbox", exact: true })
    .click();
  const dialog = tab.getByRole("dialog", { name: "Reset mailbox?" });
  await expect(dialog).toBeVisible();
  await dialog
    .getByRole("button", { name: "Reset mailbox", exact: true })
    .click();
  await expect(dialog).not.toBeVisible();
}
async function openDraft(page: Page, subject: RegExp) {
  await page
    .getByRole("navigation", { name: "Folders", exact: true })
    .getByRole("button", { name: /^Drafts/ })
    .click();
  await page
    .locator(".mail-draft-row")
    .filter({ hasText: subject })
    .getByRole("button")
    .click();
}

async function compose(page: Page) {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Case dashboard", exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("table").locator("tbody tr")).toHaveCount(0);
  const sender = await page.context().newPage();
  await sender.goto(mailboxOrigin);
  await openDraft(sender, /amortization/i);
  await expect(sender.getByRole("combobox")).toHaveCount(0);
  await expect(sender.getByLabel("Message body", { exact: true })).toHaveValue(
    /Could you please send me a current amortization schedule for my loan, number 0099000002\?/,
  );
  await sender
    .getByRole("button", { name: "Send message", exact: true })
    .click();
  await expect(
    sender.locator(".mail-letter[data-direction='outgoing']"),
  ).toBeVisible();
  await expect(sender.getByRole("link", { name: /desk|case/i })).toHaveCount(0);
  await expect(
    sender.getByRole("button", { name: "Open case in desk" }),
  ).toHaveCount(0);
  // The already-open dashboard receives the new case without a reload or a cross-app link.
  await expect(page.getByRole("table").locator("tbody tr")).toHaveCount(1);
  await expect(page.locator(".desk-rail, aside.sidebar")).toHaveCount(0);
  await expect(
    page.locator(
      'a[href*="sender"], a[href*="mailbox"], a[href*="5177"], a[href*="5176"]',
    ),
  ).toHaveCount(0);
  await page.getByRole("table").locator("tbody tr td").nth(1).click();
  return sender;
}
async function navigate(page: Page, name: string) {
  if (name === "Mailbox") {
    await page.goto(mailboxOrigin);
    return;
  }
  await page
    .getByRole("navigation", { name: "Case sections" })
    .getByRole("button", { name: "System workspaces", exact: true })
    .click();
  await page
    .getByRole("navigation", { name: "System workspaces" })
    .getByRole("button", { name, exact: true })
    .click();
}

test("Mailbox keeps drafts, separates incoming and sent mail, and supports reversible folder actions", async ({
  page,
  request,
}, testInfo) => {
  let child: ChildProcess | undefined;
  try {
    child = await server(request, page);
    await page.goto(mailboxOrigin);
    await expect(page).toHaveTitle("Mailbox");
    await expect(
      page.getByRole("link", { name: "Mailbox", exact: true }),
    ).toBeVisible();
    await openDraft(page, /amortization/i);
    await expect(page.getByRole("combobox")).toHaveCount(0);
    await page
      .getByRole("button", { name: "Close message", exact: true })
      .click();
    await page.reload();
    const folders = page.getByRole("navigation", {
      name: "Folders",
      exact: true,
    });
    await folders.getByRole("button", { name: /^Drafts/ }).click();
    await expect(page.locator(".mail-draft-row")).toHaveCount(5);
    await expect(page.getByText("Favorites", { exact: true })).toHaveCount(0);
    await page
      .locator(".mail-draft-row")
      .filter({ hasText: /amortization/i })
      .click();
    await expect(page.getByRole("combobox")).toHaveCount(0);
    await expect(page.getByLabel("Message body", { exact: true })).toHaveValue(
      /Could you please send me a current amortization schedule for my loan, number 0099000002\?/,
    );
    expect(
      (await (await request.get(origin + "/api/operations")).json()).cases,
    ).toHaveLength(0);
    await page
      .getByRole("button", { name: "Send message", exact: true })
      .click();
    await expect(
      page.getByRole("heading", { name: "Sent Items", exact: true }),
    ).toBeVisible();
    await expect(
      page.locator(".mail-letter[data-direction='outgoing']"),
    ).toBeVisible();
    await expect(
      page.locator(".mail-letter[data-direction='incoming']"),
    ).toBeVisible({ timeout: 30000 });
    await folders.getByRole("button", { name: /^Inbox/ }).click();
    await expect(page.locator(".mail-message-row")).toHaveCount(1);
    await page.locator(".mail-row-content").click();
    await expect(page.locator(".mail-message-row.unread")).toHaveCount(0);
    await page
      .getByRole("button", { name: "Read / Unread", exact: true })
      .click();
    await expect(page.locator(".mail-message-row.unread")).toHaveCount(1);
    await page.getByRole("button", { name: "Filter messages" }).click();
    await page
      .locator(".mail-popover")
      .getByRole("button", { name: "Unread", exact: true })
      .click();
    await expect(page.locator(".mail-message-row")).toHaveCount(1);
    await page.getByRole("button", { name: "Flag", exact: true }).click();
    await folders.getByRole("button", { name: /^Flagged/ }).click();
    await expect(page.locator(".mail-message-row")).toHaveCount(1);
    await page
      .getByRole("toolbar", { name: "Mail actions" })
      .getByRole("button", { name: "Archive", exact: true })
      .click();
    await folders.getByRole("button", { name: /^Archive/ }).click();
    await expect(page.locator(".mail-message-row")).toHaveCount(1);
    await page.getByRole("button", { name: "Unflag", exact: true }).click();
    await page.getByRole("button", { name: "Undo", exact: true }).click();
    await expect(page.locator(".mail-message-row")).toHaveCount(0);
    await folders.getByRole("button", { name: /^Inbox/ }).click();
    await expect(page.locator(".mail-message-row")).toHaveCount(1);
    await expect(
      page.getByRole("button", { name: "Flag", exact: true }),
    ).toBeEnabled();
    await page
      .getByRole("toolbar", { name: "Mail actions" })
      .getByRole("button", { name: "Archive", exact: true })
      .click();
    await folders.getByRole("button", { name: /^Archive/ }).click();
    await expect(
      page.getByRole("heading", { name: "Archive", exact: true }),
    ).toBeVisible();
    await expect(page.locator(".mail-message-row")).toHaveCount(1);
    await page.getByRole("button", { name: "Delete", exact: true }).click();
    await folders.getByRole("button", { name: /^Deleted Items/ }).click();
    await expect(page.locator(".mail-message-row")).toHaveCount(1);
    await page.reload();
    await expect(
      page.getByRole("heading", { name: "Deleted Items", exact: true }),
    ).toBeVisible();
    await expect(page.locator(".mail-message-row")).toHaveCount(1);
    await expect(page.locator(".mail-letter-status")).toHaveCount(0);
    await expect(
      page.getByText(
        /^(From servicing|To servicing|Received by servicing|Delivered)$/,
      ),
    ).toHaveCount(0);
    await page.getByRole("button", { name: "Move to", exact: true }).click();
    await page
      .locator(".mail-popover")
      .getByRole("button", { name: "Inbox", exact: true })
      .click();
    await folders.getByRole("button", { name: /^Inbox/ }).click();
    await expect(page.locator(".mail-message-row")).toHaveCount(1);
    await page
      .getByRole("textbox", { name: "Search mail" })
      .fill("no-matching-subject");
    await expect(page.locator(".mail-message-row")).toHaveCount(0);
    await page.getByRole("button", { name: "Clear search" }).click();
    await expect(page.locator(".mail-message-row")).toHaveCount(1);
    await page.getByRole("button", { name: "Settings", exact: true }).click();
    await page.getByLabel("Compact message list").check();
    await page.keyboard.press("Escape");
    await page.getByRole("button", { name: "Toggle folder pane" }).click();
    await expect(folders).toHaveCount(0);
    await page.getByRole("button", { name: "Toggle folder pane" }).click();
    const state = await (await request.get(origin + "/api/operations")).json();
    expect(state.cases).toHaveLength(1);
    expect(state.runs).toHaveLength(1);
    await page.screenshot({
      path: testInfo.outputPath("mailbox-reference.png"),
    });
  } finally {
    for (const tab of page.context().pages()) await tab.close();
    await stop(child);
  }
});

test("mail starts the agent and exposes the same delivery, document and servicing records across screens", async ({
  page,
  request,
}, testInfo) => {
  let child: ChildProcess | undefined;
  try {
    child = await server(request, page);
    const manualStarts: string[] = [];
    page.on("request", (r) => {
      if (r.method() === "POST" && /\/cases\/[^/]+\/runs$/.test(r.url()))
        manualStarts.push(r.url());
    });
    const sender = await compose(page);
    const cct = page.getByRole("region", { name: "Detailed case workspace" });
    await expect(cct.locator(".desk-case-header")).toContainText("Closed", {
      timeout: 30000,
    });
    await expect(
      page.getByRole("button", { name: "Start agent", exact: true }),
    ).toHaveCount(0);
    await expect(
      page.getByRole("region", { name: "Borrower correspondence" }),
    ).toBeVisible();
    await expect(
      page.getByRole("region", { name: "Agent activity timeline" }),
    ).toBeVisible();
    await expect(
      page.getByRole("region", { name: "Response draft and review" }),
    ).toBeVisible();
    await page.screenshot({
      path: testInfo.outputPath("case-workspace.png"),
      fullPage: true,
    });
    await page.getByRole("button", { name: "Replay", exact: true }).click();
    await expect(
      page.getByRole("button", { name: "Stop replay", exact: true }),
    ).toBeVisible();
    await page
      .getByRole("button", { name: "Stop replay", exact: true })
      .click();
    await navigate(page, "OnBase");
    await expect(
      page.getByRole("link", { name: "Open combined response PDF" }),
    ).toBeVisible();
    // Identity checks, index keywords and the verified document trail.
    const sources = page.getByRole("article", { name: "Source documents" });
    await expect(sources.getByText("Loan matches")).toBeVisible();
    await expect(sources.getByText(/Attached to response v1/)).toBeVisible();
    await expect(page.locator(".sx-keywords")).toContainText(
      "INQ Email Reply",
    );
    await expect(page.locator(".sx-arrow.ok").first()).toHaveText("identical");
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({
      path: testInfo.outputPath("onbase.png"),
      fullPage: true,
    });
    // Only two case layouts remain.
    await expect(
      page
        .getByRole("navigation", { name: "Case sections" })
        .getByRole("button"),
    ).toHaveText(["Case workspace", "System workspaces"]);
    // Agent activity ends with Run summary and recovery.
    await navigate(page, "Agent activity");
    await expect(
      page.getByRole("region", { name: "Run summary and recovery" }),
    ).toBeVisible();
    await expect(
      page.getByRole("region", { name: "Saved response and records" }),
    ).toHaveCount(0);
    await page.screenshot({
      path: testInfo.outputPath("agent-activity.png"),
      fullPage: true,
    });
    // The business assessment is shown inside CCT instead of its own tab.
    await navigate(page, "CCT");
    await expect(
      page.getByRole("region", { name: "Business assessment", exact: true }),
    ).toBeVisible();
    // CCT shows verified closure and the full case progress.
    await expect(
      page.getByRole("region", { name: "Closure checklist" }),
    ).toContainText("4 of 4 verified");
    await expect(
      page.getByRole("list", { name: "Case progress" }).locator(".sx-step.done"),
    ).toHaveCount(6);
    await expect(
      page.getByRole("article", { name: "Case timeline" }),
    ).toContainText("Deliver approved response");
    await page.screenshot({
      path: testInfo.outputPath("cct.png"),
      fullPage: true,
    });
    await navigate(page, "ILS");
    await expect(
      page.getByText("Servicing notes", { exact: true }),
    ).toBeVisible();
    await expect(page.getByText(/INQ Email Reply/).first()).toBeVisible();
    // Grouped, formatted servicing facts instead of raw keys.
    const profile = page.getByRole("article", { name: "Loan profile" });
    await expect(profile).toContainText("Authorized recipient");
    await expect(profile).not.toContainText("_minor");
    await expect(page.getByText("Standout Comment").first()).toBeVisible();
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({
      path: testInfo.outputPath("ils.png"),
      fullPage: true,
    });
    await navigate(page, "Secure mail");
    await expect(
      page.getByRole("region", { name: "Secure mail workspace" }),
    ).toContainText("marcus.j.delgado@outlook.com");
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({
      path: testInfo.outputPath("secure-mail.png"),
      fullPage: true,
    });
    await expect(
      sender.locator(".mail-letter[data-direction='incoming']"),
    ).toBeVisible();
    const state = await (await request.get(origin + "/api/operations")).json();
    expect(state.cases).toHaveLength(1);
    expect(state.runs).toHaveLength(1);
    expect(state.runs[0].checkpoint.trigger).toBe("mail.received");
    expect(manualStarts).toHaveLength(0);
    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: "Case dashboard", exact: true }),
    ).toBeVisible();
    await expect(page.getByRole("table").locator("tbody tr")).toHaveCount(1);
    await expect(
      page.getByRole("button", { name: "New mail", exact: true }),
    ).toHaveCount(0);
    await page
      .getByLabel("Search cases, loans or borrowers")
      .fill("0099000002");
    await page.getByLabel("Search cases, loans or borrowers").press("Enter");
    await page.getByRole("table").getByRole("link").click();
    await expect(page).toHaveURL(new RegExp(`/cases/${state.cases[0].id}$`));
    await expect(page.locator(".desk-case-header")).toContainText("Closed");
    await page.reload();
    await expect(
      page.getByRole("region", { name: "Response draft and review" }),
    ).toContainText("Delivered");
    await expect(
      page.locator('a[href*="sender"], a[href*="mailbox"], a[href*="5176"]'),
    ).toHaveCount(0);
    await page
      .getByRole("button", { name: "Case dashboard", exact: true })
      .click();
    await expect(page).toHaveURL("http://127.0.0.1:5174/");
    await expect(
      page.getByLabel("Search cases, loans or borrowers"),
    ).toHaveValue("");
    await page
      .getByRole("group", { name: "Filter cases" })
      .getByRole("button", { name: "Open cases" })
      .click();
    await expect(page.getByRole("table").locator("tbody tr")).toHaveCount(0);
    await page
      .getByRole("group", { name: "Filter cases" })
      .getByRole("button", { name: "Completed" })
      .click();
    await expect(page.getByRole("table").locator("tbody tr")).toHaveCount(1);
    await page.getByRole("table").getByRole("link").focus();
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(new RegExp(`/cases/${state.cases[0].id}$`));
    await page.goBack();
    await expect(
      page.getByRole("heading", { name: "Case dashboard", exact: true }),
    ).toBeVisible();
    await page.goto("/sender");
    await expect(
      page.getByRole("heading", { name: "Page not found" }),
    ).toBeVisible();
    await expect(page.getByRole("button", { name: "New mail" })).toHaveCount(0);
    await expect(
      sender.locator(".mail-letter[data-direction='incoming']"),
    ).toBeVisible();
    expect(
      await sender.evaluate(() => document.documentElement.scrollWidth),
    ).toBeLessThanOrEqual(sender.viewportSize()!.width);
    await sender.evaluate(() => window.scrollTo(0, 0));
    await sender.screenshot({
      path: testInfo.outputPath("mailbox.png"),
      fullPage: true,
    });
  } finally {
    for (const tab of page.context().pages()) await tab.close();
    await stop(child);
  }
});

test("human approval automatically continues processing without a Resume action", async ({
  page,
  request,
}, testInfo) => {
  let child: ChildProcess | undefined;
  try {
    child = await server(request, page);
    await request.post(origin + "/test-only/require-review");
    await compose(page);
    const review = page.getByRole("region", {
      name: "Response draft and review",
    });
    await expect(
      review.getByRole("button", { name: "Approve and send" }),
    ).toBeEnabled({ timeout: 30000 });
    const before = await (await request.get(origin + "/api/operations")).json();
    const records = await (
      await request.get(origin + `/api/cases/${before.cases[0].id}/artifacts`)
    ).json();
    expect(records.outbox).toHaveLength(0);
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({
      path: testInfo.outputPath("review-queue.png"),
      fullPage: true,
    });
    await review.getByRole("button", { name: "Return", exact: true }).click();
    const returnDialog = page.getByRole("dialog").filter({
      has: page.getByRole("heading", {
        name: "Return response for changes",
        exact: true,
      }),
    });
    await expect(
      returnDialog.getByRole("button", { name: "Return for changes" }),
    ).toBeDisabled();
    await returnDialog
      .getByLabel("Return feedback")
      .fill(
        "Recheck the schedule attachment and prepare a current version for review.",
      );
    await returnDialog
      .getByRole("button", { name: "Return for changes" })
      .click();
    await expect(returnDialog).not.toBeVisible();
    await expect(
      page.getByLabel("Response version").locator("option"),
    ).toHaveCount(2, { timeout: 30000 });
    await expect(
      review.getByRole("button", { name: "Edit draft", exact: true }),
    ).toBeEnabled({ timeout: 30000 });
    await review
      .getByRole("button", { name: "Edit draft", exact: true })
      .click();
    const editor = page.getByRole("dialog").filter({
      has: page.getByRole("heading", {
        name: "Edit supported response",
        exact: true,
      }),
    });
    await expect(editor.getByLabel("Response purpose")).toBeVisible();
    await editor
      .getByRole("button", { name: "Save validated revision" })
      .click();
    await expect(editor).not.toBeVisible();
    await expect(
      page.getByLabel("Response version").locator("option"),
    ).toHaveCount(3);
    const revised = await (
      await request.get(origin + `/api/cases/${before.cases[0].id}/workflow`)
    ).json();
    await review.getByText("Reviewer & notes", { exact: true }).click();
    await review
      .getByLabel("Review note", { exact: true })
      .fill("Verified the loan, recipient and attached schedule.");
    await review.getByRole("button", { name: "Approve and send" }).click();
    await expect(
      page
        .getByRole("region", { name: "Detailed case workspace" })
        .locator(".desk-case-header"),
    ).toContainText("Closed", { timeout: 30000 });
    const after = await (await request.get(origin + "/api/operations")).json();
    expect(after.runs).toHaveLength(3);
    expect(after.runs[2].checkpoint.trigger).toBe("response.reviewed");
    expect(after.review_case_ids).toHaveLength(0);
    const saved = await (
      await request.get(origin + `/api/cases/${before.cases[0].id}/artifacts`)
    ).json();
    expect(saved.outbox).toHaveLength(1);
    expect(saved.outbox[0].draft_id).toBe(revised.drafts[2].id);
    expect(saved.outbox[0].draft_id).not.toBe(records.drafts[0].id);
  } finally {
    for (const tab of page.context().pages()) await tab.close();
    await stop(child);
  }
});

test("a mailbox reply keeps the selected case and automatically replaces an outdated review draft", async ({
  page,
  request,
}) => {
  let child: ChildProcess | undefined;
  try {
    child = await server(request, page);
    await request.post(origin + "/test-only/require-review");
    const sender = await compose(page);
    await expect(
      page.getByRole("button", { name: "Approve and send" }),
    ).toBeEnabled({ timeout: 30000 });
    const before = await (await request.get(origin + "/api/operations")).json();
    const identity = before.cases[0].id;
    const receipt = before.cases[0].original_received_at;
    await sender.getByRole("button", { name: "Reply", exact: true }).click();
    await expect(sender.getByRole("combobox")).toHaveCount(0);
    await expect(
      sender.getByLabel("Message body", { exact: true }),
    ).toHaveValue(
      "I have attached the requested amortization schedule for this loan.",
    );
    await sender
      .getByLabel("Add attachments")
      .setInputFiles(
        path.join(workspace, "data/documents/v1/DEMO-02/base/amortization.pdf"),
      );
    await expect(sender.locator(".mail-upload-chip")).toHaveCount(1);
    await sender
      .getByRole("button", { name: "Send message", exact: true })
      .click();
    await expect
      .poll(
        async () => {
          const state = await (
            await request.get(origin + "/api/operations")
          ).json();
          return (
            state.runs.length === 2 &&
            state.runs[1].status === "waiting_for_review"
          );
        },
        { timeout: 30000 },
      )
      .toBe(true);
    await page.goto("/");
    await page.getByRole("table").getByRole("link").click();
    await expect(page).toHaveURL(new RegExp(`/cases/${identity}$`));
    await expect(
      page.getByRole("button", { name: "Approve and send" }),
    ).toBeEnabled();
    const workflow = await (
      await request.get(origin + `/api/cases/${identity}/workflow`)
    ).json();
    expect(workflow.drafts).toHaveLength(2);
    expect(workflow.drafts[0].current).toBe(false);
    expect(workflow.drafts[1].current).toBe(true);
    await page
      .getByLabel("Response version")
      .selectOption(workflow.drafts[0].id);
    await expect(
      page.getByRole("button", { name: "Approve and send" }),
    ).toHaveCount(0);
    await page
      .getByLabel("Response version")
      .selectOption(workflow.drafts[1].id);
    await page.getByRole("button", { name: "Approve and send" }).click();
    await expect(
      page
        .getByRole("region", { name: "Detailed case workspace" })
        .locator(".desk-case-header"),
    ).toContainText("Closed", { timeout: 30000 });
    const after = await (await request.get(origin + "/api/operations")).json();
    expect(after.cases).toHaveLength(1);
    expect(after.cases[0].original_received_at).toBe(receipt);
    expect(after.runs).toHaveLength(3);
    expect(
      after.runs.every(
        (run: { checkpoint: { trigger_ids?: string[] } }) =>
          run.checkpoint.trigger_ids?.length,
      ),
    ).toBe(true);
    const records = await (
      await request.get(origin + `/api/cases/${identity}/artifacts`)
    ).json();
    expect(records.outbox).toHaveLength(1);
    expect(records.outbox[0].draft_id).toBe(workflow.drafts[1].id);
    await expect(
      sender.locator(".mail-letter[data-direction='outgoing']"),
    ).toHaveCount(2);
    await expect(sender.locator(".mail-letter").first()).toHaveAttribute(
      "data-direction",
      "incoming",
    );
    const dates = await sender
      .locator(".mail-letter time")
      .evaluateAll((nodes) =>
        nodes.map((node) => Date.parse(node.getAttribute("datetime")!)),
      );
    expect(dates).toEqual([...dates].sort((a, b) => b - a));
    await expect(
      sender
        .locator(".mail-letter")
        .nth(1)
        .getByRole("button", { name: "Preview amortization.pdf", exact: true }),
    ).toBeVisible();
    await expect(
      sender.locator(".mail-letter[data-direction='incoming']"),
    ).toHaveCount(1);
    await expect(
      sender.getByRole("button", { name: "Reply", exact: true }),
    ).toHaveCount(0);
  } finally {
    for (const tab of page.context().pages()) await tab.close();
    await stop(child);
  }
});
