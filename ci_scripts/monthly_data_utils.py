#!/usr/bin/env python3
"""
Monthly Data Utils - Universelle Monatsdaten-Funktionen
=========================================================

Bietet eine einheitliche Schnittstelle für Monatsdaten, unabhängig davon
ob Tagesdaten oder Monatsdaten (_MONTH_) vorhanden sind.

STRATEGIE:
- Monate MIT Tagesdaten: Aggregiert Tagesdaten zur Laufzeit
- Monate OHNE Tagesdaten: Verwendet _MONTH_ Records direkt

VERWENDUNG:
    from monthly_data_utils import get_monthly_data, get_12_month_trend
    
    # Einzelner Monat
    data = get_monthly_data(2025, 12)  # Dezember 2025
    
    # 12-Monats-Trend
    trend = get_12_month_trend(2025, 12)  # Jan 2025 - Dez 2025
"""

import os
import requests
from collections import defaultdict
from datetime import date, timedelta
from calendar import monthrange
from typing import Dict, List, Optional, Tuple
from time import sleep

# =============================================================================
# KONFIGURATION
# =============================================================================
AIRTABLE_API_KEY = os.environ.get("AIRTABLE_API_KEY", "")
AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID", "")  # Muss in CI/CD Variables gesetzt sein

# Plattformen, die als "App" zusammengefasst werden
APP_PLATFORMS = ["iOS", "Android"]

# Standard-Metriken
METRICS = ["Page Impressions", "Visits", "Unique Clients", "Homepage PI"]


# =============================================================================
# HILFSFUNKTIONEN
# =============================================================================

def get_month_dates(year: int, month: int) -> Tuple[date, date]:
    """Gibt Start- und Enddatum eines Monats zurück."""
    start = date(year, month, 1)
    _, last_day = monthrange(year, month)
    end = date(year, month, last_day)
    return start, end


def get_previous_month(year: int, month: int) -> Tuple[int, int]:
    """Gibt Jahr und Monat des Vormonats zurück."""
    if month == 1:
        return year - 1, 12
    return year, month - 1


def aggregate_platforms(data: Dict, aggregate_app: bool = True) -> Dict:
    """
    Aggregiert iOS und Android zu 'App' falls gewünscht.
    
    Args:
        data: Dictionary mit Plattform-Keys
        aggregate_app: Wenn True, werden iOS+Android zu App zusammengefasst
    """
    if not aggregate_app:
        return data
    
    result = {}
    app_data = {}
    
    for key, metrics in data.items():
        brand, platform = key.rsplit("_", 1)
        
        if platform in APP_PLATFORMS:
            # Zu App aggregieren
            app_key = f"{brand}_App"
            if app_key not in app_data:
                app_data[app_key] = {}
            
            for metric, value in metrics.items():
                if metric not in app_data[app_key]:
                    app_data[app_key][metric] = 0
                app_data[app_key][metric] += value
        else:
            result[key] = metrics
    
    # App-Daten hinzufügen
    result.update(app_data)
    
    return result


# =============================================================================
# CORE-FUNKTIONEN
# =============================================================================

def check_daily_data_exists(year: int, month: int) -> int:
    """
    Prüft ob Tagesdaten für einen Monat existieren.
    
    Returns:
        Anzahl der Tage mit Daten (0 = keine Tagesdaten)
    """
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/Measurements"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    
    start, end = get_month_dates(year, month)
    
    params = {
        "filterByFormula": f"AND(IS_AFTER({{Datum}}, '{(start.isoformat())}'), IS_BEFORE({{Datum}}, '{end.isoformat()}'), FIND('_MONTH_', {{Unique Key}}) = 0)",
        "pageSize": 1
    }
    
    response = requests.get(url, headers=headers, params=params, timeout=30)
    if response.status_code == 200:
        records = response.json().get("records", [])
        return len(records) > 0
    return False


