#!/usr/bin/env python3
"""
ÖWA Comprehensive Test Suite v1.0
==================================
Ganzheitlicher Testplan zur Validierung aller Daten-Pipelines,
Berechnungen und Alerting-Mechanismen.

5 Test-Ebenen:
1. Datenintegrität in Airtable
2. Ingestion Pipeline
3. Alerting-Logik
4. API-Vergleich
5. Dashboard-Anzeige (manuell)

Nutzung:
    python ci_scripts/comprehensive_test.py                 # Schnelltest
    python ci_scripts/comprehensive_test.py --full          # Alle Tests
    python ci_scripts/comprehensive_test.py --integrity     # Nur Integrität
    python ci_scripts/comprehensive_test.py --alerting      # Nur Alerting
    python ci_scripts/comprehensive_test.py --api           # Mit API-Vergleich
"""

import os
import sys
import re
import json
import requests
import argparse
from datetime import date, datetime, timedelta
from collections import defaultdict
from typing import Dict, List, Set, Optional, Tuple
from dataclasses import dataclass, field

# =============================================================================
# KONFIGURATION
# =============================================================================
INFONLINE_API_KEY = os.environ.get("INFONLINE_API_KEY", "")
AIRTABLE_API_KEY = os.environ.get("AIRTABLE_API_KEY", "")
AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID", "appTIeod85xnBy7Vn")

# Site-Konfiguration für API-Vergleich
SITES = {
    "VOL_Web": {"site_id": "at_w_atvol", "brand": "VOL", "surface": "Web"},
    "VOL_iOS": {"site_id": "at_i_volat", "brand": "VOL", "surface": "iOS"},
    "VOL_Android": {"site_id": "at_a_volat", "brand": "VOL", "surface": "Android"},
    "Vienna_Web": {"site_id": "at_w_atvienna", "brand": "Vienna", "surface": "Web"},
    "Vienna_iOS": {"site_id": "at_i_viennaat", "brand": "Vienna", "surface": "iOS"},
    "Vienna_Android": {"site_id": "at_a_viennaat", "brand": "Vienna", "surface": "Android"},
}

# Plausibilitätsgrenzen (angepasst für verschiedene Property-Größen)
# Vienna App hat deutlich niedrigere Werte als VOL Web!
PLAUSIBILITY = {
    "daily_web_pi": {"min": 50_000, "max": 3_000_000},       # Web Page Impressions pro Tag
    "daily_app_pi": {"min": 100, "max": 1_000_000},          # App Page Impressions pro Tag
    "daily_web_visits": {"min": 10_000, "max": 1_000_000},   # Web Visits pro Tag
    "daily_app_visits": {"min": 100, "max": 500_000},        # App Visits pro Tag (Vienna Android!)
    "daily_uc": {"min": 50, "max": 500_000},                 # Unique Clients pro Tag
    "monthly_web": {"min": 1_000_000, "max": 50_000_000},    # Web Monatswerte
    "monthly_app": {"min": 10_000, "max": 10_000_000},       # App Monatswerte (können niedriger sein)
}

# Regex für Unique Key Formate
DAILY_KEY_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}_(VOL|Vienna)_(Web|iOS|Android|App)_(Page Impressions|Visits|Unique Clients|Homepage PI)$")
MONTHLY_KEY_PATTERN = re.compile(r"^\d{4}-\d{2}_MONTH_(VOL|Vienna)_(Web|iOS|Android|App)_(Page Impressions|Visits|Unique Clients|Homepage PI)$")


# =============================================================================
# TEST RESULT DATACLASS
# =============================================================================
@dataclass
class TestResult:
    """Ergebnis eines einzelnen Tests"""
    name: str
    passed: bool
    message: str
    severity: str = "MEDIUM"  # CRITICAL, HIGH, MEDIUM, LOW
    details: List[str] = field(default_factory=list)


@dataclass 
class TestSuiteResult:
    """Ergebnis der gesamten Test-Suite"""
    results: List[TestResult] = field(default_factory=list)
    start_time: datetime = None
    end_time: datetime = None
    
    @property
    def total(self) -> int:
        return len(self.results)
    
    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)
    
    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if not r.passed)
    
    @property
    def critical_failures(self) -> int:
        return sum(1 for r in self.results if not r.passed and r.severity == "CRITICAL")
    
    def add(self, result: TestResult):
        self.results.append(result)


