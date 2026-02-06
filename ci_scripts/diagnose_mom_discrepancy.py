#!/usr/bin/env python3
"""
Diagnose-Script: MOM-Diskrepanz zwischen PM und Tool
=====================================================

Dieses Script analysiert die Diskrepanz zwischen:
- Projektmanagement-Daten (direkt vom INFOnline Dashboard)
- Tool-Daten (aus Airtable aggregiert)

Es prüft:
1. Wie viele Tage für Januar 2026 in Airtable existieren
2. Was die Tagessummen in Airtable ergeben
3. Was die INFOnline API mit aggregation=MONTH liefert
4. Die Differenz zwischen beiden Werten

Nutzung:
    python ci_scripts/diagnose_mom_discrepancy.py
    
    # Oder für einen anderen Monat:
    python ci_scripts/diagnose_mom_discrepancy.py --year 2025 --month 12
"""

import os
import sys
import requests
import argparse
from datetime import date, timedelta
from collections import defaultdict
from calendar import monthrange

# =============================================================================
# KONFIGURATION
# =============================================================================
INFONLINE_API_KEY = os.environ.get("INFONLINE_API_KEY", "")
AIRTABLE_API_KEY = os.environ.get("AIRTABLE_API_KEY", "")
AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID", "")

# VOL.AT Sites
SITES = {
    "Web": {"site_id": "at_w_atvol", "name": "VOL.AT Web"},
    "iOS": {"site_id": "at_i_volat", "name": "VOL.AT iOS"},
    "Android": {"site_id": "at_a_volat", "name": "VOL.AT Android"},
    "Homepage": {"site_id": "BE000072", "name": "VOL.AT Homepage"},
}

METRICS = {
    "pageimpressions": {"api_field": "pis", "airtable_name": "Page Impressions"},
    "visits": {"api_field": "visits", "airtable_name": "Visits"},
    "uniqueclients": {"api_field": "uclients", "airtable_name": "Unique Clients"},
}

# Referenzwerte vom Projektmanagement (Screenshot)
PM_REFERENCE = {
    "Web": {
        "Visits": 13759624,
        "Page Impressions": 40979876,
        "Unique Clients": 1907762,
    }
}


# =============================================================================
# API FUNKTIONEN
# =============================================================================

def fetch_infonline_monthly(site_id: str, metric: str, year: int, month: int) -> dict:
    """
    Ruft Monatsdaten von der INFOnline API ab.
    Verwendet aggregation=MONTH für offizielle Monatswerte.
    """
    target_date = date(year, month, 1)
    
    url = f"https://reportingapi.infonline.de/api/v1/{metric}"
    params = {
        "site": site_id,
        "date": target_date.isoformat(),
        "aggregation": "MONTH"  # WICHTIG: Offizielle Monatswerte!
    }
    headers = {
        "authorization": INFONLINE_API_KEY,
        "Accept": "application/json"
    }
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=30)
        if response.status_code == 200:
            return {"success": True, "data": response.json()}
        else:
            return {"success": False, "error": f"HTTP {response.status_code}", "text": response.text[:200]}
    except Exception as e:
        return {"success": False, "error": str(e)}


def extract_iom_value(data: dict, api_field: str) -> int:
    """Extrahiert den IOM-Wert (hochgerechneter offizieller Wert)"""
    if not data.get("success"):
        return 0
    
    api_data = data.get("data", {})
    if "iom" in api_data and len(api_data["iom"]) > 0:
        return api_data["iom"][0].get(api_field, 0)
    
    return 0


