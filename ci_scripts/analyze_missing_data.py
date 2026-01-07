#!/usr/bin/env python3
"""
Analyse: Warum fehlen iOS/Android-Daten ab 22.12.2025?
======================================================
"""

import os
import requests
from datetime import datetime
from collections import defaultdict

AIRTABLE_API_KEY = os.environ.get("AIRTABLE_API_KEY", "")
AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID", "")  # Muss in CI/CD Variables gesetzt sein

def main():
    print("=" * 70)
    print("ANALYSE: Warum fehlen iOS/Android-Daten ab 22.12.2025?")
    print("=" * 70)
    
    if not AIRTABLE_API_KEY:
        print("FEHLER: AIRTABLE_API_KEY nicht gesetzt!")
        return
    
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/Measurements"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    
    # =========================================================================
    # 1. Alle Dezember-Daten laden (20.-31.12.)
    # =========================================================================
    print("\n1. Lade Dezember-Daten (20.12. - 31.12.)...")
    
    all_records = []
    offset = None
    
    while True:
        params = {
            "filterByFormula": "AND(IS_AFTER({Datum}, '2025-12-19'), IS_BEFORE({Datum}, '2026-01-01'), FIND('_MONTH_', {Unique Key}) = 0)",
            "pageSize": 100
        }
        if offset:
            params["offset"] = offset
        
        response = requests.get(url, headers=headers, params=params, timeout=30)
        if response.status_code != 200:
            print(f"   FEHLER: {response.status_code}")
            break
        
        data = response.json()
        all_records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break
    
    print(f"   -> {len(all_records)} Records gefunden")
    
    # =========================================================================
    # 2. Gruppiere nach Datum, Brand, Plattform
    # =========================================================================
    print("\n2. Datenverteilung nach Datum und Plattform:")
    print("-" * 70)
    
    by_date = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    
    for record in all_records:
        fields = record.get("fields", {})
        datum = fields.get("Datum", "")
        brand = fields.get("Brand", "")
        platform = fields.get("Plattform", "")
        metric = fields.get("Metrik", "")
        erfasst = fields.get("Erfasst am", "")
        
        if datum and platform:
            by_date[datum][brand][platform].append({
                "metric": metric,
                "erfasst": erfasst[:16] if erfasst else "N/A"
            })
    
    # Tabelle ausgeben
    print(f"\n{'Datum':<12} | {'Brand':<8} | {'Web':<6} | {'iOS':<6} | {'Android':<8} | {'App':<6}")
    print("-" * 70)
    
    for datum in sorted(by_date.keys()):
        for brand in sorted(by_date[datum].keys()):
            platforms = by_date[datum][brand]
            web_count = len(platforms.get("Web", []))
            ios_count = len(platforms.get("iOS", []))
            android_count = len(platforms.get("Android", []))
            app_count = len(platforms.get("App", []))
            
            # Markiere fehlende iOS/Android
            ios_str = str(ios_count) if ios_count > 0 else "FEHLT"
            android_str = str(android_count) if android_count > 0 else "FEHLT"
            
            print(f"{datum:<12} | {brand:<8} | {web_count:<6} | {ios_str:<6} | {android_str:<8} | {app_count:<6}")
    
    # =========================================================================
    # 3. Prüfe Erfassungszeitpunkte
    # =========================================================================
    print("\n3. Letzte iOS/Android-Eintraege (nach Erfassungszeit):")
    print("-" * 70)
    
    ios_android = [r for r in all_records if r.get("fields", {}).get("Plattform") in ["iOS", "Android"]]
    ios_android.sort(key=lambda x: x.get("fields", {}).get("Erfasst am", ""), reverse=True)
    
    if ios_android:
        for r in ios_android[:10]:
            f = r.get("fields", {})
            datum = f.get("Datum", "")
            brand = f.get("Brand", "")
            plat = f.get("Plattform", "")
            metric = f.get("Metrik", "")[:15]
            erfasst = f.get("Erfasst am", "N/A")[:16]
            print(f"   {datum} | {brand} {plat:<8} | {metric:<15} | Erfasst: {erfasst}")
    else:
        print("   Keine iOS/Android-Daten in diesem Zeitraum!")
    
    # =========================================================================
    # 4. Prüfe letzten Import-Zeitpunkt für iOS/Android
    # =========================================================================
    print("\n4. Letzter erfolgreicher iOS/Android-Import:")
    print("-" * 70)
    
    # Suche den letzten iOS/Android-Eintrag überhaupt
    params_last = {
        "filterByFormula": "OR({Plattform} = 'iOS', {Plattform} = 'Android')",
        "sort[0][field]": "Erfasst am",
        "sort[0][direction]": "desc",
        "maxRecords": 5
    }
    
    response = requests.get(url, headers=headers, params=params_last, timeout=30)
    if response.status_code == 200:
        last_records = response.json().get("records", [])
        if last_records:
            for r in last_records:
                f = r.get("fields", {})
                print(f"   {f.get('Datum')} | {f.get('Brand')} {f.get('Plattform')} | Erfasst: {f.get('Erfasst am', 'N/A')[:19]}")
    
    # =========================================================================
    # 5. Prüfe ob alte "App"-Daten noch importiert werden
    # =========================================================================
    print("\n5. Pruefe auf alte 'App'-Plattform-Eintraege (22.-31.12.):")
    print("-" * 70)
    
    app_records = [r for r in all_records if r.get("fields", {}).get("Plattform") == "App"]
    
    if app_records:
        print(f"   -> {len(app_records)} Records mit Plattform='App' gefunden")
        print("   PROBLEM: Es werden noch alte 'App'-Kennungen verwendet!")
        for r in app_records[:5]:
            f = r.get("fields", {})
            print(f"      {f.get('Datum')} | {f.get('Brand')} App | {f.get('Metrik')}")
    else:
        print("   -> Keine 'App'-Records in diesem Zeitraum")
    
    # =========================================================================
    # 6. Diagnose
    # =========================================================================
    print("\n" + "=" * 70)
    print("DIAGNOSE")
    print("=" * 70)
    
    # Finde den letzten Tag mit iOS/Android-Daten
    last_ios_android_date = None
    for datum in sorted(by_date.keys(), reverse=True):
        for brand in by_date[datum]:
            if "iOS" in by_date[datum][brand] or "Android" in by_date[datum][brand]:
                last_ios_android_date = datum
                break
        if last_ios_android_date:
            break
    
    if last_ios_android_date:
        print(f"\n   Letzter Tag mit iOS/Android-Daten: {last_ios_android_date}")
    else:
        print("\n   KEINE iOS/Android-Daten im Zeitraum 20.-31.12. gefunden!")
    
    # Prüfe ob das Problem am daily_ingest liegt
    print("\n   MOEGLICHE URSACHEN:")
    print("   1. Daily Ingest wurde ab 22.12. nicht mehr ausgefuehrt")
    print("   2. GitLab Schedule war waehrend Feiertagen inaktiv")
    print("   3. API-Problem bei INFOnline fuer iOS/Android-Kennungen")
    
    print("\n   LOESUNG:")
    print("   -> Backfill fuer iOS/Android fuer 22.12. - 31.12. durchfuehren")
    print("   -> unified_backfill.py mit --days 14 ausfuehren")
    
    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()