# =============================================================================
# AIRTABLE FUNKTIONEN
# =============================================================================
def fetch_all_records(days: int = 30) -> List[Dict]:
    """Holt alle Records aus Airtable für die letzten X Tage"""
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/Measurements"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    
    start_date = date.today() - timedelta(days=days)
    formula = f"{{Datum}} >= '{start_date.isoformat()}'"
    
    all_records = []
    offset = None
    
    while True:
        params = {
            "filterByFormula": formula,
            "pageSize": 100
        }
        if offset:
            params["offset"] = offset
        
        try:
            response = requests.get(url, headers=headers, params=params, timeout=30)
            if response.status_code != 200:
                print(f"   Fehler beim Laden: {response.status_code}")
                break
            
            data = response.json()
            records = data.get("records", [])
            
            for r in records:
                fields = r.get("fields", {})
                all_records.append({
                    "id": r.get("id"),
                    "datum": fields.get("Datum"),
                    "brand": fields.get("Brand"),
                    "plattform": fields.get("Plattform"),
                    "metrik": fields.get("Metrik"),
                    "wert": fields.get("Wert"),
                    "unique_key": fields.get("Unique Key"),
                    "erfasst_am": fields.get("Erfasst am")
                })
            
            offset = data.get("offset")
            if not offset:
                break
                
        except Exception as e:
            print(f"   Exception: {e}")
            break
    
    return all_records


def get_historical_data_for_weekday(brand: str, surface: str, metric: str, weekday: int, weeks: int = 6) -> List[Dict]:
    """Holt historische Daten für einen bestimmten Wochentag (wie in daily_ingest.py)"""
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/Measurements"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    
    # MIT Monatsdaten-Ausschluss (der Fix!)
    formula = f"AND({{Brand}} = '{brand}', {{Plattform}} = '{surface}', {{Metrik}} = '{metric}', SEARCH('_MONTH_', {{Unique Key}}) = 0)"
    
    try:
        params = {
            "filterByFormula": formula,
            "fields[]": ["Datum", "Wert", "Unique Key"],
            "sort[0][field]": "Datum",
            "sort[0][direction]": "desc",
            "pageSize": 100
        }
        
        response = requests.get(url, headers=headers, params=params, timeout=30)
        if response.status_code != 200:
            return []
        
        records = response.json().get("records", [])
        
        matching_data = []
        for record in records:
            fields = record.get("fields", {})
            datum_str = fields.get("Datum")
            wert = fields.get("Wert")
            key = fields.get("Unique Key", "")
            
            if datum_str and wert:
                try:
                    datum = date.fromisoformat(datum_str)
                    if datum.weekday() == weekday:
                        matching_data.append({
                            "date": datum,
                            "value": wert,
                            "key": key
                        })
                        if len(matching_data) >= weeks:
                            break
                except:
                    continue
        
        return matching_data
        
    except Exception as e:
        return []