def get_airtable_daily_data(year: int, month: int) -> dict:
    """
    Lädt alle Tagesdaten für einen Monat aus Airtable.
    Gibt auch die Anzahl der Tage mit Daten zurück.
    """
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/Measurements"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    
    _, last_day = monthrange(year, month)
    start = date(year, month, 1)
    end = date(year, month, last_day)
    
    # Filter: Nur VOL, keine _MONTH_ Records
    formula = f"AND(IS_AFTER({{Datum}}, '{(start - timedelta(days=1)).isoformat()}'), IS_BEFORE({{Datum}}, '{(end + timedelta(days=1)).isoformat()}'), {{Brand}} = 'VOL', FIND('_MONTH_', {{Unique Key}}) = 0)"
    
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
            print(f"   ⚠️ Airtable Fehler: {response.status_code}")
            break
        
        data = response.json()
        records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break
    
    # Aggregieren
    result = {
        "records": records,
        "dates": set(),
        "by_platform": defaultdict(lambda: defaultdict(int)),
        "total": defaultdict(int)
    }
    
    for record in records:
        fields = record.get("fields", {})
        datum = fields.get("Datum", "")
        platform = fields.get("Plattform", "Web")
        metric = fields.get("Metrik", "")
        value = fields.get("Wert", 0)
        
        if datum and metric and value:
            result["dates"].add(datum)
            result["by_platform"][platform][metric] += value
            result["total"][metric] += value
    
    return result


def get_airtable_monthly_records(year: int, month: int) -> dict:
    """
    Lädt _MONTH_ Records aus Airtable (falls vorhanden).
    """
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/Measurements"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    
    month_prefix = f"{year}-{month:02d}_MONTH_VOL"
    formula = f"FIND('{month_prefix}', {{Unique Key}}) > 0"
    
    params = {
        "filterByFormula": formula,
        "pageSize": 100
    }
    
    response = requests.get(url, headers=headers, params=params, timeout=30)
    
    result = defaultdict(lambda: defaultdict(int))
    
    if response.status_code == 200:
        for record in response.json().get("records", []):
            fields = record.get("fields", {})
            platform = fields.get("Plattform", "Web")
            metric = fields.get("Metrik", "")
            value = fields.get("Wert", 0)
            
            if metric and value:
                result[platform][metric] = value
    
    return dict(result)


# =============================================================================
# HAUPTANALYSE
# =============================================================================

