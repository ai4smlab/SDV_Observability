# SDV Zonal Observability Testbed

A containerized miniature Software-Defined Vehicle (SDV) zonal testbed for hands-on experimentation with distributed service communication and end-to-end observability using Docker, OpenTelemetry, Prometheus, Tempo, Loki, and Grafana.

## Overview

The testbed implements a simplified zonal SDV architecture consisting of central-compute services, two zonal gateways, and two zonal sensor services.

A continuous synthetic workload exercises the distributed service path automatically, while synthetic vehicle and sensor states evolve over time. The six application services are instrumented with OpenTelemetry to generate metrics, distributed traces, and centralized logs.

The project is intended as a practical environment for understanding the technical workflow required before transferring the observability methodology to the DreamKit platform.

## Architecture

The logical application path is:

```text
Continuous Synthetic Workload Generator
                  |
                  v
            Vehicle State
                  |
                  v
             Diagnostics
              /       \
             v         v
     Zone Gateway A   Zone Gateway B
            |               |
            v               v
     Battery Sensor    Thermal Sensor
```

Diagnostics initiates the Zone A and Zone B requests concurrently.

### Application Services

| Service | Role |
|---|---|
| Vehicle State | Top-level vehicle-status service |
| Diagnostics | Coordinates retrieval of zonal information |
| Zone Gateway A | Gateway between central compute and Zone A |
| Zone Gateway B | Gateway between central compute and Zone B |
| Battery Sensor | Provides synthetic battery-state information |
| Thermal Sensor | Provides synthetic thermal-state information |

## Technology Stack

### Application

- Python
- FastAPI
- Uvicorn
- HTTPX
- HTTP/JSON service communication

### Containerization

- Docker
- Docker Compose
- Docker bridge networks

### Observability

- OpenTelemetry
- OpenTelemetry Collector
- Prometheus
- Grafana Tempo
- Grafana Loki
- Grafana

## Containerized Deployment

The complete environment contains 12 containers:

```text
6  Application services
1  Continuous workload generator
1  OpenTelemetry Collector
1  Tempo
1  Prometheus
1  Loki
1  Grafana
-----------------------------
12 Containers
```

Docker Compose defines and manages the complete environment through `compose.yaml`.

The locally developed application services and workload generator are built from local Dockerfiles. Published container images are used for the observability infrastructure.

## Networking

The application architecture uses three main Docker bridge networks:

```text
central-compute-net
zone-a-net
zone-b-net
```

Zone Gateway A participates in both `central-compute-net` and `zone-a-net`.

Zone Gateway B participates in both `central-compute-net` and `zone-b-net`.

This provides logical separation between central compute and the two zones while allowing the gateways to provide the required communication paths.

Application services communicate using HTTP and JSON. Docker Compose service names provide internal service discovery.

For example:

```text
http://diagnostics:8010/diagnostics/check
```

The Docker bridge networks provide virtual connectivity and logical isolation on the local development host. They are not intended to reproduce an automotive Ethernet network.

## Observability Architecture

All six application services are instrumented using OpenTelemetry.

The services generate three telemetry signals:

- Metrics
- Distributed traces
- Logs

Telemetry is exported to the OpenTelemetry Collector using OTLP.

The signal pipelines are:

```text
Traces:
Application Services
        |
        v
OpenTelemetry Collector
        |
        v
      Tempo
        |
        v
     Grafana
```

```text
Metrics:
Application Services
        |
        v
OpenTelemetry Collector
        |
        v
Prometheus Exporter
        ^
        | scrape
        |
   Prometheus
        |
        v
     Grafana
```

```text
Logs:
Application Services
        |
        v
OpenTelemetry Collector
        |
        v
       Loki
        |
        v
     Grafana
```

The OpenTelemetry Collector receives, processes, and routes telemetry. Tempo, Prometheus, and Loki provide the signal-specific backends, while Grafana provides visualization and exploration.

## Grafana Dashboard

The final dashboard contains eight panels:

1. Vehicle Speed
2. Battery State of Charge
3. Battery Temperature
4. Thermal Sensor Temperature
5. Vehicle State CPU Utilization
6. Vehicle State Memory Usage
7. Vehicle Status End-to-End Latency
8. Vehicle Status Request Rate

These panels provide representative views of physical state, software resource behaviour, workload, and application performance.

## Running the Testbed

### Prerequisites

- Docker Desktop
- Docker Compose

From the project root, validate the Compose configuration:

```bash
docker compose config
```

Build and start the environment:

```bash
docker compose up -d --build
```

Check container status:

```bash
docker compose ps
```

The Vehicle State API is available at:

```text
http://localhost:8000/vehicle/status
```

Grafana is available at:

```text
http://localhost:3000
```

To follow the continuous workload:

```bash
docker compose logs -f experiment-controller
```

To stop the environment:

```bash
docker compose down
```

## Project Structure

```text
sdv-zonal-observability/
|
|-- compose.yaml
|-- README.md
|-- .gitignore
|
|-- services/
|   |-- vehicle-state/
|   |-- diagnostics/
|   |-- zone-gateway-a/
|   |-- zone-gateway-b/
|   |-- battery-sensor/
|   `-- thermal-sensor/
|
|-- experiment-controller/
|   |-- controller.py
|   |-- requirements.txt
|   `-- Dockerfile
|
`-- observability/
    |-- otel-collector-config.yaml
    |-- prometheus.yml
    |-- tempo.yaml
    `-- loki.yaml
```

## Validation

The completed testbed has been validated at four levels:

- All 12 expected containers are operational.
- All eight Grafana dashboard panels receive current metric data.
- Tempo captures the complete six-service distributed request path.
- Loki receives centralized logs from all six application services.

## Scope and Limitations

This testbed is a simplified learning and observability environment. It is not intended to reproduce the complete software, networking, timing, or physical behaviour of a production SDV or the DreamKit platform.

The vehicle and sensor states are synthetic, and the Docker bridge networks provide logical network segmentation rather than automotive Ethernet emulation.

The causal root-cause-analysis experiments are not part of the current implementation.

## Transition to DreamKit

The next stage is to characterize the actual DreamKit platform before transferring the observability workflow.

This includes identifying:

- compute nodes and zones;
- services and processes;
- Ethernet topology;
- interfaces and communication protocols;
- service dependencies;
- existing metrics, traces, and logs;
- resource measurements; and
- contextual variables.

Based on this characterization, additional instrumentation and telemetry collection can be introduced where required. Context-aware causal root-cause-analysis experiments will follow after end-to-end observability has been established and validated on the target platform.

> **The objective is to transfer the observability methodology and technical understanding, not the implementation assumptions of the local testbed.**