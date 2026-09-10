from fastapi import FastAPI
import random
import time
import logging

from opentelemetry import trace, metrics
from opentelemetry.sdk.resources import Resource

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.instrumentation.system_metrics import SystemMetricsInstrumentor

from opentelemetry._logs import set_logger_provider
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter


resource = Resource.create({
    "service.name": "thermal-sensor-service"
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
meter = metrics.get_meter("thermal-sensor-service")


thermal_requests = meter.create_counter(
    "thermal_requests",
    description="Number of thermal data requests",
    unit="1"
)

thermal_duration = meter.create_histogram(
    "thermal_duration",
    description="Duration of thermal data requests",
    unit="ms"
)


thermal_state = {
    "temperature_c": 36.0
}


def observe_thermal_temperature(options):
    yield metrics.Observation(
        thermal_state["temperature_c"]
    )


meter.create_observable_gauge(
    "thermal_temperature_c",
    callbacks=[observe_thermal_temperature],
    description="Current simulated thermal sensor temperature",
    unit="Cel"
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

logger = logging.getLogger("thermal-sensor-service")
logger.setLevel(logging.INFO)
logger.addHandler(
    LoggingHandler(
        level=logging.INFO,
        logger_provider=logger_provider
    )
)
logger.propagate = False


def update_thermal_state():

    thermal_state["temperature_c"] += random.uniform(
        -0.15,
        0.15
    )

    thermal_state["temperature_c"] = max(
        30.0,
        min(
            thermal_state["temperature_c"],
            42.0
        )
    )


app = FastAPI(
    title="Thermal Sensor Service",
    description="Simulated thermal end-node service for Zone B",
    version="1.0.0"
)


@app.get("/")
def home():
    return {
        "service": "thermal-sensor-service",
        "zone": "B",
        "status": "running"
    }


@app.get("/thermal/data")
def get_thermal_data():

    start_time = time.perf_counter()
    thermal_requests.add(1)

    logger.info("Thermal data request started")

    try:
        update_thermal_state()

        temperature = thermal_state["temperature_c"]

        cooling_status = (
            "active"
            if temperature >= 40
            else "normal"
        )

        status = (
            "warning"
            if temperature >= 45
            else "healthy"
        )

        logger.info(
            "Thermal state observed: temperature=%.2f C cooling_status=%s status=%s",
            temperature,
            cooling_status,
            status
        )

        if status == "warning":
            logger.warning(
                "Thermal warning condition detected"
            )

        return {
            "sensor_id": "THM-ZB-001",
            "zone": "B",
            "temperature_c": round(
                temperature,
                2
            ),
            "cooling_status": cooling_status,
            "status": status
        }

    finally:

        duration_ms = (
            time.perf_counter() - start_time
        ) * 1000

        thermal_duration.record(duration_ms)

        logger.info(
            "Thermal data request completed in %.2f ms",
            duration_ms
        )


FastAPIInstrumentor.instrument_app(app)
SystemMetricsInstrumentor().instrument()