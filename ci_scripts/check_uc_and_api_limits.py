#!/usr/bin/env python3
"""
Detaillierte Prüfung:
1. Unique Clients Coverage in Airtable
2. API Limits - exaktes ältestes Datum für alle Metriken
"""

import os
import requests
from datetime import date, datetime, timedelta
from collections import defaultdict

INFONLINE_API_KEY = os.environ.get("INFONLINE_API_KEY", "")
AIRTABLE_API_KEY = os.environ.get("AIRTABLE_API_KEY", "")
AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID", "appTIeod85xnBy7Vn")

SITES = [
    {"name": "VOL.AT Web", "site_id": "at_w_atvol"},
    {"name": "VIENNA.AT Web", "site_id": "at_w_atvienna"},
    {"name": "VOL.AT App", "site_id": "EA000004_mobile_app"},
    {"name": "VIENNA.AT App", "site_id": "EA000003_mobile_app"},
]

HOMEPAGE_SITES = [
    {"name": "VOL.AT Homepage", "site_id": "BE000072"},
    {"name": "VIENNA.AT Homepage", "site_id": "BE000043"},
]


def check_airtable_uc_coverage():
    """Prüft die Unique Clients Coverage in Airtable"""
    print("\n" + "=" * 70)
    print("📊 Unique Clients Coverage in Airtable")
    print("=" * 70)
    
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/Measurements"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    
    # Nur UC-Datensätze laden
    uc_dates = defaultdict(set)
    offset = None
    
    while True:
        params = {
            "filterByFormula": "{Metrik} = 'Unique Clients'",
            "fields[]": ["Datum", "Brand", "Plattform"],
            "pageSize": 100
        }
        if offset:
            params["offset"] = offset
            
        response = requests.get(url, headers=headers, params=params, timeout=30)
        if response.status_code != 200:
            break
            
        data = response.json()
        for record in data.get("records", []):
            fields = record.get("fields", {})
            datum = fields.get("Datum")
            brand = fields.get("Brand")
            platform = fields.get("Plattform")
            if datum and brand and platform:
                key = f"{brand}_{platform}"
                uc_dates[key].add(datum)
        
        offset = data.get("offset")
        if not offset:
            break
    
    print("\n📈 Unique Clients Datensätze:")
    for key in sorted(uc_dates.keys()):
        dates = sorted(uc_dates[key])
        if dates:
            print(f"   {key}: {len(dates)} Tage ({dates[0]} bis {dates[-1]})")
        else:
            print(f"   {key}: ❌ Keine Daten!")
    
    return uc_dates


def find_exact_api_limits():
    """Findet das exakte älteste verfügbare Datum für jede Site/Metrik"""
    print("\n" + "=" * 70)
    print("🔬 Exakte API-Limits (ältestes verfügbares Datum)")
    print("=" * 70)
    
    def check_date(site_id: str, metric: str, target_date: date) -> bool:
        url = f"https://reportingapi.infonline.de/api/v1/{metric}"
        params = {
            "site": site_id,
            "date": target_date.isoformat(),
            "aggregation": "DAY"
        }
        headers = {"authorization": INFONLINE_API_KEY, "Accept": "application/json"}
        
        try:
            response = requests.get(url, params=params, headers=headers, timeout=30)
            if response.status_code == 200:
                data = response.json()
                if "data" in data and "iom" in data["data"] and len(data["data"]["iom"]) > 0:
                    return True
            return False
        except:
            return False
    
    def binary_search_oldest(site_id: str, metric: str) -> date:
        """Binäre Suche für ältestes Datum"""
        low = 1
        high = 800  # Max 800 Tage zurück testen
        oldest = None
        
        while low <= high:
            mid = (low + high) // 2
            test_date = date.today() - timedelta(days=mid)
            
            if check_date(site_id, metric, test_date):
                oldest = test_date
                low = mid + 1
            else:
                high = mid - 1
        
        return oldest
    
    results = {}
    
    # Standard Sites
    print("\n📊 Standard Sites (PI, Visits, UC):")
    for site in SITES:
        print(f"\n   🌐 {site['name']}:")
        for metric in ["pageimpressions", "visits", "uniqueclients"]:
            oldest = binary_search_oldest(site["site_id"], metric)
            if oldest:
                days = (date.today() - oldest).days
                print(f"      {metric}: {oldest} ({days} Tage)")
                results[f"{site['name']}_{metric}"] = oldest
            else:
                print(f"      {metric}: ❌ Keine Daten")
    
    # Homepage Sites
    print("\n🏠 Homepage Sites (PI):")
    for site in HOMEPAGE_SITES:
        oldest = binary_search_oldest(site["site_id"], "pageimpressions")
        if oldest:
            days = (date.today() - oldest).days
            print(f"   {site['name']}: {oldest} ({days} Tage)")
            results[f"{site['name']}_pi"] = oldest
        else:
            print(f"   {site['name']}: ❌ Keine Daten")
    
    return results


def calculate_backfill_requirements(api_limits: dict):
    """Berechnet den nötigen Backfill"""
    print("\n" + "=" * 70)
    print("📋 Backfill-Anforderungen")
    print("=" * 70)
    
    # Ältestes API-Datum über alle Sites/Metriken
    all_dates = [d for d in api_limits.values() if d]
    if not all_dates:
        print("❌ Keine API-Daten verfügbar")
        return
    
    oldest_api = min(all_dates)
    newest_needed = date.today() - timedelta(days=1)
    
    print(f"\n📅 API-Verfügbarkeit:")
    print(f"   Ältestes verfügbares Datum: {oldest_api}")
    print(f"   Das entspricht: {(date.today() - oldest_api).days} Tage zurück")
    
    # Prüfen ob 1 Jahr möglich ist
    one_year_ago = date.today() - timedelta(days=365)
    
    print(f"\n🎯 Ziel-Analyse:")
    print(f"   1 Jahr zurück wäre: {one_year_ago}")
    
    if oldest_api <= one_year_ago:
        print(f"   ✅ 1 Jahr Backfill ist MÖGLICH!")
    else:
        days_missing = (oldest_api - one_year_ago).days
        print(f"   ⚠️ 1 Jahr Backfill ist NICHT möglich!")
        print(f"   ❌ Es fehlen {days_missing} Tage (API beginnt erst ab {oldest_api})")
        print(f"\n💡 EMPFEHLUNG:")
        print(f"   Führe maximalen Backfill bis {oldest_api} durch.")
        print(f"   YoY-Vergleiche werden ab {oldest_api + timedelta(days=365)} möglich.")
    
    return oldest_api


def main():
    print("=" * 70)
    print("🔍 DETAILLIERTE DATEN-ANALYSE")
    print("=" * 70)
    
    # 1. UC Coverage prüfen
    if AIRTABLE_API_KEY:
        check_airtable_uc_coverage()
    
    # 2. Exakte API-Limits
    if INFONLINE_API_KEY:
        api_limits = find_exact_api_limits()
        calculate_backfill_requirements(api_limits)
    
    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()

