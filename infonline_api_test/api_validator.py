"""
INFOnline API Validator
=======================

Testet die INFOnline Reporting API und validiert:
- Verbindung und Authentifizierung
- Parameter-Validierung
- Response-Struktur und Dateninhalt

Nutzung:
    python api_validator.py
    python api_validator.py --site BE000072
    python api_validator.py --date 2025-11-01
"""

import requests
import json
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Dict, Any, List, Optional
import sys

# ============================================================================
# KONFIGURATION
# ============================================================================

API_BASE_URL = "https://reportingapi.infonline.de"
API_KEY = "MmFiNjk4YTgtZTA2OS00MGYwLWEyNWQtNGY3ODg0NWI5ODI3"

# Standard Test-Site (VOL.AT)
DEFAULT_SITE = "at_w_atvol"

# Verfügbare Endpoints für ÖWA (Austria)
# Hinweis: Die API gibt Daten in verschachtelter Struktur zurück:
# { "metadata": {...}, "data": { "iom": [...], "iomb": [...], "iomp": [...] } }
ENDPOINTS = {
    "pageimpressions": {
        "path": "/api/v1/pageimpressions",
        "description": "Page Impressions (IOM, IOMp, IOMb)",
        "aggregations": ["HOUR", "DAY", "MONTH"],
        "expected_fields": ["iom", "iomb", "iomp"]  # Kleinbuchstaben in API
    },
    "pageimpressionsperpixelpath": {
        "path": "/api/v1/pageimpressionsperpixelpath",
        "description": "PI per Pixelpath (IOMp, IOMb)",
        "aggregations": ["HOUR", "DAY"],  # MONTH nicht unterstützt
        "expected_fields": ["iomb", "iomp"]
    },
    "pageimpressionsperurl": {
        "path": "/api/v1/pageimpressionsperurl",
        "description": "PI per URL (IOMp, IOMb)",
        "aggregations": ["HOUR", "DAY", "MONTH"],
        "expected_fields": ["iomb", "iomp"]
    },
    "visits": {
        "path": "/api/v1/visits",
        "description": "Visits (IOM, IOMp)",
        "aggregations": ["HOUR", "DAY", "MONTH"],
        "expected_fields": ["iom", "iomp"]
    },
    "clients": {
        "path": "/api/v1/clients",
        "description": "Clients (IOMp)",
        "aggregations": ["HOUR", "DAY", "MONTH"],
        "expected_fields": ["iomp"]
    },
    "uniqueclients": {
        "path": "/api/v1/uniqueclients",
        "description": "Unique Clients (IOM, IOMp)",
        "aggregations": ["HOUR", "DAY", "MONTH"],
        "expected_fields": ["iom", "iomp"]
    },
    "usetime": {
        "path": "/api/v1/usetime",
        "description": "Usetime (IOM, IOMp)",
        "aggregations": ["DAY", "MONTH"],  # HOUR nicht unterstützt
        "expected_fields": ["iom", "iomp"]
    },
    "devices": {
        "path": "/api/v1/devices",
        "description": "Devices (IOMp)",
        "aggregations": ["DAY", "MONTH"],  # HOUR nicht unterstützt
        "expected_fields": ["iomp"]
    }
}


# ============================================================================
# FARBEN FÜR KONSOLE
# ============================================================================

class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    MAGENTA = "\033[95m"
    BOLD = "\033[1m"
    END = "\033[0m"


def print_header(text: str):
    print(f"\n{Colors.CYAN}{Colors.BOLD}{'═' * 60}")
    print(f"  {text}")
    print(f"{'═' * 60}{Colors.END}")


def print_section(text: str):
    print(f"\n{Colors.MAGENTA}━━━ {text} ━━━{Colors.END}")


def print_ok(text: str):
    print(f"  {Colors.GREEN}✓{Colors.END} {text}")


def print_fail(text: str):
    print(f"  {Colors.RED}✗{Colors.END} {text}")


def print_warn(text: str):
    print(f"  {Colors.YELLOW}⚠{Colors.END} {text}")


def print_info(text: str):
    print(f"  {Colors.CYAN}ℹ{Colors.END} {text}")


# ============================================================================
# VALIDATION RESULT
# ============================================================================

@dataclass
class ValidationResult:
    endpoint: str
    success: bool
    status_code: int
    has_data: bool
    data_count: int
    fields_found: List[str]
    fields_missing: List[str]
    response_time_ms: float
    error_message: Optional[str] = None


