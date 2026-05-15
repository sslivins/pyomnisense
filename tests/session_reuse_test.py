"""Regression tests for session reuse and transparent re-login on expiry.

These cover the behaviour change introduced when we replaced the manual
SimpleCookie / Cookie-header workaround with a real aiohttp CookieJar
configured with ``quote_cookie=False``:

* A single ``login()`` should suffice for many subsequent data calls.
* If the server bounces a data request back to the login page (because
  the cached session expired), the client should transparently re-login
  once and retry without the caller having to know.
* If the *retry* also lands on the login page, the failure must
  propagate as ``OmnisenseAuthError`` instead of silently returning
  empty data.
* Cookie values with ``=`` / ``+`` characters (omnisense.com is a
  Classic ASP site that emits them) must round-trip verbatim on the
  next request - aiohttp's default cookie jar percent-encodes them and
  breaks the session.
"""

import pytest
from aioresponses import aioresponses
from yarl import URL

import aiohttp

from pyomnisense.omnisense import (
    HOST_URL,
    LOGIN_URL,
    SENSOR_LIST_URL,
    SITE_LIST_URL,
    Omnisense,
    OmnisenseAuthError,
)


@pytest.mark.offline
@pytest.mark.asyncio
async def test_session_is_reused_across_calls(
    logged_in, sample_site_html, sample_sensors_123456
):
    """Two data calls after one login must not trigger a second login.

    The ``logged_in`` fixture registers exactly ONE login round-trip; if
    the client tries to log in again, the second POST to LOGIN_URL has
    no mock and aioresponses will raise.
    """
    omnisense, m = logged_in
    m.get(SITE_LIST_URL, status=200, body=sample_site_html)
    m.get(f"{SENSOR_LIST_URL}?siteNbr=123456", status=200, body=sample_sensors_123456)

    sites = await omnisense.get_site_list()
    assert sites == {"123456": "MySite", "654321": "FirstSite"}

    sensors = await omnisense.get_sensor_data("123456")
    assert "2A000001" in sensors
    assert sensors["2A000001"]["site_name"] == "MySite"


@pytest.mark.offline
@pytest.mark.asyncio
async def test_relogin_on_session_expiry(
    logged_in, register_login, sample_site_html
):
    """If a data fetch lands on the login page, the client must re-login
    once and retry transparently."""
    omnisense, m = logged_in

    # First GET of the site list "expires": server 302s to the login
    # page and aiohttp follows the redirect (default behaviour).
    m.get(SITE_LIST_URL, status=302, headers={"Location": "/user_login.asp"})
    m.get(
        f"{HOST_URL}/user_login.asp",
        status=200,
        body="<html><form>login form here</form></html>",
    )

    # Transparent re-login: another POST + dashboard GET pair.
    register_login(m, set_cookie="ASP.NET_SessionId=def456; Path=/; HttpOnly")

    # Retry of the original data call now succeeds.
    m.get(SITE_LIST_URL, status=200, body=sample_site_html)

    sites = await omnisense.get_site_list()
    assert sites == {"123456": "MySite", "654321": "FirstSite"}


@pytest.mark.offline
@pytest.mark.asyncio
async def test_login_rejects_partial_credentials():
    """Passing only one of username/password must be a hard error, not
    a silent partial update that re-uses cached credentials of the
    *other* user."""
    omnisense = Omnisense()
    with pytest.raises(OmnisenseAuthError):
        await omnisense.login("alice", None)
    with pytest.raises(OmnisenseAuthError):
        await omnisense.login(None, "secret")
    await omnisense.close()


@pytest.mark.offline
@pytest.mark.asyncio
async def test_relogin_closes_old_session(register_login):
    """Calling login() twice must not leak the first ClientSession."""
    with aioresponses() as m:
        register_login(m)
        register_login(m, set_cookie="ASP.NET_SessionId=def456; Path=/; HttpOnly")

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


@pytest.mark.offline
@pytest.mark.asyncio
async def test_context_manager_closes_session(register_login):
    """``async with Omnisense()`` should close the session on exit."""
    with aioresponses() as m:
        register_login(m)

        async with Omnisense() as omnisense:
            assert await omnisense.login("user", "pass") is True
            session = omnisense._session
            assert session is not None and not session.closed

        assert omnisense._session is None
        assert session.closed


