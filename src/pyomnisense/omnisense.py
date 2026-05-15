import logging
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, TypedDict, Union

import aiohttp
from bs4 import BeautifulSoup

_LOGGER = logging.getLogger(__name__)

HOST_URL = "https://www.omnisense.com"
LOGIN_URL = "https://www.omnisense.com/user_login.asp"
SITE_LIST_URL = "https://www.omnisense.com/site_select.asp"
SENSOR_LIST_URL = "https://www.omnisense.com/sensor_select.asp"

_DEFAULT_TIMEOUT_SECS = 30

# Path fragment used to detect "the server bounced us back to the login page",
# i.e. the cached session expired and we need to log in again.
_LOGIN_PATH = "/user_login.asp"


class OmnisenseError(Exception):
    """Base class for all errors raised by this library."""


class OmnisenseAuthError(OmnisenseError):
    """Raised for authentication / session problems (missing credentials,
    rejected credentials, expired session that could not be re-established)."""


class SensorReading(TypedDict):
    """Shape of a single sensor's reading as returned by ``get_sensor_data``.

    Numeric fields are parsed to ``float`` (``None`` if the source page
    showed a non-numeric placeholder), and ``last_activity`` is a
    timezone-aware ``datetime`` in UTC (``None`` if it could not be
    parsed). omnisense.com emits all timestamps in UTC.
    """

    description: str
    last_activity: Optional[datetime]
    status: str
    temperature: Optional[float]
    relative_humidity: Optional[float]
    absolute_humidity: Optional[float]
    dew_point: Optional[float]
    wood_pct: Optional[float]
    battery_voltage: Optional[float]
    sensor_type: Optional[str]
    sensor_id: str
    site_name: Optional[str]


def _parse_float(value: str) -> Optional[float]:
    """Best-effort ``float`` parse for sensor-reading cells.

    Returns ``None`` instead of raising when the cell holds a non-numeric
    placeholder (e.g. an empty string for a sensor that hasn't reported
    that field yet).
    """
    if value is None:
        return None
    try:
        return float(value.strip())
    except (ValueError, AttributeError):
        return None


def _parse_timestamp(value: str) -> Optional[datetime]:
    """Parse omnisense.com's naive ``YY-MM-DD HH:MM:SS`` timestamps.

    Returns a timezone-aware ``datetime`` in UTC, or ``None`` if the
    cell could not be parsed. omnisense.com emits server-local times
    in UTC, so we label the naive parse result as UTC and let
    downstream consumers convert to local for display.
    """
    if value is None:
        return None
    try:
        naive = datetime.strptime(value.strip(), "%y-%m-%d %H:%M:%S")
    except (ValueError, AttributeError):
        return None
    return naive.replace(tzinfo=timezone.utc)


