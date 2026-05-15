"""Regression tests for session reuse and transparent re-login on expiry.

These cover the behaviour change introduced when we replaced the manual
SimpleCookie / Cookie-header workaround with a real aiohttp CookieJar
configured with ``quote_cookie=False``:

* A single ``login()`` should suffice for many subsequent data calls.
* If the server bounces a data request back to the login page (because
  the cached session expired), the client should transparently re-login
  once and retry without the caller having to know.
"""

import os
import pytest
from aioresponses import aioresponses

from pyomnisense.omnisense import (
    Omnisense,
    LOGIN_URL,
    SITE_LIST_URL,
    SENSOR_LIST_URL,
    HOST_URL,
)


SAMPLES_DIR = os.path.join(os.path.dirname(__file__), "samples")


def _load_sample(name: str) -> str:
    with open(os.path.join(SAMPLES_DIR, name), "r", encoding="utf-8") as f:
        return f.read()


def _mock_successful_login(m: aioresponses, set_cookie: str = "ASP.NET_SessionId=abc123; Path=/; HttpOnly") -> None:
    """Register a POST /user_login.asp + GET /site_select.asp pair that
    together represent one successful login round-trip."""
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


@pytest.mark.offline
@pytest.mark.asyncio
async def test_session_is_reused_across_calls():
    """Two data calls after one login must not trigger a second login.

    If the implementation accidentally re-logs in, the second POST to
    LOGIN_URL would have no registered response and aioresponses would
    raise, failing the test.
    """
    site_html = _load_sample("site_list.html")
    sensors_html = _load_sample("sensor_123456.html")

    with aioresponses() as m:
        _mock_successful_login(m)
        # One registration each: if the client tries to fetch them twice
        # (or, worse, re-login between them), aioresponses will fail.
        m.get(SITE_LIST_URL, status=200, body=site_html)
        m.get(f"{SENSOR_LIST_URL}?siteNbr=123456", status=200, body=sensors_html)

        omnisense = Omnisense()
        assert await omnisense.login("user", "pass") is True

        sites = await omnisense.get_site_list()
        assert sites == {"123456": "MySite", "654321": "FirstSite"}

        sensors = await omnisense.get_sensor_data("123456")
        assert "2A000001" in sensors
        assert sensors["2A000001"]["site_name"] == "MySite"

        await omnisense.close()


@pytest.mark.offline
@pytest.mark.asyncio
async def test_relogin_on_session_expiry():
    """If a data fetch lands on the login page, the client must re-login
    once and retry transparently."""
    site_html = _load_sample("site_list.html")

    with aioresponses() as m:
        _mock_successful_login(m)

        # First GET of the site list "expires": server redirects to the
        # login page and aiohttp follows the redirect (default behaviour).
        m.get(
            SITE_LIST_URL,
            status=302,
            headers={"Location": "/user_login.asp"},
        )
        m.get(
            f"{HOST_URL}/user_login.asp",
            status=200,
            body="<html><form>login form here</form></html>",
        )

        # Transparent re-login: another POST + dashboard GET pair.
        _mock_successful_login(m, set_cookie="ASP.NET_SessionId=def456; Path=/; HttpOnly")

        # Retry of the original data call now succeeds.
        m.get(SITE_LIST_URL, status=200, body=site_html)

        omnisense = Omnisense()
        assert await omnisense.login("user", "pass") is True

        sites = await omnisense.get_site_list()
        assert sites == {"123456": "MySite", "654321": "FirstSite"}

        await omnisense.close()


@pytest.mark.offline
@pytest.mark.asyncio
async def test_login_replaces_credentials_atomically():
    """Passing only one of username/password must be a hard error, not
    a silent partial update that re-uses cached credentials of the
    *other* user."""
    omnisense = Omnisense()
    with pytest.raises(Exception):
        await omnisense.login("alice", None)
    with pytest.raises(Exception):
        await omnisense.login(None, "secret")
    await omnisense.close()


@pytest.mark.offline
@pytest.mark.asyncio
async def test_relogin_closes_old_session():
    """Calling login() twice must not leak the first ClientSession."""
    with aioresponses() as m:
        _mock_successful_login(m)
        _mock_successful_login(m, set_cookie="ASP.NET_SessionId=def456; Path=/; HttpOnly")

        omnisense = Omnisense()
        assert await omnisense.login("user", "pass") is True
        first_session = omnisense._session
        assert first_session is not None and not first_session.closed

        assert await omnisense.login("user", "pass") is True
        second_session = omnisense._session
        assert second_session is not None and not second_session.closed
        assert second_session is not first_session
        assert first_session.closed, "previous session was leaked across re-login"

        await omnisense.close()