@pytest.mark.offline
@pytest.mark.asyncio
async def test_get_sensor_data_propagates_auth_error_on_unrecoverable_expiry(
    logged_in, register_login
):
    """If a sensor-data fetch lands on the login page AND the transparent
    re-login also lands on the login page, ``get_sensor_data`` must raise
    ``OmnisenseAuthError`` instead of silently returning ``{}`` -- callers
    have to be able to tell "session is dead" apart from "transient site
    scrape failure"."""
    omnisense, m = logged_in

    sensor_url = f"{SENSOR_LIST_URL}?siteNbr=123456"

    # First GET: server 302s to the login page (session expired).
    m.get(sensor_url, status=302, headers={"Location": "/user_login.asp"})
    m.get(
        f"{HOST_URL}/user_login.asp",
        status=200,
        body="<html><form>login form</form></html>",
    )

    # Transparent re-login happens.
    register_login(m, set_cookie="ASP.NET_SessionId=def456; Path=/; HttpOnly")

    # Retry of the original GET: server STILL 302s to login (creds are
    # bad or the server's session table is broken).
    m.get(sensor_url, status=302, headers={"Location": "/user_login.asp"})
    m.get(
        f"{HOST_URL}/user_login.asp",
        status=200,
        body="<html><form>login form</form></html>",
    )

    with pytest.raises(OmnisenseAuthError):
        await omnisense.get_sensor_data("123456")


@pytest.mark.offline
@pytest.mark.asyncio
async def test_get_site_list_propagates_auth_error_on_unrecoverable_expiry(
    logged_in, register_login
):
    """Same contract as ``get_sensor_data``: an unrecoverable auth failure
    must surface as ``OmnisenseAuthError``, not a silent empty result."""
    omnisense, m = logged_in

    m.get(SITE_LIST_URL, status=302, headers={"Location": "/user_login.asp"})
    m.get(
        f"{HOST_URL}/user_login.asp",
        status=200,
        body="<html><form>login form</form></html>",
    )
    register_login(m, set_cookie="ASP.NET_SessionId=def456; Path=/; HttpOnly")
    m.get(SITE_LIST_URL, status=302, headers={"Location": "/user_login.asp"})
    m.get(
        f"{HOST_URL}/user_login.asp",
        status=200,
        body="<html><form>login form</form></html>",
    )

    with pytest.raises(OmnisenseAuthError):
        await omnisense.get_site_list()


@pytest.mark.offline
@pytest.mark.asyncio
async def test_cookies_preserved_verbatim_for_classic_asp():
    """Regression guard for #22: omnisense.com (Classic ASP) emits
    ``Set-Cookie`` values containing characters such as ``=`` and ``+``
    (e.g. ``userPNSToken=login+failed``). aiohttp's *default*
    ``CookieJar`` wraps such values in double quotes when serializing them
    onto the next request's ``Cookie`` header (you can see this by
    comparing ``Morsel.coded_value`` between the default jar and one
    constructed with ``quote_cookie=False``). The ASP server treats the
    quoted form as a different value and rejects our session.

    To guard against this we (a) check the configuration directly and
    (b) feed a cookie with a ``+`` through the configured jar and assert
    that ``coded_value`` - the form aiohttp writes to the wire - matches
    the raw server value byte-for-byte.

    (We can't use aioresponses to test the *full* round-trip because
    aioresponses doesn't push ``Set-Cookie`` headers from mocked
    responses through aiohttp's cookie-jar pipeline.)
    """
    omnisense = Omnisense()
    omnisense._open_session()
    try:
        jar = omnisense._session.cookie_jar

        # (a) Configuration check: jar is aiohttp.CookieJar with
        # quote_cookie disabled.
        assert isinstance(jar, aiohttp.CookieJar)
        assert jar.quote_cookie is False, (
            "Omnisense._session.cookie_jar was constructed with cookie "
            "quoting enabled. classic-ASP cookies from omnisense.com "
            "contain '=' / '+' characters that get wrapped in double "
            "quotes (or percent-encoded) on the next outgoing request, "
            "which breaks server-side auth. Use "
            "aiohttp.CookieJar(quote_cookie=False) in _open_session."
        )

        # (b) Behavioural check: feed a server-set cookie with a '+' and
        # confirm the coded_value (what aiohttp will write to the wire)
        # equals the raw value rather than being wrapped in double quotes.
        jar.update_cookies(
            {"userPNSToken": "login+failed"}, URL(HOST_URL)
        )
        sent = jar.filter_cookies(URL(HOST_URL))
        morsel = sent["userPNSToken"]
        assert morsel.value == "login+failed"
        assert morsel.coded_value == "login+failed", (
            "Cookie containing '+' was re-quoted by the jar: "
            f"coded_value={morsel.coded_value!r}. This is what aiohttp "
            "writes to the outgoing Cookie header, so omnisense.com will "
            "see e.g. 'userPNSToken=\"login+failed\"' and reject the "
            "session. The fix is aiohttp.CookieJar(quote_cookie=False) "
            "in Omnisense._open_session."
        )
    finally:
        await omnisense.close()
