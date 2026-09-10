from fastapi import FastAPI
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

from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.instrumentation.system_metrics import SystemMetricsInstrumentor

from opentelemetry._logs import set_logger_provider
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter


# -------------------------------------------------
# OpenTelemetry resource
# -------------------------------------------------

resource = Resource.create({
    "service.name": "battery-sensor-service"
})


# -------------------------------------------------
# Tracing
# -------------------------------------------------

tracer_provider = TracerProvider(
    resource=resource
)

trace.set_tracer_provider(
    tracer_provider
)

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

metrics.set_meter_provider(
    meter_provider
)

meter = metrics.get_meter(
    "battery-sensor-service"
)


# -------------------------------------------------
# Logging
# -------------------------------------------------

logger_provider = LoggerProvider(
    resource=resource
)

set_logger_provider(
    logger_provider
)

logger_provider.add_log_record_processor(
    BatchLogRecordProcessor(
        OTLPLogExporter(
            endpoint="http://otel-collector:4317",
            insecure=True
        )
    )
)

logger = logging.getLogger(
    "battery-sensor-service"
)

logger.setLevel(
    logging.INFO
)

logger.addHandler(
    LoggingHandler(
        level=logging.INFO,
        logger_provider=logger_provider
    )
)

logger.propagate = False


# -------------------------------------------------
# Simulated battery state
# -------------------------------------------------

battery_state = {
    "state_of_charge_percent": 85.0,
    "temperature_c": 31.0,
    "voltage_v": 402.5,
    "operating_mode": "driving",
    "charging_state": "not_charging"
}

simulation_start = time.monotonic()


# -------------------------------------------------
# Custom metrics
# -------------------------------------------------

battery_requests = meter.create_counter(
    "battery_requests",
    description="Number of battery data requests",
    unit="1"
)

battery_duration = meter.create_histogram(
    "battery_duration",
    description="Duration of battery data requests",
    unit="ms"
)


def observe_battery_soc(options):

    yield metrics.Observation(
        battery_state[
            "state_of_charge_percent"
        ]
    )


def observe_battery_temperature(options):

    yield metrics.Observation(
        battery_state[
            "temperature_c"
        ]
    )


def observe_battery_voltage(options):

    yield metrics.Observation(
        battery_state[
            "voltage_v"
        ]
    )


meter.create_observable_gauge(
    "battery_state_of_charge_percent",
    callbacks=[observe_battery_soc],
    description=(
        "Current simulated battery "
        "state of charge"
    ),
    unit="%"
)

meter.create_observable_gauge(
    "battery_temperature_c",
    callbacks=[
        observe_battery_temperature
    ],
    description=(
        "Current simulated battery temperature"
    ),
    unit="Cel"
)

meter.create_observable_gauge(
    "battery_voltage_v",
    callbacks=[observe_battery_voltage],
    description=(
        "Current simulated battery voltage"
    ),
    unit="V"
)


# -------------------------------------------------
# Synthetic 30-minute battery cycle
#
# 0-25 min:
#   operating_mode = driving
#   charging_state = not_charging
#
# 25-27 min:
#   operating_mode = idle
#   charging_state = not_charging
#
# 27-30 min:
#   operating_mode = idle
#   charging_state = charging
# -------------------------------------------------

def determine_battery_states():

    elapsed_seconds = (
        time.monotonic() - simulation_start
    )

    cycle_position = (
        elapsed_seconds % 1800
    )

    if cycle_position < 1500:

        return (
            "driving",
            "not_charging"
        )

    if cycle_position < 1620:

        return (
            "idle",
            "not_charging"
        )

    return (
        "idle",
        "charging"
    )


