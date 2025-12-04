#!/usr/bin/env python3
"""
Cleanup-Skript: Entfernt Duplikate aus Airtable
===============================================
Behält nur den ersten Eintrag pro Unique Key.

Nutzung:
    $env:AIRTABLE_API_KEY = "dein_token"
    python cleanup_duplicates.py
"""

import os
import requests
from collections import defaultdict
from time import sleep

AIRTABLE_API_KEY = os.environ.get("AIRTABLE_API_KEY", "")
AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID", "appTIeod85xnBy7Vn")


def get_all_records():
    """Holt alle Records aus Airtable"""
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/Measurements"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    
    all_records = []
    offset = None
    
    while True:
        params = {"pageSize": 100}
        if offset:
            params["offset"] = offset
            
        response = requests.get(url, headers=headers, params=params, timeout=30)
        if response.status_code != 200:
            print(f"❌ Fehler: {response.status_code}")
            break
            
        data = response.json()
        all_records.extend(data.get("records", []))
        
        offset = data.get("offset")
        if not offset:
            break
    
    return all_records


def delete_records(record_ids: list):
    """Löscht Records aus Airtable"""
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/Measurements"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    
    deleted = 0
    
    # Batch-Delete (max 10 pro Request)
    for i in range(0, len(record_ids), 10):
        batch = record_ids[i:i+10]
        params = {"records[]": batch}
        
        # Airtable erwartet die IDs als separate Parameter
        delete_url = url + "?" + "&".join([f"records[]={rid}" for rid in batch])
        
        response = requests.delete(delete_url, headers=headers, timeout=30)
        if response.status_code == 200:
            deleted += len(batch)
            print(f"   ✅ {len(batch)} Records gelöscht")
        else:
            print(f"   ❌ Fehler beim Löschen: {response.status_code} - {response.text[:100]}")
        
        sleep(0.3)  # Rate limiting
    
    return deleted


def main():
    print("=" * 70)
    print("🧹 AIRTABLE DUPLIKAT-BEREINIGUNG")
    print("=" * 70)
    
    if not AIRTABLE_API_KEY:
        print("❌ AIRTABLE_API_KEY nicht gesetzt!")
        print("   Setze: $env:AIRTABLE_API_KEY = 'dein_token'")
        return
    
    # Alle Records holen
    print("\n📥 Lade alle Records aus Airtable...")
    records = get_all_records()
    print(f"   → {len(records)} Records gefunden")
    
    if not records:
        print("❌ Keine Records gefunden!")
        return
    
    # Nach Unique Key gruppieren
    print("\n🔍 Analysiere Duplikate...")
    records_by_key = defaultdict(list)
    
    for record in records:
        unique_key = record.get("fields", {}).get("Unique Key", "")
        datum = record.get("fields", {}).get("Datum", "")
        brand = record.get("fields", {}).get("Brand", "")
        metrik = record.get("fields", {}).get("Metrik", "")
        
        # Fallback wenn kein Unique Key gesetzt
        if not unique_key:
            unique_key = f"{datum}_{brand}_{metrik}"
        
        records_by_key[unique_key].append({
            "id": record["id"],
            "created": record.get("createdTime", ""),
            "fields": record.get("fields", {})
        })
    
    # Duplikate finden
    duplicates_to_delete = []
    
    for key, recs in records_by_key.items():
        if len(recs) > 1:
            # Sortiere nach Erstellungszeit, behalte den ersten (ältesten)
            recs_sorted = sorted(recs, key=lambda x: x["created"])
            
            # Alle außer dem ersten sind Duplikate
            for dup in recs_sorted[1:]:
                duplicates_to_delete.append(dup["id"])
                datum = dup["fields"].get("Datum", "?")
                brand = dup["fields"].get("Brand", "?")
                metrik = dup["fields"].get("Metrik", "?")
                print(f"   🔴 Duplikat: {datum} | {brand} | {metrik}")
    
    print(f"\n📊 Ergebnis:")
    print(f"   Unique Keys: {len(records_by_key)}")
    print(f"   Duplikate gefunden: {len(duplicates_to_delete)}")
    
    if not duplicates_to_delete:
        print("\n✅ Keine Duplikate gefunden!")
        return
    
    # Bestätigung
    print(f"\n⚠️ {len(duplicates_to_delete)} Duplikate werden gelöscht!")
    confirm = input("   Fortfahren? (j/n): ").strip().lower()
    
    if confirm != "j":
        print("   Abgebrochen.")
        return
    
    # Löschen
    print(f"\n🗑️ Lösche {len(duplicates_to_delete)} Duplikate...")
    deleted = delete_records(duplicates_to_delete)
    
    print(f"\n" + "=" * 70)
    print(f"✅ BEREINIGUNG ABGESCHLOSSEN")
    print(f"   Gelöscht: {deleted} Duplikate")
    print("=" * 70)


if __name__ == "__main__":
    main()

