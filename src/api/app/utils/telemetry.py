import logging
import os

from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry._logs import set_logger_provider

logger = logging.getLogger("telemetry")


def _build_logs_endpoint(endpoint: str) -> str:
    """Return an OTLP HTTP logs endpoint with the suffix exactly once."""
    endpoint = endpoint.rstrip("/")
    if endpoint.endswith("/logs"):
        return endpoint
    return f"{endpoint}/logs"


def setup_telemetry(app) -> None:
    """Configure OpenTelemetry logging."""
    del app  # Retained to keep the public function signature stable.

    logs_endpoint = os.getenv(
        "OTLP_LOGS_EXPORTER_ENDPOINT",
        os.getenv("OTLP_EXPORTER_ENDPOINT", ""),
    ).rstrip("/")

    if not logs_endpoint:
        logger.warning("No OTLP log endpoint configured; OpenTelemetry disabled")
        return

    api_key = os.getenv("POSTHOG_API_KEY")
    headers: dict[str, str] = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    else:
        logger.warning("POSTHOG_API_KEY not set; OTLP requests will be unauthenticated")

    environment = os.getenv(
        "APP_ENV", "unknown"
    )  # e.g. "production", "development", "staging"

    resource = Resource(attributes={SERVICE_NAME: f"myrunshaw-api-{environment}"})

    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(
        BatchLogRecordProcessor(
            OTLPLogExporter(
                endpoint=_build_logs_endpoint(logs_endpoint),
                headers=headers,
            )
        )
    )
    set_logger_provider(logger_provider)

    # stdlib logging -> OpenTelemetry, so existing Logger calls are captured
    logging.getLogger().addHandler(LoggingHandler(logger_provider=logger_provider))

    logger.info(
        "OpenTelemetry logging configured - %s",
        _build_logs_endpoint(logs_endpoint),
    )
