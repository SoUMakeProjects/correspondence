import { lazy, Suspense, useEffect, useState } from "react";
import DeskApp from "../desk/DeskApp";
import DeskIcon from "../desk/DeskIcon";
import { REVIEWER, REVIEWER_SESSION_KEY } from "./reviewer";
import "./login.css";

// The Classic diagnostics workspace (/?workspace=classic) is for testing only.
// It is off unless the frontend is started with VITE_ENABLE_DIAGNOSTICS=true
// (the browser tests do this). Otherwise it is left out of the bundle entirely.
const ClassicApp =
  import.meta.env.VITE_ENABLE_DIAGNOSTICS === "true"
    ? lazy(() => import("../App"))
    : null;

function hasSession() {
  try {
    return sessionStorage.getItem(REVIEWER_SESSION_KEY) === REVIEWER.username;
  } catch {
    return false;
  }
}

export default function CorrespondenceApp() {
  const [signedIn, setSignedIn] = useState(hasSession);

  function signIn() {
    try {
      sessionStorage.setItem(REVIEWER_SESSION_KEY, REVIEWER.username);
    } catch {
      // The current page can still be used when browser storage is unavailable.
    }
    history.replaceState(null, "", "/");
    setSignedIn(true);
  }

  function signOut() {
    try {
      sessionStorage.removeItem(REVIEWER_SESSION_KEY);
    } catch {
      // Always return to the login screen, including when storage is blocked.
    }
    history.replaceState(null, "", "/");
    setSignedIn(false);
  }

  if (!signedIn) return <Login onSignIn={signIn} />;
  return ClassicApp &&
    new URLSearchParams(location.search).get("workspace") === "classic" ? (
    <Suspense fallback={null}>
      <ClassicApp onSignOut={signOut} />
    </Suspense>
  ) : (
    <DeskApp onSignOut={signOut} />
  );
}

function Login({ onSignIn }: { onSignIn: () => void }) {
  const [username, setUsername] = useState("");
  const [error, setLoginError] = useState("");
  const [shake, setShake] = useState(false);
  useEffect(() => {
    document.title = "Sign in · Correspondence Desk";
  }, []);

  return (
    <main className="correspondence-login" aria-label="Correspondence sign in">
      <div className="login-shell">
        <div className="login-brand">
          <span className="login-brand-mark">
            <DeskIcon name="cases" size={25} />
          </span>
          Correspondence Desk
        </div>
        <div className="login-card">
          <section className="login-form-panel" aria-labelledby="login-title">
            <h1 id="login-title">Sign in</h1>
            <p>Enter your username to open case dashboard.</p>
            <form
              onSubmit={(event) => {
                event.preventDefault();
                if (username.trim() === REVIEWER.username) onSignIn();
                else {
                  setLoginError(
                    "This username is not authorised to access the dashboard.",
                  );
                  setUsername("");
                  setShake(true);
                }
              }}
            >
              <input
                id="reviewer-username"
                className={shake ? "shake" : undefined}
                onAnimationEnd={() => setShake(false)}
                aria-label="Username"
                name="username"
                type="password"
                autoComplete="off"
                autoCapitalize="none"
                spellCheck={false}
                autoFocus
                required
                maxLength={80}
                placeholder="Enter your username"
                value={username}
                aria-invalid={!!error}
                aria-describedby={error ? "login-error" : undefined}
                onChange={(event) => {
                  const value = event.target.value;
                  setUsername(value);
                  setLoginError("");
                  if (value.trim() === REVIEWER.username) onSignIn();
                }}
              />
              {error && (
                <p id="login-error" className="login-error" role="alert">
                  {error}
                </p>
              )}
              <button className="login-submit" type="submit">
                SSO login
              </button>
            </form>
          </section>
        </div>
      </div>
    </main>
  );
}
