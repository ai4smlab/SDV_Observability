from fastapi import FastAPI, HTTPException
import requests
import time
import logging

from opentelemetry import trace, metrics
from opentelemetry.sdk.resources import Resource

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor

from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.instrumentation.system_metrics import SystemMetricsInstrumentor

from opentelemetry._logs import set_logger_provider
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter


resource = Resource.create({
    "service.name": "zone-gateway-a"
})


# Tracing
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


# Metrics
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
meter = metrics.get_meter("zone-gateway-a")

gateway_a_requests = meter.create_counter(
    "gateway_a_requests",
    description="Number of Zone Gateway A requests",
    unit="1"
)

gateway_a_errors = meter.create_counter(
    "gateway_a_errors",
    description="Number of failed Zone Gateway A requests",
    unit="1"
)

gateway_a_duration = meter.create_histogram(
    "gateway_a_duration",
    description="Duration of Zone Gateway A requests",
    unit="ms"
)


# Logging
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

logger = logging.getLogger("zone-gateway-a")
logger.setLevel(logging.INFO)
logger.addHandler(
    LoggingHandler(
        level=logging.INFO,
        logger_provider=logger_provider
    )
)
logger.propagate = False


# Application
app = FastAPI(
    title="Zone Gateway A",
    description="Simulated Zone A gateway for the miniature zonal SDV architecture",
    version="1.0.0"
)


@app.get("/")
def home():
    return {
        "service": "zone-gateway-a",
        "zone": "A",
        "status": "running"
    }


@app.get("/zone-a/battery")
def get_zone_a_battery():

    start_time = time.perf_counter()
    gateway_a_requests.add(1)

    logger.info("Zone A battery request started")

    try:
        response = requests.get(
            "http://battery-sensor:8003/battery/data",
            timeout=2
        )

        response.raise_for_status()
        battery_data = response.json()

        logger.info(
            "Battery Sensor response received successfully"
        )

        return {
            "gateway": "zone-gateway-a",
            "zone": "A",
            "status": "healthy",
            "battery_data": battery_data
        }

    except requests.RequestException as exc:

        gateway_a_errors.add(1)

        logger.error(
            "Battery Sensor communication failure: %s",
            exc
        )

        raise HTTPException(
            status_code=503,
            detail=f"Battery Sensor Service unavailable: {exc}"
        )

    finally:

        duration_ms = (
            time.perf_counter() - start_time
        ) * 1000

        gateway_a_duration.record(duration_ms)

        logger.info(
            "Zone A gateway request completed in %.2f ms",
            duration_ms
        )


FastAPIInstrumentor.instrument_app(app)
RequestsInstrumentor().instrument()
SystemMetricsInstrumentor().instrument()