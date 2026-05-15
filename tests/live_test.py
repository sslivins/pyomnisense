"""End-to-end test against the real omnisense.com service.

Skipped unless ``OMNISENSE_USERNAME`` / ``OMNISENSE_PASSWORD`` are set
(typically loaded from a ``.env`` file or supplied by the CI job).

The assertions deliberately avoid account-specific values so that any
collaborator with valid Omnisense credentials can run this test against
*their* account and have it pass.
"""

import os
from datetime import datetime

import pytest
from dotenv import load_dotenv

from pyomnisense import Omnisense

load_dotenv()


EXPECTED_SENSOR_KEYS = {
    "description",
    "last_activity",
    "status",
    "temperature",
    "relative_humidity",
    "absolute_humidity",
    "dew_point",
    "wood_pct",
    "battery_voltage",
    "sensor_type",
    "sensor_id",
    "site_name",
}

NUMERIC_KEYS = {
    "temperature",
    "relative_humidity",
    "absolute_humidity",
    "dew_point",
    "wood_pct",
    "battery_voltage",
}


@pytest.mark.live
@pytest.mark.skipif(
    not os.getenv("OMNISENSE_USERNAME") or not os.getenv("OMNISENSE_PASSWORD"),
    reason="OMNISENSE_USERNAME or OMNISENSE_PASSWORD environment variable not set",
)
@pytest.mark.asyncio
async def test_live_login_and_fetch_data():
    username = os.environ["OMNISENSE_USERNAME"]
    password = os.environ["OMNISENSE_PASSWORD"]

    async with Omnisense() as omnisense:
        assert await omnisense.login(username, password) is True, "Login failed"

        sites = await omnisense.get_site_list()
        assert isinstance(sites, dict)
        assert sites, "Account should have at least one site"

        sensor_data = await omnisense.get_sensor_data()
        assert isinstance(sensor_data, dict)
        assert sensor_data, "Account should have at least one sensor"

        for sensor_id, reading in sensor_data.items():
            assert sensor_id, "sensor_id must be non-empty"
            assert set(reading.keys()) == EXPECTED_SENSOR_KEYS, (
                f"sensor {sensor_id} has unexpected key set: "
                f"{set(reading.keys()) ^ EXPECTED_SENSOR_KEYS}"
            )

            for key in NUMERIC_KEYS:
                value = reading[key]
                assert value is None or isinstance(value, float), (
                    f"sensor {sensor_id} field {key!r} should be Optional[float], "
                    f"got {type(value).__name__}: {value!r}"
                )

            last_activity = reading["last_activity"]
            assert last_activity is None or isinstance(last_activity, datetime), (
                f"sensor {sensor_id} last_activity should be Optional[datetime], "
                f"got {type(last_activity).__name__}: {last_activity!r}"
            )
            if last_activity is not None:
                assert last_activity.tzinfo is not None, (
                    f"sensor {sensor_id} last_activity must be tz-aware"
                )
