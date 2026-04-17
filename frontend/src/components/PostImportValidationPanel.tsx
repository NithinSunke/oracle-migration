import type { MigrationRecord } from "../types";

interface PostImportValidationPanelProps {
  migration: MigrationRecord;
  requestId: string;
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

function getPrimarySchemaHint(migration: MigrationRecord): string {
  if (
    migration.scope.migration_scope === "SCHEMA" &&
    migration.scope.schema_count === 1 &&
    migration.source_metadata?.schema_inventory.length
  ) {
    return migration.source_metadata.schema_inventory[0].owner;
  }
  return "<schema_list>";
}

function buildValidationBundle(migration: MigrationRecord): string {
  const schemaHint = getPrimarySchemaHint(migration);
  const schemaPredicate =
    migration.scope.migration_scope === "FULL_DATABASE"
      ? ""
      : schemaHint === "<schema_list>"
        ? "  and owner in (<schema_list>)"
        : `  and owner in ('${schemaHint}')`;
  const sequencePredicate =
    migration.scope.migration_scope === "FULL_DATABASE"
      ? ""
      : schemaHint === "<schema_list>"
        ? "  and sequence_owner in (<schema_list>)"
        : `  and sequence_owner in ('${schemaHint}')`;

  return [
    "sqlplus -L \"${SRC_CONNECT_STRING}\" <<'SQL' > source_post_import_validation.txt",
    "set pages 300 lines 240 trimspool on",
    "prompt === OBJECT COUNTS ===",
    "select owner, object_type, count(*)",
    "from dba_objects",
    "where owner not in ('SYS','SYSTEM')",
    schemaPredicate,
    "group by owner, object_type",
    "order by owner, object_type;",
    "prompt === INVALID OBJECTS ===",
    "select owner, object_name, object_type, status",
    "from dba_objects",
    "where status <> 'VALID'",
    schemaPredicate,
    "order by owner, object_type, object_name;",
    "prompt === SCHEMA SIZE MB ===",
    "select owner, round(sum(bytes)/1024/1024, 2) size_mb",
    "from dba_segments",
    "where owner not in ('SYS','SYSTEM')",
    schemaPredicate,
    "group by owner",
    "order by owner;",
    "prompt === OBJECT GRANTS ===",
    "select owner, count(*) object_grants",
    "from dba_tab_privs",
    "where owner not in ('SYS','SYSTEM')",
    schemaPredicate,
    "group by owner",
    "order by owner;",
    "prompt === SYNONYMS ===",
    "select owner, count(*) synonym_count",
    "from dba_synonyms",
    "where owner not in ('SYS','SYSTEM')",
    schemaPredicate,
    "group by owner",
    "order by owner;",
    "prompt === SEQUENCES ===",
    "select sequence_owner, count(*) sequence_count",
    "from dba_sequences",
    "where sequence_owner not in ('SYS','SYSTEM')",
    sequencePredicate,
    "group by sequence_owner",
    "order by sequence_owner;",
    "SQL",
    "",
    "sqlplus -L \"${TGT_CONNECT_STRING}\" <<'SQL' > target_post_import_validation.txt",
    "set pages 300 lines 240 trimspool on",
    "prompt === OBJECT COUNTS ===",
    "select owner, object_type, count(*)",
    "from dba_objects",
    "where owner not in ('SYS','SYSTEM')",
    schemaPredicate,
    "group by owner, object_type",
    "order by owner, object_type;",
    "prompt === INVALID OBJECTS ===",
    "select owner, object_name, object_type, status",
    "from dba_objects",
    "where status <> 'VALID'",
    schemaPredicate,
    "order by owner, object_type, object_name;",
    "prompt === SCHEMA SIZE MB ===",
    "select owner, round(sum(bytes)/1024/1024, 2) size_mb",
    "from dba_segments",
    "where owner not in ('SYS','SYSTEM')",
    schemaPredicate,
    "group by owner",
    "order by owner;",
    "prompt === OBJECT GRANTS ===",
    "select owner, count(*) object_grants",
    "from dba_tab_privs",
    "where owner not in ('SYS','SYSTEM')",
    schemaPredicate,
    "group by owner",
    "order by owner;",
    "prompt === SYNONYMS ===",
    "select owner, count(*) synonym_count",
    "from dba_synonyms",
    "where owner not in ('SYS','SYSTEM')",
    schemaPredicate,
    "group by owner",
    "order by owner;",
    "prompt === SEQUENCES ===",
    "select sequence_owner, count(*) sequence_count",
    "from dba_sequences",
    "where sequence_owner not in ('SYS','SYSTEM')",
    sequencePredicate,
    "group by sequence_owner",
    "order by sequence_owner;",
    "SQL",
    "",
    "diff -u source_post_import_validation.txt target_post_import_validation.txt || true",
  ]
    .filter(Boolean)
    .join("\n");
}

export function PostImportValidationPanel({
  migration,
  requestId,
}: PostImportValidationPanelProps) {
  const content = buildValidationBundle(migration);

  return (
    <section className="panel panel--inner">
      <div className="section-heading">
        <h2>Object-Level Post-Import Validation</h2>
        <p>
          Compare source and target object counts, invalid objects, schema sizes, grants,
          synonyms, sequences, and compile status as part of cutover evidence.
        </p>
      </div>

      <div className="summary-actions">
        <button
          className="secondary-button"
          type="button"
          onClick={() =>
            downloadTextFile(
              `${requestId.toLowerCase()}_post_import_object_validation.sh`,
              content,
            )
          }
        >
          Download Validation Bundle
        </button>
      </div>

      <ul className="bullet-list">
        <li>Object counts by owner and object type</li>
        <li>Invalid objects and compile status review</li>
        <li>Schema size comparison in MB</li>
        <li>Object grants, synonyms, and sequences comparison</li>
      </ul>

      <pre className="runbook-code-block">
        <code>{content}</code>
      </pre>
    </section>
  );
}
