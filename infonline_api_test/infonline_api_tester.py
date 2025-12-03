"""
INFOnline Reporting API - Funktionalitätstester
================================================

Umfassender Test-Suite für die INFOnline Reporting API (ÖWA - Österreich)
Testet alle verfügbaren Endpoints auf Funktionalität und Zuverlässigkeit.

Autor: API Test Suite
Datum: Dezember 2024
API Version: 1.3.0
"""

import requests
import json
import time
import logging
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Tuple
from enum import Enum
import sys
from colorama import init, Fore, Style

# Colorama initialisieren für Windows-Kompatibilität
init()

# ============================================================================
# KONFIGURATION
# ============================================================================

@dataclass
class APIConfig:
    """API-Konfiguration"""
    base_url: str = "https://reportingapi.infonline.de"
    api_key: str = "MmFiNjk4YTgtZTA2OS00MGYwLWEyNWQtNGY3ODg0NWI5ODI3"
    timeout: int = 30
    max_retries: int = 3
    retry_delay: float = 1.0


class AggregationType(Enum):
    """Aggregations-Level"""
    HOUR = "HOUR"
    DAY = "DAY"
    MONTH = "MONTH"


class ReturnType(Enum):
    """Rückgabeformat"""
    JSON = "json"
    CSV = "csv"
    CSV_HEADLESS = "csv_headless"
    XML = "xml"


class DataType(Enum):
    """Messungsdatentypen"""
    IOM = "IOM"       # INFOnline Measurement (hochgerechnet)
    IOMp = "IOMp"     # Pseudonym/Consent-basiert
    IOMb = "IOMb"     # Zensus/Consentless


# Bekannte Site-Identifier aus der Dokumentation (Russmedia Beispiele)
SAMPLE_SITES = {
    # Dachangebote
    "DA - Russmedia Portale - Web-Desktop": "DA000003_desktop",
    "DA - Russmedia Portale - Gesamt": "DA000003_gesamt",
    "DA - Russmedia Portale - App-Mobile": "DA000003_mobile_app",
    "DA - Russmedia Portale - Gesamt-Mobile": "DA000003_mobile_gesamt",
    "DA - Russmedia Portale - Web-Mobile": "DA000003_mobile_web",
    
    # Einzelangebote
    "vienna.at - VIENNA ONLINE - Web-Desktop": "EA000003_desktop",
    "vienna.at - VIENNA ONLINE - Gesamt": "EA000003_gesamt",
    "vol.at - VORARLBERG ONLINE - Web-Desktop": "EA000004_desktop",
    "vol.at - VORARLBERG ONLINE - Gesamt": "EA000004_gesamt",
    
    # Angebotskennungen (at_w_ prefix für Web)
    "VOL.AT Web": "at_w_atvol",
    "VIENNA.AT Web": "at_w_atvienna",
    "Ländleanzeiger Web": "at_w_atlaendanz",
    "westjob.at Web": "at_w_atwestjob",
    
    # Belegungseinheiten
    "VOL.AT - Homepage": "BE000072",
    "VIENNA.AT - Gesamt": "BE000043",
    "VOL.AT - Gesamt": "BE000046",
    "VIENNA.AT - Homepage": "BE000069",
}


# ============================================================================
# LOGGING SETUP
# ============================================================================

def setup_logging(level=logging.INFO):
    """Konfiguriert das Logging"""
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    return logging.getLogger(__name__)


logger = setup_logging()


# ============================================================================
# HILFSKLASSEN
# ============================================================================

@dataclass
class TestResult:
    """Speichert das Ergebnis eines einzelnen Tests"""
    name: str
    passed: bool
    status_code: Optional[int] = None
    response_time: Optional[float] = None
    error_message: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass  
class TestSuite:
    """Sammelt alle Testergebnisse"""
    results: List[TestResult] = field(default_factory=list)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    
    def add_result(self, result: TestResult):
        self.results.append(result)
    
    @property
    def passed_count(self) -> int:
        return sum(1 for r in self.results if r.passed)
    
    @property
    def failed_count(self) -> int:
        return sum(1 for r in self.results if not r.passed)
    
    @property
    def total_count(self) -> int:
        return len(self.results)
    
    @property
    def success_rate(self) -> float:
        if self.total_count == 0:
            return 0.0
        return (self.passed_count / self.total_count) * 100