# ============================================================================
# API VALIDATOR
# ============================================================================

class INFOnlineAPIValidator:
    """Validiert die INFOnline Reporting API"""
    
    def __init__(self, api_key: str = API_KEY, base_url: str = API_BASE_URL):
        self.api_key = api_key
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            "authorization": api_key,
            "Accept": "application/json"
        })
        self.results: List[ValidationResult] = []
    
    def _call_api(self, endpoint: str, params: Dict[str, Any]) -> tuple:
        """
        Ruft die API auf und gibt (response, time_ms, error) zurück
        """
        url = f"{self.base_url}{endpoint}"
        
        try:
            import time
            start = time.time()
            response = self.session.get(url, params=params, timeout=30)
            time_ms = (time.time() - start) * 1000
            return response, time_ms, None
        except requests.exceptions.Timeout:
            return None, 0, "Timeout"
        except requests.exceptions.ConnectionError as e:
            return None, 0, f"Verbindungsfehler: {e}"
        except Exception as e:
            return None, 0, f"Fehler: {e}"
    
    def validate_health(self) -> bool:
        """Prüft ob die API erreichbar ist"""
        print_section("API Health Check")
        
        response, time_ms, error = self._call_api("/health", {})
        
        if error:
            print_fail(f"API nicht erreichbar: {error}")
            return False
        
        if response.status_code == 200:
            print_ok(f"API erreichbar ({time_ms:.0f}ms)")
            return True
        else:
            print_fail(f"API Fehler: Status {response.status_code}")
            return False
    
    def validate_authentication(self, site: str, date: str) -> bool:
        """Prüft die API-Authentifizierung"""
        print_section("Authentifizierung")
        
        # Test mit aktuellem Key
        response, time_ms, error = self._call_api(
            "/api/v1/pageimpressions",
            {"site": site, "aggregation": "DAY", "date": date}
        )
        
        if error:
            print_fail(f"API-Aufruf fehlgeschlagen: {error}")
            return False
        
        if response.status_code == 200:
            print_ok(f"API-Key gültig ({time_ms:.0f}ms)")
            return True
        elif response.status_code == 401:
            print_fail("API-Key ungültig (401 Unauthorized)")
            return False
        elif response.status_code == 403:
            print_fail("Zugriff verweigert (403 Forbidden)")
            return False
        else:
            print_fail(f"Unerwarteter Status: {response.status_code}")
            return False
    
    def validate_parameters(self, site: str, date: str):
        """Validiert die Parameter-Behandlung"""
        print_section("Parameter-Validierung")
        
        import time
        
        tests = [
            ("Fehlender 'site' Parameter", {"aggregation": "DAY", "date": date}),
            ("Fehlender 'aggregation' Parameter", {"site": site, "date": date}),
            ("Fehlender 'date' Parameter", {"site": site, "aggregation": "DAY"}),
            ("Ungültiges Datumsformat", {"site": site, "aggregation": "DAY", "date": "invalid-date"}),
            ("Ungültige Aggregation", {"site": site, "aggregation": "INVALID", "date": date}),
        ]
        
        for test_name, params in tests:
            time.sleep(0.1)  # Kleine Pause zwischen Requests
            response, _, error = self._call_api("/api/v1/pageimpressions", params)
            
            if error:
                print_warn(f"{test_name}: Fehler - {error}")
            elif response is None:
                print_warn(f"{test_name}: Keine Response")
            elif response.status_code == 422:
                print_ok(f"{test_name} wird erkannt (422)")
            else:
                print_warn(f"{test_name}: Status {response.status_code}")
    
    def validate_endpoint(
        self, 
        name: str, 
        config: Dict, 
        site: str, 
        date: str,
        aggregation: str = "DAY"
    ) -> ValidationResult:
        """Validiert einen einzelnen Endpoint"""
        
        # Prüfe ob Aggregation unterstützt wird
        if aggregation not in config["aggregations"]:
            aggregation = config["aggregations"][0]
        
        response, time_ms, error = self._call_api(
            config["path"],
            {"site": site, "aggregation": aggregation, "date": date}
        )
        
        if error:
            return ValidationResult(
                endpoint=name,
                success=False,
                status_code=0,
                has_data=False,
                data_count=0,
                fields_found=[],
                fields_missing=config["expected_fields"],
                response_time_ms=0,
                error_message=error
            )
        
        if response.status_code != 200:
            error_msg = response.text[:100] if response.text else "Unbekannter Fehler"
            return ValidationResult(
                endpoint=name,
                success=False,
                status_code=response.status_code,
                has_data=False,
                data_count=0,
                fields_found=[],
                fields_missing=config["expected_fields"],
                response_time_ms=time_ms,
                error_message=error_msg
            )
        
        # Parse JSON Response
        try:
            data = response.json()
        except json.JSONDecodeError:
            return ValidationResult(
                endpoint=name,
                success=False,
                status_code=200,
                has_data=False,
                data_count=0,
                fields_found=[],
                fields_missing=config["expected_fields"],
                response_time_ms=time_ms,
                error_message="JSON Parse Error"
            )
        
        # Analysiere Daten - API gibt verschachtelte Struktur zurück
        # { "metadata": {...}, "data": { "iom": [...], "iomb": [...], "iomp": [...] } }
        
        fields_found = []
        fields_missing = []
        data_count = 0
        
        if isinstance(data, dict):
            # Prüfe auf verschachtelte Struktur
            if "data" in data and isinstance(data["data"], dict):
                inner_data = data["data"]
                
                # Zähle Datensätze über alle Arrays
                for field in config["expected_fields"]:
                    if field in inner_data:
                        fields_found.append(field)
                        if isinstance(inner_data[field], list):
                            data_count = max(data_count, len(inner_data[field]))
                    else:
                        fields_missing.append(field)
            
            # Prüfe auch auf flache Struktur (falls API-Format sich ändert)
            elif not fields_found:
                for field in config["expected_fields"]:
                    if field in data:
                        fields_found.append(field)
                    else:
                        fields_missing.append(field)
                data_count = 1 if fields_found else 0
        
        elif isinstance(data, list):
            data_count = len(data)
            sample = data[0] if data else {}
            if isinstance(sample, dict):
                for field in config["expected_fields"]:
                    if field in sample:
                        fields_found.append(field)
                    else:
                        fields_missing.append(field)
        
        return ValidationResult(
            endpoint=name,
            success=True,
            status_code=200,
            has_data=data_count > 0,
            data_count=data_count,
            fields_found=fields_found,
            fields_missing=fields_missing,
            response_time_ms=time_ms
        )
    
    def validate_all_endpoints(self, site: str, date: str):
        """Validiert alle Endpoints"""
        print_section("Endpoint-Validierung")
        
        for name, config in ENDPOINTS.items():
            result = self.validate_endpoint(name, config, site, date)
            self.results.append(result)
            
            if result.success:
                if result.has_data:
                    print_ok(f"{config['description']}")
                    print_info(f"  → {result.data_count} Datensätze, {result.response_time_ms:.0f}ms")
                    if result.fields_found:
                        print_info(f"  → Felder: {', '.join(result.fields_found)}")
                    if result.fields_missing:
                        print_warn(f"  → Fehlend: {', '.join(result.fields_missing)}")
                else:
                    print_warn(f"{config['description']} - Keine Daten (möglicherweise kein Traffic)")
            else:
                print_fail(f"{config['description']}")
                if result.error_message:
                    print_info(f"  → Fehler: {result.error_message}")
    
    def validate_response_formats(self, site: str, date: str):
        """Prüft verschiedene Response-Formate"""
        print_section("Response-Formate")
        
        formats = ["json", "csv", "xml"]
        
        for fmt in formats:
            response, time_ms, error = self._call_api(
                "/api/v1/pageimpressions",
                {"site": site, "aggregation": "DAY", "date": date, "returntype": fmt}
            )
            
            if error:
                print_fail(f"Format {fmt.upper()}: {error}")
            elif response.status_code == 200:
                content_length = len(response.content)
                print_ok(f"Format {fmt.upper()}: OK ({content_length} Bytes, {time_ms:.0f}ms)")
            else:
                print_fail(f"Format {fmt.upper()}: Status {response.status_code}")
    
    def print_data_sample(self, site: str, date: str):
        """Zeigt ein Beispiel der zurückgegebenen Daten"""
        print_section("Daten-Beispiel (Page Impressions)")
        
        response, _, error = self._call_api(
            "/api/v1/pageimpressions",
            {"site": site, "aggregation": "DAY", "date": date}
        )
        
        if error or response.status_code != 200:
            print_fail("Keine Daten verfügbar")
            return
        
        try:
            data = response.json()
            
            if isinstance(data, list) and len(data) > 0:
                sample = data[0]
                print_info("Erster Datensatz:")
                print(f"\n{Colors.CYAN}{json.dumps(sample, indent=2, ensure_ascii=False)}{Colors.END}\n")
            elif isinstance(data, dict):
                print_info("Response:")
                # Kürze sehr lange Daten
                data_str = json.dumps(data, indent=2, ensure_ascii=False)
                if len(data_str) > 500:
                    data_str = data_str[:500] + "\n... (gekürzt)"
                print(f"\n{Colors.CYAN}{data_str}{Colors.END}\n")
            else:
                print_warn("Unerwartetes Datenformat")
                
        except Exception as e:
            print_fail(f"Fehler beim Parsen: {e}")
    
    def print_summary(self):
        """Gibt eine Zusammenfassung aus"""
        print_header("ZUSAMMENFASSUNG")
        
        total = len(self.results)
        success = sum(1 for r in self.results if r.success)
        with_data = sum(1 for r in self.results if r.has_data)
        
        print(f"  Endpoints getestet:  {total}")
        print(f"  Erfolgreich:         {Colors.GREEN}{success}/{total}{Colors.END}")
        print(f"  Mit Daten:           {Colors.CYAN}{with_data}/{total}{Colors.END}")
        
        # Durchschnittliche Response-Zeit
        times = [r.response_time_ms for r in self.results if r.response_time_ms > 0]
        if times:
            avg_time = sum(times) / len(times)
            print(f"  Ø Response-Zeit:     {avg_time:.0f}ms")
        
        # Fehlgeschlagene Tests
        failed = [r for r in self.results if not r.success]
        if failed:
            print(f"\n  {Colors.RED}Fehlgeschlagene Endpoints:{Colors.END}")
            for r in failed:
                print(f"    • {r.endpoint}: {r.error_message or f'Status {r.status_code}'}")
        
        # Gesamt-Status
        if success == total and with_data > 0:
            print(f"\n  {Colors.GREEN}{Colors.BOLD}✓ API funktioniert einwandfrei!{Colors.END}")
        elif success == total:
            print(f"\n  {Colors.YELLOW}⚠ API erreichbar, aber keine Daten verfügbar{Colors.END}")
        else:
            print(f"\n  {Colors.RED}✗ Es gibt Probleme mit der API{Colors.END}")


