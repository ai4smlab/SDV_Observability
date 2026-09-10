import asyncio
import httpx
import time
from datetime import datetime, timezone


VEHICLE_STATE_URL = "http://vehicle-state:8000/vehicle/status"

REQUEST_INTERVAL_SECONDS = 2.0


def utc_now():
    return datetime.now(
        timezone.utc
    ).isoformat()


async def run_workload():

    request_number = 0

    print("=" * 65)
    print("SDV Continuous Workload Generator")
    print(
        f"Request interval: "
        f"{REQUEST_INTERVAL_SECONDS} seconds"
    )
    print("=" * 65)

    async with httpx.AsyncClient(
        timeout=10.0
    ) as client:

        while True:

            request_number += 1
            start_time = time.perf_counter()

            try:

                response = await client.get(
                    VEHICLE_STATE_URL
                )

                response.raise_for_status()

                duration_ms = (
                    time.perf_counter()
                    - start_time
                ) * 1000

                data = response.json()

                print(
                    f"[{utc_now()}] "
                    f"request={request_number} "
                    f"status={response.status_code} "
                    f"duration_ms={duration_ms:.2f} "
                    f"speed_kmh={data.get('speed_kmh')}"
                )

            except httpx.HTTPError as exc:

                duration_ms = (
                    time.perf_counter()
                    - start_time
                ) * 1000

                print(
                    f"[{utc_now()}] "
                    f"request={request_number} "
                    f"status=ERROR "
                    f"duration_ms={duration_ms:.2f} "
                    f"error={exc}"
                )

            await asyncio.sleep(
                REQUEST_INTERVAL_SECONDS
            )


if __name__ == "__main__":
    asyncio.run(
        run_workload()
    )