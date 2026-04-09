import { useEffect, useState } from "react";

import { useAuthSession } from "./auth";
import { HistoryPage } from "../pages/HistoryPage";
import { HomePage } from "../pages/HomePage";
import { LoginPage } from "../pages/LoginPage";
import { MigrationPage } from "../pages/MigrationPage";
import { NewMigrationPage } from "../pages/NewMigrationPage";
import { RecommendationPage } from "../pages/RecommendationPage";
import { ReportsPage } from "../pages/ReportsPage";
import { TransferJobsPage } from "../pages/TransferJobsPage";

export type AppRoute =
  | { name: "login" }
  | { name: "register" }
  | { name: "home" }
  | { name: "history" }
  | { name: "reports" }
  | { name: "transfers" }
  | { name: "migration-new" }
  | { name: "migration"; requestId: string }
  | { name: "recommendation"; requestId: string };

function parseRoute(pathname: string): AppRoute {
  if (pathname === "/login") {
    return { name: "login" };
  }

  if (pathname === "/register") {
    return { name: "register" };
  }

  if (pathname === "/" || pathname === "") {
    return { name: "home" };
  }

  if (pathname === "/migration/new") {
    return { name: "migration-new" };
  }

  if (pathname === "/history") {
    return { name: "history" };
  }

  if (pathname === "/reports") {
    return { name: "reports" };
  }

  if (pathname === "/transfers") {
    return { name: "transfers" };
  }

  const migrationMatch = pathname.match(/^\/migration\/([^/]+)$/);
  if (migrationMatch) {
    return { name: "migration", requestId: decodeURIComponent(migrationMatch[1]) };
  }

  const recommendationMatch = pathname.match(/^\/recommendation\/([^/]+)$/);
  if (recommendationMatch) {
    return { name: "recommendation", requestId: decodeURIComponent(recommendationMatch[1]) };
  }

  return { name: "home" };
}

export function navigate(path: string): void {
  window.history.pushState({}, "", path);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

export function AppRouter() {
  const [route, setRoute] = useState<AppRoute>(() => parseRoute(window.location.pathname));
  const authSession = useAuthSession();

  useEffect(() => {
    const handleRouteChange = () => {
      setRoute(parseRoute(window.location.pathname));
    };

    window.addEventListener("popstate", handleRouteChange);
    return () => {
      window.removeEventListener("popstate", handleRouteChange);
    };
  }, []);

  if (!authSession && route.name !== "login" && route.name !== "register") {
    return <LoginPage redirectPath={window.location.pathname} />;
  }

  if (authSession && (route.name === "login" || route.name === "register")) {
    return <HomePage />;
  }

  switch (route.name) {
    case "login":
      return <LoginPage />;
    case "register":
      return <LoginPage initialMode="register" />;
    case "history":
      return <HistoryPage />;
    case "reports":
      return <ReportsPage />;
    case "transfers":
      return <TransferJobsPage />;
    case "migration-new":
      return <NewMigrationPage />;
    case "migration":
      return <MigrationPage requestId={route.requestId} />;
    case "recommendation":
      return <RecommendationPage requestId={route.requestId} />;
    case "home":
    default:
      return <HomePage />;
  }
}
