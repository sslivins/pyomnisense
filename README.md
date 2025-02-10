# pyomnisense

![Live Tests](https://github.com/sslivins/pyomnisense/actions/workflows/live_tests.yml/badge.svg)
![Offline Tests](https://github.com/sslivins/pyomnisense/actions/workflows/offline_tests.yml/badge.svg)
[![PyPI version](https://badge.fury.io/py/your_package.svg)](https://badge.fury.io/py/your_package)

pyomnisense is a Python library for accessing Omnisense sensor data directly from the omnisense.com website. It supports logging into the service, retrieving site lists, and fetching sensor data.

## Features

- Login to the Omnisense website
- Retrieve a list of sites with sensor data
- Fetch detailed sensor data for a selected site
- Asynchronous methods using aiohttp

## Install this repo

Clone the repository and install in editable mode:

```bash
git clone https://github.com/your_username/pyomnisense.git
cd pyomnisense
pip install -e .
```

## Install from pypi.org

```bash
pip install pyomnisense
```

## Usage

```python
from pyomnisense import Omnisense

async def main():
    omnisense = Omnisense()
    # Login with your credentials
    await omnisense.login("your_username", "your_password")
    
    # Get list of sites
    sites = await omnisense.get_site_list()
    print("Available sites:", sites)

    sensor_data = await omnisense.get_sensor_data(sites)

    print("Sensor Data for Site:", sensor_data)
    
    # When done, close the session
    await omnisense.close()

import asyncio
asyncio.run(main())
```

Replace `"your_username"` and `"your_password"` with your actual Omnisense credentials. For more details, refer to the documentation or explore the source code.

## Testing
Tests are written using pytest and pytest-asyncio. You can run tests as follows:

### Install the test dependancies
pip install -e .[tests]

### Run offline tests
_Note: network access not required_
`pytest -m offline`

## Run live tests 
_Note: requires internet access, an account on omnisense and the following environment variables to be set:_ OMNISENSE_USERNAME and OMNISENSE_PASSWORD
`pytest -m live`

## Run all tests
_Note: See live test note_
`pytest`
