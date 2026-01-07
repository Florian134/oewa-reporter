#!/usr/bin/env python3
"""
Daten-Coverage-Analyse
======================
Analysiert:
1. Welche Daten sind bereits in Airtable gespeichert?
2. Wie weit reichen die ÖWA API Daten zurück?
3. Welche Lücken gibt es?

Nutzung:
    python ci_scripts/analyze_data_coverage.py
"""

import os
import requests
from datetime import date, datetime, timedelta
from collections import defaultdict

# Konfiguration
INFONLINE_API_KEY = os.environ.get("INFONLINE_API_KEY", "")
AIRTABLE_API_KEY = os.environ.get("AIRTABLE_API_KEY", "")
AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID", "")  # Muss in CI/CD Variables gesetzt sein

# Sites zum Testen (Web + iOS + Android)
TEST_SITES = [
    # === WEB ===
    {"name": "VOL.AT Web", "site_id": "at_w_atvol", "brand": "VOL", "surface": "Web"},
    {"name": "VIENNA.AT Web", "site_id": "at_w_atvienna", "brand": "Vienna", "surface": "Web"},
    
    # === iOS ===
    {"name": "VOL.AT iOS", "site_id": "at_i_volat", "brand": "VOL", "surface": "iOS"},
    {"name": "VIENNA.AT iOS", "site_id": "at_i_viennaat", "brand": "Vienna", "surface": "iOS"},
    
    # === Android ===
    {"name": "VOL.AT Android", "site_id": "at_a_volat", "brand": "VOL", "surface": "Android"},
    {"name": "VIENNA.AT Android", "site_id": "at_a_viennaat", "brand": "Vienna", "surface": "Android"},
    
    # === Homepage ===
    {"name": "VOL.AT Homepage", "site_id": "BE000072", "brand": "VOL", "surface": "Web", "metric": "Homepage PI"},
    {"name": "VIENNA.AT Homepage", "site_id": "BE000043", "brand": "Vienna", "surface": "Web", "metric": "Homepage PI"},
]

METRICS = ["pageimpressions", "visits", "uniqueclients"]


def analyze_airtable_data():
    """Analysiert die vorhandenen Daten in Airtable"""
    print("\n" + "=" * 70)
    print("📊 PHASE 1: Analyse der Airtable-Daten")
    print("=" * 70)
    
    if not AIRTABLE_API_KEY:
        print("❌ AIRTABLE_API_KEY nicht gesetzt!")
        return None
    
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/Measurements"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    
    all_records = []
    offset = None
    
    print("\n📥 Lade alle Datensätze aus Airtable...")
    
    while True:
        params = {
            "fields[]": ["Datum", "Brand", "Plattform", "Metrik"],
            "pageSize": 100
        }
        if offset:
            params["offset"] = offset
            
        response = requests.get(url, headers=headers, params=params, timeout=30)
        if response.status_code != 200:
            print(f"❌ Fehler: {response.status_code}")
            break
            
        data = response.json()
        all_records.extend(data.get("records", []))
        
        offset = data.get("offset")
        print(f"   ... {len(all_records)} Datensätze geladen", end="\r")
        
        if not offset:
            break
    
    print(f"\n\n✅ Gesamt: {len(all_records)} Datensätze in Airtable")
    
    # Analyse der Daten
    dates = set()
    metrics_count = defaultdict(int)
    brands_count = defaultdict(int)
    platforms_count = defaultdict(int)
    combination_coverage = defaultdict(set)  # {brand_platform_metric: set(dates)}
    
    for record in all_records:
        fields = record.get("fields", {})
        datum = fields.get("Datum")
        brand = fields.get("Brand")
        platform = fields.get("Plattform")
        metric = fields.get("Metrik")
        
        if datum:
            dates.add(datum)
        if brand:
            brands_count[brand] += 1
        if platform:
            platforms_count[platform] += 1
        if metric:
            metrics_count[metric] += 1
        
        if all([datum, brand, platform, metric]):
            key = f"{brand}_{platform}_{metric}"
            combination_coverage[key].add(datum)
    
    # Sortieren
    sorted_dates = sorted(dates)
    min_date = sorted_dates[0] if sorted_dates else None
    max_date = sorted_dates[-1] if sorted_dates else None
    
    print("\n" + "-" * 70)
    print("📅 DATUMS-RANGE:")
    print(f"   Ältestes Datum:  {min_date}")
    print(f"   Neuestes Datum:  {max_date}")
    if min_date and max_date:
        days_covered = (date.fromisoformat(max_date) - date.fromisoformat(min_date)).days + 1
        print(f"   Zeitspanne:      {days_covered} Tage")
        print(f"   Tage mit Daten:  {len(dates)}")
        if days_covered > len(dates):
            print(f"   ⚠️ Lücken:        {days_covered - len(dates)} Tage fehlen möglicherweise")
    
    print("\n" + "-" * 70)
    print("📊 METRIKEN:")
    for metric, count in sorted(metrics_count.items()):
        print(f"   {metric}: {count} Datensätze")
    
    print("\n" + "-" * 70)
    print("🏢 BRANDS:")
    for brand, count in sorted(brands_count.items()):
        print(f"   {brand}: {count} Datensätze")
    
    print("\n" + "-" * 70)
    print("📱 PLATTFORMEN:")
    for platform, count in sorted(platforms_count.items()):
        print(f"   {platform}: {count} Datensätze")
    
    print("\n" + "-" * 70)
    print("📈 COVERAGE PRO KOMBINATION:")
    for key in sorted(combination_coverage.keys()):
        dates_set = combination_coverage[key]
        min_d = min(dates_set)
        max_d = max(dates_set)
        print(f"   {key}: {len(dates_set)} Tage ({min_d} bis {max_d})")
    
    return {
        "total_records": len(all_records),
        "min_date": min_date,
        "max_date": max_date,
        "dates_with_data": len(dates),
        "metrics": dict(metrics_count),
        "combination_coverage": {k: len(v) for k, v in combination_coverage.items()}
    }


