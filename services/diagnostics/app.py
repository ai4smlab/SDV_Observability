from fastapi import FastAPI, HTTPException
import asyncio
import httpx
import time
import logging

from opentelemetry import trace, metrics
from opentelemetry.sdk.resources import Resource

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.instrumentation.system_metrics import SystemMetricsInstrumentor

from opentelemetry._logs import set_logger_provider
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter


resource = Resource.create({
    "service.name": "diagnostics-service"
})


# -------------------------------------------------
# Tracing
# -------------------------------------------------

tracer_provider = TracerProvider(resource=resource)
trace.set_tracer_provider(tracer_provider)

tracer_provider.add_span_processor(
    BatchSpanProcessor(
        OTLPSpanExporter(
            endpoint="http://otel-collector:4317",
            insecure=True
        )
    )
)


# -------------------------------------------------
# Metrics
# -------------------------------------------------

metric_reader = PeriodicExportingMetricReader(
    OTLPMetricExporter(
        endpoint="http://otel-collector:4317",
        insecure=True
    ),
    export_interval_millis=5000
)

meter_provider = MeterProvider(
    resource=resource,
    metric_readers=[metric_reader]
)

metrics.set_meter_provider(meter_provider)

meter = metrics.get_meter("diagnostics-service")

diagnostics_requests = meter.create_counter(
    "diagnostics_requests",
    description="Number of diagnostics requests",
    unit="1"
)

diagnostics_errors = meter.create_counter(
    "diagnostics_errors",
    description="Number of failed diagnostics requests",
    unit="1"
)

diagnostics_duration = meter.create_histogram(
    "diagnostics_duration",
    description="Duration of diagnostics requests",
    unit="ms"
)


# -------------------------------------------------
# Logging
# -------------------------------------------------

logger_provider = LoggerProvider(resource=resource)
set_logger_provider(logger_provider)

logger_provider.add_log_record_processor(
    BatchLogRecordProcessor(
        OTLPLogExporter(
            endpoint="http://otel-collector:4317",
            insecure=True
        )
    )
)

logger = logging.getLogger("diagnostics-service")
logger.setLevel(logging.INFO)
logger.addHandler(
    LoggingHandler(
        level=logging.INFO,
        logger_provider=logger_provider
    )
)
logger.propagate = False


# -------------------------------------------------
# Application
# -------------------------------------------------

app = FastAPI(
    title="Diagnostics Service",
    description="Central-compute diagnostics service for the miniature zonal SDV architecture",
    version="1.0.0"
)


@app.get("/")
def home():
    return {
        "service": "diagnostics-service",
        "location": "central-compute",
        "status": "running"
    }


@app.get("/diagnostics/check")
async def run_diagnostics():

    start_time = time.perf_counter()
    diagnostics_requests.add(1)

    logger.info("Diagnostics request started")

    zone_a_url = "http://zone-gateway-a:8001/zone-a/battery"
    zone_b_url = "http://zone-gateway-b:8002/zone-b/thermal"

    try:
        async with httpx.AsyncClient(timeout=3.0) as client:

            zone_a_response, zone_b_response = await asyncio.gather(
                client.get(zone_a_url),
                client.get(zone_b_url)
            )

            zone_a_response.raise_for_status()
            zone_b_response.raise_for_status()

            zone_a_data = zone_a_response.json()
            zone_b_data = zone_b_response.json()

        logger.info(
            "Zone A and Zone B diagnostic responses received successfully"
        )

        return {
            "service": "diagnostics-service",
            "status": "healthy",
            "zones": {
                "zone_a": zone_a_data,
                "zone_b": zone_b_data
            }
        }

    except httpx.HTTPError as exc:

        diagnostics_errors.add(1)

        logger.error(
            "Unable to complete zonal diagnostics: %s",
            exc
        )

        raise HTTPException(
            status_code=503,
            detail=f"Unable to complete zonal diagnostics: {exc}"
        )

    finally:

        duration_ms = (
            time.perf_counter() - start_time
        ) * 1000

        diagnostics_duration.record(duration_ms)

        logger.info(
            "Diagnostics request completed in %.2f ms",
            duration_ms
        )


FastAPIInstrumentor.instrument_app(app)
HTTPXClientInstrumentor().instrument()
SystemMetricsInstrumentor().instrument()