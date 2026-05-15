"""Tests for ``Omnisense.login`` (success, failure modes, close)."""

import aiohttp
import pytest
from aioresponses import aioresponses

from pyomnisense.omnisense import (
    HOST_URL,
    LOGIN_URL,
    Omnisense,
    OmnisenseAuthError,
)


@pytest.mark.offline
@pytest.mark.asyncio
async def test_successful_login(register_login):
    with aioresponses() as m:
        register_login(m)
        omnisense = Omnisense()
        assert await omnisense.login("user", "pass") is True
        await omnisense.close()


@pytest.mark.offline
@pytest.mark.asyncio
async def test_failed_login_response_status():
    """A non-redirect / non-200 status on the login POST is treated as a
    failure (no Location header is supplied)."""
    with aioresponses() as m:
        m.post(LOGIN_URL, status=401, body="Unauthorized")
        omnisense = Omnisense()
        assert await omnisense.login("user", "wrong") is False
        await omnisense.close()


@pytest.mark.offline
@pytest.mark.asyncio
async def test_failed_login_redirect_with_failure_cookie():
    """When the server hands us a ``userPNSToken=login+failed`` cookie we
    must abort the login flow before following the redirect."""
    with aioresponses() as m:
        m.post(
            LOGIN_URL,
            status=302,
            headers={
                "Set-Cookie": "userPNSToken=login+failed; Path=/",
                "Location": "/user_login.asp",
            },
            body="",
        )
        omnisense = Omnisense()
        assert await omnisense.login("user", "wrong") is False
        await omnisense.close()


@pytest.mark.offline
@pytest.mark.asyncio
async def test_no_credentials_raises_typed_error():
    omnisense = Omnisense()
    with pytest.raises(OmnisenseAuthError, match="No username or password"):
        await omnisense.login()
    await omnisense.close()


@pytest.mark.offline
@pytest.mark.asyncio
async def test_close_idempotent_and_clears_session():
    omnisense = Omnisense()
    omnisense._session = aiohttp.ClientSession()
    await omnisense.close()
    assert omnisense._session is None
    # second close must not raise
    await omnisense.close()