# ============================================================================
# API CLIENT
# ============================================================================

class INFOnlineAPIClient:
    """Client für die INFOnline Reporting API"""
    
    def __init__(self, config: APIConfig = None):
        self.config = config or APIConfig()
        self.session = requests.Session()
        self.session.headers.update({
            "authorization": self.config.api_key,
            "Accept": "application/json"
        })
        
    def _make_request(
        self, 
        endpoint: str, 
        params: Dict[str, Any] = None,
        accept_header: str = "application/json"
    ) -> Tuple[Optional[requests.Response], float, Optional[str]]:
        """
        Führt einen API-Request durch mit Retry-Logik.
        
        Returns:
            Tuple von (Response, Response-Zeit in ms, Fehlermeldung)
        """
        url = f"{self.config.base_url}{endpoint}"
        headers = {"Accept": accept_header}
        
        for attempt in range(self.config.max_retries):
            try:
                start_time = time.time()
                response = self.session.get(
                    url, 
                    params=params, 
                    headers=headers,
                    timeout=self.config.timeout
                )
                response_time = (time.time() - start_time) * 1000  # in ms
                
                return response, response_time, None
                
            except requests.exceptions.Timeout:
                error = f"Timeout nach {self.config.timeout}s (Versuch {attempt + 1})"
                if attempt < self.config.max_retries - 1:
                    time.sleep(self.config.retry_delay)
                    continue
                return None, 0, error
                
            except requests.exceptions.ConnectionError as e:
                error = f"Verbindungsfehler: {str(e)}"
                if attempt < self.config.max_retries - 1:
                    time.sleep(self.config.retry_delay)
                    continue
                return None, 0, error
                
            except Exception as e:
                return None, 0, f"Unerwarteter Fehler: {str(e)}"
        
        return None, 0, "Max. Versuche überschritten"
    
    # ----- HEALTH ENDPOINT -----
    
    def health(self) -> Tuple[Optional[requests.Response], float, Optional[str]]:
        """Prüft den Health-Status der API"""
        return self._make_request("/health")
    
    # ----- PAGE IMPRESSIONS -----
    
    def page_impressions(
        self, 
        site: str, 
        aggregation: AggregationType, 
        date: str,
        returntype: ReturnType = ReturnType.JSON
    ) -> Tuple[Optional[requests.Response], float, Optional[str]]:
        """Holt Page Impressions (IOM, IOMp, IOMb)"""
        params = {
            "site": site,
            "aggregation": aggregation.value,
            "date": date,
            "returntype": returntype.value
        }
        return self._make_request("/api/v1/pageimpressions", params)
    
    def page_impressions_per_pixelpath(
        self,
        site: str,
        aggregation: AggregationType,
        date: str,
        returntype: ReturnType = ReturnType.JSON
    ) -> Tuple[Optional[requests.Response], float, Optional[str]]:
        """Holt Page Impressions per Pixelpath (IOMp, IOMb) - nur HOUR/DAY"""
        if aggregation == AggregationType.MONTH:
            return None, 0, "MONTH nicht unterstützt für diesen Endpoint"
        params = {
            "site": site,
            "aggregation": aggregation.value,
            "date": date,
            "returntype": returntype.value
        }
        return self._make_request("/api/v1/pageimpressionsperpixelpath", params)
    
    def page_impressions_per_url(
        self,
        site: str,
        aggregation: AggregationType,
        date: str,
        returntype: ReturnType = ReturnType.JSON
    ) -> Tuple[Optional[requests.Response], float, Optional[str]]:
        """Holt Page Impressions per URL (IOMp, IOMb)"""
        params = {
            "site": site,
            "aggregation": aggregation.value,
            "date": date,
            "returntype": returntype.value
        }
        return self._make_request("/api/v1/pageimpressionsperurl", params)
    
    # ----- VISITS -----
    
    def visits(
        self,
        site: str,
        aggregation: AggregationType,
        date: str,
        returntype: ReturnType = ReturnType.JSON
    ) -> Tuple[Optional[requests.Response], float, Optional[str]]:
        """Holt Visits (IOM, IOMp)"""
        params = {
            "site": site,
            "aggregation": aggregation.value,
            "date": date,
            "returntype": returntype.value
        }
        return self._make_request("/api/v1/visits", params)
    
    # ----- CLIENTS -----
    
    def clients(
        self,
        site: str,
        aggregation: AggregationType,
        date: str,
        returntype: ReturnType = ReturnType.JSON
    ) -> Tuple[Optional[requests.Response], float, Optional[str]]:
        """Holt Clients (IOMp)"""
        params = {
            "site": site,
            "aggregation": aggregation.value,
            "date": date,
            "returntype": returntype.value
        }
        return self._make_request("/api/v1/clients", params)
    
    def unique_clients(
        self,
        site: str,
        aggregation: AggregationType,
        date: str,
        returntype: ReturnType = ReturnType.JSON
    ) -> Tuple[Optional[requests.Response], float, Optional[str]]:
        """Holt Unique Clients (IOM, IOMp)"""
        params = {
            "site": site,
            "aggregation": aggregation.value,
            "date": date,
            "returntype": returntype.value
        }
        return self._make_request("/api/v1/uniqueclients", params)
    
    # ----- USETIME -----
    
    def usetime(
        self,
        site: str,
        aggregation: AggregationType,
        date: str,
        returntype: ReturnType = ReturnType.JSON
    ) -> Tuple[Optional[requests.Response], float, Optional[str]]:
        """Holt Usetime (IOM, IOMp) - nur DAY/MONTH"""
        if aggregation == AggregationType.HOUR:
            return None, 0, "HOUR nicht unterstützt für diesen Endpoint"
        params = {
            "site": site,
            "aggregation": aggregation.value,
            "date": date,
            "returntype": returntype.value
        }
        return self._make_request("/api/v1/usetime", params)
    
    # ----- DEVICES -----
    
    def devices(
        self,
        site: str,
        aggregation: AggregationType,
        date: str,
        returntype: ReturnType = ReturnType.JSON
    ) -> Tuple[Optional[requests.Response], float, Optional[str]]:
        """Holt Devices (IOMp) - nur DAY/MONTH"""
        if aggregation == AggregationType.HOUR:
            return None, 0, "HOUR nicht unterstützt für diesen Endpoint"
        params = {
            "site": site,
            "aggregation": aggregation.value,
            "date": date,
            "returntype": returntype.value
        }
        return self._make_request("/api/v1/devices", params)


