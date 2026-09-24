import { expect, test } from "./fixtures";
import type { APIRequestContext, Page } from "@playwright/test";
import { spawn, execFileSync } from "node:child_process";
import type { ChildProcess } from "node:child_process";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const workspace = fileURLToPath(new URL("../../..", import.meta.url));
const python = path.join(
  workspace,
  ".venv",
  process.platform === "win32" ? "Scripts/python.exe" : "bin/python",
);
const origin = "http://127.0.0.1:8022";
test.setTimeout(90000);

function server(data: string, crash = false) {
  return spawn(
    python,
    [
      "-m",
      "uvicorn",
      "backend.tests.recovery_server:app",
      "--host",
      "127.0.0.1",
      "--port",
      "8022",
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
        TEST_CRASH_MARKER: crash ? path.join(data, "committed-send.txt") : "",
      },
    },
  );
}
// Waits for exit so the next test's server can bind the same port and its
// health check cannot reach a server that is still shutting down.
async function stop(child: ChildProcess) {
  if (child.exitCode !== null || child.signalCode !== null || !child.pid)
    return;
  const exited = new Promise<void>((resolve) => child.once("exit", () => resolve()));
  if (process.platform === "win32") {
    try {
      execFileSync("taskkill", ["/PID", String(child.pid), "/T", "/F"], {
        windowsHide: true,
        stdio: "ignore",
      });
    } catch {
      /* Process already exited. */
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
async function ready(request: APIRequestContext) {
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
}
async function proxy(page: Page) {
  await page.route(
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
        await route.abort();
      }
    },
  );
}

test("desktop restores status access, verifies a lost result, resumes and downloads evidence", async ({
  page,
  request,
}, testInfo) => {
  const data = path.join(
    workspace,
    ".local",
    "recovery-browser",
    crypto.randomUUID(),
  );
  await fs.mkdir(data, { recursive: true });
  const child = server(data);
  try {
    await ready(request);
    await proxy(page);
    await page.goto("/?workspace=classic");
    await page.getByRole("button", { name: "New case", exact: true }).click();
    await page
      .getByRole("button", { name: "Create case", exact: true })
      .click();
    await page.getByText("Advanced controls", { exact: true }).click();
    await page.getByLabel("Recovery test").selectOption("unknown_send_status");
    await page
      .getByRole("button", { name: "Start agent", exact: true })
      .click();
    const summary = page.getByRole("region", {
      name: "Run summary and recovery",
      exact: true,
    });
    await expect(
      summary.getByRole("button", { name: "Restore status access" }),
    ).toBeEnabled({ timeout: 20000 });
    await summary
      .getByRole("button", { name: "Check persisted results" })
      .click();
    await expect(summary.getByRole("status")).toContainText("still unknown");
    await summary
      .getByRole("button", { name: "Restore status access" })
      .click();
    await expect(
      summary.getByRole("button", { name: "Restore status access" }),
    ).toHaveCount(0);
    await summary
      .getByRole("button", { name: "Check persisted results" })
      .click();
    await expect(summary.getByRole("status")).toContainText(
      "Persisted results verified",
    );
    await page
      .getByRole("button", { name: "Resume agent", exact: true })
      .click();
    await expect(page.getByText("Case closed", { exact: true })).toBeVisible({
      timeout: 20000,
    });
    const link = summary.getByRole("link", {
      name: "Download evidence",
    });
    const exportPath = (await link.getAttribute("href"))!;
    const exported = await request.get(origin + exportPath);
    const payload = await exported.json();
    expect(payload.synthetic).toBe(true);
    expect(payload.outbox).toHaveLength(1);
    expect(payload.packages).toHaveLength(1);
    expect(payload.notes).toHaveLength(1);
    expect(
      payload.actions.filter((a: any) => a.operation === "csp.send"),
    ).toHaveLength(1);
    const runId = payload.run.run_id;
    await page.reload();
    await expect(
      summary.getByRole("link", { name: "Download evidence" }),
    ).toHaveAttribute("href", exportPath);
    const fresh = await request.post(
      origin + "/api/scenarios/DEMO-02/instances",
      { data: { request_id: crypto.randomUUID(), variant: "base" } },
    );
    expect((await fresh.json()).id).not.toBe(payload.run.case_id);
    expect(
      (await (await request.get(origin + `/api/runs/${runId}`)).json()).status,
    ).toBe("completed");
    await expect(
      summary.getByText("Completed actions", { exact: true }),
    ).toBeVisible();
    await summary.screenshot({
      path: testInfo.outputPath("phase8-recovery.png"),
    });
  } finally {
    await stop(child);
  }
});

test("server process exits after committed send and restart recovers the same run across browser reload", async ({
  page,
  request,
}, testInfo) => {
  const data = path.join(
    workspace,
    ".local",
    "recovery-browser",
    crypto.randomUUID(),
  );
  await fs.mkdir(data, { recursive: true });
  let child = server(data, true);
  try {
    await ready(request);
    await proxy(page);
    await page.goto("/?workspace=classic");
    await page.getByRole("button", { name: "New case", exact: true }).click();
    await page
      .getByRole("button", { name: "Create case", exact: true })
      .click();
    const exited = new Promise((resolve) => child.once("exit", resolve));
    const started = page.waitForResponse(
      (r) =>
        /\/api\/cases\/[^/]+\/runs$/.test(r.url()) &&
        r.request().method() === "POST",
    );
    await page
      .getByRole("button", { name: "Start agent", exact: true })
      .click();
    const initial = await (await started).json();
    expect(await exited).toBe(86);
    expect(
      await fs.readFile(path.join(data, "committed-send.txt"), "utf8"),
    ).toContain("Committed send");
    child = server(data);
    await ready(request);
    await page.reload();
    await expect(page.getByText("Case closed", { exact: true })).toBeVisible({
      timeout: 25000,
    });
    const runs = await (
      await request.get(origin + `/api/cases/${initial.case_id}/runs`)
    ).json();
    expect(runs).toHaveLength(1);
    expect(runs[0].id).toBe(initial.id);
    expect(runs[0].status).toBe("completed");
    expect(runs[0].checkpoint.recovery_count).toBe(1);
    expect(
      runs[0].checkpoint.history.some(
        (h: any) => h.tool === "send_response" && h.recovered,
      ),
    ).toBe(true);
    const records = await (
      await request.get(origin + `/api/cases/${initial.case_id}/artifacts`)
    ).json();
    expect(records.outbox).toHaveLength(1);
    expect(records.packages).toHaveLength(1);
    expect(records.notes).toHaveLength(1);
    const summary = page.getByRole("region", {
      name: "Run summary and recovery",
      exact: true,
    });
    await expect(
      summary.getByText("Completed actions", { exact: true }),
    ).toBeVisible();
    await summary.screenshot({
      path: testInfo.outputPath("phase8-restart.png"),
    });
    await fs.writeFile(
      path.join(workspace, ".local", "phase8-process-browser.json"),
      JSON.stringify(
        {
          source: "test_double",
          run_id: initial.id,
          case_id: initial.case_id,
          data_directory: data,
          hard_exit_code: 86,
          same_run_recovered: true,
          delivery_count: records.outbox.length,
          package_count: records.packages.length,
          note_count: records.notes.length,
        },
        null,
        2,
      ),
    );
  } finally {
    await stop(child);
  }
});
