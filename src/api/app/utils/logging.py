import logging
import typing


class LogLevel:
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    DEBUG = "DEBUG"
    CRITICAL = "CRITICAL"


class Logger:
    # I'm using ANSI escape codes for colors, as this works well in docker
    def __init__(self, name):
        self.name = name

    def log(self, level, message):
        print(f"{level}: {self.name}: {message}")

    def info(self, message):
        self.log(LogLevel.INFO, "\x1b[36m" + message + "\x1b[0m")

    def warning(self, message):
        self.log(LogLevel.WARNING, "\x1b[33m" + message + "\x1b[0m")

    def error(self, message):
        self.log(LogLevel.ERROR, "\x1b[31m" + message + "\x1b[0m")

    def debug(self, message):
        self.log(LogLevel.DEBUG, "\x1b[36m" + message + "\x1b[0m")

    def critical(self, message):
        self.log(LogLevel.CRITICAL, "\x1b[35m" + message + "\x1b[0m")


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