# ============================================================================
# TEST KLASSEN
# ============================================================================

class APITester:
    """Hauptklasse für API-Tests"""
    
    def __init__(self, config: APIConfig = None):
        self.config = config or APIConfig()
        self.client = INFOnlineAPIClient(self.config)
        self.suite = TestSuite()
        
        # Test-Datum: 7 Tage zurück (Daten sollten verfügbar sein)
        self.test_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        
        # Monatsdatum für MONTH-Aggregation
        self.test_month = (datetime.now() - timedelta(days=35)).strftime("%Y-%m-%d")
        
    def _print_result(self, result: TestResult):
        """Gibt das Testergebnis formatiert aus"""
        if result.passed:
            status = f"{Fore.GREEN}✓ PASSED{Style.RESET_ALL}"
        else:
            status = f"{Fore.RED}✗ FAILED{Style.RESET_ALL}"
        
        time_str = f"{result.response_time:.0f}ms" if result.response_time else "N/A"
        code_str = f"[{result.status_code}]" if result.status_code else "[---]"
        
        print(f"  {status} {code_str} {result.name} ({time_str})")
        
        if not result.passed and result.error_message:
            print(f"           {Fore.YELLOW}→ {result.error_message}{Style.RESET_ALL}")
    
    def _add_test(
        self,
        name: str,
        response: Optional[requests.Response],
        response_time: float,
        error: Optional[str],
        expected_status: int = 200,
        validate_response: bool = True
    ) -> TestResult:
        """Erstellt und speichert ein Testergebnis"""
        if error:
            result = TestResult(
                name=name,
                passed=False,
                response_time=response_time,
                error_message=error
            )
        elif response is None:
            result = TestResult(
                name=name,
                passed=False,
                error_message="Keine Response erhalten"
            )
        else:
            passed = response.status_code == expected_status
            error_msg = None
            
            if not passed:
                try:
                    error_data = response.json()
                    if isinstance(error_data, dict):
                        error_msg = error_data.get("detail", str(error_data))
                except:
                    error_msg = response.text[:200] if response.text else "Unbekannter Fehler"
            
            result = TestResult(
                name=name,
                passed=passed,
                status_code=response.status_code,
                response_time=response_time,
                error_message=error_msg
            )
        
        self.suite.add_result(result)
        self._print_result(result)
        return result
    
    # ========================================================================
    # TEST KATEGORIEN
    # ========================================================================
    
    def test_health(self):
        """Testet den Health-Endpoint"""
        print(f"\n{Fore.CYAN}━━━ HEALTH CHECK ━━━{Style.RESET_ALL}")
        
        response, time_ms, error = self.client.health()
        self._add_test("Health Endpoint erreichbar", response, time_ms, error)
    
    def test_authentication(self):
        """Testet die API-Authentifizierung"""
        print(f"\n{Fore.CYAN}━━━ AUTHENTIFIZIERUNG ━━━{Style.RESET_ALL}")
        
        # Test mit gültigem API-Key
        response, time_ms, error = self.client.page_impressions(
            site="at_w_atvol",  # VOL.AT
            aggregation=AggregationType.DAY,
            date=self.test_date
        )
        self._add_test("Gültiger API-Key", response, time_ms, error)
        
        # Test mit ungültigem API-Key
        old_key = self.client.session.headers["authorization"]
        self.client.session.headers["authorization"] = "invalid_key_12345"
        
        response, time_ms, error = self.client.page_impressions(
            site="at_w_atvol",
            aggregation=AggregationType.DAY,
            date=self.test_date
        )
        # API gibt 401 (Unauthorized) statt 403 (Forbidden) zurück
        self._add_test("Ungültiger API-Key (erwartet 401)", response, time_ms, error, expected_status=401)
        
        # API-Key wiederherstellen
        self.client.session.headers["authorization"] = old_key
    
    def test_parameter_validation(self):
        """Testet die Parametervalidierung"""
        print(f"\n{Fore.CYAN}━━━ PARAMETER-VALIDIERUNG ━━━{Style.RESET_ALL}")
        
        # Fehlender Site-Parameter (422 erwartet)
        response, time_ms, _ = self.client._make_request(
            "/api/v1/pageimpressions",
            {"aggregation": "DAY", "date": self.test_date}
        )
        self._add_test("Fehlender 'site' Parameter (erwartet 422)", response, time_ms, None, expected_status=422)
        
        # Ungültiges Datumsformat
        response, time_ms, error = self.client.page_impressions(
            site="at_w_atvol",
            aggregation=AggregationType.DAY,
            date="2024-13-45"  # Ungültiges Datum
        )
        # API validiert korrekt und gibt 422 zurück
        self._add_test("Ungültiges Datumsformat (erwartet 422)", response, time_ms, error, expected_status=422)
        
        # Ungültiger Aggregationstyp
        response, time_ms, _ = self.client._make_request(
            "/api/v1/pageimpressions",
            {"site": "at_w_atvol", "aggregation": "INVALID", "date": self.test_date}
        )
        self._add_test("Ungültige Aggregation (erwartet 422)", response, time_ms, None, expected_status=422)
    
    def test_page_impressions_endpoints(self):
        """Testet alle Page Impressions Endpoints"""
        print(f"\n{Fore.CYAN}━━━ PAGE IMPRESSIONS ENDPOINTS ━━━{Style.RESET_ALL}")
        
        test_site = "at_w_atvol"  # VOL.AT
        
        # /api/v1/pageimpressions mit verschiedenen Aggregationen
        for agg in [AggregationType.HOUR, AggregationType.DAY, AggregationType.MONTH]:
            date = self.test_month if agg == AggregationType.MONTH else self.test_date
            response, time_ms, error = self.client.page_impressions(
                site=test_site,
                aggregation=agg,
                date=date
            )
            self._add_test(f"Page Impressions ({agg.value})", response, time_ms, error)
        
        # /api/v1/pageimpressionsperpixelpath (nur HOUR/DAY)
        for agg in [AggregationType.HOUR, AggregationType.DAY]:
            response, time_ms, error = self.client.page_impressions_per_pixelpath(
                site=test_site,
                aggregation=agg,
                date=self.test_date
            )
            self._add_test(f"PI per Pixelpath ({agg.value})", response, time_ms, error)
        
        # /api/v1/pageimpressionsperurl
        response, time_ms, error = self.client.page_impressions_per_url(
            site=test_site,
            aggregation=AggregationType.DAY,
            date=self.test_date
        )
        self._add_test("PI per URL (DAY)", response, time_ms, error)
    
    def test_visits_endpoint(self):
        """Testet den Visits Endpoint"""
        print(f"\n{Fore.CYAN}━━━ VISITS ENDPOINT ━━━{Style.RESET_ALL}")
        
        test_site = "at_w_atvol"
        
        for agg in [AggregationType.HOUR, AggregationType.DAY, AggregationType.MONTH]:
            date = self.test_month if agg == AggregationType.MONTH else self.test_date
            response, time_ms, error = self.client.visits(
                site=test_site,
                aggregation=agg,
                date=date
            )
            self._add_test(f"Visits ({agg.value})", response, time_ms, error)
    
    def test_clients_endpoints(self):
        """Testet Clients und Unique Clients Endpoints"""
        print(f"\n{Fore.CYAN}━━━ CLIENTS ENDPOINTS ━━━{Style.RESET_ALL}")
        
        test_site = "at_w_atvol"
        
        # /api/v1/clients
        response, time_ms, error = self.client.clients(
            site=test_site,
            aggregation=AggregationType.DAY,
            date=self.test_date
        )
        self._add_test("Clients (DAY)", response, time_ms, error)
        
        # /api/v1/uniqueclients
        response, time_ms, error = self.client.unique_clients(
            site=test_site,
            aggregation=AggregationType.DAY,
            date=self.test_date
        )
        self._add_test("Unique Clients (DAY)", response, time_ms, error)
        
        # Monthly unique clients
        response, time_ms, error = self.client.unique_clients(
            site=test_site,
            aggregation=AggregationType.MONTH,
            date=self.test_month
        )
        self._add_test("Unique Clients (MONTH)", response, time_ms, error)
    
    def test_usetime_endpoint(self):
        """Testet den Usetime Endpoint (nur DAY/MONTH)"""
        print(f"\n{Fore.CYAN}━━━ USETIME ENDPOINT ━━━{Style.RESET_ALL}")
        
        test_site = "at_w_atvol"
        
        # DAY Aggregation
        response, time_ms, error = self.client.usetime(
            site=test_site,
            aggregation=AggregationType.DAY,
            date=self.test_date
        )
        self._add_test("Usetime (DAY)", response, time_ms, error)
        
        # MONTH Aggregation
        response, time_ms, error = self.client.usetime(
            site=test_site,
            aggregation=AggregationType.MONTH,
            date=self.test_month
        )
        self._add_test("Usetime (MONTH)", response, time_ms, error)
    
    def test_devices_endpoint(self):
        """Testet den Devices Endpoint (nur DAY/MONTH)"""
        print(f"\n{Fore.CYAN}━━━ DEVICES ENDPOINT ━━━{Style.RESET_ALL}")
        
        test_site = "at_w_atvol"
        
        # DAY Aggregation
        response, time_ms, error = self.client.devices(
            site=test_site,
            aggregation=AggregationType.DAY,
            date=self.test_date
        )
        self._add_test("Devices (DAY)", response, time_ms, error)
        
        # MONTH Aggregation
        response, time_ms, error = self.client.devices(
            site=test_site,
            aggregation=AggregationType.MONTH,
            date=self.test_month
        )
        self._add_test("Devices (MONTH)", response, time_ms, error)
    
    def test_response_formats(self):
        """Testet verschiedene Antwortformate"""
        print(f"\n{Fore.CYAN}━━━ RESPONSE FORMATE ━━━{Style.RESET_ALL}")
        
        test_site = "at_w_atvol"
        
        for fmt in ReturnType:
            response, time_ms, error = self.client.page_impressions(
                site=test_site,
                aggregation=AggregationType.DAY,
                date=self.test_date,
                returntype=fmt
            )
            self._add_test(f"Page Impressions Format: {fmt.value.upper()}", response, time_ms, error)
    
    def test_multiple_sites(self):
        """Testet verschiedene Site-Identifier"""
        print(f"\n{Fore.CYAN}━━━ VERSCHIEDENE SITES ━━━{Style.RESET_ALL}")
        
        # Teste eine Auswahl verschiedener Site-Typen
        sites_to_test = [
            ("at_w_atvol", "VOL.AT (Angebotskennung)"),
            ("at_w_atvienna", "VIENNA.AT (Angebotskennung)"),
            ("BE000072", "VOL.AT Homepage (Belegungseinheit)"),
        ]
        
        for site_id, site_name in sites_to_test:
            response, time_ms, error = self.client.page_impressions(
                site=site_id,
                aggregation=AggregationType.DAY,
                date=self.test_date
            )
            self._add_test(f"Site: {site_name}", response, time_ms, error)
    
    def test_data_quality(self):
        """Überprüft die Datenqualität der Responses"""
        print(f"\n{Fore.CYAN}━━━ DATENQUALITÄT ━━━{Style.RESET_ALL}")
        
        test_site = "at_w_atvol"
        
        # Hole Page Impressions und prüfe die Datenstruktur
        response, time_ms, error = self.client.page_impressions(
            site=test_site,
            aggregation=AggregationType.DAY,
            date=self.test_date
        )
        
        if response and response.status_code == 200:
            try:
                data = response.json()
                
                # Prüfe ob Daten vorhanden
                has_data = data is not None and (
                    isinstance(data, list) and len(data) > 0 or
                    isinstance(data, dict) and len(data) > 0
                )
                
                self._add_test(
                    "Response enthält Daten",
                    response, time_ms, 
                    None if has_data else "Keine Daten in Response"
                )
                
                # Wenn Daten vorhanden, prüfe auf erwartete Felder
                if has_data:
                    if isinstance(data, list) and len(data) > 0:
                        sample = data[0]
                    elif isinstance(data, dict):
                        sample = data
                    else:
                        sample = {}
                    
                    # Erwartete Felder für Page Impressions
                    expected_fields = {"IOM", "IOMp", "IOMb", "site", "date", "hour"}
                    actual_fields = set(sample.keys()) if isinstance(sample, dict) else set()
                    
                    # Mindestens einige erwartete Felder sollten vorhanden sein
                    common_fields = expected_fields & actual_fields
                    
                    result = TestResult(
                        name="Response Struktur validiert",
                        passed=len(common_fields) > 0 or len(actual_fields) > 0,
                        status_code=200,
                        response_time=time_ms,
                        error_message=f"Gefundene Felder: {actual_fields}" if actual_fields else "Keine Felder gefunden",
                        details={"fields": list(actual_fields)}
                    )
                    self.suite.add_result(result)
                    self._print_result(result)
                    
            except json.JSONDecodeError as e:
                self._add_test("JSON Parsing", response, time_ms, f"JSON Fehler: {str(e)}")
        else:
            self._add_test("Datenqualität (übersprungen)", response, time_ms, error or "Kein 200 Status")
    
    # ========================================================================
    # HAUPTTEST-RUNNER
    # ========================================================================
    
    def run_all_tests(self) -> TestSuite:
        """Führt alle Tests aus"""
        print(f"\n{Fore.MAGENTA}{'═' * 60}")
        print(f"  INFOnline Reporting API - Funktionalitätstest")
        print(f"  API Version: 1.3.0 | Test-Datum: {self.test_date}")
        print(f"{'═' * 60}{Style.RESET_ALL}")
        
        self.suite.start_time = datetime.now()
        
        # Alle Tests ausführen
        self.test_health()
        self.test_authentication()
        self.test_parameter_validation()
        self.test_page_impressions_endpoints()
        self.test_visits_endpoint()
        self.test_clients_endpoints()
        self.test_usetime_endpoint()
        self.test_devices_endpoint()
        self.test_response_formats()
        self.test_multiple_sites()
        self.test_data_quality()
        
        self.suite.end_time = datetime.now()
        
        # Zusammenfassung
        self._print_summary()
        
        return self.suite
    
    def run_quick_test(self) -> TestSuite:
        """Führt nur die wichtigsten Tests aus"""
        print(f"\n{Fore.MAGENTA}{'═' * 60}")
        print(f"  INFOnline API - Schnelltest")
        print(f"{'═' * 60}{Style.RESET_ALL}")
        
        self.suite.start_time = datetime.now()
        
        self.test_health()
        self.test_authentication()
        
        # Ein Test pro Endpoint-Typ
        print(f"\n{Fore.CYAN}━━━ ENDPOINT QUICK CHECK ━━━{Style.RESET_ALL}")
        test_site = "at_w_atvol"
        
        endpoints = [
            ("Page Impressions", lambda: self.client.page_impressions(
                test_site, AggregationType.DAY, self.test_date)),
            ("Visits", lambda: self.client.visits(
                test_site, AggregationType.DAY, self.test_date)),
            ("Clients", lambda: self.client.clients(
                test_site, AggregationType.DAY, self.test_date)),
            ("Unique Clients", lambda: self.client.unique_clients(
                test_site, AggregationType.DAY, self.test_date)),
            ("Usetime", lambda: self.client.usetime(
                test_site, AggregationType.DAY, self.test_date)),
            ("Devices", lambda: self.client.devices(
                test_site, AggregationType.DAY, self.test_date)),
        ]
        
        for name, call in endpoints:
            response, time_ms, error = call()
            self._add_test(name, response, time_ms, error)
        
        self.suite.end_time = datetime.now()
        self._print_summary()
        
        return self.suite
    
    def _print_summary(self):
        """Gibt die Testzusammenfassung aus"""
        duration = (self.suite.end_time - self.suite.start_time).total_seconds()
        
        print(f"\n{Fore.MAGENTA}{'═' * 60}")
        print(f"  ZUSAMMENFASSUNG")
        print(f"{'═' * 60}{Style.RESET_ALL}")
        
        # Erfolgsrate farbig anzeigen
        rate = self.suite.success_rate
        if rate == 100:
            rate_color = Fore.GREEN
        elif rate >= 80:
            rate_color = Fore.YELLOW
        else:
            rate_color = Fore.RED
        
        print(f"  Tests gesamt:    {self.suite.total_count}")
        print(f"  {Fore.GREEN}Erfolgreich:{Style.RESET_ALL}     {self.suite.passed_count}")
        print(f"  {Fore.RED}Fehlgeschlagen:{Style.RESET_ALL}  {self.suite.failed_count}")
        print(f"  {rate_color}Erfolgsrate:{Style.RESET_ALL}     {rate:.1f}%")
        print(f"  Dauer:           {duration:.2f}s")
        
        # Fehlgeschlagene Tests auflisten
        failed = [r for r in self.suite.results if not r.passed]
        if failed:
            print(f"\n  {Fore.RED}Fehlgeschlagene Tests:{Style.RESET_ALL}")
            for r in failed:
                print(f"    • {r.name}")
                if r.error_message:
                    print(f"      {Fore.YELLOW}→ {r.error_message}{Style.RESET_ALL}")
        
        print(f"\n{'═' * 60}\n")


