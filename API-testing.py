"""
ÖWA / INFOnline Reporting API - Test Script
============================================

Testet die INFOnline Reporting API für Österreich (ÖWA).
Prüft Verbindung, Authentifizierung, Parameter und Datenrückgabe.

Nutzung:
    python API-testing.py
    python API-testing.py --site BE000072
    python API-testing.py --show-data
"""

import requests
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
import sys

# ============================================================================
# KONFIGURATION
# ============================================================================

API_CONFIG = {
    "base_url": "https://reportingapi.infonline.de",
    "api_key": "MmFiNjk4YTgtZTA2OS00MGYwLWEyNWQtNGY3ODg0NWI5ODI3",
    "timeout": 30
}

# Standard Test-Site (VOL.AT)
DEFAULT_SITE = "at_w_atvol"

# Verfügbare ÖWA Endpoints
OEWA_ENDPOINTS = {
    "pageimpressions": {
        "path": "/api/v1/pageimpressions",
        "name": "Page Impressions",
        "beschreibung": "Seitenaufrufe (IOM, IOMp, IOMb)",
        "aggregationen": ["HOUR", "DAY", "MONTH"],
        "datentypen": ["iom", "iomb", "iomp"]
    },
    "pageimpressionsperpixelpath": {
        "path": "/api/v1/pageimpressionsperpixelpath",
        "name": "PI per Pixelpath",
        "beschreibung": "Seitenaufrufe nach Pixelpath",
        "aggregationen": ["HOUR", "DAY"],
        "datentypen": ["iomb", "iomp"]
    },
    "pageimpressionsperurl": {
        "path": "/api/v1/pageimpressionsperurl",
        "name": "PI per URL",
        "beschreibung": "Seitenaufrufe nach URL",
        "aggregationen": ["HOUR", "DAY", "MONTH"],
        "datentypen": ["iomb", "iomp"]
    },
    "visits": {
        "path": "/api/v1/visits",
        "name": "Visits",
        "beschreibung": "Besuche",
        "aggregationen": ["HOUR", "DAY", "MONTH"],
        "datentypen": ["iom", "iomp"]
    },
    "clients": {
        "path": "/api/v1/clients",
        "name": "Clients",
        "beschreibung": "Clients/Browser",
        "aggregationen": ["HOUR", "DAY", "MONTH"],
        "datentypen": ["iomp"]
    },
    "uniqueclients": {
        "path": "/api/v1/uniqueclients",
        "name": "Unique Clients",
        "beschreibung": "Eindeutige Clients",
        "aggregationen": ["HOUR", "DAY", "MONTH"],
        "datentypen": ["iom", "iomp"]
    },
    "usetime": {
        "path": "/api/v1/usetime",
        "name": "Usetime",
        "beschreibung": "Nutzungszeit",
        "aggregationen": ["DAY", "MONTH"],
        "datentypen": ["iom", "iomp"]
    },
    "devices": {
        "path": "/api/v1/devices",
        "name": "Devices",
        "beschreibung": "Gerätetypen",
        "aggregationen": ["DAY", "MONTH"],
        "datentypen": ["iomp"]
    }
}

# Bekannte Site-Identifier (Russmedia)
SITE_IDENTIFIER = {
    "at_w_atvol": "VOL.AT (Web)",
    "at_w_atvienna": "VIENNA.AT (Web)",
    "at_w_atlaendanz": "Ländleanzeiger (Web)",
    "at_w_atwestjob": "westjob.at (Web)",
    "BE000072": "VOL.AT - Homepage",
    "BE000043": "VIENNA.AT - Gesamt",
    "BE000046": "VOL.AT - Gesamt",
    "BE000069": "VIENNA.AT - Homepage",
}


# ============================================================================
# KONSOLEN-FORMATIERUNG
# ============================================================================

class Farben:
    GRUEN = "\033[92m"
    ROT = "\033[91m"
    GELB = "\033[93m"
    CYAN = "\033[96m"
    MAGENTA = "\033[95m"
    FETT = "\033[1m"
    ENDE = "\033[0m"


def drucke_header(text: str):
    print(f"\n{Farben.CYAN}{Farben.FETT}{'═' * 65}")
    print(f"  {text}")
    print(f"{'═' * 65}{Farben.ENDE}")


def drucke_abschnitt(text: str):
    print(f"\n{Farben.MAGENTA}━━━ {text} ━━━{Farben.ENDE}")


