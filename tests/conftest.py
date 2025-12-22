"""
ÖWA Reporter - Pytest Fixtures und Konfiguration
=================================================
"""

import pytest
import os
from datetime import date, timedelta

# Test-Konfiguration
TEST_AIRTABLE_API_KEY = os.environ.get("AIRTABLE_API_KEY", "")
TEST_AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID", "appTIeod85xnBy7Vn")
TEST_INFONLINE_API_KEY = os.environ.get("INFONLINE_API_KEY", "")


@pytest.fixture
def airtable_config():
    """Airtable-Konfiguration für Tests"""
    return {
        "api_key": TEST_AIRTABLE_API_KEY,
        "base_id": TEST_AIRTABLE_BASE_ID,
        "table_name": "Measurements"
    }


@pytest.fixture
def infonline_config():
    """INFOnline-Konfiguration für Tests"""
    return {
        "api_key": TEST_INFONLINE_API_KEY,
        "base_url": "https://reportingapi.infonline.de"
    }


@pytest.fixture
def test_date_range():
    """Standard-Datumsbereich für Tests (letzte 7 Tage)"""
    end_date = date.today() - timedelta(days=2)  # 2-Tage-Delay
    start_date = end_date - timedelta(days=7)
    return {
        "start": start_date,
        "end": end_date
    }


@pytest.fixture
def vol_sites():
    """VOL.AT Site-IDs"""
    return {
        "web": "at_w_atvol",
        "app": "EA000004_mobile_app",
        "homepage": "BE000072"
    }


@pytest.fixture
def vienna_sites():
    """VIENNA.AT Site-IDs"""
    return {
        "web": "at_w_atvienna",
        "app": "EA000003_mobile_app",
        "homepage": "BE000043"
    }


@pytest.fixture
def expected_metrics():
    """Erwartete Metriken"""
    return ["Page Impressions", "Visits", "Unique Clients", "Homepage PI"]


@pytest.fixture
def unique_key_pattern():
    """Regex-Pattern für Unique Keys"""
    import re
    # Format: YYYY-MM-DD_Brand_Plattform_Metrik
    return re.compile(r"^\d{4}-\d{2}-\d{2}_(VOL|Vienna)_(Web|App)_.+$")


def pytest_configure(config):
    """Pytest Marker konfigurieren"""
    config.addinivalue_line("markers", "critical: Kritische Tests (höchste Priorität)")
    config.addinivalue_line("markers", "integration: Integrations-Tests (benötigen API-Zugang)")
    config.addinivalue_line("markers", "security: Sicherheits-Tests")
    config.addinivalue_line("markers", "slow: Langsame Tests")

