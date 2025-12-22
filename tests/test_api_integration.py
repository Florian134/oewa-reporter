"""
ÖWA Reporter - API Integrations-Tests
======================================
Testet die Verbindung zu allen externen APIs.
"""

import pytest
import requests
import os
from datetime import date, timedelta


class TestINFOnlineAPI:
    """Tests für die INFOnline API"""
    
    @pytest.fixture(autouse=True)
    def setup(self, infonline_config):
        """Setup für jeden Test"""
        self.api_key = infonline_config["api_key"]
        self.base_url = infonline_config["base_url"]
    
    @pytest.mark.integration
    @pytest.mark.critical
    def test_api_authentication(self):
        """
        KRITISCH: Prüft ob die INFOnline API-Authentifizierung funktioniert.
        """
        if not self.api_key:
            pytest.skip("INFONLINE_API_KEY nicht gesetzt")
        
        url = f"{self.base_url}/api/v1/pageimpressions"
        headers = {
            "authorization": self.api_key,
            "Accept": "application/json"
        }
        params = {
            "site": "at_w_atvol",
            "date": (date.today() - timedelta(days=3)).isoformat(),
            "aggregation": "DAY"
        }
        
        response = requests.get(url, headers=headers, params=params, timeout=30)
        
        assert response.status_code != 401, "INFOnline API: Authentifizierung fehlgeschlagen!"
        assert response.status_code != 403, "INFOnline API: Zugriff verweigert!"
    
    @pytest.mark.integration
    def test_api_data_availability(self):
        """
        Prüft ob die INFOnline API Daten liefert.
        """
        if not self.api_key:
            pytest.skip("INFONLINE_API_KEY nicht gesetzt")
        
        url = f"{self.base_url}/api/v1/pageimpressions"
        headers = {
            "authorization": self.api_key,
            "Accept": "application/json"
        }
        
        # Teste für 3 Tage zurück (sollte finale Daten haben)
        test_date = date.today() - timedelta(days=3)
        params = {
            "site": "at_w_atvol",
            "date": test_date.isoformat(),
            "aggregation": "DAY"
        }
        
        response = requests.get(url, headers=headers, params=params, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            assert "data" in data, "Keine 'data' in API-Response"
            assert "iom" in data.get("data", {}), "Keine 'iom' Daten in Response"
        elif response.status_code == 404:
            pytest.skip(f"Keine Daten für {test_date} verfügbar")
        else:
            pytest.fail(f"API-Fehler: {response.status_code}")


class TestAirtableAPI:
    """Tests für die Airtable API"""
    
    @pytest.fixture(autouse=True)
    def setup(self, airtable_config):
        """Setup für jeden Test"""
        self.api_key = airtable_config["api_key"]
        self.base_id = airtable_config["base_id"]
        self.table_name = airtable_config["table_name"]
    
    @pytest.mark.integration
    @pytest.mark.critical
    def test_api_authentication(self):
        """
        KRITISCH: Prüft ob die Airtable API-Authentifizierung funktioniert.
        """
        if not self.api_key:
            pytest.skip("AIRTABLE_API_KEY nicht gesetzt")
        
        url = f"https://api.airtable.com/v0/{self.base_id}/{self.table_name}"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        params = {"maxRecords": 1}
        
        response = requests.get(url, headers=headers, params=params, timeout=30)
        
        assert response.status_code != 401, "Airtable API: Authentifizierung fehlgeschlagen!"
        assert response.status_code != 403, "Airtable API: Zugriff verweigert!"
        assert response.status_code == 200, f"Airtable API: Unerwarteter Status {response.status_code}"
    
    @pytest.mark.integration
    def test_table_exists(self):
        """
        Prüft ob die Measurements-Tabelle existiert.
        """
        if not self.api_key:
            pytest.skip("AIRTABLE_API_KEY nicht gesetzt")
        
        url = f"https://api.airtable.com/v0/{self.base_id}/{self.table_name}"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        params = {"maxRecords": 1}
        
        response = requests.get(url, headers=headers, params=params, timeout=30)
        
        assert response.status_code == 200, f"Tabelle '{self.table_name}' nicht gefunden!"
        
        data = response.json()
        assert "records" in data, "Unerwartetes Response-Format"
    
    @pytest.mark.integration
    def test_required_fields_exist(self):
        """
        Prüft ob alle erforderlichen Felder in der Tabelle existieren.
        """
        if not self.api_key:
            pytest.skip("AIRTABLE_API_KEY nicht gesetzt")
        
        url = f"https://api.airtable.com/v0/{self.base_id}/{self.table_name}"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        params = {"maxRecords": 1}
        
        response = requests.get(url, headers=headers, params=params, timeout=30)
        
        if response.status_code != 200:
            pytest.fail(f"API-Fehler: {response.status_code}")
        
        data = response.json()
        records = data.get("records", [])
        
        if not records:
            pytest.skip("Keine Records in der Tabelle")
        
        fields = records[0].get("fields", {})
        required_fields = ["Datum", "Brand", "Plattform", "Metrik", "Wert", "Unique Key"]
        
        missing = [f for f in required_fields if f not in fields]
        
        if missing:
            pytest.fail(f"Fehlende Felder in Airtable: {missing}")


class TestImgBBAPI:
    """Tests für die imgBB API"""
    
    @pytest.mark.integration
    def test_api_authentication(self):
        """
        Prüft ob die imgBB API-Authentifizierung funktioniert.
        """
        api_key = os.environ.get("IMGBB_API_KEY", "")
        
        if not api_key:
            pytest.skip("IMGBB_API_KEY nicht gesetzt")
        
        # Test mit minimalem Bild (1x1 transparent PNG)
        import base64
        minimal_png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        )
        
        response = requests.post(
            "https://api.imgbb.com/1/upload",
            data={
                "key": api_key,
                "image": base64.b64encode(minimal_png).decode("utf-8")
            },
            timeout=30
        )
        
        assert response.status_code != 401, "imgBB API: Authentifizierung fehlgeschlagen!"
        assert response.status_code == 200, f"imgBB API: Unerwarteter Status {response.status_code}"