def drucke_ok(text: str):
    print(f"  {Farben.GRUEN}✓{Farben.ENDE} {text}")


def drucke_fehler(text: str):
    print(f"  {Farben.ROT}✗{Farben.ENDE} {text}")


def drucke_warnung(text: str):
    print(f"  {Farben.GELB}⚠{Farben.ENDE} {text}")


def drucke_info(text: str):
    print(f"  {Farben.CYAN}ℹ{Farben.ENDE} {text}")


# ============================================================================
# API CLIENT
# ============================================================================

class OEWAApiClient:
    """Client für die ÖWA/INFOnline Reporting API"""
    
    def __init__(self, api_key: str = None, base_url: str = None):
        self.api_key = api_key or API_CONFIG["api_key"]
        self.base_url = base_url or API_CONFIG["base_url"]
        self.timeout = API_CONFIG["timeout"]
        
        # Session mit API-Key einrichten
        self.session = requests.Session()
        self.session.headers.update({
            "authorization": self.api_key,
            "Accept": "application/json"
        })
    
    def api_aufruf(self, endpoint: str, params: Dict[str, Any] = None) -> Dict:
        """
        Führt einen API-Aufruf durch.
        
        Returns:
            Dict mit: success, status_code, data, error, response_time_ms
        """
        url = f"{self.base_url}{endpoint}"
        
        try:
            import time
            start = time.time()
            response = self.session.get(url, params=params, timeout=self.timeout)
            zeit_ms = (time.time() - start) * 1000
            
            # Response parsen
            try:
                daten = response.json() if response.text else None
            except json.JSONDecodeError:
                daten = response.text
            
            return {
                "success": response.status_code == 200,
                "status_code": response.status_code,
                "data": daten,
                "error": None,
                "response_time_ms": zeit_ms
            }
            
        except requests.exceptions.Timeout:
            return {"success": False, "status_code": 0, "data": None, 
                    "error": f"Timeout nach {self.timeout}s", "response_time_ms": 0}
        except requests.exceptions.ConnectionError as e:
            return {"success": False, "status_code": 0, "data": None,
                    "error": f"Verbindungsfehler: {e}", "response_time_ms": 0}
        except Exception as e:
            return {"success": False, "status_code": 0, "data": None,
                    "error": f"Fehler: {e}", "response_time_ms": 0}
    
    # ----- CONVENIENCE METHODEN -----
    
    def health_check(self) -> Dict:
        """Prüft ob die API erreichbar ist"""
        return self.api_aufruf("/health")
    
    def hole_page_impressions(self, site: str, aggregation: str, date: str, 
                               returntype: str = "json") -> Dict:
        """Holt Page Impressions"""
        return self.api_aufruf("/api/v1/pageimpressions", {
            "site": site,
            "aggregation": aggregation,
            "date": date,
            "returntype": returntype
        })
    
    def hole_visits(self, site: str, aggregation: str, date: str) -> Dict:
        """Holt Visits"""
        return self.api_aufruf("/api/v1/visits", {
            "site": site,
            "aggregation": aggregation,
            "date": date
        })
    
    def hole_clients(self, site: str, aggregation: str, date: str) -> Dict:
        """Holt Clients"""
        return self.api_aufruf("/api/v1/clients", {
            "site": site,
            "aggregation": aggregation,
            "date": date
        })
    
    def hole_unique_clients(self, site: str, aggregation: str, date: str) -> Dict:
        """Holt Unique Clients"""
        return self.api_aufruf("/api/v1/uniqueclients", {
            "site": site,
            "aggregation": aggregation,
            "date": date
        })
    
    def hole_usetime(self, site: str, aggregation: str, date: str) -> Dict:
        """Holt Usetime (nur DAY/MONTH)"""
        return self.api_aufruf("/api/v1/usetime", {
            "site": site,
            "aggregation": aggregation,
            "date": date
        })
    
    def hole_devices(self, site: str, aggregation: str, date: str) -> Dict:
        """Holt Devices (nur DAY/MONTH)"""
        return self.api_aufruf("/api/v1/devices", {
            "site": site,
            "aggregation": aggregation,
            "date": date
        })


# ============================================================================
# API TESTER
# ============================================================================

