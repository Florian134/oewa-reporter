"""
Tests für die Daten-Ingestion
=============================
"""

import pytest
from datetime import date, datetime
from unittest.mock import Mock, patch, MagicMock

from oewa_reporting.api_client import INFOnlineAPIClient, APIResponse, MetricData
from oewa_reporting.config import SiteConfig


class TestAPIClient:
    """Tests für den API Client"""
    
    @pytest.fixture
    def client(self):
        """API Client mit Mock-Key"""
        return INFOnlineAPIClient(api_key="test_key")
    
    @pytest.fixture
    def sample_response(self):
        """Beispiel API Response"""
        return {
            "metadata": {
                "site": "EA000004_desktop",
                "aggregation": "DAY",
                "date": "2024-01-15",
                "exported_at": "2024-01-16T08:00:00",
                "version": "1"
            },
            "data": {
                "iom": [{
                    "datetime": "2024-01-15T00:00:00",
                    "pis": 100000,
                    "pisnat": 90000,
                    "pisint": 10000,
                    "preliminary": False
                }],
                "iomp": [{
                    "datetime": "2024-01-15T00:00:00",
                    "pis": 80000,
                    "pisnat": 72000,
                    "pisint": 8000,
                    "preliminary": False
                }],
                "iomb": [{
                    "datetime": "2024-01-15T00:00:00",
                    "pis": 100000
                }]
            }
        }
    
    def test_metric_endpoints_mapping(self, client):
        """Metrik-Endpunkte sind korrekt gemappt"""
        assert client.METRIC_ENDPOINTS["pageimpressions"] == "/api/v1/pageimpressions"
        assert client.METRIC_ENDPOINTS["visits"] == "/api/v1/visits"
        assert client.METRIC_ENDPOINTS["clients"] == "/api/v1/clients"
    
    @patch("oewa_reporting.api_client.requests.Session")
    def test_fetch_metric_success(self, mock_session_class, client, sample_response):
        """Erfolgreicher API-Aufruf"""
        # Mock Response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample_response
        
        mock_session = Mock()
        mock_session.get.return_value = mock_response
        client.session = mock_session
        
        result = client.fetch_metric(
            metric="pageimpressions",
            site_id="EA000004_desktop",
            date="2024-01-15"
        )
        
        assert result.success
        assert result.status_code == 200
        assert result.data is not None
    
    @patch("oewa_reporting.api_client.requests.Session")
    def test_fetch_metric_unauthorized(self, mock_session_class, client):
        """401 bei ungültigem API-Key"""
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.json.return_value = {"detail": "Unauthorized"}
        mock_response.text = "Unauthorized"
        
        mock_session = Mock()
        mock_session.get.return_value = mock_response
        client.session = mock_session
        
        result = client.fetch_metric(
            metric="pageimpressions",
            site_id="EA000004_desktop",
            date="2024-01-15"
        )
        
        assert not result.success
        assert result.status_code == 401
    
    def test_parse_metric_response(self, client, sample_response):
        """Response wird korrekt geparst"""
        response = APIResponse(
            success=True,
            status_code=200,
            data=sample_response
        )
        
        metric_data = client._parse_metric_response(
            response,
            "pageimpressions",
            "EA000004_desktop",
            "2024-01-15",
            "DAY"
        )
        
        assert metric_data is not None
        assert metric_data.iom_total == 100000
        assert metric_data.iom_national == 90000
        assert metric_data.iom_international == 10000
        assert metric_data.iomp_total == 80000
        assert metric_data.iomb_total == 100000
        assert metric_data.iom_preliminary == False


class TestMetricData:
    """Tests für MetricData Objekt"""
    
    def test_metric_data_creation(self):
        """MetricData kann erstellt werden"""
        data = MetricData(
            site_id="EA000004_desktop",
            metric="pageimpressions",
            date="2024-01-15",
            aggregation="DAY",
            iom_total=100000,
            iom_national=90000,
            iom_international=10000
        )
        
        assert data.site_id == "EA000004_desktop"
        assert data.iom_total == 100000
    
    def test_metric_data_defaults(self):
        """MetricData hat sinnvolle Defaults"""
        data = MetricData(
            site_id="test",
            metric="pi",
            date="2024-01-15",
            aggregation="DAY"
        )
        
        assert data.iom_total is None
        assert data.iom_preliminary == True


class TestSiteConfig:
    """Tests für SiteConfig"""
    
    def test_site_config_creation(self):
        """SiteConfig kann erstellt werden"""
        config = SiteConfig(
            site_id="EA000004_desktop",
            brand="vol",
            surface="web_desktop",
            name="VOL.at Web Desktop"
        )
        
        assert config.site_id == "EA000004_desktop"
        assert config.brand == "vol"
        assert config.surface == "web_desktop"


class TestAPIResponse:
    """Tests für APIResponse"""
    
    def test_api_response_success(self):
        """Erfolgreiche Response"""
        response = APIResponse(
            success=True,
            status_code=200,
            data={"test": "data"}
        )
        
        assert response.success
        assert response.error is None
    
    def test_api_response_error(self):
        """Fehlerhafte Response"""
        response = APIResponse(
            success=False,
            status_code=500,
            error="Internal Server Error"
        )
        
        assert not response.success
        assert "Server Error" in response.error
    
    def test_api_response_metadata(self):
        """Metadata Extraktion"""
        response = APIResponse(
            success=True,
            status_code=200,
            data={
                "metadata": {"site": "test"},
                "data": {"iom": []}
            }
        )
        
        assert response.metadata == {"site": "test"}
        assert response.measurements == {"iom": []}