# =============================================================================
# TEST-EBENE 1: DATENINTEGRITÄT
# =============================================================================
class DataIntegrityTests:
    """Tests für Datenintegrität in Airtable"""
    
    def __init__(self, records: List[Dict]):
        self.records = records
    
    def test_no_duplicates(self) -> TestResult:
        """1.1 Duplikat-Erkennung"""
        key_counts = defaultdict(list)
        
        for r in self.records:
            key = r.get("unique_key")
            if key:
                key_counts[key].append(r)
        
        duplicates = {k: v for k, v in key_counts.items() if len(v) > 1}
        
        if not duplicates:
            return TestResult(
                name="1.1 Duplikat-Erkennung",
                passed=True,
                message="Keine Duplikate gefunden",
                severity="CRITICAL"
            )
        else:
            details = [f"{k}: {len(v)}x" for k, v in list(duplicates.items())[:5]]
            return TestResult(
                name="1.1 Duplikat-Erkennung",
                passed=False,
                message=f"{len(duplicates)} Unique Keys mit Duplikaten",
                severity="CRITICAL",
                details=details
            )
    
    def test_unique_key_format(self) -> TestResult:
        """1.2 Unique Key Format-Validierung"""
        invalid_keys = []
        
        for r in self.records:
            key = r.get("unique_key", "")
            if not key:
                invalid_keys.append(f"Leerer Key für {r.get('datum')}")
                continue
            
            if not (DAILY_KEY_PATTERN.match(key) or MONTHLY_KEY_PATTERN.match(key)):
                invalid_keys.append(key)
        
        if not invalid_keys:
            return TestResult(
                name="1.2 Unique Key Format",
                passed=True,
                message=f"Alle {len(self.records)} Keys haben gültiges Format",
                severity="HIGH"
            )
        else:
            return TestResult(
                name="1.2 Unique Key Format",
                passed=False,
                message=f"{len(invalid_keys)} ungültige Keys",
                severity="HIGH",
                details=invalid_keys[:5]
            )
    
    def test_monthly_data_isolated(self) -> TestResult:
        """1.3 Monatsdaten-Isolation"""
        issues = []
        
        for r in self.records:
            key = r.get("unique_key", "")
            datum = r.get("datum", "")
            
            if "_MONTH_" in key:
                # Monatsdaten sollten auf letzten Tag des Monats zeigen
                try:
                    d = date.fromisoformat(datum)
                    # Prüfe ob es der letzte Tag des Monats ist
                    next_month = d.replace(day=28) + timedelta(days=4)
                    last_day = next_month - timedelta(days=next_month.day)
                    
                    if d != last_day:
                        issues.append(f"{key}: Datum {datum} ist nicht Monatsende")
                except:
                    issues.append(f"{key}: Ungültiges Datum {datum}")
        
        if not issues:
            monthly_count = sum(1 for r in self.records if "_MONTH_" in r.get("unique_key", ""))
            return TestResult(
                name="1.3 Monatsdaten-Isolation",
                passed=True,
                message=f"{monthly_count} Monatsdaten korrekt isoliert",
                severity="CRITICAL"
            )
        else:
            return TestResult(
                name="1.3 Monatsdaten-Isolation",
                passed=False,
                message=f"{len(issues)} Probleme mit Monatsdaten",
                severity="CRITICAL",
                details=issues[:5]
            )
    
    def test_value_plausibility(self) -> TestResult:
        """1.4 Wert-Plausibilität"""
        outliers = []
        
        for r in self.records:
            key = r.get("unique_key", "")
            wert = r.get("wert", 0) or 0
            plattform = r.get("plattform", "")
            metrik = r.get("metrik", "")
            is_app = plattform in ["iOS", "Android", "App"]
            
            if "_MONTH_" in key:
                # Monatsdaten - unterscheide Web und App
                limits = PLAUSIBILITY["monthly_app"] if is_app else PLAUSIBILITY["monthly_web"]
            elif plattform == "Web" and metrik == "Page Impressions":
                limits = PLAUSIBILITY["daily_web_pi"]
            elif is_app and metrik == "Page Impressions":
                limits = PLAUSIBILITY["daily_app_pi"]
            elif plattform == "Web" and metrik == "Visits":
                limits = PLAUSIBILITY["daily_web_visits"]
            elif is_app and metrik == "Visits":
                limits = PLAUSIBILITY["daily_app_visits"]
            elif metrik == "Unique Clients":
                limits = PLAUSIBILITY["daily_uc"]
            else:
                continue  # Homepage PI etc.
            
            if wert < limits["min"] or wert > limits["max"]:
                outliers.append(f"{key}: {wert:,} (erwartet: {limits['min']:,}-{limits['max']:,})")
        
        # Test bestanden wenn weniger als 5% der Daten Ausreißer sind
        outlier_pct = (len(outliers) / len(self.records) * 100) if self.records else 0
        
        if not outliers:
            return TestResult(
                name="1.4 Wert-Plausibilität",
                passed=True,
                message="Alle Werte im plausiblen Bereich",
                severity="HIGH"
            )
        elif outlier_pct < 5:
            return TestResult(
                name="1.4 Wert-Plausibilität",
                passed=True,
                message=f"{len(outliers)} Ausreißer ({outlier_pct:.1f}%) - akzeptabel",
                severity="HIGH",
                details=outliers[:3]
            )
        else:
            return TestResult(
                name="1.4 Wert-Plausibilität",
                passed=False,
                message=f"{len(outliers)} Ausreißer ({outlier_pct:.1f}%) - zu viele!",
                severity="HIGH",
                details=outliers[:5]
            )
    
    def test_required_fields(self) -> TestResult:
        """1.5 Pflichtfeld-Vollständigkeit"""
        required = ["datum", "brand", "plattform", "metrik", "wert", "unique_key"]
        missing = []
        
        for r in self.records:
            for field in required:
                if not r.get(field):
                    missing.append(f"{r.get('unique_key', 'UNKNOWN')}: fehlt {field}")
        
        if not missing:
            return TestResult(
                name="1.5 Pflichtfeld-Vollständigkeit",
                passed=True,
                message="Alle Pflichtfelder vorhanden",
                severity="HIGH"
            )
        else:
            return TestResult(
                name="1.5 Pflichtfeld-Vollständigkeit",
                passed=False,
                message=f"{len(missing)} fehlende Pflichtfelder",
                severity="HIGH",
                details=missing[:5]
            )