async def simulate_battery_state():

    previous_operating_mode = None
    previous_charging_state = None

    while True:

        (
            operating_mode,
            charging_state
        ) = determine_battery_states()

        battery_state[
            "operating_mode"
        ] = operating_mode

        battery_state[
            "charging_state"
        ] = charging_state

        if (
            operating_mode
            != previous_operating_mode
        ):

            logger.info(
                "Battery operating mode changed to %s",
                operating_mode
            )

            previous_operating_mode = (
                operating_mode
            )

        if (
            charging_state
            != previous_charging_state
        ):

            logger.info(
                "Battery charging state changed to %s",
                charging_state
            )

            previous_charging_state = (
                charging_state
            )

        if operating_mode == "driving":

            # Synthetic accelerated discharge.
            # Approximate expected discharge:
            # ~0.04 percentage points every 5 s.
            battery_state[
                "state_of_charge_percent"
            ] -= random.uniform(
                0.03,
                0.05
            )

            battery_state[
                "temperature_c"
            ] += random.uniform(
                -0.04,
                0.08
            )

        elif (
            operating_mode == "idle"
            and charging_state
            == "not_charging"
        ):

            # Very small auxiliary consumption.
            battery_state[
                "state_of_charge_percent"
            ] -= random.uniform(
                0.0,
                0.003
            )

            # Slowly cool while stationary.
            if (
                battery_state[
                    "temperature_c"
                ] > 30.0
            ):

                battery_state[
                    "temperature_c"
                ] -= random.uniform(
                    0.0,
                    0.04
                )

        elif charging_state == "charging":

            # Synthetic accelerated charging.
            # Chosen so the short charging phase can
            # approximately replenish the demo-cycle
            # discharge.
            battery_state[
                "state_of_charge_percent"
            ] += random.uniform(
                0.45,
                0.55
            )

            battery_state[
                "temperature_c"
            ] += random.uniform(
                -0.02,
                0.06
            )

        battery_state[
            "state_of_charge_percent"
        ] = max(
            0.0,
            min(
                battery_state[
                    "state_of_charge_percent"
                ],
                100.0
            )
        )

        battery_state[
            "temperature_c"
        ] = max(
            25.0,
            min(
                battery_state[
                    "temperature_c"
                ],
                45.0
            )
        )

        # Simplified voltage-SOC relationship.
        battery_state[
            "voltage_v"
        ] = (
            360.0
            + (
                battery_state[
                    "state_of_charge_percent"
                ] / 100.0
            ) * 50.0
            + random.uniform(
                -0.25,
                0.25
            )
        )

        await asyncio.sleep(5)


# -------------------------------------------------
# FastAPI application
# -------------------------------------------------

app = FastAPI(
    title="Battery Sensor Service",
    description=(
        "Simulated battery end-node service "
        "for Zone A"
    ),
    version="1.0.0"
)


@app.on_event("startup")
async def startup_event():

    asyncio.create_task(
        simulate_battery_state()
    )

    logger.info(
        "Continuous battery-state simulation started"
    )


@app.get("/")
def home():

    return {
        "service": "battery-sensor-service",
        "zone": "A",
        "status": "running"
    }


@app.get("/battery/data")
def get_battery_data():

    start_time = time.perf_counter()

    battery_requests.add(1)

    logger.info(
        "Battery data request started"
    )

    try:

        soc = battery_state[
            "state_of_charge_percent"
        ]

        temperature = battery_state[
            "temperature_c"
        ]

        voltage = battery_state[
            "voltage_v"
        ]

        operating_mode = battery_state[
            "operating_mode"
        ]

        charging_state = battery_state[
            "charging_state"
        ]

        status = (
            "warning"
            if (
                temperature >= 45
                or soc < 20
            )
            else "healthy"
        )

        logger.info(
            "Battery state observed: "
            "SOC=%.2f%% "
            "temperature=%.2f C "
            "voltage=%.2f V "
            "operating_mode=%s "
            "charging_state=%s "
            "status=%s",
            soc,
            temperature,
            voltage,
            operating_mode,
            charging_state,
            status
        )

        return {
            "sensor_id": "BAT-ZA-001",
            "zone": "A",
            "state_of_charge_percent": round(
                soc,
                2
            ),
            "temperature_c": round(
                temperature,
                2
            ),
            "voltage_v": round(
                voltage,
                2
            ),
            "operating_mode": operating_mode,
            "charging_state": charging_state,
            "status": status
        }

    finally:

        duration_ms = (
            time.perf_counter()
            - start_time
        ) * 1000

        battery_duration.record(
            duration_ms
        )

        logger.info(
            "Battery data request completed in %.2f ms",
            duration_ms
        )


FastAPIInstrumentor.instrument_app(
    app
)

SystemMetricsInstrumentor().instrument()