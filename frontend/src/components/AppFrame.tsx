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
  const pathname = window.location.pathname;
  const navigationItems = [
    { label: "Dashboard", path: "/" },
    { label: "New Assessment", path: "/migration/new" },
    { label: "History", path: "/history" },
    { label: "Reports", path: "/reports" },
    { label: "Export-Import", path: "/transfers" },
  ];

  function isActive(path: string): boolean {
    if (path === "/") {
      return pathname === "/";
    }

    return pathname === path || pathname.startsWith(`${path}/`);
  }

  return (
    <div className="shell">
      <div className="app-shell">
        <aside className="sidebar">
          <button
            className="brand"
            type="button"
            onClick={() => navigate("/")}
          >
            <span className="brand-mark" aria-hidden="true">
              OM
            </span>
            <span className="brand-copy">
              <strong>Oracle Migration App</strong>
              <small>Assessment and execution workspace</small>
            </span>
          </button>

          {authSession ? (
            <section className="sidebar-profile">
              <div className="sidebar-profile__avatar" aria-hidden="true">
                {authSession.username.slice(0, 1).toUpperCase()}
              </div>
              <div>
                <strong>{authSession.username}</strong>
                <p>Migration operator</p>
              </div>
            </section>
          ) : null}

          <nav className="sidebar-nav" aria-label="Primary">
            {navigationItems.map((item) => (
              <button
                key={item.path}
                type="button"
                className={isActive(item.path) ? "nav-link nav-link--active" : "nav-link"}
                onClick={() => navigate(item.path)}
              >
                <span className="nav-link__icon" aria-hidden="true" />
                <span>{item.label}</span>
              </button>
            ))}
          </nav>

          <section className="sidebar-theme-card">
            <p className="sidebar-theme-card__label">Workspace Theme</p>
            <strong>Operations dashboard</strong>
            <span>Dark rail, bright canvas, cleaner analytics cards, and blue-orange accents.</span>
          </section>
        </aside>

        <div className="workspace">
          <header className="topbar">
            <div className="topbar-search" aria-hidden="true">
              <span className="topbar-search__icon" />
              <span>Search assessments, reports, or request IDs</span>
            </div>
            <div className="topbar-links">
              <span className="user-pill">Oracle to Oracle</span>
              {authSession ? (
                <span className="user-pill user-pill--user">{authSession.username}</span>
              ) : null}
              {authSession ? (
                <button
                  type="button"
                  className="nav-link nav-link--ghost"
                  onClick={() => {
                    signOut();
                    navigate("/login");
                  }}
                >
                  Sign Out
                </button>
              ) : null}
            </div>
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
      </div>
    </div>
  );
}