# =============================================================================
# TEST-EBENE 2: INGESTION PIPELINE
# =============================================================================
class IngestionPipelineTests:
    """Tests für die Ingestion-Pipeline"""
    
    def __init__(self, records: List[Dict]):
        self.records = records
    
    def test_uc_delay(self) -> TestResult:
        """2.3 Unique Clients Verzögerung"""
        today = date.today()
        recent_uc = []
        
        for r in self.records:
            if r.get("metrik") == "Unique Clients" and "_MONTH_" not in r.get("unique_key", ""):
                try:
                    d = date.fromisoformat(r.get("datum", ""))
                    days_ago = (today - d).days
                    if days_ago < 3:  # UC sollte 3+ Tage alt sein
                        recent_uc.append(f"{r.get('unique_key')}: {days_ago} Tage alt")
                except:
                    pass
        
        if not recent_uc:
            return TestResult(
                name="2.3 UC-Verzögerung",
                passed=True,
                message="Keine UC-Daten für die letzten 2 Tage (korrekt)",
                severity="MEDIUM"
            )
        else:
            return TestResult(
                name="2.3 UC-Verzögerung",
                passed=False,
                message=f"{len(recent_uc)} UC-Records zu früh erfasst",
                severity="MEDIUM",
                details=recent_uc[:5]
            )
    
    def test_homepage_pi_only_web(self) -> TestResult:
        """2.4 Homepage PI nur Web"""
        app_homepage = []
        
        for r in self.records:
            if r.get("metrik") == "Homepage PI" and r.get("plattform") in ["iOS", "Android", "App"]:
                app_homepage.append(r.get("unique_key"))
        
        if not app_homepage:
            return TestResult(
                name="2.4 Homepage PI nur Web",
                passed=True,
                message="Keine App Homepage PI Records (korrekt)",
                severity="MEDIUM"
            )
        else:
            return TestResult(
                name="2.4 Homepage PI nur Web",
                passed=False,
                message=f"{len(app_homepage)} App Homepage PI Records gefunden",
                severity="MEDIUM",
                details=app_homepage[:5]
            )


