import logging
import aiohttp
from bs4 import BeautifulSoup
import re
from typing import List, Dict, Optional, Union
from playwright.async_api import async_playwright

_LOGGER = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

CONF_SITE_NAME = "site_name"       # The name of the site (e.g., "home")
CONF_SENSOR_IDS = "sensor_ids"     # List of sensor IDs to extract (empty = all)
CONF_USERNAME = "username"         # Login username
CONF_PASSWORD = "password"         # Login password

LOGIN_URL = "https://www.omnisense.com/user_login.asp"
SITE_LIST_URL = "https://www.omnisense.com/site_select.asp"
SENSOR_LIST_URL = "https://www.omnisense.com/sensor_select.asp"

class Omnisense:

    def __init__(self): 
        self._username = None
        self._password = None
        self._session = None
        self._playwright = None
        self._browser = None
        self._page = None        
    
    async def login(self, username: str = None, password: str = None) -> bool:
        '''Login to the Omnisense website using Playwright. Returns True if login is successful.'''

        if not username or not password:
            if not self._username or not self._password:
                _LOGGER.error("No username or password provided.")
                raise Exception("No username or password provided.")
        else:
            self._username = username
            self._password = password

        try:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=True)
            self._page = await self._browser.new_page()

            # Navigate to the login page
            await self._page.goto("https://www.omnisense.com/user_login.asp")

            # Fill out the form
            await self._page.fill('input[name="userId"]', self._username)
            await self._page.fill('input[name="userPass"]', self._password)

            # Click the submit button
            await self._page.click('button[name="btnAct"]')

            # Wait for navigation to complete (redirect to site_select.asp)
            await self._page.wait_for_url("**/site_select.asp", timeout=10000)

            # Verify login succeeded by checking the page content or URL
            content = await self._page.content()
            if "User Log-In" in content or "user_login.asp" in self._page.url.lower():
                raise Exception("Login failed: incorrect credentials or unexpected redirect.")

        except Exception as err:
            _LOGGER.error("Login error: %s", err)
            await self.close()
            raise err

        _LOGGER.info("Login successful.")
        return True

    async def close(self):
        '''Cleanup resources.'''
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None       
        
    async def get_site_list(self) -> dict:
        '''Fetch the available sites using Playwright and return a dictionary of {site_id: site_name}'''

        if not self._page:
            success = await self.login()
            if not success:
                return {}

        try:
            # Navigate to the site list page
            await self._page.goto(SITE_LIST_URL, timeout=10000)

            # Get page HTML content
            html = await self._page.content()
            soup = BeautifulSoup(html, "html.parser")

        except Exception as err:
            _LOGGER.error("Error fetching site list: %s", err)
            return {}

        sites = {}
        for link in soup.find_all("a", onclick=True):
            onclick = link.get("onclick", "")
            match = re.search(r"ShowSiteDetail\('(\d+)'\)", onclick)
            if match:
                site_id = match.group(1)
                site_name = link.get_text(strip=True)
                sites[site_id] = site_name

        return sites
    
    async def get_site_sensor_list(self, site_ids: Union[str, List[str], Dict[str, str]] = None) -> Dict[str, Dict[str, str]]:
        '''Fetch sensors for the selected site(s) using Playwright.

        Args:
            site_ids: Can be a single site_id string, list of site_ids, or dict of {site_id: site_name}.
                    If not provided, all sensors for all sites will be returned.

        Returns:
            Dict of sensor_id → {description, sensor_type, site_name}
        '''

        if not self._page:
            success = await self.login()
            if not success:
                return {}

        if not site_ids:
            site_ids = await self.get_site_list()

        if isinstance(site_ids, str):
            site_ids = [site_ids]
        elif isinstance(site_ids, list):
            pass  # Already correct format
        elif isinstance(site_ids, dict):
            site_ids = list(site_ids.keys())
        else:
            raise TypeError("Unsupported data type, expected str, list of str, or dict with str keys.")

        sensors = {}

        try:
            # Delegate to updated Playwright-based sensor data fetch
            sensor_data = await self.get_sensor_data(site_ids)

            if not sensor_data:
                return {}

            for sensor_id, sensor_info in sensor_data.items():
                sensors[sensor_id] = {
                    "description": sensor_info["description"],
                    "sensor_type": sensor_info["sensor_type"],
                    "site_name": sensor_info["site_name"]
                }

        except Exception as e:
            _LOGGER.error("Error fetching sensors: %s", e)
            return {}

        return sensors


    async def get_sensor_data(
        self,
        site_ids: Union[str, List[str], Dict[str, str]] = None,
        sensor_ids: Union[str, List[str]] = []
    ) -> dict:
        '''Fetch sensor data from the Omnisense dashboard using Playwright.'''

        if not self._page:
            success = await self.login()
            if not success:
                return {}

        if not site_ids:
            site_ids = await self.get_site_list()

        if isinstance(site_ids, str):
            site_ids = [site_ids]
        elif isinstance(site_ids, dict):
            site_ids = list(site_ids.keys())
        elif not isinstance(site_ids, list):
            raise TypeError("Unsupported data type for site_ids.")

        if isinstance(sensor_ids, str):
            sensor_ids = [sensor_ids]

        all_sensors = {}

        for site_id in site_ids:
            url = f"{SENSOR_LIST_URL}?siteNbr={site_id}"

            try:
                await self._page.goto(url, timeout=10000)
                html = await self._page.content()
                soup = BeautifulSoup(html, "html.parser")

                # Extract site name from the page title
                title_text = soup.find("title").get_text().strip()
                match = re.search(r"Sensors for\s+(.+)", title_text)
                site_name = match.group(1) if match else "Unknown"

                # Parse sensor tables
                for table in soup.select("table.sortable.table"):
                    sensor_type = None

                    table_id = table.get("id", "")
                    if table_id.startswith("sensorType"):
                        sensor_type = f"S-{table_id[len('sensorType'):]}"
                    else:
                        caption = table.find("caption")
                        if caption and caption.text:
                            m = re.search(r"Sensor Type\s*(\d+)", caption.text)
                            if m:
                                sensor_type = f"S-{m.group(1)}"

                    for row in table.select("tr.sensorTable"):
                        tds = row.find_all("td")
                        if len(tds) >= 10:
                            sid = tds[0].get_text(strip=True)
                            if sensor_ids and sid not in sensor_ids:
                                continue

                            try:
                                temperature = float(tds[4].get_text(strip=True))
                            except ValueError:
                                temperature = None

                            desc = tds[1].get_text(strip=True)
                            if desc == "~click to edit~":
                                desc = "<description not set>"

                            all_sensors[sid] = {
                                "description": desc,
                                "last_activity": tds[2].get_text(strip=True),
                                "status": tds[3].get_text(strip=True),
                                "temperature": temperature,
                                "relative_humidity": tds[5].get_text(strip=True),
                                "absolute_humidity": tds[6].get_text(strip=True),
                                "dew_point": tds[7].get_text(strip=True),
                                "wood_pct": tds[8].get_text(strip=True),
                                "battery_voltage": tds[9].get_text(strip=True),
                                "sensor_type": sensor_type,
                                "sensor_id": sid,
                                "site_name": site_name,
                            }

            except Exception as e:
                _LOGGER.error(f"Error fetching/parsing sensor data for site id '{site_id}': {e}")
                continue

        return all_sensors



