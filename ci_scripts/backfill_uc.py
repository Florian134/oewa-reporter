#!/usr/bin/env python3
"""
Unique Clients Backfill Script
==============================
Korrigiert fehlende oder fehlerhafte Unique Clients Daten in Airtable.

Hintergrund:
- INFOnline API liefert UC erst nach ~2 Tagen mit echten Werten
- Vorher wird 0 zurückgegeben
- Dieses Script lädt korrekte UC-Daten nach und aktualisiert/erstellt Records

Nutzung:
    python ci_scripts/backfill_uc.py --days 30
    python ci_scripts/backfill_uc.py --start 2025-12-01 --end 2025-12-15
"""

import os
import json
import requests
import argparse
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

# =============================================================================
# KONFIGURATION
# =============================================================================
INFONLINE_API_KEY = os.environ.get("INFONLINE_API_KEY", "")
AIRTABLE_API_KEY = os.environ.get("AIRTABLE_API_KEY", "")
AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID", "appTIeod85xnBy7Vn")

SITES = [
    # === WEB ===
    {"name": "VOL.AT Web", "site_id": "at_w_atvol", "brand": "VOL", "surface": "Web"},
    {"name": "VIENNA.AT Web", "site_id": "at_w_atvienna", "brand": "Vienna", "surface": "Web"},
    
    # === iOS ===
    {"name": "VOL.AT iOS", "site_id": "at_i_volat", "brand": "VOL", "surface": "iOS"},
    {"name": "VIENNA.AT iOS", "site_id": "at_i_viennaat", "brand": "Vienna", "surface": "iOS"},
    
    # === Android ===
    {"name": "VOL.AT Android", "site_id": "at_a_volat", "brand": "VOL", "surface": "Android"},
    {"name": "VIENNA.AT Android", "site_id": "at_a_viennaat", "brand": "Vienna", "surface": "Android"},
]


def fetch_uc_from_api(site_id: str, target_date: date) -> Optional[int]:
    """Holt Unique Clients von der INFOnline API"""
    url = "https://reportingapi.infonline.de/api/v1/uniqueclients"
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
            iom = data.get("data", {}).get("iom", [])
            
            if iom and len(iom) > 0:
                value = iom[0].get("uclients")
                if value is not None and value > 0:
                    return value
        return None
    except Exception as e:
        print(f"      API Error: {e}")
        return None


def get_existing_uc_records(target_date: date) -> Dict[str, Dict]:
    """Holt existierende UC-Records für ein Datum aus Airtable"""
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/Measurements"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    
    params = {
        "filterByFormula": f"AND({{Datum}} = '{target_date.isoformat()}', {{Metrik}} = 'Unique Clients')",
        "pageSize": 100
    }
    
    records = {}
    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        if response.status_code == 200:
            data = response.json()
            for r in data.get("records", []):
                fields = r.get("fields", {})
                key = f"{fields.get('Brand')}_{fields.get('Plattform')}"
                records[key] = {
                    "id": r.get("id"),
                    "value": fields.get("Wert", 0)
                }
    except Exception as e:
        print(f"   Airtable Error: {e}")
    
    return records


def update_record(record_id: str, new_value: int) -> bool:
    """Aktualisiert einen Airtable-Record"""
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/Measurements/{record_id}"
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.patch(
            url,
            headers=headers,
            json={"fields": {"Wert": new_value, "Erfasst am": datetime.utcnow().isoformat()}},
            timeout=30
        )
        return response.status_code == 200
    except:
        return False


