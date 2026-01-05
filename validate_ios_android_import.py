#!/usr/bin/env python3
"""
Validierung: iOS/Android Import
================================
Vergleicht die importierten iOS+Android Summen mit den gesicherten App-Statistiken.

Nutzung:
    python validate_ios_android_import.py
"""

import os
import json
import requests
from collections import defaultdict
from datetime import datetime

AIRTABLE_API_KEY = os.environ.get("AIRTABLE_API_KEY", "")
AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID", "appTIeod85xnBy7Vn")

BACKUP_FILE = "app_data_backup_stats.json"


def load_backup_stats() -> dict:
    """Laedt die gesicherten App-Statistiken."""
    if not os.path.exists(BACKUP_FILE):
        print(f"[ERROR] Backup-Datei nicht gefunden: {BACKUP_FILE}")
        return None
    
    with open(BACKUP_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def get_ios_android_stats() -> dict:
    """Holt aktuelle iOS/Android Summen aus Airtable."""
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/Measurements"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    
    stats = defaultdict(lambda: defaultdict(lambda: {"sum": 0, "count": 0}))
    records_count = 0
    offset = None
    
    print("Lade iOS/Android Daten aus Airtable...")
    
    while True:
        params = {
            "filterByFormula": "OR({Plattform} = 'iOS', {Plattform} = 'Android')",
            "pageSize": 100
        }
        if offset:
            params["offset"] = offset
        
        response = requests.get(url, headers=headers, params=params, timeout=30)
        if response.status_code != 200:
            print(f"[ERROR] Airtable Fehler: {response.status_code}")
            break
        
        data = response.json()
        
        for record in data.get("records", []):
            fields = record.get("fields", {})
            brand = fields.get("Brand", "Unknown")
            metric = fields.get("Metrik", "Unknown")
            wert = fields.get("Wert", 0) or 0
            
            stats[brand][metric]["sum"] += wert
            stats[brand][metric]["count"] += 1
            records_count += 1
        
        offset = data.get("offset")
        if not offset:
            break
        
        print(f"   ... {records_count} Records geladen", end="\r")
    
    print(f"   [OK] {records_count} iOS/Android Records geladen")
    return dict(stats)


def main():
    print("=" * 70)
    print("Validierung: iOS/Android Import")
    print("=" * 70)
    
    if not AIRTABLE_API_KEY:
        print("[ERROR] AIRTABLE_API_KEY nicht gesetzt!")
        return
    
    # Backup laden
    print(f"\nLade Backup-Statistik aus: {BACKUP_FILE}")
    backup = load_backup_stats()
    
    if not backup:
        print("[ERROR] Keine Backup-Daten verfuegbar - Validierung nicht moeglich!")
        return
    
    print(f"   [OK] Backup vom {backup.get('created_at', 'unbekannt')}")
    print(f"   [OK] {backup.get('total_records', 0)} alte App-Records")
    
    # Aktuelle iOS/Android Daten laden
    print()
    current = get_ios_android_stats()
    
    if not current:
        print("[ERROR] Keine iOS/Android Daten in Airtable!")
        return
    
    # Vergleich
    print("\n" + "=" * 70)
    print("VERGLEICH: Alt (App) vs. Neu (iOS + Android)")
    print("=" * 70)
    
    backup_summary = backup.get("summary", {})
    
    overall_ok = True
    
    for brand in sorted(set(backup_summary.keys()) | set(current.keys())):
        print(f"\n{brand}:")
        
        backup_metrics = backup_summary.get(brand, {})
        current_metrics = current.get(brand, {})
        
        all_metrics = sorted(set(backup_metrics.keys()) | set(current_metrics.keys()))
        
        for metric in all_metrics:
            old_sum = backup_metrics.get(metric, {}).get("sum", 0)
            new_sum = current_metrics.get(metric, {}).get("sum", 0)
            old_count = backup_metrics.get(metric, {}).get("count", 0)
            new_count = current_metrics.get(metric, {}).get("count", 0)
            
            if old_sum > 0:
                diff_pct = ((new_sum - old_sum) / old_sum) * 100
            else:
                diff_pct = 100 if new_sum > 0 else 0
            
            # Status bestimmen
            if abs(diff_pct) < 5:
                status = "[OK]"
            elif abs(diff_pct) < 10:
                status = "[WARNUNG]"
                overall_ok = False
            else:
                status = "[FEHLER]"
                overall_ok = False
            
            print(f"   {metric}:")
            print(f"      Alt (App):         {old_sum:>15,.0f} ({old_count} Records)")
            print(f"      Neu (iOS+Android): {new_sum:>15,.0f} ({new_count} Records)")
            print(f"      Differenz:         {diff_pct:>+15.2f}% {status}")
    
    # Zusammenfassung
    print("\n" + "=" * 70)
    if overall_ok:
        print("[OK] VALIDIERUNG ERFOLGREICH")
        print("    Die iOS + Android Summen entsprechen den alten App-Daten!")
    else:
        print("[WARNUNG] VALIDIERUNG MIT ABWEICHUNGEN")
        print("    Bitte pruefen Sie die Differenzen oben.")
    print("=" * 70)


if __name__ == "__main__":
    main()

