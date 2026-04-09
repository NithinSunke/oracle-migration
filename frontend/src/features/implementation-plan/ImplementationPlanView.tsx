import { useState } from "react";

import type {
  MigrationRecord,
  RecommendationResponse,
  RecommendationReport,
} from "../../types";
import {
  buildImplementationPlan,
  buildImplementationPlanFromReport,
} from "./implementationPlan";

interface ImplementationPlanFromRecommendationProps {
  migration: MigrationRecord;
  recommendation: RecommendationResponse;
}

interface ImplementationPlanFromReportProps {
  report: RecommendationReport;
}

function downloadTextFile(filename: string, content: string): void {
  const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}

function fallbackCopyText(content: string): void {
  const textArea = document.createElement("textarea");
  textArea.value = content;
  textArea.setAttribute("readonly", "true");
  textArea.style.position = "fixed";
  textArea.style.top = "-1000px";
  textArea.style.left = "-1000px";
  document.body.appendChild(textArea);
  textArea.focus();
  textArea.select();

  const copied = document.execCommand("copy");
  textArea.remove();

  if (!copied) {
    throw new Error("Clipboard copy failed");
  }
}

async function copyText(content: string): Promise<void> {
  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(content);
    return;
  }

  fallbackCopyText(content);
}

function toMarkdown(source: ReturnType<typeof buildImplementationPlan>): string {
  const lines: string[] = [];
  lines.push(`# Implementation Runbook`);
  lines.push("");
  lines.push(source.overview);
  lines.push("");
  lines.push("## Assumptions");
  lines.push("");
  for (const item of source.assumptions) {
    lines.push(`- ${item}`);
  }
  lines.push("");
  lines.push("## Required Documents");
  lines.push("");
  for (const item of source.documents) {
    lines.push(`- ${item.title} \`${item.filename}\``);
    lines.push(`  ${item.description}`);
  }
  lines.push("");
  lines.push("## Prerequisites");
  lines.push("");
  if (source.prerequisites.length > 0) {
    for (const item of source.prerequisites) {
      lines.push(`- ${item}`);
    }
  } else {
    lines.push("- No explicit prerequisites were returned.");
  }
  lines.push("");
  if (source.warnings.length > 0) {
    lines.push("## Warnings");
    lines.push("");
    for (const item of source.warnings) {
      lines.push(`- ${item}`);
    }
    lines.push("");
  }
  for (const section of source.sections) {
    lines.push(`## ${section.title}`);
    lines.push("");
    lines.push(section.description);
    lines.push("");
    for (const command of section.commands) {
      lines.push(`### ${command.title}`);
      lines.push("");
      lines.push(command.description);
      lines.push("");
      if (command.filename) {
        lines.push(`File: \`${command.filename}\``);
        lines.push("");
      }
      lines.push(`\`\`\`${command.language}`);
      lines.push(command.content);
      lines.push("```");
      lines.push("");
    }
  }
  return lines.join("\n");
}

function ImplementationPlanBody({
  source,
}: {
  source: ReturnType<typeof buildImplementationPlan>;
}) {
  const [copiedCommand, setCopiedCommand] = useState<string | null>(null);
  const [copyErrorCommand, setCopyErrorCommand] = useState<string | null>(null);

  async function handleCopy(commandTitle: string, content: string): Promise<void> {
    try {
      await copyText(content);
      setCopiedCommand(commandTitle);
      setCopyErrorCommand(null);
      window.setTimeout(() => {
        setCopiedCommand((current) => (current === commandTitle ? null : current));
      }, 2000);
    } catch (error) {
      console.error("Unable to copy command", error);
      setCopyErrorCommand(commandTitle);
      setCopiedCommand(null);
      window.setTimeout(() => {
        setCopyErrorCommand((current) => (current === commandTitle ? null : current));
      }, 2500);
    }
  }

  return (
    <>
      <section className="panel">
        <div className="section-heading">
          <h2>Implementation Runbook</h2>
          <p>{source.overview}</p>
        </div>
        <div className="summary-actions">
          <button
            className="secondary-button"
            type="button"
            onClick={() => downloadTextFile("implementation_runbook.md", toMarkdown(source))}
          >
            Download Runbook Markdown
          </button>
        </div>
        <dl className="snapshot-grid">
          {source.assumptions.map((item) => {
            const [label, ...rest] = item.split(":");
            return (
              <div key={item}>
                <dt>{label}</dt>
                <dd>{rest.join(":").trim() || "Not provided"}</dd>
              </div>
            );
          })}
        </dl>
      </section>

      <section className="panel panel-grid">
        <div>
          <div className="section-heading">
            <h2>Required Documents</h2>
            <p>Prepare these artifacts alongside the commands below so execution evidence stays aligned with the assessment.</p>
          </div>
          <div className="runbook-document-list">
            {source.documents.map((item) => (
              <article className="runbook-document-card" key={item.filename}>
                <h3>{item.title}</h3>
                <p>{item.description}</p>
                <code>{item.filename}</code>
              </article>
            ))}
          </div>
        </div>
        <div>
          <div className="section-heading">
            <h2>Prerequisites And Warnings</h2>
            <p>Review blockers, caveats, and review flags before reusing the runbook in a rehearsal or production window.</p>
          </div>
          <ul className="bullet-list">
            {source.prerequisites.length > 0 ? (
              source.prerequisites.map((item) => <li key={item}>{item}</li>)
            ) : (
              <li>No explicit prerequisites were returned.</li>
            )}
          </ul>
          {source.warnings.length > 0 ? (
            <ul className="bullet-list bullet-list--danger">
              {source.warnings.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          ) : null}
        </div>
      </section>

      {source.sections.map((section) => (
        <section className="panel" key={section.title}>
          <div className="section-heading">
            <h2>{section.title}</h2>
            <p>{section.description}</p>
          </div>
          <div className="runbook-command-list">
            {section.commands.map((command) => (
              <article className="runbook-command-card" key={`${section.title}-${command.title}`}>
                <div className="section-heading">
                  <h3>{command.title}</h3>
                  <p>{command.description}</p>
                </div>
                <div className="runbook-command-meta">
                  <span className="chip">{command.language}</span>
                  {command.filename ? <code>{command.filename}</code> : null}
                  <button
                    className="secondary-button"
                    type="button"
                    onClick={() => {
                      void handleCopy(command.title, command.content);
                    }}
                  >
                    {copiedCommand === command.title
                      ? "Copied"
                      : copyErrorCommand === command.title
                        ? "Copy Failed"
                        : "Copy Command"}
                  </button>
                  {command.filename ? (
                    <button
                      className="secondary-button"
                      type="button"
                      onClick={() => downloadTextFile(command.filename as string, command.content)}
                    >
                      Download File
                    </button>
                  ) : null}
                </div>
                <pre className="runbook-code-block">
                  <code>{command.content}</code>
                </pre>
              </article>
            ))}
          </div>
        </section>
      ))}
    </>
  );
}

export function ImplementationPlanFromRecommendation({
  migration,
  recommendation,
}: ImplementationPlanFromRecommendationProps) {
  const plan = buildImplementationPlan(migration, recommendation);
  return <ImplementationPlanBody source={plan} />;
}

export function ImplementationPlanFromReport({
  report,
}: ImplementationPlanFromReportProps) {
  const plan = buildImplementationPlanFromReport(report);
  return <ImplementationPlanBody source={plan} />;
}
