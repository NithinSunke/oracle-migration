import type { ReactNode } from "react";

interface StatusPanelProps {
  title: string;
  description: string;
  tone?: "info" | "error" | "success";
  action?: ReactNode;
}

export function StatusPanel({
  title,
  description,
  tone = "info",
  action,
}: StatusPanelProps) {
  return (
    <section className={`status-panel status-panel--${tone}`}>
      <h2>{title}</h2>
      <p>{description}</p>
      {action ? <div className="status-panel__action">{action}</div> : null}
    </section>
  );
}