def get_daily_data_aggregated(year: int, month: int, brand_filter: str = None) -> Dict:
    """
    Lädt Tagesdaten und aggregiert sie zu Monatssummen.
    
    Args:
        year: Jahr
        month: Monat
        brand_filter: Optional - nur bestimmte Brand laden (z.B. 'VOL')
    
    Returns:
        Dictionary: {
            "VOL_Web": {"Page Impressions": 24500000, "Visits": 8400000, ...},
            "VOL_iOS": {...},
            ...
        }
    """
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/Measurements"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    
    start, end = get_month_dates(year, month)
    
    # Filter: Nur Tagesdaten (kein _MONTH_), optional Brand
    formula = f"AND(IS_AFTER({{Datum}}, '{(start - timedelta(days=1)).isoformat()}'), IS_BEFORE({{Datum}}, '{(end + timedelta(days=1)).isoformat()}'), FIND('_MONTH_', {{Unique Key}}) = 0)"
    
    if brand_filter:
        formula = f"AND({formula}, {{Brand}} = '{brand_filter}')"
    
    records = []
    offset = None
    
    while True:
        params = {
            "filterByFormula": formula,
            "pageSize": 100
        }
        if offset:
            params["offset"] = offset
        
        response = requests.get(url, headers=headers, params=params, timeout=30)
        if response.status_code != 200:
            break
        
        data = response.json()
        records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break
    
    # Aggregieren
    result = defaultdict(lambda: defaultdict(int))
    
    for record in records:
        fields = record.get("fields", {})
        brand = fields.get("Brand", "")
        platform = fields.get("Plattform", "Web")
        metric = fields.get("Metrik", "")
        value = fields.get("Wert", 0)
        
        if brand and metric and value:
            key = f"{brand}_{platform}"
            result[key][metric] += value
    
    return dict(result)


def get_monthly_data_records(year: int, month: int, brand_filter: str = None) -> Dict:
    """
    Lädt Monatsdaten (_MONTH_ Records) direkt.
    
    Args:
        year: Jahr
        month: Monat
        brand_filter: Optional - nur bestimmte Brand laden
    
    Returns:
        Dictionary: {
            "VOL_Web": {"Page Impressions": 24500000, ...},
            ...
        }
    """
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/Measurements"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    
    month_prefix = f"{year}-{month:02d}_MONTH_"
    
    formula = f"FIND('{month_prefix}', {{Unique Key}}) > 0"
    
    if brand_filter:
        formula = f"AND({formula}, {{Brand}} = '{brand_filter}')"
    
    params = {
        "filterByFormula": formula,
        "pageSize": 100
    }
    
    response = requests.get(url, headers=headers, params=params, timeout=30)
    
    result = defaultdict(lambda: defaultdict(int))
    
    if response.status_code == 200:
        for record in response.json().get("records", []):
            fields = record.get("fields", {})
            brand = fields.get("Brand", "")
            platform = fields.get("Plattform", "Web")
            metric = fields.get("Metrik", "")
            value = fields.get("Wert", 0)
            
            if brand and metric:
                key = f"{brand}_{platform}"
                result[key][metric] = value  # Überschreiben, nicht addieren
    
    return dict(result)


def count_daily_data_days(year: int, month: int, brand_filter: str = None) -> int:
    """
    Zählt wie viele Tage mit Tagesdaten für einen Monat existieren.
    
    Returns:
        Anzahl der Tage mit Daten
    """
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/Measurements"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    
    start, end = get_month_dates(year, month)
    
    formula = f"AND(IS_AFTER({{Datum}}, '{(start - timedelta(days=1)).isoformat()}'), IS_BEFORE({{Datum}}, '{(end + timedelta(days=1)).isoformat()}'), FIND('_MONTH_', {{Unique Key}}) = 0)"
    
    if brand_filter:
        formula = f"AND({formula}, {{Brand}} = '{brand_filter}')"
    
    dates = set()
    offset = None
    
    while True:
        params = {
            "filterByFormula": formula,
            "fields[]": "Datum",
            "pageSize": 100
        }
        if offset:
            params["offset"] = offset
        
        response = requests.get(url, headers=headers, params=params, timeout=30)
        if response.status_code != 200:
            break
        
        data = response.json()
        for record in data.get("records", []):
            datum = record.get("fields", {}).get("Datum")
            if datum:
                dates.add(datum)
        
        offset = data.get("offset")
        if not offset:
            break
    
    return len(dates)


