import logging

from fastapi import FastAPI
from opentelemetry import _logs, metrics, trace
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.celery import CeleryInstrumentor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased

from app.core.config import Settings

_configured = False
_providers: list[TracerProvider | MeterProvider | LoggerProvider] = []


def _resource(settings: Settings) -> Resource:
    return Resource.create(
        {
            SERVICE_NAME: settings.otel_service_name,
            "deployment.environment.name": settings.app_env,
        }
    )


def _configure_providers(settings: Settings) -> None:
    endpoint = settings.otel_exporter_otlp_endpoint
    if not endpoint:
        return

    resource = _resource(settings)
    insecure = endpoint.startswith("http://")

    tracer_provider = TracerProvider(
        resource=resource,
        sampler=ParentBased(TraceIdRatioBased(settings.otel_trace_sample_ratio)),
    )
    tracer_provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=insecure))
    )
    trace.set_tracer_provider(tracer_provider)

    metric_reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=endpoint, insecure=insecure)
    )
    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(meter_provider)

    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(
        BatchLogRecordProcessor(OTLPLogExporter(endpoint=endpoint, insecure=insecure))
    )
    _logs.set_logger_provider(logger_provider)
    logging.getLogger().addHandler(
        LoggingHandler(level=logging.INFO, logger_provider=logger_provider)
    )

    _providers.extend([tracer_provider, meter_provider, logger_provider])


def _configure_common_instrumentation() -> None:
    SQLAlchemyInstrumentor().instrument()
    RedisInstrumentor().instrument()


def configure_observability(application: FastAPI, settings: Settings) -> None:
    global _configured
    if _configured or not settings.otel_exporter_otlp_endpoint:
        return

    _configure_providers(settings)
    _configure_common_instrumentation()
    FastAPIInstrumentor.instrument_app(application)
    _configured = True


def configure_celery_observability(settings: Settings) -> None:
    global _configured
    if _configured or not settings.otel_exporter_otlp_endpoint:
        return

    _configure_providers(settings)
    _configure_common_instrumentation()
    CeleryInstrumentor().instrument()  # type: ignore[no-untyped-call]
    _configured = True


def shutdown_observability() -> None:
    for provider in reversed(_providers):
        provider.shutdown()
    _providers.clear()
