"""Tests for ``Omnisense.get_site_list``."""

import pytest

from pyomnisense.omnisense import SITE_LIST_URL


@pytest.mark.offline
@pytest.mark.asyncio
async def test_get_site_list_parses_sample_html(logged_in, sample_site_html):
    omnisense, m = logged_in
    m.get(SITE_LIST_URL, status=200, body=sample_site_html)

    assert await omnisense.get_site_list() == {
        "123456": "MySite",
        "654321": "FirstSite",
    }