def create_record(target_date: date, brand: str, surface: str, value: int, site_id: str) -> bool:
    """Erstellt einen neuen Airtable-Record"""
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/Measurements"
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json"
    }
    
    unique_key = f"{target_date.isoformat()}_{brand}_{surface}_Unique Clients"
    
    try:
        response = requests.post(
            url,
            headers=headers,
            json={
                "records": [{
                    "fields": {
                        "Datum": target_date.isoformat(),
                        "Brand": brand,
                        "Plattform": surface,
                        "Metrik": "Unique Clients",
                        "Wert": value,
                        "Site ID": site_id,
                        "Vorläufig": False,
                        "Erfasst am": datetime.utcnow().isoformat(),
                        "Unique Key": unique_key
                    }
                }]
            },
            timeout=30
        )
        return response.status_code in (200, 201)
    except:
        return False


def backfill_uc(start_date: date, end_date: date):
    """Führt UC-Backfill für den angegebenen Zeitraum durch"""
    print("=" * 70)
    print("👤 UNIQUE CLIENTS BACKFILL")
    print("=" * 70)
    print(f"\n📅 Zeitraum: {start_date.isoformat()} bis {end_date.isoformat()}")
    print(f"📊 Sites: {len(SITES)}")
    print()
    
    stats = {"updated": 0, "created": 0, "skipped": 0, "errors": 0}
    
    current_date = start_date
    while current_date <= end_date:
        print(f"\n📅 {current_date.isoformat()}...")
        
        # Existierende Records laden
        existing = get_existing_uc_records(current_date)
        
        for site in SITES:
            key = f"{site['brand']}_{site['surface']}"
            
            # UC von API holen
            api_value = fetch_uc_from_api(site["site_id"], current_date)
            
            if api_value is None:
                print(f"   ⚠️ {site['name']}: Keine Daten in API")
                stats["skipped"] += 1
                continue
            
            if key in existing:
                # Record existiert
                old_value = existing[key]["value"]
                
                if old_value == 0 and api_value > 0:
                    # Update nötig!
                    if update_record(existing[key]["id"], api_value):
                        print(f"   🔄 {site['name']}: {old_value:,} → {api_value:,}")
                        stats["updated"] += 1
                    else:
                        print(f"   ❌ {site['name']}: Update fehlgeschlagen")
                        stats["errors"] += 1
                elif old_value > 0:
                    print(f"   ✅ {site['name']}: {old_value:,} (OK)")
                    stats["skipped"] += 1
                else:
                    print(f"   ⏭️ {site['name']}: Übersprungen")
                    stats["skipped"] += 1
            else:
                # Record existiert nicht - erstellen
                if create_record(current_date, site["brand"], site["surface"], api_value, site["site_id"]):
                    print(f"   ➕ {site['name']}: {api_value:,} (neu erstellt)")
                    stats["created"] += 1
                else:
                    print(f"   ❌ {site['name']}: Erstellen fehlgeschlagen")
                    stats["errors"] += 1
        
        current_date += timedelta(days=1)
    
    # Zusammenfassung
    print("\n" + "=" * 70)
    print("📋 ZUSAMMENFASSUNG")
    print("=" * 70)
    print(f"   🔄 Aktualisiert: {stats['updated']}")
    print(f"   ➕ Neu erstellt: {stats['created']}")
    print(f"   ⏭️ Übersprungen: {stats['skipped']}")
    print(f"   ❌ Fehler: {stats['errors']}")
    print("=" * 70)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Unique Clients Backfill")
    parser.add_argument("--days", type=int, default=30, help="Anzahl Tage zurück")
    parser.add_argument("--start", type=str, help="Startdatum (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, help="Enddatum (YYYY-MM-DD)")
    args = parser.parse_args()
    
    if not INFONLINE_API_KEY or not AIRTABLE_API_KEY:
        print("❌ INFONLINE_API_KEY oder AIRTABLE_API_KEY nicht gesetzt!")
        exit(1)
    
    if args.start and args.end:
        start_date = date.fromisoformat(args.start)
        end_date = date.fromisoformat(args.end)
    else:
        end_date = date.today() - timedelta(days=3)  # Mindestens 3 Tage alt
        start_date = end_date - timedelta(days=args.days - 1)
    
    backfill_uc(start_date, end_date)