def test_api_historical_availability():
    """Testet, wie weit die ÖWA API historische Daten bereitstellt"""
    print("\n" + "=" * 70)
    print("🔍 PHASE 2: Test der ÖWA API - Historische Datenverfügbarkeit")
    print("=" * 70)
    
    if not INFONLINE_API_KEY:
        print("❌ INFONLINE_API_KEY nicht gesetzt!")
        return None
    
    results = {}
    
    # Test-Daten: verschiedene Zeitpunkte in der Vergangenheit
    test_dates = [
        date.today() - timedelta(days=7),    # 1 Woche
        date.today() - timedelta(days=30),   # 1 Monat
        date.today() - timedelta(days=90),   # 3 Monate
        date.today() - timedelta(days=180),  # 6 Monate
        date.today() - timedelta(days=365),  # 1 Jahr
        date.today() - timedelta(days=400),  # 13 Monate
        date.today() - timedelta(days=730),  # 2 Jahre
    ]
    
    def check_date(site_id: str, metric: str, target_date: date) -> bool:
        """Prüft ob Daten für ein bestimmtes Datum verfügbar sind"""
        url = f"https://reportingapi.infonline.de/api/v1/{metric}"
        params = {
            "site": site_id,
            "date": target_date.isoformat(),
            "aggregation": "DAY"
        }
        headers = {
            "authorization": INFONLINE_API_KEY,
            "Accept": "application/json"
        }
        
        try:
            response = requests.get(url, params=params, headers=headers, timeout=30)
            if response.status_code == 200:
                data = response.json()
                # Prüfen ob tatsächlich Daten vorhanden sind
                if "data" in data and "iom" in data["data"] and len(data["data"]["iom"]) > 0:
                    return True
            return False
        except:
            return False
    
    print("\n📡 Teste API-Verfügbarkeit für verschiedene Zeiträume...")
    print("-" * 70)
    
    # Für jede Site und Metrik testen
    for site in TEST_SITES[:2]:  # Nur VOL und Vienna Web testen
        site_name = site["name"]
        site_id = site["site_id"]
        
        print(f"\n🌐 {site_name}:")
        
        for metric in METRICS:
            print(f"   📊 {metric}:", end=" ")
            
            oldest_available = None
            for td in test_dates:
                if check_date(site_id, metric, td):
                    oldest_available = td
                else:
                    break
            
            if oldest_available:
                days_back = (date.today() - oldest_available).days
                print(f"✅ Mindestens {days_back} Tage zurück ({oldest_available})")
                results[f"{site_name}_{metric}"] = oldest_available
            else:
                print("❌ Keine historischen Daten gefunden")
    
    # Genaueren Test für älteste Daten (binäre Suche)
    print("\n" + "-" * 70)
    print("🔬 Detailierte Suche nach ältestem verfügbaren Datum...")
    
    site = TEST_SITES[0]  # VOL.AT Web
    
    # Binäre Suche für genaues ältestes Datum
    def find_oldest_date(site_id: str, metric: str, start_days: int = 1, end_days: int = 800):
        """Findet das älteste verfügbare Datum mittels binärer Suche"""
        low = start_days
        high = end_days
        oldest_found = None
        
        while low <= high:
            mid = (low + high) // 2
            test_date = date.today() - timedelta(days=mid)
            
            if check_date(site_id, metric, test_date):
                oldest_found = test_date
                low = mid + 1  # Suche nach älteren Daten
            else:
                high = mid - 1  # Suche nach neueren Daten
        
        return oldest_found
    
    for metric in ["pageimpressions", "visits"]:
        print(f"\n   🔍 {site['name']} - {metric}:")
        oldest = find_oldest_date(site["site_id"], metric, 1, 800)
        if oldest:
            days_back = (date.today() - oldest).days
            print(f"      Ältestes Datum: {oldest} ({days_back} Tage zurück)")
            results[f"oldest_{metric}"] = oldest
        else:
            print("      Konnte ältestes Datum nicht bestimmen")
    
    return results


