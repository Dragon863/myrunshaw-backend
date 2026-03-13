import logging
import typing

_ANSI_COLORS = {
    logging.DEBUG: "\x1b[36m",  # cyan
    logging.INFO: "\x1b[36m",  # cyan
    logging.WARNING: "\x1b[33m",  # yellow
    logging.ERROR: "\x1b[31m",  # red
    logging.CRITICAL: "\x1b[35m",  # magenta
}
_ANSI_RESET = "\x1b[0m"


class ANSIFormatter(logging.Formatter):
    """Adds ANSI colour codes to log output based on level (works well in Docker)."""

    def format(self, record: logging.LogRecord) -> str:
        color = _ANSI_COLORS.get(record.levelno, "")
        return f"{color}{super().format(record)}{_ANSI_RESET}"


def configure_logging(level: int = logging.INFO) -> None:
    """
    Set up the root logger with a coloured StreamHandler.
    Call once at application startup, before setup_telemetry().
    The OpenTelemetry LoggingHandler is added later by setup_telemetry().
    """
    handler = logging.StreamHandler()
    handler.setFormatter(ANSIFormatter("%(levelname)s: %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(handler)


class Logger:
    """
    Thin wrapper around stdlib logging.Logger that routes all records through
    the standard logging infrastructure, so they are captured by OpenTelemetry
    and any configured handlers.
    """

    def __init__(self, name: str) -> None:
        self._logger = logging.getLogger(name)

    def info(self, message: str, extra: dict | None = None) -> None:
        self._logger.info(message, extra=extra)

    def warning(self, message: str, extra: dict | None = None) -> None:
        self._logger.warning(message, extra=extra)

    def error(self, message: str, extra: dict | None = None) -> None:
        self._logger.error(message, extra=extra)

    def debug(self, message: str, extra: dict | None = None) -> None:
        self._logger.debug(message, extra=extra)

    def critical(self, message: str, extra: dict | None = None) -> None:
        self._logger.critical(message, extra=extra)

    def exception(self, message: str, extra: dict | None = None) -> None:
        self._logger.exception(message, extra=extra)


class EndpointFilter(logging.Filter):
    # https://github.com/encode/starlette/issues/864#issuecomment-1254987630
    def __init__(
        self,
        path: str,
        *args: typing.Any,
        **kwargs: typing.Any,
    ):
        super().__init__(*args, **kwargs)
        self._path = path

    def filter(self, record: logging.LogRecord) -> bool:
        return record.getMessage().find(self._path) == -1
