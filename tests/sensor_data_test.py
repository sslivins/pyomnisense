"""Tests for ``Omnisense.get_sensor_data``.

Each test sets up the *minimum* extra mocks it needs on top of the
``logged_in`` fixture (which already supplied a working login), invokes
``get_sensor_data`` with the variation under test, and asserts on the
expected projection of ``ALL_SENSORS``.
"""

from datetime import datetime, timezone

import pytest

from pyomnisense.omnisense import SITE_LIST_URL


def _ts(s: str) -> datetime:
    """Helper: parse an ``YY-MM-DD HH:MM:SS`` string as the same UTC
    timestamp ``Omnisense.get_sensor_data`` will produce."""
    return datetime.strptime(s, "%y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)


# Canonical "everything" result, computed by parsing the two sample
# sensor_*.html files. Individual tests slice this dict to express the
# expected result of filtering by site or sensor.
ALL_SENSORS = {
    "2A000001": {"description": "Dining Room",         "last_activity": _ts("24-12-30 10:57:44"), "status": "A", "temperature": 25.1, "relative_humidity": 39.0, "absolute_humidity": 7.7, "dew_point": 10.2, "wood_pct": 7.2,  "battery_voltage": 3.4, "sensor_type": "S-11",  "sensor_id": "2A000001", "site_name": "MySite"},
    "2A000002": {"description": "Basement",            "last_activity": _ts("24-12-30 10:59:04"), "status": "A", "temperature": 29.2, "relative_humidity": 30.4, "absolute_humidity": 7.7, "dew_point": 10.1, "wood_pct": 6.9,  "battery_voltage": 3.4, "sensor_type": "S-11",  "sensor_id": "2A000002", "site_name": "MySite"},
    "2A000003": {"description": "Gateway",             "last_activity": _ts("24-12-22 10:55:33"), "status": "A", "temperature": 11.8, "relative_humidity": 78.4, "absolute_humidity": 6.8, "dew_point": 8.3,  "wood_pct": 13.0, "battery_voltage": 3.1, "sensor_type": "S-11",  "sensor_id": "2A000003", "site_name": "MySite"},
    "2A000004": {"description": "Kitchen",             "last_activity": _ts("24-12-30 10:59:40"), "status": "A", "temperature": 24.7, "relative_humidity": 42.1, "absolute_humidity": 8.2, "dew_point": 11.0, "wood_pct": 7.8,  "battery_voltage": 3.4, "sensor_type": "S-11",  "sensor_id": "2A000004", "site_name": "MySite"},
    "2A000005": {"description": "Laundry Room",        "last_activity": _ts("24-12-22 10:51:17"), "status": "A", "temperature": 14.4, "relative_humidity": 63.6, "absolute_humidity": 6.5, "dew_point": 7.6,  "wood_pct": 13.2, "battery_voltage": 3.2, "sensor_type": "S-11",  "sensor_id": "2A000005", "site_name": "MySite"},
    "6BC00000": {"description": "<description not set>", "last_activity": _ts("24-12-30 10:59:28"), "status": "A", "temperature": 0.0,  "relative_humidity": 26.0, "absolute_humidity": 0.0, "dew_point": 60.0, "wood_pct": 11.0, "battery_voltage": 0.0, "sensor_type": "S-100", "sensor_id": "6BC00000", "site_name": "MySite"},
    "2A001001": {"description": "Dining Room",         "last_activity": _ts("24-12-30 10:57:44"), "status": "A", "temperature": 25.1, "relative_humidity": 39.0, "absolute_humidity": 7.7, "dew_point": 10.2, "wood_pct": 7.2,  "battery_voltage": 3.4, "sensor_type": "S-11",  "sensor_id": "2A001001", "site_name": "FirstSite"},
    "2A001002": {"description": "Basement",            "last_activity": _ts("24-12-30 10:59:04"), "status": "A", "temperature": 29.2, "relative_humidity": 30.4, "absolute_humidity": 7.7, "dew_point": 10.1, "wood_pct": 6.9,  "battery_voltage": 3.4, "sensor_type": "S-11",  "sensor_id": "2A001002", "site_name": "FirstSite"},
    "2A001003": {"description": "Gateway",             "last_activity": _ts("24-12-22 10:55:33"), "status": "A", "temperature": 11.8, "relative_humidity": 78.4, "absolute_humidity": 6.8, "dew_point": 8.3,  "wood_pct": 13.0, "battery_voltage": 3.1, "sensor_type": "S-11",  "sensor_id": "2A001003", "site_name": "FirstSite"},
    "2A001004": {"description": "Kitchen",             "last_activity": _ts("24-12-30 10:59:40"), "status": "A", "temperature": 24.7, "relative_humidity": 42.1, "absolute_humidity": 8.2, "dew_point": 11.0, "wood_pct": 7.8,  "battery_voltage": 3.4, "sensor_type": "S-11",  "sensor_id": "2A001004", "site_name": "FirstSite"},
    "2A001005": {"description": "Laundry Room",        "last_activity": _ts("24-12-22 10:51:17"), "status": "A", "temperature": 14.4, "relative_humidity": 63.6, "absolute_humidity": 6.5, "dew_point": 7.6,  "wood_pct": 13.2, "battery_voltage": 3.2, "sensor_type": "S-11",  "sensor_id": "2A001005", "site_name": "FirstSite"},
}

SITE_123456_IDS = {sid for sid, info in ALL_SENSORS.items() if info["site_name"] == "MySite"}
SITE_654321_IDS = {sid for sid, info in ALL_SENSORS.items() if info["site_name"] == "FirstSite"}


def _subset(*sensor_ids):
    return {sid: ALL_SENSORS[sid] for sid in sensor_ids}


@pytest.mark.offline
@pytest.mark.asyncio
async def test_no_args_returns_all_sensors_across_all_sites(
    logged_in, sample_site_html, all_sensors_html, register_sensors
):
    omnisense, m = logged_in
    m.get(SITE_LIST_URL, status=200, body=sample_site_html)
    register_sensors(m, all_sensors_html)

    assert await omnisense.get_sensor_data() == ALL_SENSORS


@pytest.mark.offline
@pytest.mark.asyncio
async def test_pass_site_id_dict(
    logged_in, sample_site_html, all_sensors_html, register_sensors
):
    omnisense, m = logged_in
    m.get(SITE_LIST_URL, status=200, body=sample_site_html)
    register_sensors(m, all_sensors_html)

    site_ids = await omnisense.get_site_list()
    assert await omnisense.get_sensor_data(site_ids) == ALL_SENSORS


@pytest.mark.offline
@pytest.mark.asyncio
async def test_pass_site_id_list(
    logged_in, sample_site_html, all_sensors_html, register_sensors
):
    omnisense, m = logged_in
    m.get(SITE_LIST_URL, status=200, body=sample_site_html)
    register_sensors(m, all_sensors_html)

    site_ids = await omnisense.get_site_list()
    assert await omnisense.get_sensor_data(list(site_ids.keys())) == ALL_SENSORS


@pytest.mark.offline
@pytest.mark.asyncio
async def test_pass_single_site_id_string(
    logged_in, all_sensors_html, register_sensors
):
    omnisense, m = logged_in
    register_sensors(m, {"123456": all_sensors_html["123456"]})

    result = await omnisense.get_sensor_data("123456")
    assert result == _subset(*SITE_123456_IDS)


@pytest.mark.offline
@pytest.mark.asyncio
async def test_single_sensor_id_filter(
    logged_in, sample_site_html, all_sensors_html, register_sensors
):
    omnisense, m = logged_in
    m.get(SITE_LIST_URL, status=200, body=sample_site_html)
    register_sensors(m, {"123456": all_sensors_html["123456"]})

    result = await omnisense.get_sensor_data(sensor_ids="2A000005")
    assert result == _subset("2A000005")


@pytest.mark.offline
@pytest.mark.asyncio
async def test_sensor_id_list_single_site(
    logged_in, sample_site_html, all_sensors_html, register_sensors
):
    omnisense, m = logged_in
    m.get(SITE_LIST_URL, status=200, body=sample_site_html)
    register_sensors(m, {"123456": all_sensors_html["123456"]})

    result = await omnisense.get_sensor_data(
        sensor_ids=["2A000001", "2A000003", "2A000005", "6BC00000"]
    )
    assert result == _subset("2A000001", "2A000003", "2A000005", "6BC00000")


@pytest.mark.offline
@pytest.mark.asyncio
async def test_sensor_id_list_multiple_sites(
    logged_in, sample_site_html, all_sensors_html, register_sensors
):
    omnisense, m = logged_in
    m.get(SITE_LIST_URL, status=200, body=sample_site_html)
    register_sensors(m, all_sensors_html)

    result = await omnisense.get_sensor_data(
        sensor_ids=["2A000002", "2A000003", "2A001002", "2A001005"]
    )
    assert result == _subset("2A000002", "2A000003", "2A001002", "2A001005")


@pytest.mark.offline
@pytest.mark.asyncio
async def test_sensor_id_list_with_some_unknown_ids(
    logged_in, sample_site_html, all_sensors_html, register_sensors
):
    omnisense, m = logged_in
    m.get(SITE_LIST_URL, status=200, body=sample_site_html)
    register_sensors(m, all_sensors_html)

    result = await omnisense.get_sensor_data(
        sensor_ids=["2A000002", "2A008003", "2A008002", "2A001005"]
    )
    assert result == _subset("2A000002", "2A001005")


@pytest.mark.offline
@pytest.mark.asyncio
async def test_specific_site_and_sensor_id(
    logged_in, all_sensors_html, register_sensors
):
    omnisense, m = logged_in
    register_sensors(m, {"123456": all_sensors_html["123456"]})

    result = await omnisense.get_sensor_data("123456", "2A000002")
    assert result == _subset("2A000002")


@pytest.mark.offline
@pytest.mark.asyncio
async def test_all_unknown_sensor_ids_returns_empty(
    logged_in, sample_site_html, all_sensors_html, register_sensors
):
    omnisense, m = logged_in
    m.get(SITE_LIST_URL, status=200, body=sample_site_html)
    register_sensors(m, all_sensors_html)

    result = await omnisense.get_sensor_data(
        sensor_ids=["DEADBEEF", "CAFEBABE"]
    )
    assert result == {}
