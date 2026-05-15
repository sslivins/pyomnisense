"""Tests for ``Omnisense.get_site_sensor_list`` (the projection helper)."""

import pytest

from pyomnisense.omnisense import SITE_LIST_URL


# Canonical projection result for all sites - description / sensor_type /
# site_name only.
ALL_PROJECTED = {
    "2A000001": {"description": "Dining Room",         "sensor_type": "S-11",  "site_name": "MySite"},
    "2A000002": {"description": "Basement",            "sensor_type": "S-11",  "site_name": "MySite"},
    "2A000003": {"description": "Gateway",             "sensor_type": "S-11",  "site_name": "MySite"},
    "2A000004": {"description": "Kitchen",             "sensor_type": "S-11",  "site_name": "MySite"},
    "2A000005": {"description": "Laundry Room",        "sensor_type": "S-11",  "site_name": "MySite"},
    "6BC00000": {"description": "<description not set>", "sensor_type": "S-100", "site_name": "MySite"},
    "2A001001": {"description": "Dining Room",         "sensor_type": "S-11",  "site_name": "FirstSite"},
    "2A001002": {"description": "Basement",            "sensor_type": "S-11",  "site_name": "FirstSite"},
    "2A001003": {"description": "Gateway",             "sensor_type": "S-11",  "site_name": "FirstSite"},
    "2A001004": {"description": "Kitchen",             "sensor_type": "S-11",  "site_name": "FirstSite"},
    "2A001005": {"description": "Laundry Room",        "sensor_type": "S-11",  "site_name": "FirstSite"},
}

SITE_123456_IDS = {sid for sid, info in ALL_PROJECTED.items() if info["site_name"] == "MySite"}


@pytest.mark.offline
@pytest.mark.asyncio
async def test_no_args_returns_projection_for_all_sites(
    logged_in, sample_site_html, all_sensors_html, register_sensors
):
    omnisense, m = logged_in
    m.get(SITE_LIST_URL, status=200, body=sample_site_html)
    register_sensors(m, all_sensors_html)

    assert await omnisense.get_site_sensor_list() == ALL_PROJECTED


@pytest.mark.offline
@pytest.mark.asyncio
async def test_pass_site_id_dict(
    logged_in, sample_site_html, all_sensors_html, register_sensors
):
    omnisense, m = logged_in
    m.get(SITE_LIST_URL, status=200, body=sample_site_html)
    register_sensors(m, all_sensors_html)

    site_ids = await omnisense.get_site_list()
    assert await omnisense.get_site_sensor_list(site_ids) == ALL_PROJECTED


@pytest.mark.offline
@pytest.mark.asyncio
async def test_pass_site_id_list(
    logged_in, sample_site_html, all_sensors_html, register_sensors
):
    omnisense, m = logged_in
    m.get(SITE_LIST_URL, status=200, body=sample_site_html)
    register_sensors(m, all_sensors_html)

    site_ids = await omnisense.get_site_list()
    result = await omnisense.get_site_sensor_list(list(site_ids.keys()))
    assert result == ALL_PROJECTED


@pytest.mark.offline
@pytest.mark.asyncio
async def test_pass_single_site_id_string(
    logged_in, all_sensors_html, register_sensors
):
    omnisense, m = logged_in
    register_sensors(m, {"123456": all_sensors_html["123456"]})

    result = await omnisense.get_site_sensor_list("123456")
    assert result == {sid: ALL_PROJECTED[sid] for sid in SITE_123456_IDS}