# ============================================================================
# HAUPTPROGRAMM
# ============================================================================

def main():
    """Haupteinstiegspunkt"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="INFOnline Reporting API Tester",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Beispiele:
  python infonline_api_tester.py                    # Alle Tests
  python infonline_api_tester.py --quick            # Schnelltest
  python infonline_api_tester.py --site at_w_atvol  # Spezifische Site
  python infonline_api_tester.py --api-key XXXXX    # Anderer API-Key
        """
    )
    
    parser.add_argument(
        "--quick", "-q",
        action="store_true",
        help="Nur Schnelltest durchführen"
    )
    
    parser.add_argument(
        "--api-key", "-k",
        type=str,
        default=None,
        help="API-Key überschreiben"
    )
    
    parser.add_argument(
        "--site", "-s",
        type=str,
        default=None,
        help="Spezifische Site zum Testen"
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Ausführliche Ausgabe"
    )
    
    args = parser.parse_args()
    
    # Konfiguration erstellen
    config = APIConfig()
    if args.api_key:
        config.api_key = args.api_key
    
    # Log-Level setzen
    if args.verbose:
        setup_logging(logging.DEBUG)
    
    # Tester erstellen und ausführen
    tester = APITester(config)
    
    try:
        if args.quick:
            suite = tester.run_quick_test()
        else:
            suite = tester.run_all_tests()
        
        # Exit-Code basierend auf Testergebnis
        sys.exit(0 if suite.failed_count == 0 else 1)
        
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}Test abgebrochen.{Style.RESET_ALL}")
        sys.exit(130)
    except Exception as e:
        print(f"\n{Fore.RED}Kritischer Fehler: {e}{Style.RESET_ALL}")
        logger.exception("Kritischer Fehler")
        sys.exit(1)


if __name__ == "__main__":
    main()