class OEWAApiTester:
    """Testet die ÖWA/INFOnline API"""
    
    def __init__(self, api_key: str = None):
        self.client = OEWAApiClient(api_key=api_key)
        self.test_ergebnisse = []
        
        # Test-Datum: 7 Tage zurück
        self.test_datum = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    
    def _speichere_ergebnis(self, name: str, erfolg: bool, details: str = ""):
        self.test_ergebnisse.append({
            "name": name,
            "erfolg": erfolg,
            "details": details
        })
    
    # ----- TEST METHODEN -----
    
    def teste_health(self) -> bool:
        """Testet den Health-Endpoint"""
        drucke_abschnitt("1. Health Check")
        
        result = self.client.health_check()
        
        if result["success"]:
            drucke_ok(f"API erreichbar ({result['response_time_ms']:.0f}ms)")
            self._speichere_ergebnis("Health Check", True)
            return True
        else:
            drucke_fehler(f"API nicht erreichbar: {result['error']}")
            self._speichere_ergebnis("Health Check", False, result['error'])
            return False
    
    def teste_authentifizierung(self, site: str) -> bool:
        """Testet die API-Authentifizierung"""
        drucke_abschnitt("2. Authentifizierung")
        
        result = self.client.hole_page_impressions(site, "DAY", self.test_datum)
        
        if result["success"]:
            drucke_ok(f"API-Key gültig ({result['response_time_ms']:.0f}ms)")
            self._speichere_ergebnis("Authentifizierung", True)
            return True
        elif result["status_code"] == 401:
            drucke_fehler("API-Key ungültig (401 Unauthorized)")
            self._speichere_ergebnis("Authentifizierung", False, "Ungültiger API-Key")
            return False
        elif result["status_code"] == 403:
            drucke_fehler("Zugriff verweigert (403 Forbidden)")
            self._speichere_ergebnis("Authentifizierung", False, "Zugriff verweigert")
            return False
        else:
            drucke_fehler(f"Fehler: {result['error'] or result['status_code']}")
            self._speichere_ergebnis("Authentifizierung", False, str(result['status_code']))
            return False
    
    def teste_parameter_validierung(self, site: str):
        """Testet die Parameter-Validierung"""
        drucke_abschnitt("3. Parameter-Validierung")
        
        import time
        
        tests = [
            ("Fehlender 'site' Parameter", 
             {"aggregation": "DAY", "date": self.test_datum}),
            ("Fehlender 'aggregation' Parameter", 
             {"site": site, "date": self.test_datum}),
            ("Fehlender 'date' Parameter", 
             {"site": site, "aggregation": "DAY"}),
            ("Ungültiges Datumsformat", 
             {"site": site, "aggregation": "DAY", "date": "ungueltig"}),
            ("Ungültige Aggregation", 
             {"site": site, "aggregation": "FALSCH", "date": self.test_datum}),
        ]
        
        for test_name, params in tests:
            time.sleep(0.1)
            result = self.client.api_aufruf("/api/v1/pageimpressions", params)
            
            if result["status_code"] == 422:
                drucke_ok(f"{test_name} → 422 (korrekt abgelehnt)")
                self._speichere_ergebnis(f"Validierung: {test_name}", True)
            else:
                drucke_warnung(f"{test_name} → Status {result['status_code']}")
                self._speichere_ergebnis(f"Validierung: {test_name}", False)
    
    def teste_endpoints(self, site: str):
        """Testet alle Endpoints"""
        drucke_abschnitt("4. Endpoint-Tests")
        
        for key, config in OEWA_ENDPOINTS.items():
            # Wähle passende Aggregation
            aggregation = "DAY" if "DAY" in config["aggregationen"] else config["aggregationen"][0]
            
            result = self.client.api_aufruf(config["path"], {
                "site": site,
                "aggregation": aggregation,
                "date": self.test_datum
            })
            
            if result["success"]:
                # Analysiere Daten
                daten = result["data"]
                anzahl = 0
                felder = []
                
                if isinstance(daten, dict) and "data" in daten:
                    inner = daten["data"]
                    for dtype in config["datentypen"]:
                        if dtype in inner and isinstance(inner[dtype], list):
                            felder.append(dtype)
                            anzahl = max(anzahl, len(inner[dtype]))
                
                drucke_ok(f"{config['name']}: {anzahl} Datensätze ({result['response_time_ms']:.0f}ms)")
                if felder:
                    drucke_info(f"  → Datentypen: {', '.join(felder)}")
                
                self._speichere_ergebnis(f"Endpoint: {config['name']}", True, f"{anzahl} Datensätze")
            else:
                drucke_fehler(f"{config['name']}: {result['error'] or result['status_code']}")
                self._speichere_ergebnis(f"Endpoint: {config['name']}", False)
    
    def teste_response_formate(self, site: str):
        """Testet verschiedene Response-Formate"""
        drucke_abschnitt("5. Response-Formate")
        
        formate = ["json", "csv", "xml"]
        
        for fmt in formate:
            # Direkter API-Aufruf für nicht-JSON Formate
            try:
                import time
                url = f"{self.client.base_url}/api/v1/pageimpressions"
                params = {
                    "site": site,
                    "aggregation": "DAY",
                    "date": self.test_datum,
                    "returntype": fmt
                }
                
                start = time.time()
                response = self.client.session.get(url, params=params, timeout=30)
                zeit_ms = (time.time() - start) * 1000
                
                if response.status_code == 200:
                    groesse = len(response.content)
                    drucke_ok(f"Format {fmt.upper()}: OK ({groesse} Bytes, {zeit_ms:.0f}ms)")
                    self._speichere_ergebnis(f"Format: {fmt.upper()}", True)
                else:
                    drucke_fehler(f"Format {fmt.upper()}: Status {response.status_code}")
                    self._speichere_ergebnis(f"Format: {fmt.upper()}", False)
                    
            except Exception as e:
                drucke_fehler(f"Format {fmt.upper()}: {e}")
                self._speichere_ergebnis(f"Format: {fmt.upper()}", False)
    
    def zeige_beispiel_daten(self, site: str):
        """Zeigt Beispiel-Daten an"""
        drucke_abschnitt("6. Beispiel-Daten (Page Impressions)")
        
        result = self.client.hole_page_impressions(site, "DAY", self.test_datum)
        
        if not result["success"]:
            drucke_fehler("Keine Daten verfügbar")
            return
        
        daten = result["data"]
        
        if isinstance(daten, dict):
            # Metadata anzeigen
            if "metadata" in daten:
                drucke_info("Metadata:")
                meta = daten["metadata"]
                print(f"      Site: {meta.get('site', 'N/A')}")
                print(f"      Datum: {meta.get('date', 'N/A')}")
                print(f"      Aggregation: {meta.get('aggregation', 'N/A')}")
                print(f"      Exportiert: {meta.get('exported_at', 'N/A')}")
            
            # Daten anzeigen
            if "data" in daten:
                inner = daten["data"]
                
                # IOM Daten (hochgerechnet)
                if "iom" in inner and inner["iom"]:
                    drucke_info("IOM (INFOnline Measurement - hochgerechnet):")
                    for eintrag in inner["iom"][:2]:  # Erste 2 Einträge
                        print(f"      {json.dumps(eintrag, indent=6)}")
                
                # IOMb Daten (Zensus/Consentless)
                if "iomb" in inner and inner["iomb"]:
                    drucke_info("IOMb (Zensus/Consentless):")
                    for eintrag in inner["iomb"][:2]:
                        print(f"      {json.dumps(eintrag, indent=6)}")
                
                # IOMp Daten (Pseudonym/Consent)
                if "iomp" in inner and inner["iomp"]:
                    drucke_info("IOMp (Pseudonym/Consent):")
                    for eintrag in inner["iomp"][:2]:
                        print(f"      {json.dumps(eintrag, indent=6)}")
    
    def zeige_zusammenfassung(self):
        """Zeigt die Test-Zusammenfassung"""
        drucke_header("ZUSAMMENFASSUNG")
        
        gesamt = len(self.test_ergebnisse)
        erfolgreich = sum(1 for t in self.test_ergebnisse if t["erfolg"])
        fehlgeschlagen = gesamt - erfolgreich
        
        print(f"  Tests gesamt:     {gesamt}")
        print(f"  {Farben.GRUEN}Erfolgreich:{Farben.ENDE}      {erfolgreich}")
        print(f"  {Farben.ROT}Fehlgeschlagen:{Farben.ENDE}   {fehlgeschlagen}")
        
        erfolgsrate = (erfolgreich / gesamt * 100) if gesamt > 0 else 0
        
        if erfolgsrate == 100:
            farbe = Farben.GRUEN
        elif erfolgsrate >= 80:
            farbe = Farben.GELB
        else:
            farbe = Farben.ROT
        
        print(f"  {farbe}Erfolgsrate:{Farben.ENDE}      {erfolgsrate:.1f}%")
        
        # Fehlgeschlagene Tests anzeigen
        fehler = [t for t in self.test_ergebnisse if not t["erfolg"]]
        if fehler:
            print(f"\n  {Farben.ROT}Fehlgeschlagene Tests:{Farben.ENDE}")
            for t in fehler:
                print(f"    • {t['name']}")
                if t["details"]:
                    print(f"      → {t['details']}")
        
        # Gesamtstatus
        if erfolgsrate == 100:
            print(f"\n  {Farben.GRUEN}{Farben.FETT}✓ Alle Tests bestanden!{Farben.ENDE}")
        elif erfolgsrate >= 80:
            print(f"\n  {Farben.GELB}⚠ API funktioniert mit Einschränkungen{Farben.ENDE}")
        else:
            print(f"\n  {Farben.ROT}✗ Es gibt Probleme mit der API{Farben.ENDE}")
    
    # ----- HAUPTMETHODE -----
    
    def fuehre_alle_tests_aus(self, site: str, zeige_daten: bool = False):
        """Führt alle Tests aus"""
        
        site_name = SITE_IDENTIFIER.get(site, site)
        
        drucke_header("ÖWA / INFOnline API Test")
        print(f"  Site:   {site} ({site_name})")
        print(f"  Datum:  {self.test_datum}")
        print(f"  API:    {self.client.base_url}")
        
        # Tests ausführen
        if not self.teste_health():
            drucke_fehler("\nAPI nicht erreichbar - Test abgebrochen")
            return False
        
        if not self.teste_authentifizierung(site):
            drucke_fehler("\nAuthentifizierung fehlgeschlagen - Test abgebrochen")
            return False
        
        self.teste_parameter_validierung(site)
        self.teste_endpoints(site)
        self.teste_response_formate(site)
        
        if zeige_daten:
            self.zeige_beispiel_daten(site)
        
        self.zeige_zusammenfassung()
        
        return all(t["erfolg"] for t in self.test_ergebnisse)