def run_diagnosis(year: int, month: int):
    """Führt die vollständige Diagnose durch."""
    
    print("=" * 80)
    print(f"📊 DIAGNOSE: MOM-Diskrepanz für {month:02d}/{year}")
    print("=" * 80)
    
    _, last_day = monthrange(year, month)
    
    # Prüfe Konfiguration
    if not INFONLINE_API_KEY:
        print("❌ INFONLINE_API_KEY nicht gesetzt!")
        print("   Bitte setzen Sie die Umgebungsvariable.")
        return
    
    if not AIRTABLE_API_KEY or not AIRTABLE_BASE_ID:
        print("❌ Airtable-Konfiguration fehlt!")
        print("   Bitte setzen Sie AIRTABLE_API_KEY und AIRTABLE_BASE_ID.")
        return
    
    # =========================================================================
    # PHASE 1: Airtable Tagesdaten
    # =========================================================================
    print("\n" + "=" * 80)
    print("📁 PHASE 1: Airtable Tagesdaten")
    print("=" * 80)
    
    daily_data = get_airtable_daily_data(year, month)
    days_with_data = len(daily_data["dates"])
    
    print(f"\n   📅 Tage mit Daten: {days_with_data} von {last_day} ({days_with_data/last_day*100:.1f}%)")
    
    if days_with_data < last_day:
        missing_days = last_day - days_with_data
        print(f"   ⚠️  ACHTUNG: {missing_days} Tage FEHLEN!")
        
        # Welche Tage fehlen?
        all_dates = set()
        for d in range(1, last_day + 1):
            all_dates.add(f"{year}-{month:02d}-{d:02d}")
        
        missing = all_dates - daily_data["dates"]
        if missing:
            print(f"   📋 Fehlende Tage: {sorted(missing)[:10]}...")
    
    print("\n   === Tagesdaten-Summen (Airtable) ===")
    print(f"\n   {'Plattform':<15} {'Visits':>15} {'PI':>18} {'UC':>15}")
    print("   " + "-" * 65)
    
    for platform in ["Web", "iOS", "Android"]:
        data = daily_data["by_platform"].get(platform, {})
        visits = data.get("Visits", 0)
        pi = data.get("Page Impressions", 0)
        uc = data.get("Unique Clients", 0)
        print(f"   {platform:<15} {visits:>15,} {pi:>18,} {uc:>15,}")
    
    print("   " + "-" * 65)
    total = daily_data["total"]
    print(f"   {'GESAMT':<15} {total.get('Visits', 0):>15,} {total.get('Page Impressions', 0):>18,} {total.get('Unique Clients', 0):>15,}")
    
    # =========================================================================
    # PHASE 2: Airtable Monatsdaten (_MONTH_)
    # =========================================================================
    print("\n" + "=" * 80)
    print("📁 PHASE 2: Airtable Monatsdaten (_MONTH_ Records)")
    print("=" * 80)
    
    monthly_records = get_airtable_monthly_records(year, month)
    
    if monthly_records:
        print("\n   ✅ _MONTH_ Records gefunden:")
        print(f"\n   {'Plattform':<15} {'Visits':>15} {'PI':>18} {'UC':>15}")
        print("   " + "-" * 65)
        
        total_monthly = defaultdict(int)
        for platform in ["Web", "iOS", "Android"]:
            data = monthly_records.get(platform, {})
            visits = data.get("Visits", 0)
            pi = data.get("Page Impressions", 0)
            uc = data.get("Unique Clients", 0)
            total_monthly["Visits"] += visits
            total_monthly["Page Impressions"] += pi
            total_monthly["Unique Clients"] += uc
            print(f"   {platform:<15} {visits:>15,} {pi:>18,} {uc:>15,}")
        
        print("   " + "-" * 65)
        print(f"   {'GESAMT':<15} {total_monthly['Visits']:>15,} {total_monthly['Page Impressions']:>18,} {total_monthly['Unique Clients']:>15,}")
    else:
        print("\n   ⚠️ KEINE _MONTH_ Records gefunden!")
        print("   → Das Tool aggregiert vermutlich Tagesdaten (die unvollständig sein könnten)")
    
    # =========================================================================
    # PHASE 3: INFOnline API (aggregation=MONTH)
    # =========================================================================
    print("\n" + "=" * 80)
    print("🌐 PHASE 3: INFOnline API (aggregation=MONTH)")
    print("=" * 80)
    
    api_data = {}
    
    print("\n   Rufe offizielle Monatswerte von INFOnline API ab...")
    
    for platform, site_info in SITES.items():
        if platform == "Homepage":
            continue  # Überspringen für diese Analyse
        
        api_data[platform] = {}
        site_id = site_info["site_id"]
        
        for metric_key, metric_info in METRICS.items():
            result = fetch_infonline_monthly(site_id, metric_key, year, month)
            value = extract_iom_value(result, metric_info["api_field"])
            api_data[platform][metric_info["airtable_name"]] = value
            
            if not result.get("success"):
                print(f"   ⚠️ {platform}/{metric_key}: {result.get('error', 'Fehler')}")
    
    print("\n   === INFOnline API Werte (OFFIZIELL) ===")
    print(f"\n   {'Plattform':<15} {'Visits':>15} {'PI':>18} {'UC':>15}")
    print("   " + "-" * 65)
    
    total_api = defaultdict(int)
    for platform in ["Web", "iOS", "Android"]:
        data = api_data.get(platform, {})
        visits = data.get("Visits", 0)
        pi = data.get("Page Impressions", 0)
        uc = data.get("Unique Clients", 0)
        total_api["Visits"] += visits
        total_api["Page Impressions"] += pi
        total_api["Unique Clients"] += uc
        print(f"   {platform:<15} {visits:>15,} {pi:>18,} {uc:>15,}")
    
    print("   " + "-" * 65)
    print(f"   {'GESAMT':<15} {total_api['Visits']:>15,} {total_api['Page Impressions']:>18,} {total_api['Unique Clients']:>15,}")
    
    # =========================================================================
    # PHASE 4: Vergleich
    # =========================================================================
    print("\n" + "=" * 80)
    print("📊 PHASE 4: VERGLEICH")
    print("=" * 80)
    
    # Web-Vergleich mit PM-Referenz
    print("\n   === Vergleich: Web (API vs. PM-Referenz) ===")
    web_api = api_data.get("Web", {})
    web_pm = PM_REFERENCE.get("Web", {})
    
    print(f"\n   {'Metrik':<20} {'INFOnline API':>15} {'PM-Referenz':>15} {'Differenz':>12}")
    print("   " + "-" * 65)
    
    for metric in ["Visits", "Page Impressions", "Unique Clients"]:
        api_val = web_api.get(metric, 0)
        pm_val = web_pm.get(metric, 0)
        diff = api_val - pm_val
        diff_pct = (diff / pm_val * 100) if pm_val > 0 else 0
        status = "✓" if abs(diff_pct) < 1 else "⚠️"
        print(f"   {metric:<20} {api_val:>15,} {pm_val:>15,} {diff:>+12,} {status}")
    
    # Airtable Tagesdaten vs. API
    print("\n   === Vergleich: Airtable Tagessumme vs. INFOnline API (Web) ===")
    
    airtable_web = daily_data["by_platform"].get("Web", {})
    
    print(f"\n   {'Metrik':<20} {'Airtable (Tage)':>15} {'INFOnline API':>15} {'Differenz':>12} {'Delta %':>10}")
    print("   " + "-" * 75)
    
    for metric in ["Visits", "Page Impressions", "Unique Clients"]:
        at_val = airtable_web.get(metric, 0)
        api_val = web_api.get(metric, 0)
        diff = at_val - api_val
        diff_pct = (diff / api_val * 100) if api_val > 0 else 0
        status = "✓" if abs(diff_pct) < 1 else "❌"
        print(f"   {metric:<20} {at_val:>15,} {api_val:>15,} {diff:>+12,} {diff_pct:>+9.2f}% {status}")
    
    # =========================================================================
    # PHASE 5: DIAGNOSE
    # =========================================================================
    print("\n" + "=" * 80)
    print("🔍 DIAGNOSE & EMPFEHLUNG")
    print("=" * 80)
    
    # Berechne Hauptdiskrepanz
    airtable_web_visits = airtable_web.get("Visits", 0)
    api_web_visits = web_api.get("Visits", 0)
    visits_diff_pct = ((airtable_web_visits - api_web_visits) / api_web_visits * 100) if api_web_visits > 0 else 0
    
    if days_with_data < last_day:
        print(f"""
   🔴 HAUPTPROBLEM IDENTIFIZIERT: UNVOLLSTÄNDIGE TAGESDATEN
   
   In Airtable existieren nur {days_with_data} von {last_day} Tagen für {month:02d}/{year}.
   
   → Die Tagessummen sind daher um ca. {100 - (days_with_data/last_day*100):.1f}% zu niedrig!
   → Das erklärt die Diskrepanz zwischen Tool und PM-Daten.
   
   LÖSUNG:
   1. Fehlende Tagesdaten nachimportieren (backfill.py)
   ODER
   2. _MONTH_ Records aus INFOnline API verwenden (aggregation=MONTH)
""")
    elif abs(visits_diff_pct) > 2:
        print(f"""
   🟡 DISKREPANZ GEFUNDEN: Airtable-Tagessumme ≠ INFOnline-Monatswert
   
   Differenz bei Web-Visits: {visits_diff_pct:+.2f}%
   
   Mögliche Ursachen:
   - IOM-Hochrechnung variiert zwischen Tages- und Monatsaggregation
   - Vorläufige vs. endgültige Daten
   
   LÖSUNG:
   Verwenden Sie aggregation=MONTH für die offiziellen ÖWA-Werte.
""")
    else:
        print(f"""
   🟢 KEINE SIGNIFIKANTE DISKREPANZ
   
   Airtable-Tagesdaten und INFOnline-Monatswerte stimmen weitgehend überein.
   
   Falls dennoch Unterschiede zum PM auftreten, prüfen Sie:
   - Werden im PM andere Filterkriterien verwendet?
   - Werden im PM andere Zeiträume verglichen?
""")
    
    print("\n" + "=" * 80)
    print("✅ DIAGNOSE ABGESCHLOSSEN")
    print("=" * 80)


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MOM-Diskrepanz Diagnose")
    parser.add_argument("--year", type=int, default=2026, help="Jahr (default: 2026)")
    parser.add_argument("--month", type=int, default=1, help="Monat (default: 1)")
    args = parser.parse_args()
    
    run_diagnosis(args.year, args.month)
