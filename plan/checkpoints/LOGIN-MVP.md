# Correspondence reviewer login

- The correspondence app starts with a light login screen containing Username and an **SSO login** button.
- Typing **admin** opens the case dashboard immediately as **Admin — Reviewer**. Other usernames cannot enter the workspace.
- There is one fixed reviewer profile. There are no password, registration, account-creation or role-creation controls.
- A tab session survives refresh. Sign out clears that session and returns to a blank login screen. Case and diagnostics URLs also show login when signed out.
- The dashboard displays the reviewer's name, initials and role. Intake decisions, response reviews, edits and handoff acknowledgments use his fixed name.
- Mailbox remains a separate page without a login requirement. Signing out does not reset mail or stop server-side case processing.
- This is a frontend MVP entry flow, not production authentication or an external SSO integration. Backend authorization is outside this change.

Five browser tests and the production build passed. Coverage includes login and rejection, desktop layouts, session refresh/sign-out, direct URLs, Mailbox independence, intake review, response approval and handoff acknowledgment. A check against the running app at port 5173 also passed with no browser errors or horizontal overflow at 1280 px and 1100 px. Screenshots and results are saved under `.local/reviewer-login/`. No Azure calls are needed for this UI change.