def get_monthly_data(year: int, month: int, brand_filter: str = None, aggregate_app: bool = True) -> Dict:
    """
    UNIVERSELLE FUNKTION: Lädt Monatsdaten intelligent.
    
    STRATEGIE (Priorisierung):
    1. Prüfe ob vollständige Tagesdaten existieren (>= 28 Tage)
       -> Ja: Aggregiere Tagesdaten
    2. Prüfe ob Monatsdaten existieren
       -> Ja: Verwende Monatsdaten
    3. Fallback: Verwende unvollständige Tagesdaten
    
    Args:
        year: Jahr
        month: Monat
        brand_filter: Optional - nur bestimmte Brand (z.B. 'VOL')
        aggregate_app: Wenn True, werden iOS+Android zu 'App' zusammengefasst
    
    Returns:
        Dictionary mit Monatssummen pro Brand/Plattform/Metrik
    """
    _, last_day = monthrange(year, month)
    
    # Prüfe wie viele Tage mit Tagesdaten existieren
    days_with_data = count_daily_data_days(year, month, brand_filter)
    
    # Schwellwert: Mindestens 90% der Tage müssen Daten haben
    completeness_threshold = int(last_day * 0.9)  # z.B. 28 von 31 Tagen
    
    # Strategie 1: Vollständige Tagesdaten vorhanden
    if days_with_data >= completeness_threshold:
        daily_data = get_daily_data_aggregated(year, month, brand_filter)
        if daily_data:
            if aggregate_app:
                return aggregate_platforms(daily_data, aggregate_app=True)
            return daily_data
    
    # Strategie 2: Monatsdaten verfügbar (bevorzugt bei unvollständigen Tagesdaten)
    monthly_data = get_monthly_data_records(year, month, brand_filter)
    if monthly_data:
        if aggregate_app:
            return aggregate_platforms(monthly_data, aggregate_app=True)
        return monthly_data
    
    # Strategie 3: Fallback auf unvollständige Tagesdaten
    daily_data = get_daily_data_aggregated(year, month, brand_filter)
    if daily_data:
        if aggregate_app:
            return aggregate_platforms(daily_data, aggregate_app=True)
        return daily_data
    
    # Keine Daten gefunden
    return {}


# =============================================================================
# TREND-FUNKTIONEN
# =============================================================================

