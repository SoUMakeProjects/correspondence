import { test as base, expect } from "@playwright/test";
import { REVIEWER, REVIEWER_SESSION_KEY } from "../../src/auth/reviewer";

// Workflow tests begin with the fixed reviewer's existing browser session.
// Login tests use Playwright directly and exercise the complete sign-in flow.
export const test = base.extend({
  context: async ({ context }, use) => {
    await context.addInitScript(
      ({ key, username }) => {
        if (location.port === "5174") sessionStorage.setItem(key, username);
      },
      { key: REVIEWER_SESSION_KEY, username: REVIEWER.username },
    );
    await use(context);
  },
});
export { expect };
