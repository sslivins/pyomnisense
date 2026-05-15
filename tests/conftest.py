"""Shared pytest fixtures for the offline test suite.

Before this conftest existed, every test re-stamped ~30 lines of
``aioresponses`` setup (login POST + dashboard GET + sample HTML loads).
The fixtures below let each test focus on its actual subject - the call
under test and the expected result.
"""

import os
from typing import Dict

import pytest
from aioresponses import aioresponses

from pyomnisense.omnisense import (
    HOST_URL,
    LOGIN_URL,
    SENSOR_LIST_URL,
    SITE_LIST_URL,
    Omnisense,
)


SAMPLES_DIR = os.path.join(os.path.dirname(__file__), "samples")


def _load_sample(name: str) -> str:
    with open(os.path.join(SAMPLES_DIR, name), encoding="utf-8") as f:
        return f.read()


@pytest.fixture
def sample_site_html() -> str:
    return _load_sample("site_list.html")


@pytest.fixture
def sample_sensors_123456() -> str:
    return _load_sample("sensor_123456.html")


@pytest.fixture
def sample_sensors_654321() -> str:
    return _load_sample("sensor_654321.html")


@pytest.fixture
def all_sensors_html(sample_sensors_123456, sample_sensors_654321) -> Dict[str, str]:
    """``{site_id: sensor_list_html}`` for both sample sites."""
    return {
        "123456": sample_sensors_123456,
        "654321": sample_sensors_654321,
    }


@pytest.fixture
def register_login():
    """Returns a helper that registers one successful login round-trip
    (POST /user_login.asp -> 302, GET /site_select.asp -> dashboard) on a
    given ``aioresponses`` mock."""

    def _register(
        m: aioresponses,
        set_cookie: str = "ASP.NET_SessionId=abc123; Path=/; HttpOnly",
    ) -> None:
        m.post(
            LOGIN_URL,
            status=302,
            headers={"Set-Cookie": set_cookie, "Location": "/site_select.asp"},
            body="",
        )
        m.get(
            f"{HOST_URL}/site_select.asp",
            status=200,
            body="Welcome to your dashboard",
        )

    return _register


@pytest.fixture
def register_sensors():
    """Returns a helper that registers the per-site sensor-list endpoints
    on a given ``aioresponses`` mock for each ``{site_id: html}`` entry."""

    def _register(m: aioresponses, html_by_site_id: Dict[str, str]) -> None:
        for site_id, html in html_by_site_id.items():
            m.get(
                f"{SENSOR_LIST_URL}?siteNbr={site_id}",
                status=200,
                body=html,
            )

    return _register


@pytest.fixture
async def logged_in(register_login):
    """Yields ``(omnisense, mock)`` with login already done.

    The caller can keep registering additional GET endpoints on ``mock``
    before invoking data methods on ``omnisense``. Session is closed on
    teardown.
    """
    with aioresponses() as m:
        register_login(m)
        omnisense = Omnisense()
        assert await omnisense.login("testuser", "testpass") is True
        try:
            yield omnisense, m
        finally:
            await omnisense.close()
