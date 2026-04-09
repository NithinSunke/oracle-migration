import type { ReactNode } from "react";

import { getAuthSession, signOut } from "../app/auth";
import { navigate } from "../app/router";

interface AppFrameProps {
  children: ReactNode;
  eyebrow: string;
  title: string;
  summary: string;
  actions?: ReactNode;
  pageClassName?: string;
}

export function AppFrame({
  children,
  eyebrow,
  title,
  summary,
  actions,
  pageClassName,
}: AppFrameProps) {
  const authSession = getAuthSession();

  return (
    <div className="shell">
      <header className="topbar">
        <button
          className="brand"
          type="button"
          onClick={() => navigate("/")}
        >
          Oracle Migration App
        </button>
        <nav className="topbar-links" aria-label="Primary">
          <button type="button" className="nav-link" onClick={() => navigate("/migration/new")}>
            New Assessment
          </button>
          <button type="button" className="nav-link" onClick={() => navigate("/history")}>
            History
          </button>
          <button type="button" className="nav-link" onClick={() => navigate("/reports")}>
            Reports
          </button>
          <button type="button" className="nav-link" onClick={() => navigate("/transfers")}>
            Export-Import
          </button>
          {authSession ? (
            <>
              <span className="user-pill">{authSession.username}</span>
              <button
                type="button"
                className="nav-link"
                onClick={() => {
                  signOut();
                  navigate("/login");
                }}
              >
                Sign Out
              </button>
            </>
          ) : null}
        </nav>
      </header>

      <main className={pageClassName ? `page ${pageClassName}` : "page"}>
        <section className="page-hero">
          <div>
            <p className="eyebrow">{eyebrow}</p>
            <h1>{title}</h1>
            <p className="summary">{summary}</p>
          </div>
          {actions ? <div className="page-actions">{actions}</div> : null}
        </section>
        {children}
      </main>
    </div>
  );
}