def get_12_month_trend(year: int, month: int, brand_filter: str = None, aggregate_app: bool = True) -> List[Dict]:
    """
    Lädt Monatsdaten für die letzten 12 Monate (inkl. aktuellem Monat).
    
    Args:
        year: Jahr des Endmonats
        month: Endmonat
        brand_filter: Optional - nur bestimmte Brand
        aggregate_app: iOS+Android zu App zusammenfassen
    
    Returns:
        Liste von Dictionaries (ältester Monat zuerst):
        [
            {"year": 2024, "month": 12, "month_str": "Dez 2024", "data": {...}},
            {"year": 2025, "month": 1, "month_str": "Jan 2025", "data": {...}},
            ...
        ]
    """
    month_names = ["", "Jan", "Feb", "Mär", "Apr", "Mai", "Jun", 
                   "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]
    
    trend = []
    current_year, current_month = year, month
    
    # 12 Monate rückwärts sammeln (dann umkehren)
    for _ in range(12):
        month_str = f"{month_names[current_month]} {current_year}"
        
        data = get_monthly_data(current_year, current_month, brand_filter, aggregate_app)
        
        trend.append({
            "year": current_year,
            "month": current_month,
            "month_str": month_str,
            "data": data
        })
        
        # Vormonat
        current_year, current_month = get_previous_month(current_year, current_month)
        sleep(0.1)  # Rate limit
    
    # Umkehren (ältester zuerst)
    return list(reversed(trend))


def get_yoy_comparison(year: int, month: int, brand_filter: str = None, aggregate_app: bool = True) -> Dict:
    """
    Year-over-Year Vergleich: Aktueller Monat vs. Vorjahresmonat.
    
    Args:
        year: Jahr des aktuellen Monats
        month: Aktueller Monat
        brand_filter: Optional - nur bestimmte Brand
        aggregate_app: iOS+Android zu App zusammenfassen
    
    Returns:
        Dictionary mit YoY-Vergleich:
        {
            "current": {"year": 2025, "month": 12, "data": {...}},
            "previous_year": {"year": 2024, "month": 12, "data": {...}},
            "yoy_changes": {"VOL_Web": {"Page Impressions": 0.12, ...}, ...}
        }
    """
    current_data = get_monthly_data(year, month, brand_filter, aggregate_app)
    prev_year_data = get_monthly_data(year - 1, month, brand_filter, aggregate_app)
    
    # YoY-Änderungen berechnen
    yoy_changes = {}
    
    for key in current_data:
        if key in prev_year_data:
            yoy_changes[key] = {}
            for metric in current_data[key]:
                current_val = current_data[key][metric]
                prev_val = prev_year_data.get(key, {}).get(metric, 0)
                
                if prev_val > 0:
                    yoy_changes[key][metric] = (current_val - prev_val) / prev_val
                else:
                    yoy_changes[key][metric] = None
    
    return {
        "current": {
            "year": year,
            "month": month,
            "data": current_data
        },
        "previous_year": {
            "year": year - 1,
            "month": month,
            "data": prev_year_data
        },
        "yoy_changes": yoy_changes
    }


# =============================================================================
# TEST
# =============================================================================

def test_monthly_data():
    """Testet die Monatsdaten-Funktionen."""
    print("=" * 70)
    print("TEST: Monthly Data Utils")
    print("=" * 70)
    
    if not AIRTABLE_API_KEY:
        print("FEHLER: AIRTABLE_API_KEY nicht gesetzt!")
        return
    
    # Test 1: Dezember 2025 (nur Tagesdaten)
    print("\n1. Test: Dezember 2025 (NUR Tagesdaten)")
    print("-" * 70)
    dec_2025 = get_monthly_data(2025, 12, brand_filter="VOL", aggregate_app=True)
    
    for key, metrics in sorted(dec_2025.items()):
        print(f"\n   {key}:")
        for metric, value in sorted(metrics.items()):
            print(f"      {metric}: {value:,}")
    
    # Test 2: Januar 2024 (nur Monatsdaten)
    print("\n2. Test: Januar 2024 (NUR Monatsdaten)")
    print("-" * 70)
    jan_2024 = get_monthly_data(2024, 1, brand_filter="VOL", aggregate_app=True)
    
    for key, metrics in sorted(jan_2024.items()):
        print(f"\n   {key}:")
        for metric, value in sorted(metrics.items()):
            print(f"      {metric}: {value:,}")
    
    # Test 3: YoY Vergleich Dezember 2025 vs 2024
    print("\n3. Test: YoY Vergleich Dezember 2025 vs. 2024")
    print("-" * 70)
    yoy = get_yoy_comparison(2025, 12, brand_filter="VOL", aggregate_app=True)
    
    print(f"\n   Dezember 2025 vs. Dezember 2024:")
    for key in yoy["yoy_changes"]:
        print(f"\n   {key}:")
        for metric, change in yoy["yoy_changes"][key].items():
            if change is not None:
                print(f"      {metric}: {change*100:+.1f}%")
            else:
                print(f"      {metric}: N/A")
    
    print("\n" + "=" * 70)
    print("TEST ABGESCHLOSSEN")
    print("=" * 70)


if __name__ == "__main__":
    # Import für Standalone-Test
    from datetime import timedelta
    test_monthly_data()

