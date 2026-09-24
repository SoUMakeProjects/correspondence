import { expect, test } from "./fixtures";

test("desktop start, stop and reconnect show explicitly labeled test runs without repeating mutations", async ({
  page,
}) => {
  // Test-only browser transport stub; no model or Azure calls are made here.
  let run: Record<string, unknown> | null = null;
  let starts = 0;
  let stops = 0;
  await page.route("**/api/config", async (route) => {
    const response = await route.fetch();
    const config = await response.json();
    await route.fulfill({ json: { ...config, agent_available: true } });
  });
  await page.route(/\/api\/cases\/[^/]+\/runs$/, async (route) => {
    if (route.request().method() === "POST") {
      starts++;
      const caseId = route.request().url().split("/").at(-2)!;
      run = {
        id: crypto.randomUUID(),
        case_id: caseId,
        case_revision: 1,
        status: "running",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        model_configuration: {
          source: "test_double",
          configuration_id: "browser-test-only",
          protocol: "test",
          tool_contract: 6,
        },
        checkpoint: {
          phase: "choosing_tool",
          steps: 1,
          model_calls: 1,
          history: [
            {
              step: 1,
              tool: "observe_case",
              status: "ok",
              code: "observed",
              message: "Scoped records inspected.",
            },
          ],
          usage: { total_tokens: 12 },
        },
      };
      await route.fulfill({ status: 202, json: run });
    } else await route.fulfill({ json: run ? [run] : [] });
  });
  await page.route(/\/api\/runs\/[^/]+\/stop$/, async (route) => {
    stops++;
    run = {
      ...run,
      status: "stopped",
      checkpoint: {
        steps: 1,
        model_calls: 1,
        reason: "presenter_stop",
        history: [],
        usage: { total_tokens: 12 },
      },
    };
    await route.fulfill({ json: run });
  });
  await page.goto("/?workspace=classic");
  await page.getByRole("button", { name: "New case", exact: true }).click();
  await page.getByRole("button", { name: "Create case", exact: true }).click();
  const agent = page.getByRole("region", {
    name: "AI agent workspace",
    exact: true,
  });
  await expect(
    agent.getByRole("button", { name: "Start agent" }),
  ).toBeEnabled();
  await agent.getByRole("button", { name: "Start agent" }).click();
  await expect(
    agent.getByText("Agent · running", { exact: true }),
  ).toBeVisible();
  await expect(
    agent.getByRole("button", { name: "Start agent" }),
  ).toBeDisabled();
  await page.reload();
  await expect(
    agent.getByText("Agent · running", { exact: true }),
  ).toBeVisible();
  expect(starts).toBe(1);
  await agent.getByRole("button", { name: "Stop agent" }).click();
  await expect(
    agent.getByText("Agent · stopped", { exact: true }),
  ).toBeVisible();
  await expect(
    agent.getByText(
      "Stopped at a safe boundary. Already completed actions are retained.",
    ),
  ).toBeVisible();
  expect(stops).toBe(1);
  expect(starts).toBe(1);
  await agent.getByText("Run details", { exact: true }).click();
  await expect(agent.getByText("Test provider", { exact: true })).toBeVisible();
});
