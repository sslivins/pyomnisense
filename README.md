# pyomnisense

pyomnisense is a Python library for accessing Omnisense sensor data directly from the omnisense.com website. It supports logging into the service, retrieving site lists, and fetching sensor data.

## Features

- Login to the Omnisense website
- Retrieve a list of sites with sensor data
- Fetch detailed sensor data for a selected site
- Asynchronous methods using aiohttp
- Transparent re-login if the server expires the session between calls

## Install this repo

Clone the repository and install in editable mode:

```bash
git clone https://github.com/sslivins/pyomnisense.git
cd pyomnisense
pip install -e .
```

## Install from pypi.org

```bash
pip install pyomnisense
```

## Usage

```python
import asyncio
from pyomnisense import Omnisense, OmnisenseAuthError

async def main():
    async with Omnisense() as omnisense:
        try:
            await omnisense.login("your_username", "your_password")
        except OmnisenseAuthError as err:
            print(f"Login failed: {err}")
            return

        sites = await omnisense.get_site_list()
        print("Available sites:", sites)

        sensor_data = await omnisense.get_sensor_data(sites)
        print("Sensor data:", sensor_data)

asyncio.run(main())
```

Replace `"your_username"` and `"your_password"` with your actual Omnisense credentials. The `async with` block guarantees the underlying HTTP session is closed even on errors.

## Testing
Tests are written using pytest and pytest-asyncio. You can run tests as follows:

```bash
pytest -m offline
```