# ============================================================================
# HAUPTPROGRAMM
# ============================================================================

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="INFOnline API Validator")
    parser.add_argument("--site", "-s", default=DEFAULT_SITE, 
                        help=f"Site-Identifier (default: {DEFAULT_SITE})")
    parser.add_argument("--date", "-d", default=None,
                        help="Datum im Format YYYY-MM-DD (default: vor 7 Tagen)")
    parser.add_argument("--api-key", "-k", default=API_KEY,
                        help="API-Key")
    parser.add_argument("--show-data", action="store_true",
                        help="Zeige Beispiel-Daten")
    
    args = parser.parse_args()
    
    # Datum setzen
    if args.date:
        test_date = args.date
    else:
        test_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    
    print_header("INFOnline API Validator")
    print(f"  Site:     {args.site}")
    print(f"  Datum:    {test_date}")
    print(f"  API-Key:  {args.api_key[:8]}...{args.api_key[-4:]}")
    
    # Validator erstellen und ausführen
    validator = INFOnlineAPIValidator(api_key=args.api_key)
    
    # 1. Health Check
    if not validator.validate_health():
        print_fail("\nAPI nicht erreichbar. Abbruch.")
        sys.exit(1)
    
    # 2. Authentifizierung prüfen
    if not validator.validate_authentication(args.site, test_date):
        print_fail("\nAuthentifizierung fehlgeschlagen. Abbruch.")
        sys.exit(1)
    
    # 3. Parameter-Validierung
    validator.validate_parameters(args.site, test_date)
    
    # 4. Alle Endpoints testen
    validator.validate_all_endpoints(args.site, test_date)
    
    # 5. Response-Formate prüfen
    validator.validate_response_formats(args.site, test_date)
    
    # 6. Optional: Daten-Beispiel
    if args.show_data:
        validator.print_data_sample(args.site, test_date)
    
    # 7. Zusammenfassung
    validator.print_summary()


if __name__ == "__main__":
    main()

