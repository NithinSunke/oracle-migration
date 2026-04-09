from __future__ import annotations

from pathlib import Path
from threading import Lock
from contextlib import contextmanager
from typing import Iterator

from backend.app.core.config import settings
from backend.app.schemas.migration import OracleConnectionConfig

try:
    import oracledb
except ImportError:  # pragma: no cover - depends on runtime package availability
    oracledb = None


class OracleClientError(RuntimeError):
    """Raised when Oracle connectivity cannot be established safely."""


class OracleDriverUnavailableError(OracleClientError):
    """Raised when python-oracledb is unavailable in the runtime."""


_oracle_client_init_lock = Lock()


class OracleDatabaseClient:
    def __init__(self, connection: OracleConnectionConfig) -> None:
        self._connection = connection

    def _requested_thick_mode(self) -> bool:
        return self._connection.mode == "thick"

    def _wallet_config_dir(self) -> str | None:
        wallet_location = (self._connection.wallet_location or "").strip()
        return wallet_location or None

    def _initialize_oracle_client(self) -> None:
        if oracledb is None or not self._requested_thick_mode():
            return

        with _oracle_client_init_lock:
            if not oracledb.is_thin_mode():
                return

            lib_dir = Path(settings.oracle_client_lib_dir).expanduser()
            if not lib_dir.exists():
                raise OracleClientError(
                    "Oracle Thick mode was requested, but the Oracle client library directory is unavailable."
                )

            init_kwargs: dict[str, str] = {"lib_dir": str(lib_dir)}
            config_dir = self._wallet_config_dir()
            if config_dir is not None:
                init_kwargs["config_dir"] = config_dir

            try:
                oracledb.init_oracle_client(**init_kwargs)
            except Exception as exc:  # pragma: no cover - exercised against live runtime
                raise self._normalize_connection_error(exc) from exc

    def _validate_connection_mode(self) -> None:
        if self._connection.username.strip().lower() == "sys" and not self._connection.sysdba:
            raise OracleClientError(
                "The SYS account must connect with 'Connect as SYSDBA' enabled."
            )

    def _build_connect_kwargs(self) -> dict[str, object]:
        if oracledb is None:
            raise OracleDriverUnavailableError(
                "python-oracledb is not available in the current runtime."
            )

        dsn = oracledb.makedsn(
            self._connection.host,
            self._connection.port,
            service_name=self._connection.service_name,
        )
        kwargs: dict[str, object] = {
            "user": self._connection.username,
            "password": self._connection.password.get_secret_value()
            if self._connection.password is not None
            else None,
            "dsn": dsn,
        }
        config_dir = self._wallet_config_dir()
        if config_dir is not None:
            kwargs["config_dir"] = config_dir
        if self._connection.sysdba:
            kwargs["mode"] = oracledb.SYSDBA
        return kwargs

    @staticmethod
    def _normalize_connection_error(exc: Exception) -> OracleClientError:
        error_text = str(exc).strip()

        if "ORA-28009" in error_text:
            message = "The SYS account must connect with 'Connect as SYSDBA' enabled."
        elif "ORA-01017" in error_text:
            message = "Oracle rejected the username or password. Verify the credentials and privilege mode."
        elif "ORA-12154" in error_text or "DPY-6001" in error_text:
            message = "Oracle could not resolve the connection details. Verify host, port, and service name."
        elif "ORA-12514" in error_text:
            message = "The Oracle listener does not recognize that service name. Verify the service name."
        elif "ORA-12541" in error_text:
            message = "The Oracle listener is not reachable on the specified host and port."
        elif "ORA-12545" in error_text or "getaddrinfo" in error_text:
            message = "The Oracle database host could not be resolved from the application runtime."
        elif "ORA-12638" in error_text or "ORA-28759" in error_text:
            message = "Oracle wallet or external credential configuration could not be used with the supplied settings."
        elif "DPY-2017" in error_text:
            message = (
                "Oracle Thick mode was initialized earlier in this backend process with different wallet or config settings. Use the same wallet location for both source and target validation, or clear the wallet path when it is not needed."
            )
        elif "DPY-2019" in error_text or "python-oracledb thick mode cannot be used" in error_text:
            message = (
                "Oracle Thick mode was requested after a Thin-mode connection had already been created in this backend process. Restart the service and retry with the same mode selected for both source and target validation."
            )
        elif "DPY-3015" in error_text:
            message = (
                "Oracle Thick mode was requested after Thin mode was already initialized in this process. Restart the service and retry with Thick mode selected before making other Oracle connections."
            )
        elif "DPY-3010" in error_text or "DPY-3001" in error_text or "DPI-1047" in error_text:
            message = (
                "Oracle Thick mode could not be initialized. Verify the Oracle Instant Client libraries are mounted and readable in the runtime."
            )
        elif "DPY-301" in error_text:
            message = (
                "This Oracle database requires features that python-oracledb Thin mode cannot use. Retry with Thick mode selected."
            )
        else:
            message = (
                "Unable to connect to the Oracle database with the supplied connection settings."
            )
            if error_text:
                message = f"{message} Oracle reported: {error_text}"

        return OracleClientError(message)

    def open_connection(self) -> object:
        if not self._connection.has_secret():
            raise OracleClientError(
                "Oracle metadata collection requires a password-enabled source connection."
            )

        self._validate_connection_mode()
        self._initialize_oracle_client()

        try:
            connection = oracledb.connect(**self._build_connect_kwargs())
            if hasattr(connection, "call_timeout"):
                connection.call_timeout = settings.oracle_call_timeout_ms
            return connection
        except OracleClientError:
            raise
        except Exception as exc:  # pragma: no cover - exercised against live Oracle only
            raise self._normalize_connection_error(exc) from exc

    @contextmanager
    def connect(self) -> Iterator[object]:
        connection = self.open_connection()
        try:
            yield connection
        finally:
            connection.close()


def initialize_oracle_client_runtime() -> None:
    if oracledb is None:
        return
    if not oracledb.is_thin_mode():
        return

    lib_dir = Path(settings.oracle_client_lib_dir).expanduser()
    if not lib_dir.exists():
        return

    with _oracle_client_init_lock:
        if not oracledb.is_thin_mode():
            return
        oracledb.init_oracle_client(lib_dir=str(lib_dir))