# ============================================================================
# HAUPTPROGRAMM
# ============================================================================

def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="ÖWA / INFOnline Reporting API Tester",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Beispiele:
  python API-testing.py                      # Standard-Test mit VOL.AT
  python API-testing.py --site BE000072      # Test mit anderer Site
  python API-testing.py --show-data          # Zeige Beispiel-Daten
  python API-testing.py --list-sites         # Zeige bekannte Sites

Verfügbare Site-Identifier:
  at_w_atvol      - VOL.AT (Web)
  at_w_atvienna   - VIENNA.AT (Web)
  BE000072        - VOL.AT - Homepage
  BE000043        - VIENNA.AT - Gesamt
        """
    )
    
    parser.add_argument(
        "--site", "-s",
        default=DEFAULT_SITE,
        help=f"Site-Identifier (Standard: {DEFAULT_SITE})"
    )
    
    parser.add_argument(
        "--api-key", "-k",
        default=None,
        help="API-Key (Standard: aus Konfiguration)"
    )
    
    parser.add_argument(
        "--show-data", "-d",
        action="store_true",
        help="Zeige Beispiel-Daten an"
    )
    
    parser.add_argument(
        "--list-sites",
        action="store_true",
        help="Zeige bekannte Site-Identifier"
    )
    
    args = parser.parse_args()
    
    # Sites auflisten
    if args.list_sites:
        print("\nBekannte Site-Identifier:")
        print("-" * 40)
        for site_id, name in SITE_IDENTIFIER.items():
            print(f"  {site_id:<20} {name}")
        print()
        return
    
    # Tester erstellen und ausführen
    tester = OEWAApiTester(api_key=args.api_key)
    
    try:
        erfolg = tester.fuehre_alle_tests_aus(
            site=args.site,
            zeige_daten=args.show_data
        )
        sys.exit(0 if erfolg else 1)
        
    except KeyboardInterrupt:
        print(f"\n{Farben.GELB}Test abgebrochen.{Farben.ENDE}")
        sys.exit(130)
    except Exception as e:
        print(f"\n{Farben.ROT}Kritischer Fehler: {e}{Farben.ENDE}")
        sys.exit(1)


if __name__ == "__main__":
    main()