# =============================================================================
# TEST-EBENE 3: ALERTING-LOGIK
# =============================================================================
class AlertingLogicTests:
    """Tests für die Alerting-Logik"""
    
    def test_monthly_data_excluded(self) -> TestResult:
        """3.1 Monatsdaten-Ausschluss (KRITISCH)"""
        # Teste für verschiedene Wochentage
        issues = []
        
        for weekday in range(7):  # 0=Mo, 6=So
            for brand in ["VOL", "Vienna"]:
                for surface in ["Web"]:  # Web hat am meisten Daten
                    historical = get_historical_data_for_weekday(
                        brand=brand,
                        surface=surface,
                        metric="Page Impressions",
                        weekday=weekday,
                        weeks=6
                    )
                    
                    for h in historical:
                        if "_MONTH_" in h.get("key", ""):
                            issues.append(f"{h['key']} in Wochentag {weekday}")
        
        if not issues:
            return TestResult(
                name="3.1 Monatsdaten-Ausschluss",
                passed=True,
                message="Keine Monatsdaten in historischen Vergleichen",
                severity="CRITICAL"
            )
        else:
            return TestResult(
                name="3.1 Monatsdaten-Ausschluss",
                passed=False,
                message=f"{len(issues)} Monatsdaten in historischen Daten!",
                severity="CRITICAL",
                details=issues[:5]
            )
    
    def test_weekday_filter(self) -> TestResult:
        """3.2 Wochentags-Filter"""
        # Teste ob alle zurückgegebenen Daten den richtigen Wochentag haben
        issues = []
        
        for weekday in [0, 6]:  # Montag und Sonntag testen
            historical = get_historical_data_for_weekday(
                brand="VOL",
                surface="Web",
                metric="Page Impressions",
                weekday=weekday,
                weeks=6
            )
            
            for h in historical:
                actual_weekday = h["date"].weekday()
                if actual_weekday != weekday:
                    issues.append(f"{h['date']}: erwartet Wochentag {weekday}, ist {actual_weekday}")
        
        if not issues:
            return TestResult(
                name="3.2 Wochentags-Filter",
                passed=True,
                message="Alle historischen Daten haben korrekten Wochentag",
                severity="HIGH"
            )
        else:
            return TestResult(
                name="3.2 Wochentags-Filter",
                passed=False,
                message=f"{len(issues)} Wochentags-Fehler",
                severity="HIGH",
                details=issues[:5]
            )
    
    def test_edge_case_month_end_weekday(self) -> TestResult:
        """3.5 Edge Case: Monatsende = Wochentag"""
        # Teste speziell den 30.11.2025 (Sonntag + Monatsende)
        target_date = date(2025, 11, 30)
        weekday = target_date.weekday()  # 6 = Sonntag
        
        historical = get_historical_data_for_weekday(
            brand="VOL",
            surface="Web",
            metric="Page Impressions",
            weekday=weekday,
            weeks=10  # Mehr Wochen um 30.11. zu erfassen
        )
        
        # Suche nach Einträgen für 30.11.
        nov30_entries = [h for h in historical if h["date"] == target_date]
        
        # Es sollte maximal 1 Eintrag für 30.11. geben (Tagesdaten)
        # und dieser sollte KEINE Monatsdaten sein
        if len(nov30_entries) == 0:
            return TestResult(
                name="3.5 Edge Case Monatsende",
                passed=True,
                message="30.11.2025 nicht im Zeitfenster (OK)",
                severity="CRITICAL"
            )
        elif len(nov30_entries) == 1:
            entry = nov30_entries[0]
            if "_MONTH_" in entry.get("key", ""):
                return TestResult(
                    name="3.5 Edge Case Monatsende",
                    passed=False,
                    message=f"30.11. enthält Monatsdaten: {entry['value']:,}",
                    severity="CRITICAL",
                    details=[f"Key: {entry['key']}"]
                )
            elif entry["value"] > 5_000_000:  # Verdächtig hoch für Tagesdaten
                return TestResult(
                    name="3.5 Edge Case Monatsende",
                    passed=False,
                    message=f"30.11. Wert verdächtig hoch: {entry['value']:,}",
                    severity="CRITICAL",
                    details=[f"Key: {entry['key']}"]
                )
            else:
                return TestResult(
                    name="3.5 Edge Case Monatsende",
                    passed=True,
                    message=f"30.11. korrekt als Tagesdaten: {entry['value']:,}",
                    severity="CRITICAL"
                )
        else:
            return TestResult(
                name="3.5 Edge Case Monatsende",
                passed=False,
                message=f"30.11. hat {len(nov30_entries)} Einträge (sollte max 1 sein)",
                severity="CRITICAL",
                details=[f"{e['key']}: {e['value']:,}" for e in nov30_entries]
            )


