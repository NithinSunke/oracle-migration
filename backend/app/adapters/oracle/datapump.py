from __future__ import annotations

import re
import shutil
import subprocess
from os import X_OK, access
from pathlib import Path
from urllib.parse import quote

from backend.app.adapters.oracle.client import (
    OracleClientError,
    OracleDatabaseClient,
    OracleDriverUnavailableError,
    oracledb,
)
from backend.app.core.config import settings
from backend.app.schemas.migration import OracleConnectionConfig
from backend.app.schemas.transfer import (
    DataPumpCommandPreview,
    DataPumpJobCreate,
    DataPumpJobOptions,
    DataPumpResolvedBackend,
)


class OracleDataPumpError(RuntimeError):
    """Raised when a Data Pump job cannot be planned or executed safely."""


class OracleDataPumpExecutionDisabledError(OracleDataPumpError):
    """Raised when runtime execution is disabled for this environment."""


class OracleDataPumpExecutionFailedError(OracleDataPumpError):
    """Raised when a Data Pump job fails after producing execution artifacts."""

    def __init__(self, message: str, result_payload: dict[str, object]) -> None:
        super().__init__(message)
        self.result_payload = result_payload


class OracleDataPumpAdapter:
    OBJECT_STORAGE_FILESIZE = "10MB"

    def __init__(
        self,
        client_factory: type[OracleDatabaseClient] | None = None,
    ) -> None:
        self._client_factory = client_factory or OracleDatabaseClient

    def get_runtime_capabilities(self) -> dict[str, object]:
        expdp_resolved = self._find_executable(settings.datapump_expdp_path)
        impdp_resolved = self._find_executable(settings.datapump_impdp_path)
        cli_work_dir_ready, cli_work_dir_error = self._ensure_work_dir_ready()
        cli_available = bool(
            expdp_resolved is not None
            and impdp_resolved is not None
            and cli_work_dir_ready
        )
        db_api_available = self._db_api_runtime_available()
        execution_backend = self._normalized_backend_setting()
        blockers: list[str] = []

        if not settings.datapump_enabled:
            blockers.append("DATAPUMP_ENABLED is false.")
        elif execution_backend not in {"auto", "cli", "db_api"}:
            blockers.append(
                "DATAPUMP_EXECUTION_BACKEND must be one of auto, cli, or db_api."
            )
        elif execution_backend == "cli":
            blockers.extend(
                self._cli_runtime_blockers(
                    require_export=True,
                    require_import=True,
                    expdp_resolved=expdp_resolved,
                    impdp_resolved=impdp_resolved,
                    cli_work_dir_error=cli_work_dir_error,
                )
            )
        elif execution_backend == "db_api":
            blockers.extend(self._db_api_runtime_blockers())
        elif not cli_available and not db_api_available:
            blockers.extend(
                self._cli_runtime_blockers(
                    require_export=True,
                    require_import=True,
                    expdp_resolved=expdp_resolved,
                    impdp_resolved=impdp_resolved,
                    cli_work_dir_error=cli_work_dir_error,
                )
            )
            blockers.extend(self._db_api_runtime_blockers())

        resolved_backend = self._resolve_runtime_backend(
            expdp_resolved=expdp_resolved,
            impdp_resolved=impdp_resolved,
            cli_work_dir_ready=cli_work_dir_ready,
            db_api_available=db_api_available,
        )

        return {
            "actual_run_ready": settings.datapump_enabled and resolved_backend is not None,
            "blockers": blockers,
            "execution_backend": execution_backend,
            "resolved_backend": resolved_backend,
            "cli_available": cli_available,
            "db_api_available": db_api_available,
            "resolved_expdp_path": expdp_resolved,
            "resolved_impdp_path": impdp_resolved,
        }

    def ensure_execution_ready(self, request: DataPumpJobCreate) -> DataPumpResolvedBackend:
        return self._resolve_execution_backend(request)

    def plan_job(
        self,
        request: DataPumpJobCreate,
    ) -> tuple[DataPumpCommandPreview, list[str]]:
        backend = self._resolve_preview_backend(request)
        executable = self._resolve_preview_executable(request.operation, backend)
        parameter_lines = self._build_parameter_lines(request, backend)

        if backend == "cli":
            command_line = (
                f"{executable} {self._masked_userid_arg(request)} "
                f"parfile={self._parfile_path(request.job_id)}"
            )
        else:
            command_line = self._db_api_command_preview(request)

        return (
            DataPumpCommandPreview(
                backend=backend,
                executable=executable,
                command_line=command_line,
                parameter_lines=parameter_lines,
            ),
            parameter_lines,
        )

    def execute_job(self, request: DataPumpJobCreate) -> dict[str, object]:
        command_preview, parameter_lines = self.plan_job(request)
        work_dir = Path(settings.datapump_work_dir) / request.job_id
        plan_path = self._write_plan_artifact(
            request=request,
            command_preview=command_preview,
            parameter_lines=parameter_lines,
            work_dir=work_dir,
        )

        if request.dry_run:
            full_log = [
                f"Job ID: {request.job_id}",
                f"Backend: {command_preview.backend}",
                f"Operation: {request.operation}",
                f"Scope: {request.scope}",
                f"Command preview: {command_preview.command_line}",
                "Dry-run only. The app generated the Data Pump job plan but did not execute Oracle Data Pump.",
            ]
            return {
                "command_preview": command_preview.model_dump(mode="json"),
                "output_excerpt": [
                    "Dry-run only. The app generated the Data Pump job plan but did not execute Oracle Data Pump.",
                ],
                "output_log": full_log,
                "oracle_log_lines": [],
                "artifact_paths": [str(plan_path)],
            }

        backend = self._resolve_execution_backend(request)
        if backend == "cli":
            return self._execute_cli_job(
                request=request,
                command_preview=command_preview,
                parameter_lines=parameter_lines,
                work_dir=work_dir,
                artifact_paths=[str(plan_path)],
            )

        return self._execute_db_api_job(
            request=request,
            command_preview=command_preview,
            work_dir=work_dir,
            artifact_paths=[str(plan_path)],
        )

    def _build_parameter_lines(
        self,
        request: DataPumpJobCreate,
        backend: DataPumpResolvedBackend | None = None,
    ) -> list[str]:
        options = request.options
        lines = [
            f"DIRECTORY={options.directory_object}",
            f"LOGFILE={options.log_file or self._default_log_file(request)}",
            f"PARALLEL={options.parallel}",
        ]
        if self._uses_object_storage(request):
            lines.append(
                f"CREDENTIAL={self._object_storage_credential_name(request, backend)}"
            )
            lines.append(f"DUMPFILE={self._object_storage_dump_uri(request)}")
        else:
            lines.append(f"DUMPFILE={options.dump_file}")
        if options.exclude_statistics:
            lines.append("EXCLUDE=STATISTICS")
        if options.compression_enabled and request.operation == "EXPORT":
            lines.append("COMPRESSION=ALL")

        if request.scope == "FULL":
            lines.append("FULL=Y")
        else:
            lines.append(f"SCHEMAS={','.join(options.schemas)}")

        if request.operation == "IMPORT":
            lines.append(f"TABLE_EXISTS_ACTION={options.table_exists_action}")
            for remap in options.remap_schemas:
                lines.append(f"REMAP_SCHEMA={remap.source_schema}:{remap.target_schema}")

        return lines

    def _object_storage_credential_name(
        self,
        request: DataPumpJobCreate,
        backend: DataPumpResolvedBackend | None = None,
    ) -> str:
        credential_name = self._object_storage_config(request).credential_name.strip()
        if backend != "cli" or "." in credential_name:
            return credential_name

        connection = self._connection_for_operation(request)
        owner = connection.username.strip().upper()
        return f"{owner}.{credential_name}"

    def _resolve_executable(self, operation: str) -> str:
        return (
            settings.datapump_expdp_path
            if operation == "EXPORT"
            else settings.datapump_impdp_path
        )

    def _resolve_preview_executable(
        self,
        operation: str,
        backend: DataPumpResolvedBackend,
    ) -> str:
        if backend == "db_api":
            return "DBMS_DATAPUMP"
        return self._resolve_executable(operation)

    def _userid_arg(self, request: DataPumpJobCreate) -> str:
        connection = self._connection_for_operation(request)
        password = (
            connection.password.get_secret_value()
            if connection.password is not None
            else ""
        )
        dsn = f"//{connection.host}:{connection.port}/{connection.service_name}"
        credential = f"{connection.username}/{password}@{dsn}"
        if connection.sysdba:
            return f'userid="{credential} as sysdba"'
        return f"userid={credential}"

    def _masked_userid_arg(self, request: DataPumpJobCreate) -> str:
        connection = self._connection_for_operation(request)
        dsn = f"//{connection.host}:{connection.port}/{connection.service_name}"
        credential = f"{connection.username}/******@{dsn}"
        if connection.sysdba:
            return f'userid="{credential} as sysdba"'
        return f"userid={credential}"

    def _connection_for_operation(self, request: DataPumpJobCreate) -> OracleConnectionConfig:
        if request.operation == "EXPORT":
            if request.source_connection is None:
                raise OracleDataPumpError(
                    "Source Oracle connection is required for Data Pump exports."
                )
            return request.source_connection
        if request.target_connection is None:
            raise OracleDataPumpError(
                "Target Oracle connection is required for Data Pump imports."
            )
        return request.target_connection

    @staticmethod
    def _default_log_file(request: DataPumpJobCreate) -> str:
        return f"{request.job_id.lower()}.log"

    @staticmethod
    def _parfile_path(job_id: str) -> str:
        return f"{Path(settings.datapump_work_dir) / job_id / 'job.par'}"

    @staticmethod
    def _find_executable(value: str) -> str | None:
        candidate = Path(value)
        if candidate.is_file() and access(candidate, X_OK):
            return str(candidate)
        return shutil.which(value)

    @staticmethod
    def _normalized_backend_setting() -> str:
        return settings.datapump_execution_backend.strip().lower()

    def _db_api_runtime_available(self) -> bool:
        try:
            probe = self._client_factory(
                OracleConnectionConfig(
                    host="placeholder",
                    port=1521,
                    service_name="placeholder",
                    username="placeholder",
                    password=None,
                )
            )
            probe._build_connect_kwargs()
        except OracleDriverUnavailableError:
            return False
        except OracleClientError:
            return True
        except Exception:
            return True
        return True

    def _db_api_runtime_blockers(self) -> list[str]:
        if self._db_api_runtime_available():
            return []
        return ["python-oracledb is not available in the worker runtime."]

    def _ensure_work_dir_ready(self) -> tuple[bool, str | None]:
        try:
            Path(settings.datapump_work_dir).mkdir(parents=True, exist_ok=True)
            return True, None
        except Exception as exc:
            return (
                False,
                f"Data Pump work directory '{settings.datapump_work_dir}' is not writable: {exc}",
            )

    def _cli_runtime_blockers(
        self,
        *,
        require_export: bool,
        require_import: bool,
        expdp_resolved: str | None,
        impdp_resolved: str | None,
        cli_work_dir_error: str | None,
    ) -> list[str]:
        blockers: list[str] = []
        if require_export and expdp_resolved is None:
            blockers.append(
                f"Export executable was not found at '{settings.datapump_expdp_path}'."
            )
        if require_import and impdp_resolved is None:
            blockers.append(
                f"Import executable was not found at '{settings.datapump_impdp_path}'."
            )
        if cli_work_dir_error is not None:
            blockers.append(cli_work_dir_error)
        return blockers

    def _resolve_runtime_backend(
        self,
        *,
        expdp_resolved: str | None,
        impdp_resolved: str | None,
        cli_work_dir_ready: bool,
        db_api_available: bool,
    ) -> DataPumpResolvedBackend | None:
        backend = self._normalized_backend_setting()
        if backend not in {"auto", "cli", "db_api"} or not settings.datapump_enabled:
            return None
        if backend == "cli":
            if expdp_resolved and impdp_resolved and cli_work_dir_ready:
                return "cli"
            return None
        if backend == "db_api":
            return "db_api" if db_api_available else None
        if expdp_resolved and impdp_resolved and cli_work_dir_ready:
            return "cli"
        if db_api_available:
            return "db_api"
        return None

    def _resolve_preview_backend(self, request: DataPumpJobCreate) -> DataPumpResolvedBackend:
        operation = request.operation
        backend = self._normalized_backend_setting()
        cli_work_dir_ready, _ = self._ensure_work_dir_ready()
        executable = self._find_executable(self._resolve_executable(operation))

        if self._requires_cli_backend(request):
            return "cli"
        if backend == "cli":
            return "cli"
        if backend == "db_api":
            return "db_api"
        if executable is not None and cli_work_dir_ready:
            return "cli"
        return "db_api"

    def _resolve_execution_backend(self, request: DataPumpJobCreate) -> DataPumpResolvedBackend:
        if not settings.datapump_enabled:
            raise OracleDataPumpExecutionDisabledError(
                "Live Data Pump execution is disabled because DATAPUMP_ENABLED is false."
            )

        operation = request.operation
        backend = self._normalized_backend_setting()
        cli_work_dir_ready, cli_work_dir_error = self._ensure_work_dir_ready()
        expdp_resolved = self._find_executable(settings.datapump_expdp_path)
        impdp_resolved = self._find_executable(settings.datapump_impdp_path)
        requires_cli_backend = self._requires_cli_backend(request)

        if requires_cli_backend:
            blockers = self._cli_runtime_blockers(
                require_export=operation == "EXPORT",
                require_import=operation == "IMPORT",
                expdp_resolved=expdp_resolved,
                impdp_resolved=impdp_resolved,
                cli_work_dir_error=cli_work_dir_error,
            )
            if blockers:
                raise OracleDataPumpExecutionDisabledError(
                    "Direct OCI Object Storage import actual-runs require the CLI impdp "
                    "backend in the worker runtime. "
                    + " ".join(blockers)
                )
            return "cli"

        if backend == "cli":
            blockers = self._cli_runtime_blockers(
                require_export=operation == "EXPORT",
                require_import=operation == "IMPORT",
                expdp_resolved=expdp_resolved,
                impdp_resolved=impdp_resolved,
                cli_work_dir_error=cli_work_dir_error,
            )
            if blockers:
                raise OracleDataPumpExecutionDisabledError(" ".join(blockers))
            return "cli"

        if backend == "db_api":
            blockers = self._db_api_runtime_blockers()
            if blockers:
                raise OracleDataPumpExecutionDisabledError(" ".join(blockers))
            return "db_api"

        if backend != "auto":
            raise OracleDataPumpExecutionDisabledError(
                "DATAPUMP_EXECUTION_BACKEND must be one of auto, cli, or db_api."
            )

        selected_executable = expdp_resolved if operation == "EXPORT" else impdp_resolved
        if selected_executable is not None and cli_work_dir_ready:
            return "cli"
        if self._db_api_runtime_available():
            return "db_api"

        blockers = self._cli_runtime_blockers(
            require_export=operation == "EXPORT",
            require_import=operation == "IMPORT",
            expdp_resolved=expdp_resolved,
            impdp_resolved=impdp_resolved,
            cli_work_dir_error=cli_work_dir_error,
        )
        blockers.extend(self._db_api_runtime_blockers())
        raise OracleDataPumpExecutionDisabledError(" ".join(blockers))

    @staticmethod
    def _requires_cli_backend(request: DataPumpJobCreate) -> bool:
        return (
            request.operation == "IMPORT"
            and request.options.storage_type == "OCI_OBJECT_STORAGE"
        )

    def _execute_cli_job(
        self,
        *,
        request: DataPumpJobCreate,
        command_preview: DataPumpCommandPreview,
        parameter_lines: list[str],
        work_dir: Path,
        artifact_paths: list[str],
    ) -> dict[str, object]:
        executable = self._find_executable(command_preview.executable)
        if executable is None:
            raise OracleDataPumpError(
                f"The Data Pump executable '{command_preview.executable}' is not available in the worker runtime."
            )

        work_dir.mkdir(parents=True, exist_ok=True)
        parfile_path = work_dir / f"{request.operation.lower()}.par"
        parfile_path.write_text("\n".join(parameter_lines) + "\n", encoding="utf-8")

        command = [
            executable,
            self._userid_arg(request),
            f"parfile={parfile_path}",
        ]

        completed = subprocess.run(
            command,
            cwd=work_dir,
            capture_output=True,
            text=True,
            timeout=settings.datapump_call_timeout_seconds,
            check=False,
        )

        stdout_lines = [line for line in completed.stdout.splitlines() if line.strip()]
        stderr_lines = [line for line in completed.stderr.splitlines() if line.strip()]
        output_log = [
            f"Backend: {command_preview.backend}",
            f"Command: {' '.join(command)}",
            f"Return code: {completed.returncode}",
            f"Storage type: {request.options.storage_type}",
            "",
            "[stdout]",
            *(stdout_lines or ["(no stdout output)"]),
            "",
            "[stderr]",
            *(stderr_lines or ["(no stderr output)"]),
        ]
        connected_to_oracle = any(
            "Connected to:" in line for line in [*stdout_lines, *stderr_lines]
        )
        if completed.returncode == 0 or connected_to_oracle:
            oracle_log_lines, oracle_log_note = self._try_read_oracle_datapump_log(
                request=request,
                connection=None,
            )
        else:
            oracle_log_lines = []
            oracle_log_note = (
                "Oracle log fetch was skipped because the Data Pump CLI failed before "
                "it connected to Oracle."
            )
        if oracle_log_note:
            output_log.extend(["", "[oracle-log-fetch]", oracle_log_note])
        if oracle_log_lines:
            output_log.extend(["", "[oracle-datapump-log]", *oracle_log_lines])
        output_excerpt = (oracle_log_lines[-20:] if oracle_log_lines else output_log[-20:])
        worker_log_path = work_dir / "worker_output.log"
        worker_log_path.write_text("\n".join(output_log) + "\n", encoding="utf-8")
        artifact_paths = [*artifact_paths, str(parfile_path), str(worker_log_path)]
        if oracle_log_lines:
            oracle_log_path = work_dir / "oracle_datapump.log"
            oracle_log_path.write_text("\n".join(oracle_log_lines) + "\n", encoding="utf-8")
            artifact_paths.append(str(oracle_log_path))

        if completed.returncode != 0:
            message = "Data Pump execution failed."
            failure_candidates = [
                *reversed(stderr_lines),
                *reversed(stdout_lines),
                *reversed(oracle_log_lines),
            ]
            terminal_line = next(
                (
                    line
                    for line in failure_candidates
                    if line
                    and (
                        line.startswith("ORA-")
                        or line.startswith("UDI-")
                        or line.startswith("LRM-")
                        or line.startswith("EXP-")
                        or line.startswith("IMP-")
                    )
                ),
                "",
            )
            if not terminal_line:
                terminal_line = next(
                    (line for line in reversed(output_log) if line and not line.startswith("[")),
                    "",
                )
            if terminal_line:
                message = f"{message} {terminal_line}"
            raise OracleDataPumpExecutionFailedError(
                message,
                {
                    "command_preview": command_preview.model_dump(mode="json"),
                    "output_excerpt": output_excerpt
                    or ["Data Pump failed before producing any worker output."],
                    "output_log": output_log,
                    "oracle_log_lines": oracle_log_lines,
                    "artifact_paths": artifact_paths,
                },
            )

        return {
            "command_preview": command_preview.model_dump(mode="json"),
            "output_excerpt": output_excerpt
            or ["Data Pump completed successfully through the CLI runtime."],
            "output_log": output_log,
            "oracle_log_lines": oracle_log_lines,
            "artifact_paths": artifact_paths,
        }

    def _execute_db_api_job(
        self,
        *,
        request: DataPumpJobCreate,
        command_preview: DataPumpCommandPreview,
        work_dir: Path,
        artifact_paths: list[str],
    ) -> dict[str, object]:
        work_dir.mkdir(parents=True, exist_ok=True)
        status_path = work_dir / "db_api_status.txt"
        execution_log_path = work_dir / "execution_log.txt"
        connection = None
        cursor = None
        oracle_log_lines: list[str] = []
        oracle_log_note: str | None = None
        execution_log: list[str] = [
            f"Backend: {command_preview.backend}",
            f"Operation: {request.operation}",
            f"Scope: {request.scope}",
            f"Storage type: {request.options.storage_type}",
            f"Oracle job name: {self._oracle_job_name(request)}",
            f"Connection role: {self._connection_role_label(request)}",
            f"Directory object: {request.options.directory_object}",
            f"Dump file: {request.options.dump_file}",
            f"Log file: {request.options.log_file or self._default_log_file(request)}",
        ]
        if self._uses_object_storage(request):
            execution_log.extend(
                [
                    f"Object Storage credential: {self._object_storage_config(request).credential_name}",
                    f"Object Storage URI: {self._object_storage_dump_uri(request)}",
                ]
            )

        try:
            execution_log.append("Opening Oracle connection.")
            connection = self._client_factory(
                self._connection_for_operation(request)
            ).open_connection()
            if hasattr(connection, "call_timeout"):
                connection.call_timeout = settings.datapump_call_timeout_seconds * 1000
                execution_log.append(
                    f"Connection call timeout set to {settings.datapump_call_timeout_seconds} seconds."
                )
            cursor = connection.cursor()
            execution_log.append("Opening DBMS_DATAPUMP job handle.")
            handle = self._open_db_api_job(cursor, request)
            execution_log.append(f"Job handle allocated: {handle}")
            execution_log.append("Registering dump and log files with DBMS_DATAPUMP.")
            registration_notes = self._add_common_files(cursor, handle, request)
            execution_log.extend(registration_notes)
            execution_log.append("Applying Data Pump parameters and filters.")
            self._apply_job_parameters(cursor, handle, request)
            execution_log.append("Starting DBMS_DATAPUMP job and waiting for completion.")
            job_state = self._start_db_api_job(cursor, handle)
            execution_log.append(f"DBMS_DATAPUMP completed with job state: {job_state}")
            connection.commit()
            execution_log.append("Oracle transaction committed.")
            oracle_log_lines, oracle_log_note = self._try_read_oracle_datapump_log(
                request=request,
                connection=connection,
            )
        except OracleClientError as exc:
            execution_log.append(f"Oracle connection error: {exc}")
            execution_log_path.write_text("\n".join(execution_log) + "\n", encoding="utf-8")
            raise OracleDataPumpExecutionFailedError(
                str(exc),
                {
                    "command_preview": command_preview.model_dump(mode="json"),
                    "output_excerpt": execution_log[-20:],
                    "output_log": execution_log,
                    "oracle_log_lines": oracle_log_lines,
                    "artifact_paths": [*artifact_paths, str(execution_log_path)],
                },
            ) from exc
        except Exception as exc:  # pragma: no cover - requires live Oracle
            execution_log.append(self._format_db_api_error(exc))
            execution_log_path.write_text("\n".join(execution_log) + "\n", encoding="utf-8")
            raise OracleDataPumpExecutionFailedError(
                self._format_db_api_error(exc),
                {
                    "command_preview": command_preview.model_dump(mode="json"),
                    "output_excerpt": execution_log[-20:],
                    "output_log": execution_log,
                    "oracle_log_lines": oracle_log_lines,
                    "artifact_paths": [*artifact_paths, str(execution_log_path)],
                },
            ) from exc
        finally:
            if cursor is not None:
                cursor.close()
            if connection is not None:
                connection.close()

        if job_state.upper() not in {"COMPLETED", "FINISHED"}:
            execution_log.append(
                f"DBMS_DATAPUMP ended in non-success job state: {job_state}"
            )
            execution_log_path.write_text("\n".join(execution_log) + "\n", encoding="utf-8")
            raise OracleDataPumpExecutionFailedError(
                f"DBMS_DATAPUMP finished with job state '{job_state}'. Check the Oracle log file for details.",
                {
                    "command_preview": command_preview.model_dump(mode="json"),
                    "output_excerpt": execution_log[-20:],
                    "output_log": execution_log,
                    "oracle_log_lines": oracle_log_lines,
                    "artifact_paths": [*artifact_paths, str(execution_log_path)],
                },
            )

        execution_log.append("Job finished successfully.")
        execution_log.append(
            "Inspect the Oracle log file inside the Oracle DIRECTORY object for object-level import or export details."
        )
        if oracle_log_note:
            execution_log.append(oracle_log_note)
        if oracle_log_lines:
            execution_log.extend(["[oracle-datapump-log]", *oracle_log_lines])
        execution_log_path.write_text("\n".join(execution_log) + "\n", encoding="utf-8")

        output_log = execution_log
        output_excerpt = oracle_log_lines[-20:] if oracle_log_lines else [
            f"Executed DBMS_DATAPUMP {request.operation} job '{self._oracle_job_name(request)}' via the {self._connection_role_label(request)}.",
            f"Oracle job state: {job_state}",
            f"Oracle DIRECTORY object: {request.options.directory_object}",
            f"Dump file: {request.options.dump_file}",
            f"Log file: {request.options.log_file or self._default_log_file(request)}",
            "Inspect the Oracle log file for detailed progress and object-level messages.",
        ]
        status_path.write_text(
            "\n".join(
                [
                    "backend=db_api",
                    f"operation={request.operation}",
                    f"scope={request.scope}",
                    f"job_state={job_state}",
                    f"directory_object={request.options.directory_object}",
                    f"dump_file={request.options.dump_file}",
                    f"log_file={request.options.log_file or self._default_log_file(request)}",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        artifact_paths = [*artifact_paths, str(status_path), str(execution_log_path)]
        if oracle_log_lines:
            oracle_log_path = work_dir / "oracle_datapump.log"
            oracle_log_path.write_text("\n".join(oracle_log_lines) + "\n", encoding="utf-8")
            artifact_paths.append(str(oracle_log_path))
        return {
            "command_preview": command_preview.model_dump(mode="json"),
            "output_excerpt": output_excerpt,
            "output_log": output_log,
            "oracle_log_lines": oracle_log_lines,
            "artifact_paths": artifact_paths,
        }

    def _write_plan_artifact(
        self,
        *,
        request: DataPumpJobCreate,
        command_preview: DataPumpCommandPreview,
        parameter_lines: list[str],
        work_dir: Path,
    ) -> Path:
        work_dir.mkdir(parents=True, exist_ok=True)
        plan_path = work_dir / "job_plan.txt"
        plan_lines = [
            f"backend={command_preview.backend}",
            f"operation={request.operation}",
            f"scope={request.scope}",
            f"command={command_preview.command_line}",
            "",
            *parameter_lines,
        ]
        plan_path.write_text("\n".join(plan_lines) + "\n", encoding="utf-8")
        return plan_path

    def _db_api_command_preview(self, request: DataPumpJobCreate) -> str:
        storage_hint = (
            f" to OCI Object Storage ({self._object_storage_dump_uri(request)})"
            if self._uses_object_storage(request)
            else ""
        )
        return (
            f"DBMS_DATAPUMP {request.operation} {request.scope} via "
            f"{self._connection_role_label(request)} "
            f"(job_name={self._oracle_job_name(request)})"
            f"{storage_hint}"
        )

    def _connection_role_label(self, request: DataPumpJobCreate) -> str:
        if request.operation == "EXPORT":
            return "source Oracle connection"
        return "target Oracle connection"

    def _oracle_job_name(self, request: DataPumpJobCreate) -> str:
        base = f"OMA_{request.operation}_{request.job_id}"
        sanitized = re.sub(r"[^A-Za-z0-9_]+", "_", base.upper())
        return sanitized[:30]

    def _open_db_api_job(self, cursor: object, request: DataPumpJobCreate) -> int:
        handle_var = cursor.var(int)
        cursor.execute(
            """
            BEGIN
              :handle := DBMS_DATAPUMP.OPEN(
                operation => :operation,
                job_mode => :job_mode,
                job_name => :job_name
              );
            END;
            """,
            handle=handle_var,
            operation=request.operation,
            job_mode=request.scope,
            job_name=self._oracle_job_name(request),
        )
        return int(handle_var.getvalue())

    def _add_common_files(
        self,
        cursor: object,
        handle: int,
        request: DataPumpJobCreate,
    ) -> list[str]:
        notes: list[str] = []
        if self._uses_object_storage(request):
            credential_name = self._object_storage_config(request).credential_name
            credential_owner, credential_lookup_note = self._lookup_visible_credential_owner(
                cursor,
                credential_name,
            )
            if credential_owner is not None:
                notes.append(
                    f"Credential '{credential_name}' is visible to the session"
                    + (f" through owner '{credential_owner}'." if credential_owner else ".")
                )
            elif credential_lookup_note:
                notes.append(
                    f"Credential visibility precheck could not confirm '{credential_name}': "
                    f"{credential_lookup_note}. Continuing with DBMS_DATAPUMP."
                )
            else:
                notes.append(
                    f"Credential visibility precheck could not confirm '{credential_name}', "
                    "but the app will continue and let Oracle validate it during execution."
                )

            if request.operation == "EXPORT":
                self._register_log_file(cursor, handle, request)
                self._register_object_storage_export_file(cursor, handle, request)
                return notes

            if self._should_skip_import_log_registration(request):
                notes.append(
                    "Skipping Oracle log-file registration for this Object Storage import "
                    "because DATA_PUMP_DIR is often not usable inside a PDB. The app will "
                    "still capture DBMS_DATAPUMP status messages."
                )
            else:
                try:
                    self._register_log_file(cursor, handle, request)
                except Exception as exc:  # pragma: no cover - requires live Oracle
                    notes.append(
                        "Oracle log-file registration was skipped after Oracle rejected the "
                        f"DIRECTORY object: {self._format_db_api_error(exc)}"
                    )

            try:
                self._register_object_storage_import_file(cursor, handle, request)
            except Exception as exc:  # pragma: no cover - requires live Oracle
                raise OracleDataPumpError(
                    "Object Storage dump-file registration failed for the import job. "
                    "Verify that the target database user can see the credential, that the "
                    "dump-file URI is correct, and that this database version supports "
                    "direct DBMS_DATAPUMP imports from OCI Object Storage. "
                    f"Oracle reported: {self._format_db_api_error(exc)}"
                ) from exc
            return notes

        cursor.execute(
            """
            BEGIN
              DBMS_DATAPUMP.ADD_FILE(
                handle => :handle,
                filename => :filename,
                directory => :directory_name,
                filetype => DBMS_DATAPUMP.KU$_FILE_TYPE_DUMP_FILE,
                reusefile => 1
              );
              DBMS_DATAPUMP.ADD_FILE(
                handle => :handle,
                filename => :log_filename,
                directory => :directory_name,
                filetype => DBMS_DATAPUMP.KU$_FILE_TYPE_LOG_FILE,
                reusefile => 1
              );
            END;
            """,
            handle=handle,
            filename=request.options.dump_file,
            log_filename=request.options.log_file or self._default_log_file(request),
            directory_name=request.options.directory_object,
        )
        return notes

    def _register_log_file(self, cursor: object, handle: int, request: DataPumpJobCreate) -> None:
        cursor.execute(
            """
            BEGIN
              DBMS_DATAPUMP.ADD_FILE(
                :handle,
                :log_filename,
                :directory_name,
                NULL,
                DBMS_DATAPUMP.KU$_FILE_TYPE_LOG_FILE,
                1
              );
            END;
            """,
            handle=handle,
            log_filename=request.options.log_file or self._default_log_file(request),
            directory_name=request.options.directory_object,
        )

    def _register_object_storage_export_file(
        self,
        cursor: object,
        handle: int,
        request: DataPumpJobCreate,
    ) -> None:
        cursor.execute(
            """
            BEGIN
              DBMS_DATAPUMP.ADD_FILE(
                :handle,
                :dump_uri,
                :credential_name,
                :file_size,
                DBMS_DATAPUMP.KU$_FILE_TYPE_URIDUMP_FILE,
                1
              );
            END;
            """,
            handle=handle,
            dump_uri=self._object_storage_dump_uri(request),
            credential_name=self._object_storage_config(request).credential_name,
            file_size=self.OBJECT_STORAGE_FILESIZE,
        )

    def _register_object_storage_import_file(
        self,
        cursor: object,
        handle: int,
        request: DataPumpJobCreate,
    ) -> None:
        cursor.execute(
            """
            BEGIN
              DBMS_DATAPUMP.ADD_FILE(
                :handle,
                :dump_uri,
                :credential_name,
                NULL,
                DBMS_DATAPUMP.KU$_FILE_TYPE_URIDUMP_FILE
              );
            END;
            """,
            handle=handle,
            dump_uri=self._object_storage_dump_uri(request),
            credential_name=self._object_storage_config(request).credential_name,
        )

    def _lookup_visible_credential_owner(
        self,
        cursor: object,
        credential_name: str,
    ) -> tuple[str | None, str | None]:
        lookup_queries = [
            (
                "USER_CREDENTIALS",
                """
                SELECT USER
                FROM user_credentials
                WHERE credential_name = UPPER(:credential_name)
                FETCH FIRST 1 ROWS ONLY
                """,
            ),
            (
                "ALL_CREDENTIALS",
                """
                SELECT owner
                FROM all_credentials
                WHERE credential_name = UPPER(:credential_name)
                FETCH FIRST 1 ROWS ONLY
                """,
            ),
            (
                "DBA_CREDENTIALS",
                """
                SELECT owner
                FROM dba_credentials
                WHERE credential_name = UPPER(:credential_name)
                FETCH FIRST 1 ROWS ONLY
                """,
            ),
        ]

        errors: list[str] = []
        for view_name, sql_text in lookup_queries:
            try:
                cursor.execute(sql_text, credential_name=credential_name)
                row = cursor.fetchone()
            except Exception as exc:  # pragma: no cover - requires live Oracle
                errors.append(f"{view_name}: {exc}")
                continue

            if row is None:
                continue
            return (
                str(row[0]) if row[0] is not None else None,
                None,
            )

        note = "; ".join(errors[-2:]) if errors else None
        return None, note

    @staticmethod
    def _should_skip_import_log_registration(request: DataPumpJobCreate) -> bool:
        return (
            request.operation == "IMPORT"
            and request.options.storage_type == "OCI_OBJECT_STORAGE"
            and request.options.directory_object.strip().upper() == "DATA_PUMP_DIR"
        )

    def _apply_job_parameters(self, cursor: object, handle: int, request: DataPumpJobCreate) -> None:
        cursor.execute(
            """
            BEGIN
              DBMS_DATAPUMP.SET_PARALLEL(
                handle => :handle,
                degree => :parallel_degree
              );
            END;
            """,
            handle=handle,
            parallel_degree=request.options.parallel,
        )

        if request.scope == "SCHEMA":
            cursor.execute(
                """
                BEGIN
                  DBMS_DATAPUMP.METADATA_FILTER(
                    handle => :handle,
                    name => 'SCHEMA_EXPR',
                    value => :schema_expr
                  );
                END;
                """,
                handle=handle,
                schema_expr=self._schema_expression(request.options.schemas),
            )

        if request.options.exclude_statistics:
            cursor.execute(
                """
                BEGIN
                  DBMS_DATAPUMP.METADATA_FILTER(
                    handle => :handle,
                    name => 'EXCLUDE_PATH_EXPR',
                    value => :exclude_expr
                  );
                END;
                """,
                handle=handle,
                exclude_expr="IN ('STATISTICS')",
            )

        if request.operation == "EXPORT" and request.options.compression_enabled:
            cursor.execute(
                """
                BEGIN
                  DBMS_DATAPUMP.SET_PARAMETER(
                    handle => :handle,
                    name => 'COMPRESSION',
                    value => 'ALL'
                  );
                END;
                """,
                handle=handle,
            )

        if request.operation == "IMPORT":
            cursor.execute(
                """
                BEGIN
                  DBMS_DATAPUMP.SET_PARAMETER(
                    handle => :handle,
                    name => 'TABLE_EXISTS_ACTION',
                    value => :table_exists_action
                  );
                END;
                """,
                handle=handle,
                table_exists_action=request.options.table_exists_action,
            )
            for remap in request.options.remap_schemas:
                cursor.execute(
                    """
                    BEGIN
                      DBMS_DATAPUMP.METADATA_REMAP(
                        handle => :handle,
                        name => 'REMAP_SCHEMA',
                        old_value => :old_value,
                        value => :new_value
                      );
                    END;
                    """,
                    handle=handle,
                    old_value=remap.source_schema,
                    new_value=remap.target_schema,
                )

    def _start_db_api_job(self, cursor: object, handle: int) -> str:
        job_state = cursor.var(str)
        cursor.execute(
            """
            DECLARE
              v_job_state VARCHAR2(30);
            BEGIN
              DBMS_DATAPUMP.START_JOB(handle => :handle);
              DBMS_DATAPUMP.WAIT_FOR_JOB(handle => :handle, job_state => v_job_state);
              DBMS_DATAPUMP.DETACH(handle => :handle);
              :job_state := v_job_state;
            EXCEPTION
              WHEN OTHERS THEN
                BEGIN
                  DBMS_DATAPUMP.DETACH(handle => :handle);
                EXCEPTION
                  WHEN OTHERS THEN NULL;
                END;
                RAISE;
            END;
            """,
            handle=handle,
            job_state=job_state,
        )
        return str(job_state.getvalue() or "UNKNOWN")

    def _uses_object_storage(self, request: DataPumpJobCreate) -> bool:
        return request.options.storage_type == "OCI_OBJECT_STORAGE"

    def _object_storage_config(
        self,
        request: DataPumpJobCreate,
    ) -> DataPumpJobOptions.ObjectStorageConfig:
        if request.options.object_storage is None:
            raise OracleDataPumpError(
                "OCI Object Storage configuration is required when storage type is OCI_OBJECT_STORAGE."
            )
        return request.options.object_storage

    def _object_storage_dump_uri(self, request: DataPumpJobCreate) -> str:
        config = self._object_storage_config(request)
        region = config.region.strip().rstrip(".")
        prefix = (config.object_prefix or "").strip().strip("/")
        object_name = request.options.dump_file.strip()
        if prefix:
            object_name = f"{prefix}/{object_name}"
        encoded_object_name = quote(object_name, safe="")
        return (
            f"https://objectstorage.{region}.oraclecloud.com"
            f"/n/{config.namespace}/b/{config.bucket}/o/{encoded_object_name}"
        )

    @staticmethod
    def _schema_expression(schemas: list[str]) -> str:
        values: list[str] = []
        for schema in schemas:
            normalized = schema.strip().upper()
            if not normalized:
                continue
            values.append("'" + normalized.replace("'", "''") + "'")
        quoted = ",".join(values)
        return f"IN ({quoted})"

    @staticmethod
    def _format_db_api_error(exc: Exception) -> str:
        error_text = str(exc).strip()
        if error_text:
            return f"DBMS_DATAPUMP execution failed. Oracle reported: {error_text}"
        return "DBMS_DATAPUMP execution failed."

    def _try_read_oracle_datapump_log(
        self,
        *,
        request: DataPumpJobCreate,
        connection: object | None,
    ) -> tuple[list[str], str | None]:
        managed_connection = None
        cursor = None

        try:
            active_connection = connection
            if active_connection is None:
                managed_connection = self._client_factory(
                    self._connection_for_operation(request)
                ).open_connection()
                active_connection = managed_connection

            if oracledb is None:
                return [], "Oracle Data Pump log could not be fetched because python-oracledb is unavailable."

            cursor = active_connection.cursor()
            content_var = cursor.var(oracledb.DB_TYPE_CLOB)
            cursor.execute(
                """
                DECLARE
                  l_file UTL_FILE.FILE_TYPE;
                  l_line VARCHAR2(32767);
                  l_content CLOB;
                BEGIN
                  DBMS_LOB.CREATETEMPORARY(l_content, TRUE);
                  l_file := UTL_FILE.FOPEN(:directory_name, :file_name, 'r', 32767);
                  BEGIN
                    LOOP
                      UTL_FILE.GET_LINE(l_file, l_line, 32767);
                      DBMS_LOB.WRITEAPPEND(l_content, LENGTH(l_line || CHR(10)), l_line || CHR(10));
                    END LOOP;
                  EXCEPTION
                    WHEN NO_DATA_FOUND THEN
                      NULL;
                  END;
                  IF UTL_FILE.IS_OPEN(l_file) THEN
                    UTL_FILE.FCLOSE(l_file);
                  END IF;
                  :content := l_content;
                EXCEPTION
                  WHEN OTHERS THEN
                    BEGIN
                      IF UTL_FILE.IS_OPEN(l_file) THEN
                        UTL_FILE.FCLOSE(l_file);
                      END IF;
                    EXCEPTION
                      WHEN OTHERS THEN NULL;
                    END;
                    RAISE;
                END;
                """,
                directory_name=request.options.directory_object,
                file_name=request.options.log_file or self._default_log_file(request),
                content=content_var,
            )
            content = content_var.getvalue()
            if content is None:
                return [], "Oracle Data Pump log file was not available for reading."

            lines = [line.rstrip() for line in str(content).splitlines()]
            if not lines:
                return [], "Oracle Data Pump log file was read but it is empty."

            return lines, None
        except Exception as exc:  # pragma: no cover - requires live Oracle privileges
            error_text = str(exc).strip()
            if error_text:
                return [], f"Oracle Data Pump log could not be fetched from the DIRECTORY object. Oracle reported: {error_text}"
            return [], "Oracle Data Pump log could not be fetched from the DIRECTORY object."
        finally:
            if cursor is not None:
                cursor.close()
            if managed_connection is not None:
                managed_connection.close()