class Omnisense:

    def __init__(self):
        self._username: Optional[str] = None
        self._password: Optional[str] = None
        self._session: Optional[aiohttp.ClientSession] = None

        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 "
                "Mobile Safari/537.36 Edg/138.0.0.0"
            ),
        }

    def _open_session(self) -> None:
        # quote_cookie=False is load-bearing: omnisense.com is a classic ASP
        # site whose Set-Cookie values contain characters ('=', '+') that
        # aiohttp's default cookie jar would re-quote, breaking subsequent
        # authenticated requests. With quote_cookie=False the jar preserves
        # the server's cookie values verbatim, so we can let aiohttp manage
        # session cookies normally instead of building Cookie headers by hand.
        jar = aiohttp.CookieJar(quote_cookie=False)
        self._session = aiohttp.ClientSession(
            cookie_jar=jar,
            headers=self.headers,
            timeout=aiohttp.ClientTimeout(total=_DEFAULT_TIMEOUT_SECS),
        )

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def __aenter__(self) -> "Omnisense":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    async def login(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ) -> bool:
        """Log in to omnisense.com.

        Pass both ``username`` and ``password`` to set / replace cached
        credentials, or neither to reuse the credentials supplied on a
        previous successful call (this is what allows transparent
        re-login when the server expires our session).

        Returns ``True`` on success, ``False`` if the server rejected the
        credentials. Raises ``OmnisenseAuthError`` if no credentials are
        available, or if only one of username/password is supplied.
        """
        if (username is None) != (password is None):
            raise OmnisenseAuthError("Provide both username and password, or neither.")
        if username is not None:
            self._username = username
            self._password = password
        if not self._username or not self._password:
            _LOGGER.error("No username or password provided.")
            raise OmnisenseAuthError("No username or password provided.")

        # Always close any prior session before allocating a new one,
        # otherwise repeated login() calls leak ClientSessions / sockets.
        await self.close()
        self._open_session()

        payload = {
            "userId": self._username,
            "userPass": self._password,
            "target": "",
            "btnAct": "Log-In",
        }

        # POST the login form but don't follow the redirect yet, so we can
        # inspect the failure-sentinel cookie before making more requests.
        async with self._session.post(
            LOGIN_URL,
            data=payload,
            allow_redirects=False,
        ) as resp:
            _LOGGER.debug("Login POST status: %s", resp.status)

            token = resp.cookies.get("userPNSToken")
            if token is not None and "failed" in token.value.lower():
                _LOGGER.warning("Login rejected by server.")
                await self.close()
                return False

            location = resp.headers.get("Location")
            if not location:
                _LOGGER.error(
                    "Login POST returned status %s with no redirect location.",
                    resp.status,
                )
                await self.close()
                return False
            if not location.startswith("http"):
                location = HOST_URL + location

        # Follow the redirect. Cookies set on the POST response are now in
        # the jar and will be attached automatically.
        async with self._session.get(location) as resp:
            if resp.status != 200:
                _LOGGER.error(
                    "Post-login GET %s returned status %s", location, resp.status
                )
                await self.close()
                return False
            if _LOGIN_PATH in str(resp.url):
                _LOGGER.warning("Post-login GET landed back on the login page.")
                await self.close()
                return False

        return True

    async def _ensure_session(self) -> None:
        if self._session is None or self._session.closed:
            if not await self.login():
                raise OmnisenseAuthError("Login failed.")

    async def _fetch_html(self, url: str) -> str:
        """GET ``url``, transparently re-logging in once if the session expired.

        Detects expiry by checking whether the (post-redirect) response URL
        landed on the login page.
        """
        await self._ensure_session()

        for attempt in (0, 1):
            async with self._session.get(url) as resp:
                if resp.status != 200:
                    raise OmnisenseError(
                        f"GET {url} returned status {resp.status}"
                    )
                final_url = str(resp.url)
                if _LOGIN_PATH in final_url:
                    if attempt == 0:
                        _LOGGER.info("Session expired; re-logging in.")
                        if not await self.login():
                            raise OmnisenseAuthError("Re-login failed.")
                        continue
                    raise OmnisenseAuthError(
                        "Server kept redirecting to the login page after re-login."
                    )
                return await resp.text()

        raise OmnisenseError("unreachable")

    async def get_site_list(self) -> dict:
        """Fetch the available sites.

        If no session has been established yet, this implicitly logs in
        using credentials previously supplied via :meth:`login`. If
        no credentials are cached, ``OmnisenseAuthError`` is raised.

        Returns:
            dict: ``{site_id: site_name}``. Returns an empty dict on
            scrape / transport errors.

        Raises:
            OmnisenseAuthError: if the session is unrecoverable
                (e.g. cached credentials no longer work).
        """
        try:
            text = await self._fetch_html(SITE_LIST_URL)
        except OmnisenseAuthError:
            # Unrecoverable auth failure -- propagate so callers can
            # distinguish "session is dead" from "this scrape failed".
            raise
        except Exception as err:
            _LOGGER.error("Error fetching site list: %s", err)
            return {}

        soup = BeautifulSoup(text, "html.parser")
        sites = {}
        for link in soup.find_all("a", onclick=True):
            match = re.search(r"ShowSiteDetail\('(\d+)'\)", link.get("onclick", ""))
            if match:
                sites[match.group(1)] = link.get_text(strip=True)
        return sites

    async def get_site_sensor_list(
        self,
        site_ids: Union[str, List[str], Dict[str, str]] = None,
    ) -> Dict[str, Dict[str, Optional[str]]]:
        """Fetch sensors for the selected site(s) and project to the
        ``{description, sensor_type, site_name}`` subset.

        Args:
            site_ids: ``{site_id: site_name}`` dict, list of site_id strings,
                or a single site_id string. If omitted, all sites are
                queried.

        Raises:
            OmnisenseAuthError: if the session has expired and re-login
                fails (propagated from :meth:`get_sensor_data`).
        """
        sensor_data = await self.get_sensor_data(site_ids)
        return {
            sid: {
                "description": info["description"],
                "sensor_type": info["sensor_type"],
                "site_name": info["site_name"],
            }
            for sid, info in sensor_data.items()
        }

    async def get_sensor_data(
        self,
        site_ids: Union[str, List[str], Dict[str, str]] = None,
        sensor_ids: Union[str, List[str]] = None,
    ) -> Dict[str, SensorReading]:
        """Fetch sensor readings for one or more sites.

        Args:
            site_ids: A single site_id string, list of site_id strings,
                or ``{site_id: site_name}`` dict. If omitted, all sites are
                queried.
            sensor_ids: Optional filter; a single sensor_id or a list. If
                omitted, all sensors are returned.

        Returns:
            dict keyed by sensor_id. Numeric fields (``temperature``,
            ``relative_humidity``, ``absolute_humidity``, ``dew_point``,
            ``wood_pct``, ``battery_voltage``) are parsed to ``float``
            (``None`` on parse failure). ``last_activity`` is a
            timezone-aware ``datetime`` in UTC (``None`` on parse
            failure). See :class:`SensorReading` for the full shape.

        Raises:
            OmnisenseAuthError: if the session has expired and re-login
                fails. Per-site scrape / transport failures are logged
                and skipped (other sites still return their data).
        """
        if not site_ids:
            site_ids = await self.get_site_list()

        if isinstance(site_ids, str):
            site_ids = [site_ids]
        elif isinstance(site_ids, list):
            pass
        elif isinstance(site_ids, dict):
            site_ids = list(site_ids.keys())
        else:
            raise TypeError(
                "Unsupported data type, expected str, list of str, or dict with str keys."
            )

        if sensor_ids is None:
            sensor_ids = []
        elif isinstance(sensor_ids, str):
            sensor_ids = [sensor_ids]

        all_sensors: Dict[str, SensorReading] = {}
        for site_id in site_ids:
            sensor_page_url = f"{SENSOR_LIST_URL}?siteNbr={site_id}"

            try:
                text = await self._fetch_html(sensor_page_url)
            except OmnisenseAuthError:
                # Unrecoverable auth failure -- propagate so callers can
                # distinguish "session is dead" from "this one site was
                # transiently unreachable".
                raise
            except Exception:
                _LOGGER.exception(
                    "Error fetching sensor data for site id '%s'.", site_id
                )
                continue

            try:
                soup = BeautifulSoup(text, "html.parser")

                site_name = None
                title = soup.find("title")
                if title and title.get_text():
                    match = re.search(r"Sensors for\s+(.+)", title.get_text().strip())
                    if match:
                        site_name = match.group(1)

                for table in soup.select("table.sortable.table"):
                    sensor_type = None
                    table_id = table.get("id", "")
                    if table_id.startswith("sensorType"):
                        sensor_type = f"S-{table_id[len('sensorType'):]}"
                    if not sensor_type:
                        caption = table.find("caption")
                        if caption and caption.text:
                            m = re.search(r"Sensor Type\s*(\d+)", caption.text)
                            if m:
                                sensor_type = f"S-{m.group(1)}"

                    for row in table.select("tr.sensorTable"):
                        tds = row.find_all("td")
                        if len(tds) < 10:
                            continue
                        sid = tds[0].get_text(strip=True)
                        if sensor_ids and sid not in sensor_ids:
                            continue

                        desc = tds[1].get_text(strip=True)
                        if desc == "~click to edit~":
                            desc = "<description not set>"

                        all_sensors[sid] = {
                            "description": desc,
                            "last_activity": _parse_timestamp(tds[2].get_text(strip=True)),
                            "status": tds[3].get_text(strip=True),
                            "temperature": _parse_float(tds[4].get_text(strip=True)),
                            "relative_humidity": _parse_float(tds[5].get_text(strip=True)),
                            "absolute_humidity": _parse_float(tds[6].get_text(strip=True)),
                            "dew_point": _parse_float(tds[7].get_text(strip=True)),
                            "wood_pct": _parse_float(tds[8].get_text(strip=True)),
                            "battery_voltage": _parse_float(tds[9].get_text(strip=True)),
                            "sensor_type": sensor_type,
                            "sensor_id": sid,
                            "site_name": site_name,
                        }
            except Exception:
                _LOGGER.exception(
                    "Error parsing sensor data for site id '%s'.", site_id
                )
                continue

        return all_sensors