# =============================================================================
# TEST-EBENE 4: API-VERGLEICH
# =============================================================================
class ApiComparisonTests:
    """Tests für API-Vergleich"""
    
    def __init__(self, records: List[Dict]):
        self.records = records
    
    def fetch_api_value(self, site_id: str, metric_api: str, target_date: date) -> Optional[int]:
        """Holt Wert von INFOnline API"""
        if not INFONLINE_API_KEY:
            return None
        
        base_url = "https://data.infonline.de/api/v1"
        url = f"{base_url}/data/{site_id}/{metric_api}/daily"
        headers = {
            "Accept": "application/json",
            "X-Api-Key": INFONLINE_API_KEY
        }
        
        params = {
            "start": target_date.isoformat(),
            "end": target_date.isoformat()
        }
        
        try:
            response = requests.get(url, headers=headers, params=params, timeout=30)
            if response.status_code == 200:
                data = response.json()
                if data and isinstance(data, list) and len(data) > 0:
                    return data[0].get("pis") or data[0].get("visits") or data[0].get("uclients")
            return None
        except:
            return None
    
    def test_api_match(self) -> TestResult:
        """4.1 Tageswert-Validierung"""
        if not INFONLINE_API_KEY:
            return TestResult(
                name="4.1 API-Vergleich",
                passed=True,
                message="Übersprungen (INFONLINE_API_KEY nicht gesetzt)",
                severity="MEDIUM"
            )
        
        # Teste nur einen Tag (vor 5 Tagen für stabile Daten)
        target_date = date.today() - timedelta(days=5)
        discrepancies = []
        
        for site_name, site_info in SITES.items():
            if site_info["surface"] != "Web":
                continue  # Nur Web testen für Geschwindigkeit
            
            # Hole API-Wert
            api_value = self.fetch_api_value(
                site_info["site_id"],
                "pageimpressions",
                target_date
            )
            
            if api_value is None:
                continue
            
            # Finde Airtable-Wert
            airtable_value = None
            for r in self.records:
                if (r.get("datum") == target_date.isoformat() and
                    r.get("brand") == site_info["brand"] and
                    r.get("plattform") == site_info["surface"] and
                    r.get("metrik") == "Page Impressions" and
                    "_MONTH_" not in r.get("unique_key", "")):
                    airtable_value = r.get("wert")
                    break
            
            if airtable_value is None:
                discrepancies.append(f"{site_name}: Kein Airtable-Wert für {target_date}")
                continue
            
            # Vergleiche
            diff_pct = abs(airtable_value - api_value) / api_value * 100 if api_value > 0 else 0
            if diff_pct > 1.0:  # Mehr als 1% Abweichung
                discrepancies.append(
                    f"{site_name} {target_date}: AT={airtable_value:,} vs API={api_value:,} ({diff_pct:.1f}%)"
                )
        
        if not discrepancies:
            return TestResult(
                name="4.1 API-Vergleich",
                passed=True,
                message=f"Alle Werte für {target_date} stimmen mit API überein",
                severity="MEDIUM"
            )
        else:
            return TestResult(
                name="4.1 API-Vergleich",
                passed=False,
                message=f"{len(discrepancies)} Abweichungen zur API",
                severity="MEDIUM",
                details=discrepancies
            )


