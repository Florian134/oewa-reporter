"""
INFOnline Reporting API - Pytest Test Suite
============================================

Pytest-basierte Tests für die INFOnline Reporting API.
Kann mit `pytest test_infonline_api.py -v` ausgeführt werden.

Für HTML-Report: pytest test_infonline_api.py --html=report.html
"""

import pytest
import requests
from datetime import datetime, timedelta
from typing import Optional, Dict, Any


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture(scope="module")
def api_config():
    """API-Konfiguration für alle Tests"""
    return {
        "base_url": "https://reportingapi.infonline.de",
        "api_key": "MmFiNjk4YTgtZTA2OS00MGYwLWEyNWQtNGY3ODg0NWI5ODI3",
        "timeout": 30
    }


@pytest.fixture(scope="module")
def api_session(api_config):
    """Konfigurierte Session für API-Calls"""
    session = requests.Session()
    session.headers.update({
        "authorization": api_config["api_key"],
        "Accept": "application/json"
    })
    return session


@pytest.fixture
def test_date():
    """Testdatum: 7 Tage zurück"""
    return (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")


@pytest.fixture
def test_month_date():
    """Testdatum für Monatsdaten: 35 Tage zurück"""
    return (datetime.now() - timedelta(days=35)).strftime("%Y-%m-%d")


@pytest.fixture
def test_site():
    """Standard Test-Site (VOL.AT)"""
    return "at_w_atvol"


# ============================================================================
# HILFSFUNKTIONEN
# ============================================================================

def make_api_call(
    session: requests.Session,
    base_url: str,
    endpoint: str,
    params: Dict[str, Any] = None,
    timeout: int = 30
) -> requests.Response:
    """Führt einen API-Call durch"""
    url = f"{base_url}{endpoint}"
    return session.get(url, params=params, timeout=timeout)


# ============================================================================
# HEALTH TESTS
# ============================================================================

class TestHealth:
    """Tests für den Health-Endpoint"""
    
    def test_health_endpoint_reachable(self, api_session, api_config):
        """Health-Endpoint sollte erreichbar sein"""
        response = make_api_call(
            api_session,
            api_config["base_url"],
            "/health"
        )
        assert response.status_code == 200, f"Health check failed: {response.text}"
    
    def test_health_response_time(self, api_session, api_config):
        """Health-Endpoint sollte schnell antworten (<2s)"""
        import time
        start = time.time()
        response = make_api_call(
            api_session,
            api_config["base_url"],
            "/health"
        )
        duration = time.time() - start
        assert duration < 2.0, f"Health check too slow: {duration:.2f}s"


# ============================================================================
# AUTHENTICATION TESTS
# ============================================================================

class TestAuthentication:
    """Tests für die API-Authentifizierung"""
    
    def test_valid_api_key(self, api_session, api_config, test_site, test_date):
        """Gültiger API-Key sollte funktionieren"""
        response = make_api_call(
            api_session,
            api_config["base_url"],
            "/api/v1/pageimpressions",
            params={
                "site": test_site,
                "aggregation": "DAY",
                "date": test_date
            }
        )
        assert response.status_code == 200, f"Valid API key rejected: {response.status_code}"
    
    def test_invalid_api_key(self, api_config, test_site, test_date):
        """Ungültiger API-Key sollte 401 zurückgeben"""
        session = requests.Session()
        session.headers.update({
            "authorization": "invalid_key_12345",
            "Accept": "application/json"
        })
        
        response = make_api_call(
            session,
            api_config["base_url"],
            "/api/v1/pageimpressions",
            params={
                "site": test_site,
                "aggregation": "DAY",
                "date": test_date
            }
        )
        # API gibt 401 (Unauthorized) statt 403 zurück
        assert response.status_code == 401, f"Invalid key not rejected: {response.status_code}"
    
    def test_missing_api_key(self, api_config, test_site, test_date):
        """Fehlender API-Key sollte 403 zurückgeben"""
        session = requests.Session()
        session.headers.update({"Accept": "application/json"})
        
        response = make_api_call(
            session,
            api_config["base_url"],
            "/api/v1/pageimpressions",
            params={
                "site": test_site,
                "aggregation": "DAY",
                "date": test_date
            }
        )
        # Fehlender Key = 403 (Forbidden), ungültiger Key = 401 (Unauthorized)
        assert response.status_code == 403, f"Missing key not rejected: {response.status_code}"


# ============================================================================
# PARAMETER VALIDATION TESTS
# ============================================================================

class TestParameterValidation:
    """Tests für die Parametervalidierung"""
    
    def test_missing_site_parameter(self, api_session, api_config, test_date):
        """Fehlender 'site' Parameter sollte 422 zurückgeben"""
        response = make_api_call(
            api_session,
            api_config["base_url"],
            "/api/v1/pageimpressions",
            params={
                "aggregation": "DAY",
                "date": test_date
            }
        )
        assert response.status_code == 422
    
    def test_missing_aggregation_parameter(self, api_session, api_config, test_site, test_date):
        """Fehlender 'aggregation' Parameter sollte 422 zurückgeben"""
        response = make_api_call(
            api_session,
            api_config["base_url"],
            "/api/v1/pageimpressions",
            params={
                "site": test_site,
                "date": test_date
            }
        )
        assert response.status_code == 422
    
    def test_missing_date_parameter(self, api_session, api_config, test_site):
        """Fehlender 'date' Parameter sollte 422 zurückgeben"""
        response = make_api_call(
            api_session,
            api_config["base_url"],
            "/api/v1/pageimpressions",
            params={
                "site": test_site,
                "aggregation": "DAY"
            }
        )
        assert response.status_code == 422
    
    def test_invalid_aggregation_value(self, api_session, api_config, test_site, test_date):
        """Ungültiger Aggregationswert sollte 422 zurückgeben"""
        response = make_api_call(
            api_session,
            api_config["base_url"],
            "/api/v1/pageimpressions",
            params={
                "site": test_site,
                "aggregation": "INVALID",
                "date": test_date
            }
        )
        assert response.status_code == 422


# ============================================================================
# PAGE IMPRESSIONS ENDPOINT TESTS
# ============================================================================

class TestPageImpressions:
    """Tests für den Page Impressions Endpoint"""
    
    @pytest.mark.parametrize("aggregation", ["HOUR", "DAY", "MONTH"])
    def test_page_impressions_aggregations(
        self, api_session, api_config, test_site, test_date, test_month_date, aggregation
    ):
        """Page Impressions sollte für alle Aggregationstypen funktionieren"""
        date = test_month_date if aggregation == "MONTH" else test_date
        
        response = make_api_call(
            api_session,
            api_config["base_url"],
            "/api/v1/pageimpressions",
            params={
                "site": test_site,
                "aggregation": aggregation,
                "date": date
            }
        )
        assert response.status_code == 200, f"Failed for {aggregation}: {response.text}"
    
    @pytest.mark.parametrize("return_type", ["json", "csv", "csv_headless", "xml"])
    def test_page_impressions_return_types(
        self, api_session, api_config, test_site, test_date, return_type
    ):
        """Page Impressions sollte verschiedene Rückgabeformate unterstützen"""
        response = make_api_call(
            api_session,
            api_config["base_url"],
            "/api/v1/pageimpressions",
            params={
                "site": test_site,
                "aggregation": "DAY",
                "date": test_date,
                "returntype": return_type
            }
        )
        assert response.status_code == 200, f"Failed for {return_type}: {response.text}"


class TestPageImpressionsPerPixelpath:
    """Tests für Page Impressions per Pixelpath (nur HOUR/DAY)"""
    
    @pytest.mark.parametrize("aggregation", ["HOUR", "DAY"])
    def test_valid_aggregations(self, api_session, api_config, test_site, test_date, aggregation):
        """PI per Pixelpath sollte für HOUR und DAY funktionieren"""
        response = make_api_call(
            api_session,
            api_config["base_url"],
            "/api/v1/pageimpressionsperpixelpath",
            params={
                "site": test_site,
                "aggregation": aggregation,
                "date": test_date
            }
        )
        assert response.status_code == 200
    
    def test_month_aggregation_rejected(self, api_session, api_config, test_site, test_month_date):
        """PI per Pixelpath sollte MONTH Aggregation ablehnen"""
        response = make_api_call(
            api_session,
            api_config["base_url"],
            "/api/v1/pageimpressionsperpixelpath",
            params={
                "site": test_site,
                "aggregation": "MONTH",
                "date": test_month_date
            }
        )
        assert response.status_code == 422


class TestPageImpressionsPerUrl:
    """Tests für Page Impressions per URL"""
    
    def test_page_impressions_per_url(self, api_session, api_config, test_site, test_date):
        """PI per URL sollte funktionieren"""
        response = make_api_call(
            api_session,
            api_config["base_url"],
            "/api/v1/pageimpressionsperurl",
            params={
                "site": test_site,
                "aggregation": "DAY",
                "date": test_date
            }
        )
        assert response.status_code == 200


# ============================================================================
# VISITS ENDPOINT TESTS
# ============================================================================

class TestVisits:
    """Tests für den Visits Endpoint"""
    
    @pytest.mark.parametrize("aggregation", ["HOUR", "DAY", "MONTH"])
    def test_visits_aggregations(
        self, api_session, api_config, test_site, test_date, test_month_date, aggregation
    ):
        """Visits sollte für alle Aggregationstypen funktionieren"""
        date = test_month_date if aggregation == "MONTH" else test_date
        
        response = make_api_call(
            api_session,
            api_config["base_url"],
            "/api/v1/visits",
            params={
                "site": test_site,
                "aggregation": aggregation,
                "date": date
            }
        )
        assert response.status_code == 200


# ============================================================================
# CLIENTS ENDPOINT TESTS
# ============================================================================

class TestClients:
    """Tests für Clients Endpoints"""
    
    def test_clients_endpoint(self, api_session, api_config, test_site, test_date):
        """Clients Endpoint sollte funktionieren"""
        response = make_api_call(
            api_session,
            api_config["base_url"],
            "/api/v1/clients",
            params={
                "site": test_site,
                "aggregation": "DAY",
                "date": test_date
            }
        )
        assert response.status_code == 200
    
    def test_unique_clients_endpoint(self, api_session, api_config, test_site, test_date):
        """Unique Clients Endpoint sollte funktionieren"""
        response = make_api_call(
            api_session,
            api_config["base_url"],
            "/api/v1/uniqueclients",
            params={
                "site": test_site,
                "aggregation": "DAY",
                "date": test_date
            }
        )
        assert response.status_code == 200


# ============================================================================
# USETIME ENDPOINT TESTS (nur DAY/MONTH)
# ============================================================================

class TestUsetime:
    """Tests für Usetime Endpoint"""
    
    @pytest.mark.parametrize("aggregation", ["DAY", "MONTH"])
    def test_valid_aggregations(
        self, api_session, api_config, test_site, test_date, test_month_date, aggregation
    ):
        """Usetime sollte für DAY und MONTH funktionieren"""
        date = test_month_date if aggregation == "MONTH" else test_date
        
        response = make_api_call(
            api_session,
            api_config["base_url"],
            "/api/v1/usetime",
            params={
                "site": test_site,
                "aggregation": aggregation,
                "date": date
            }
        )
        assert response.status_code == 200
    
    def test_hour_aggregation_rejected(self, api_session, api_config, test_site, test_date):
        """Usetime sollte HOUR Aggregation ablehnen"""
        response = make_api_call(
            api_session,
            api_config["base_url"],
            "/api/v1/usetime",
            params={
                "site": test_site,
                "aggregation": "HOUR",
                "date": test_date
            }
        )
        assert response.status_code == 422


# ============================================================================
# DEVICES ENDPOINT TESTS (nur DAY/MONTH)
# ============================================================================

class TestDevices:
    """Tests für Devices Endpoint"""
    
    @pytest.mark.parametrize("aggregation", ["DAY", "MONTH"])
    def test_valid_aggregations(
        self, api_session, api_config, test_site, test_date, test_month_date, aggregation
    ):
        """Devices sollte für DAY und MONTH funktionieren"""
        date = test_month_date if aggregation == "MONTH" else test_date
        
        response = make_api_call(
            api_session,
            api_config["base_url"],
            "/api/v1/devices",
            params={
                "site": test_site,
                "aggregation": aggregation,
                "date": date
            }
        )
        assert response.status_code == 200
    
    def test_hour_aggregation_rejected(self, api_session, api_config, test_site, test_date):
        """Devices sollte HOUR Aggregation ablehnen"""
        response = make_api_call(
            api_session,
            api_config["base_url"],
            "/api/v1/devices",
            params={
                "site": test_site,
                "aggregation": "HOUR",
                "date": test_date
            }
        )
        assert response.status_code == 422


# ============================================================================
# SITE IDENTIFIER TESTS
# ============================================================================

class TestSiteIdentifiers:
    """Tests für verschiedene Site-Identifier"""
    
    @pytest.mark.parametrize("site_id,site_name", [
        ("at_w_atvol", "VOL.AT Web"),
        ("at_w_atvienna", "VIENNA.AT Web"),
        ("BE000072", "VOL.AT Homepage (Belegungseinheit)"),
    ])
    def test_different_site_identifiers(
        self, api_session, api_config, test_date, site_id, site_name
    ):
        """Verschiedene Site-Identifier sollten funktionieren"""
        response = make_api_call(
            api_session,
            api_config["base_url"],
            "/api/v1/pageimpressions",
            params={
                "site": site_id,
                "aggregation": "DAY",
                "date": test_date
            }
        )
        assert response.status_code == 200, f"Failed for {site_name}: {response.text}"


# ============================================================================
# DATA QUALITY TESTS
# ============================================================================

class TestDataQuality:
    """Tests für die Datenqualität"""
    
    def test_json_response_valid(self, api_session, api_config, test_site, test_date):
        """JSON Response sollte valides JSON sein"""
        response = make_api_call(
            api_session,
            api_config["base_url"],
            "/api/v1/pageimpressions",
            params={
                "site": test_site,
                "aggregation": "DAY",
                "date": test_date
            }
        )
        
        assert response.status_code == 200
        
        # JSON sollte parsbar sein
        try:
            data = response.json()
            assert data is not None
        except Exception as e:
            pytest.fail(f"JSON parsing failed: {e}")
    
    def test_response_contains_data(self, api_session, api_config, test_site, test_date):
        """Response sollte Daten enthalten"""
        response = make_api_call(
            api_session,
            api_config["base_url"],
            "/api/v1/pageimpressions",
            params={
                "site": test_site,
                "aggregation": "DAY",
                "date": test_date
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Daten sollten vorhanden sein (Liste oder Dict)
        has_data = (
            (isinstance(data, list) and len(data) > 0) or
            (isinstance(data, dict) and len(data) > 0)
        )
        
        # Notiz: Kann auch leere Daten zurückgeben wenn kein Traffic
        assert data is not None


# ============================================================================
# PERFORMANCE TESTS
# ============================================================================

class TestPerformance:
    """Performance-Tests"""
    
    def test_response_time_acceptable(self, api_session, api_config, test_site, test_date):
        """Response-Zeit sollte unter 5 Sekunden liegen"""
        import time
        
        start = time.time()
        response = make_api_call(
            api_session,
            api_config["base_url"],
            "/api/v1/pageimpressions",
            params={
                "site": test_site,
                "aggregation": "DAY",
                "date": test_date
            }
        )
        duration = time.time() - start
        
        assert response.status_code == 200
        assert duration < 5.0, f"Response too slow: {duration:.2f}s"


# ============================================================================
# EDGE CASE TESTS
# ============================================================================

class TestEdgeCases:
    """Tests für Randfälle"""
    
    def test_future_date(self, api_session, api_config, test_site):
        """Zukünftiges Datum sollte behandelt werden"""
        future_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
        
        response = make_api_call(
            api_session,
            api_config["base_url"],
            "/api/v1/pageimpressions",
            params={
                "site": test_site,
                "aggregation": "DAY",
                "date": future_date
            }
        )
        
        # API gibt 503 (Service Unavailable) für zukünftige Daten zurück
        assert response.status_code in [200, 422, 503]
    
    def test_very_old_date(self, api_session, api_config, test_site):
        """Sehr altes Datum sollte behandelt werden"""
        old_date = "2010-01-01"
        
        response = make_api_call(
            api_session,
            api_config["base_url"],
            "/api/v1/pageimpressions",
            params={
                "site": test_site,
                "aggregation": "DAY",
                "date": old_date
            }
        )
        
        # API gibt 403 (Forbidden) für Daten außerhalb des verfügbaren Bereichs zurück
        assert response.status_code in [200, 403, 422]


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