def generate_backfill_plan(airtable_data: dict, api_data: dict):
    """Erstellt einen Backfill-Plan basierend auf der Analyse"""
    print("\n" + "=" * 70)
    print("📋 PHASE 3: Backfill-Plan")
    print("=" * 70)
    
    if not airtable_data or not api_data:
        print("❌ Nicht genug Daten für Planberechnung")
        return
    
    # Aktuelles ältestes Datum in Airtable
    current_oldest = date.fromisoformat(airtable_data["min_date"]) if airtable_data.get("min_date") else None
    
    # Ziel: 1 Jahr zurück
    target_oldest = date.today() - timedelta(days=365)
    
    print(f"\n📅 Aktuelles ältestes Datum: {current_oldest}")
    print(f"🎯 Ziel (1 Jahr zurück):     {target_oldest}")
    
    if current_oldest and current_oldest <= target_oldest:
        print("\n✅ Ziel bereits erreicht! Kein zusätzlicher Backfill nötig.")
        return
    
    # Berechne benötigte Tage
    if current_oldest:
        days_needed = (current_oldest - target_oldest).days
        start_date = target_oldest
        end_date = current_oldest - timedelta(days=1)
    else:
        days_needed = 365
        start_date = target_oldest
        end_date = date.today() - timedelta(days=1)
    
    print(f"\n📊 Backfill benötigt:")
    print(f"   Von: {start_date}")
    print(f"   Bis: {end_date}")
    print(f"   Tage: {days_needed}")
    
    # Geschätzte Datensätze
    sites = 4  # VOL Web, VOL App, Vienna Web, Vienna App
    metrics = 3  # PI, Visits, UC
    homepage_sites = 2  # VOL Homepage, Vienna Homepage
    
    estimated_records = days_needed * (sites * metrics + homepage_sites)
    print(f"   Geschätzte neue Datensätze: ~{estimated_records}")
    
    # API-Limits
    print(f"\n⏱️ Geschätzte Dauer:")
    api_calls = estimated_records
    seconds = api_calls * 0.15  # ~0.15s pro Call inkl. Rate Limiting
    minutes = seconds / 60
    print(f"   API Calls: ~{api_calls}")
    print(f"   Zeit: ~{minutes:.0f} Minuten")
    
    # Empfehlung
    print("\n" + "-" * 70)
    print("💡 EMPFEHLUNG:")
    print(f"   Führe aus: python ci_scripts/backfill.py --days {days_needed + 10}")
    print("   (+10 Tage Puffer für Überlappung)")
    
    return {
        "start_date": start_date,
        "end_date": end_date,
        "days_needed": days_needed,
        "estimated_records": estimated_records
    }


def main():
    print("=" * 70)
    print("🔍 ÖWA DATEN-COVERAGE-ANALYSE")
    print("=" * 70)
    print(f"📅 Datum: {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    
    # Phase 1: Airtable analysieren
    airtable_data = analyze_airtable_data()
    
    # Phase 2: API testen
    api_data = test_api_historical_availability()
    
    # Phase 3: Backfill-Plan
    plan = generate_backfill_plan(airtable_data, api_data)
    
    print("\n" + "=" * 70)
    print("✅ ANALYSE ABGESCHLOSSEN")
    print("=" * 70)
    
    return {
        "airtable": airtable_data,
        "api": api_data,
        "plan": plan
    }


if __name__ == "__main__":
    main()

