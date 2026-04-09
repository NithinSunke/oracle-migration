import { FormEvent, useEffect, useState } from "react";

import { registerAccount, signIn } from "../app/auth";
import { navigate } from "../app/router";

interface LoginPageProps {
  redirectPath?: string;
  initialMode?: "login" | "register";
}

export function LoginPage({ redirectPath, initialMode = "login" }: LoginPageProps) {
  const [mode, setMode] = useState<"login" | "register">(initialMode);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [remember, setRemember] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    setMode(initialMode);
  }, [initialMode]);

  function switchMode(nextMode: "login" | "register") {
    setMode(nextMode);
    setErrorMessage(null);
    setSuccessMessage(null);
    navigate(nextMode === "register" ? "/register" : "/login");
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErrorMessage(null);
    setSuccessMessage(null);

    if (mode === "register" && password !== confirmPassword) {
      setErrorMessage("Password confirmation does not match.");
      return;
    }

    try {
      setIsSubmitting(true);

      if (mode === "register") {
        await registerAccount(username, password, remember);
        setSuccessMessage("Registration completed. You are now signed in.");
      } else {
        await signIn(username, password, remember);
      }

      navigate(redirectPath && redirectPath !== "/login" ? redirectPath : "/");
    } catch (error) {
      if (error instanceof Error) {
        setErrorMessage(error.message);
      } else {
        setErrorMessage("Unable to sign in right now.");
      }
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="login-shell">
      <section className="login-hero">
        <div className="login-copy">
          <p className="eyebrow">Secure Access</p>
          <h1>Sign in to the Oracle Migration App</h1>
          <p className="summary">
            Enter your application credentials to review assessments, recommendations, history,
            and reports from one place.
          </p>
          <div className="login-highlights">
            <article className="panel">
              <p className="chip">Protected Workflow</p>
              <h2>Assessment Data Behind a Login Gate</h2>
              <p>
                Migration requests, explainable recommendations, and report downloads now sit
                behind a dedicated sign-in experience.
              </p>
            </article>
            <article className="panel">
              <p className="chip">Credential Storage</p>
              <h2>Application Login with Database Persistence</h2>
              <p>
                User credentials are registered through the application and saved in the
                platform database as password hashes instead of plaintext values.
              </p>
            </article>
          </div>
        </div>

        <div className="login-card panel">
          <div className="section-heading">
            <h2>{mode === "register" ? "Create Your Account" : "Welcome Back"}</h2>
            <p>
              {mode === "register"
                ? "Register once to create a database-backed application login."
                : "Sign in with a username and password that was already registered."}
            </p>
          </div>

          <div className="auth-switch" role="tablist" aria-label="Authentication options">
            <button
              type="button"
              className={`auth-switch__button ${mode === "login" ? "auth-switch__button--active" : ""}`}
              onClick={() => switchMode("login")}
            >
              Sign In
            </button>
            <button
              type="button"
              className={`auth-switch__button ${mode === "register" ? "auth-switch__button--active" : ""}`}
              onClick={() => switchMode("register")}
            >
              Register
            </button>
          </div>

          {redirectPath && redirectPath !== "/" && mode === "login" ? (
            <div className="form-alert">
              Sign in to continue to <strong>{redirectPath}</strong>.
            </div>
          ) : null}

          {successMessage ? <div className="form-alert form-alert--success">{successMessage}</div> : null}

          {errorMessage ? (
            <div className="form-alert form-alert--error">{errorMessage}</div>
          ) : null}

          <form className="login-form" onSubmit={handleSubmit}>
            <label className="field">
              <span>Username</span>
              <input
                autoComplete="username"
                name="username"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                placeholder="migration.admin"
                disabled={isSubmitting}
              />
            </label>

            <label className="field">
              <span>Password</span>
              <input
                autoComplete={mode === "register" ? "new-password" : "current-password"}
                type="password"
                name="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="Enter password"
                disabled={isSubmitting}
              />
            </label>

            {mode === "register" ? (
              <label className="field">
                <span>Confirm Password</span>
                <input
                  autoComplete="new-password"
                  type="password"
                  name="confirmPassword"
                  value={confirmPassword}
                  onChange={(event) => setConfirmPassword(event.target.value)}
                  placeholder="Re-enter password"
                  disabled={isSubmitting}
                />
              </label>
            ) : null}

            <label className="login-remember">
              <input
                type="checkbox"
                checked={remember}
                onChange={(event) => setRemember(event.target.checked)}
              />
              <span>Keep me signed in on this browser</span>
            </label>

            <button className="primary-button login-submit" type="submit" disabled={isSubmitting}>
              {isSubmitting
                ? mode === "register"
                  ? "Creating Account..."
                  : "Signing In..."
                : mode === "register"
                  ? "Create Account"
                  : "Sign In"}
            </button>
          </form>

          <p className="auth-helper">
            {mode === "register"
              ? "Already have an account?"
              : "Need an account before you can log in?"}{" "}
            <button
              type="button"
              className="auth-helper__link"
              onClick={() => switchMode(mode === "register" ? "login" : "register")}
            >
              {mode === "register" ? "Sign in here" : "Register here"}
            </button>
          </p>
        </div>
      </section>
    </div>
  );
}
