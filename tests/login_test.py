import pytest
import aiohttp
from aioresponses import aioresponses
from pyomnisense.omnisense import Omnisense, LOGIN_URL, HOST_URL

@pytest.mark.offline
@pytest.mark.asyncio
async def test_successful_login():
    omnisense = Omnisense()
    username = "testuser"
    password = "testpass"

    # Simulate the Set-Cookie and Location headers in the login POST response
    set_cookie_value = "ASP.NET_SessionId=abc123; Path=/; HttpOnly"
    redirect_location = "/site_select.asp"

    with aioresponses() as m:
        # Mock the POST to LOGIN_URL with Set-Cookie and Location headers
        m.post(
            LOGIN_URL,
            status=302,
            headers={
                "Set-Cookie": set_cookie_value,
                "Location": redirect_location,
            },
            body="",
        )
        # Mock the GET to the redirect location with the manual Cookie header
        m.get(
            f"{HOST_URL}{redirect_location}",
            status=200,
            body="Welcome to your dashboard",
        )

        result = await omnisense.login(username, password)
        assert result is True
        await omnisense.close()

@pytest.mark.offline
@pytest.mark.asyncio
async def test_failed_login_response_status():
    omnisense = Omnisense()
    username = "testuser"
    password = "wrongpass"
    # Simulate a failed login with non-200 status.
    with aioresponses() as m:
        m.post(LOGIN_URL, status=401, body="Unauthorized")
        result = await omnisense.login(username, password)
        await omnisense.close()
        assert result is False

@pytest.mark.offline
@pytest.mark.asyncio
async def test_failed_login_redirect_to_signin():
    omnisense = Omnisense()
    username = "testuser"
    password = "wrongpass"
    # Simulate a failed login: POST returns 302 redirecting back to LOGIN_URL
    set_cookie_value = "userPNSToken=login+failed; Path=/"
    redirect_location = "/user_login.asp"

    with aioresponses() as m:
        m.post(
            LOGIN_URL,
            status=302,
            headers={
                "Set-Cookie": set_cookie_value,
                "Location": "/user_login.asp",
            },
            body="",
        )

        result = await omnisense.login(username, password)
        await omnisense.close()
        assert result is False

@pytest.mark.offline
@pytest.mark.asyncio
async def test_no_credentials_provided():
    omnisense = Omnisense()
    # Calling login without credentials should raise an Exception.
    with pytest.raises(Exception) as excinfo:
        await omnisense.login()
    assert "No username or password provided." in str(excinfo.value)
    await omnisense.close()

@pytest.mark.offline
@pytest.mark.asyncio
async def test_close_session():
    omnisense = Omnisense()
    # Manually create an aiohttp session to simulate an active session.
    omnisense._session = aiohttp.ClientSession()
    await omnisense.close()
    assert omnisense._session is None