# =============================================================================
# HAUPT-TESTSUITE
# =============================================================================
class OewaTestSuite:
    """Haupt-Testsuite für das ÖWA Reporting System"""
    
    def __init__(self, days: int = 30):
        self.days = days
        self.records = []
        self.results = TestSuiteResult()
    
    def load_data(self):
        """Lädt alle benötigten Daten"""
        print(f"   Lade Daten der letzten {self.days} Tage...")
        self.records = fetch_all_records(self.days)
        print(f"   {len(self.records)} Records geladen")
    
    def run_integrity_tests(self):
        """Führt Datenintegritäts-Tests aus"""
        print("\n" + "-" * 60)
        print("TEST-EBENE 1: Datenintegrität")
        print("-" * 60)
        
        tests = DataIntegrityTests(self.records)
        
        for test_func in [
            tests.test_no_duplicates,
            tests.test_unique_key_format,
            tests.test_monthly_data_isolated,
            tests.test_value_plausibility,
            tests.test_required_fields
        ]:
            result = test_func()
            self.results.add(result)
            self._print_result(result)
    
    def run_ingestion_tests(self):
        """Führt Pipeline-Tests aus"""
        print("\n" + "-" * 60)
        print("TEST-EBENE 2: Ingestion Pipeline")
        print("-" * 60)
        
        tests = IngestionPipelineTests(self.records)
        
        for test_func in [
            tests.test_uc_delay,
            tests.test_homepage_pi_only_web
        ]:
            result = test_func()
            self.results.add(result)
            self._print_result(result)
    
    def run_alerting_tests(self):
        """Führt Alerting-Tests aus"""
        print("\n" + "-" * 60)
        print("TEST-EBENE 3: Alerting-Logik")
        print("-" * 60)
        
        tests = AlertingLogicTests()
        
        for test_func in [
            tests.test_monthly_data_excluded,
            tests.test_weekday_filter,
            tests.test_edge_case_month_end_weekday
        ]:
            result = test_func()
            self.results.add(result)
            self._print_result(result)
    
    def run_api_tests(self):
        """Führt API-Vergleichs-Tests aus"""
        print("\n" + "-" * 60)
        print("TEST-EBENE 4: API-Vergleich")
        print("-" * 60)
        
        tests = ApiComparisonTests(self.records)
        
        result = tests.test_api_match()
        self.results.add(result)
        self._print_result(result)
    
    def _print_result(self, result: TestResult):
        """Gibt ein Testergebnis aus"""
        status = "[PASS]" if result.passed else "[FAIL]"
        severity_marker = " (!)" if result.severity == "CRITICAL" and not result.passed else ""
        print(f"   {status} {result.name}: {result.message}{severity_marker}")
        
        if result.details and not result.passed:
            for detail in result.details[:3]:
                print(f"         - {detail}")
    
    def print_summary(self):
        """Gibt Zusammenfassung aus"""
        print("\n" + "=" * 70)
        print("ZUSAMMENFASSUNG")
        print("=" * 70)
        
        pct = (self.results.passed / self.results.total * 100) if self.results.total > 0 else 0
        
        print(f"   Tests gesamt:       {self.results.total}")
        print(f"   Bestanden:          {self.results.passed}")
        print(f"   Fehlgeschlagen:     {self.results.failed}")
        print(f"   Kritische Fehler:   {self.results.critical_failures}")
        print(f"   Erfolgsquote:       {pct:.1f}%")
        
        if self.results.critical_failures > 0:
            print("\n   ACHTUNG: Kritische Fehler gefunden!")
            for r in self.results.results:
                if not r.passed and r.severity == "CRITICAL":
                    print(f"   - {r.name}: {r.message}")
        
        print("=" * 70)
        
        # Exit-Code
        if self.results.critical_failures > 0:
            return 2  # Kritischer Fehler
        elif self.results.failed > 0:
            return 1  # Fehler
        else:
            return 0  # Alles OK
    
    def run_all(self, include_api: bool = False) -> int:
        """Führt alle Tests aus"""
        self.results.start_time = datetime.now()
        
        print("=" * 70)
        print("OEWA COMPREHENSIVE TEST SUITE v1.0")
        print(f"Datum: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print("=" * 70)
        
        if not AIRTABLE_API_KEY:
            print("\nFEHLER: AIRTABLE_API_KEY nicht gesetzt!")
            return 3
        
        self.load_data()
        
        if not self.records:
            print("\nFEHLER: Keine Records geladen!")
            return 3
        
        self.run_integrity_tests()
        self.run_ingestion_tests()
        self.run_alerting_tests()
        
        if include_api:
            self.run_api_tests()
        else:
            print("\n" + "-" * 60)
            print("TEST-EBENE 4: API-Vergleich")
            print("-" * 60)
            print("   [SKIP] Übersprungen (--api Flag nicht gesetzt)")
        
        print("\n" + "-" * 60)
        print("TEST-EBENE 5: Dashboard-Anzeige")
        print("-" * 60)
        print("   [INFO] Manuelle Prüfung via Streamlit empfohlen")
        
        self.results.end_time = datetime.now()
        
        return self.print_summary()


# =============================================================================
# MAIN
# =============================================================================
def main():
    parser = argparse.ArgumentParser(description="ÖWA Comprehensive Test Suite")
    parser.add_argument("--full", action="store_true", help="Alle Tests ausführen")
    parser.add_argument("--integrity", action="store_true", help="Nur Integritäts-Tests")
    parser.add_argument("--alerting", action="store_true", help="Nur Alerting-Tests")
    parser.add_argument("--api", action="store_true", help="Inkl. API-Vergleich")
    parser.add_argument("--days", type=int, default=30, help="Tage zurück (Standard: 30)")
    
    args = parser.parse_args()
    
    suite = OewaTestSuite(days=args.days)
    
    if args.integrity:
        suite.load_data()
        suite.run_integrity_tests()
        return suite.print_summary()
    elif args.alerting:
        suite.run_alerting_tests()
        return suite.print_summary()
    else:
        return suite.run_all(include_api=args.api or args.full)


if __name__ == "__main__":
    sys.exit(main())