class TestOpenAIAPI:
    """Tests für die OpenAI API"""
    
    @pytest.mark.integration
    def test_api_authentication(self):
        """
        Prüft ob die OpenAI API-Authentifizierung funktioniert.
        """
        api_key = os.environ.get("OPENAI_API_KEY", "")
        
        if not api_key:
            pytest.skip("OPENAI_API_KEY nicht gesetzt")
        
        response = requests.get(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30
        )
        
        assert response.status_code != 401, "OpenAI API: Authentifizierung fehlgeschlagen!"
        assert response.status_code == 200, f"OpenAI API: Unerwarteter Status {response.status_code}"


class TestTeamsWebhook:
    """Tests für den MS Teams Webhook"""
    
    @pytest.mark.integration
    def test_webhook_accessible(self):
        """
        Prüft ob der Teams Webhook erreichbar ist.
        
        Hinweis: Sendet KEINE echte Nachricht, prüft nur die Erreichbarkeit.
        """
        webhook_url = os.environ.get("TEAMS_WEBHOOK_URL", "")
        
        if not webhook_url:
            pytest.skip("TEAMS_WEBHOOK_URL nicht gesetzt")
        
        # Sende ein minimales Payload das von Teams ignoriert wird
        # (leere Nachricht wird akzeptiert aber nicht angezeigt)
        test_payload = {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "summary": "Test"
        }
        
        response = requests.post(
            webhook_url,
            json=test_payload,
            timeout=10
        )
        
        # Teams gibt 200 auch für leere Nachrichten zurück
        assert response.status_code == 200, f"Teams Webhook nicht erreichbar: {response.status_code}"

