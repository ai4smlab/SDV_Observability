from fastapi import FastAPI, HTTPException
import httpx
import random
import time
import logging
import asyncio

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


# -------------------------------------------------
# Shared OpenTelemetry resource
# -------------------------------------------------

resource = Resource.create({
    "service.name": "vehicle-state-service"
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
meter = metrics.get_meter("vehicle-state-service")


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

logger = logging.getLogger("vehicle-state-service")
logger.setLevel(logging.INFO)

logger.addHandler(
    LoggingHandler(
        level=logging.INFO,
        logger_provider=logger_provider
    )
)

logger.propagate = False


# -------------------------------------------------
# Simulated vehicle state
# -------------------------------------------------

vehicle_state = {
    "vehicle_id": "SDV-001",
    "speed_kmh": 60.0,
    "operating_mode": "driving"
}

simulation_start = time.monotonic()


# -------------------------------------------------
# Custom metrics
# -------------------------------------------------

vehicle_status_requests = meter.create_counter(
    "vehicle_status_requests",
    description="Number of vehicle status requests",
    unit="1"
)

vehicle_status_duration = meter.create_histogram(
    "vehicle_status_duration",
    description="Duration of vehicle status requests",
    unit="ms"
)


def observe_vehicle_speed(options):
    yield metrics.Observation(
        vehicle_state["speed_kmh"]
    )


meter.create_observable_gauge(
    "vehicle_speed_kmh",
    callbacks=[observe_vehicle_speed],
    description="Current simulated vehicle speed",
    unit="km/h"
)


# -------------------------------------------------
# Synthetic operating cycle
#
# 0-25 min  : driving
# 25-30 min : idle
#
# Charging is a separate battery state and is
# handled by the Battery Sensor.
# -------------------------------------------------

def determine_operating_mode():

    elapsed_seconds = (
        time.monotonic() - simulation_start
    )

    cycle_position = (
        elapsed_seconds % 1800
    )

    if cycle_position < 1500:
        return "driving"

    return "idle"


async def simulate_vehicle_state():

    previous_mode = None

    while True:

        mode = determine_operating_mode()

        vehicle_state[
            "operating_mode"
        ] = mode

        if mode != previous_mode:

            logger.info(
                "Vehicle operating mode changed to %s",
                mode
            )

            previous_mode = mode

        if mode == "driving":

            vehicle_state[
                "speed_kmh"
            ] += random.uniform(
                -4.0,
                4.0
            )

            vehicle_state[
                "speed_kmh"
            ] = max(
                20.0,
                min(
                    vehicle_state[
                        "speed_kmh"
                    ],
                    100.0
                )
            )

        else:

            vehicle_state[
                "speed_kmh"
            ] = 0.0

        await asyncio.sleep(5)


# -------------------------------------------------
# FastAPI application
# -------------------------------------------------

app = FastAPI(
    title="Vehicle State Service",
    description=(
        "Central-compute vehicle-state service "
        "for the miniature zonal SDV architecture"
    ),
    version="1.0.0"
)


@app.on_event("startup")
async def startup_event():

    asyncio.create_task(
        simulate_vehicle_state()
    )

    logger.info(
        "Continuous vehicle-state simulation started"
    )


@app.get("/")
def home():

    return {
        "service": "vehicle-state-service",
        "location": "central-compute",
        "status": "running"
    }


@app.get("/vehicle/status")
async def get_vehicle_status():

    start_time = time.perf_counter()

    vehicle_status_requests.add(1)

    logger.info(
        "Vehicle status request started"
    )

    diagnostics_url = (
        "http://diagnostics:8010/diagnostics/check"
    )

    try:

        async with httpx.AsyncClient(
            timeout=5.0
        ) as client:

            response = await client.get(
                diagnostics_url
            )

            response.raise_for_status()

            diagnostics_data = response.json()

        logger.info(
            "Diagnostics response received successfully"
        )

        return {
            "vehicle_id": vehicle_state[
                "vehicle_id"
            ],
            "speed_kmh": round(
                vehicle_state[
                    "speed_kmh"
                ],
                1
            ),
            "operating_mode": vehicle_state[
                "operating_mode"
            ],
            "diagnostics": diagnostics_data
        }

    except httpx.HTTPError as exc:

        logger.error(
            "Diagnostics Service unavailable: %s",
            exc
        )

        raise HTTPException(
            status_code=503,
            detail=(
                f"Diagnostics Service unavailable: {exc}"
            )
        )

    finally:

        duration_ms = (
            time.perf_counter()
            - start_time
        ) * 1000

        vehicle_status_duration.record(
            duration_ms
        )

        logger.info(
            "Vehicle status request completed in %.2f ms",
            duration_ms
        )


FastAPIInstrumentor.instrument_app(app)
HTTPXClientInstrumentor().instrument()
SystemMetricsInstrumentor().instrument()