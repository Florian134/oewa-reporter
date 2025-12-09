#!/usr/bin/env python3
"""
Backfill Script - Historische Daten laden
==========================================
Lädt ÖWA-Daten für die letzten X Tage und speichert sie in Airtable.

Nutzung:
    python ci_scripts/backfill.py              # Letzte 30 Tage
    python ci_scripts/backfill.py --days 7     # Letzte 7 Tage
    python ci_scripts/backfill.py --days 90    # Letzte 90 Tage
"""

import os
import sys
import json
import requests
import argparse
from datetime import date, datetime, timedelta
from time import sleep

# =============================================================================
# KONFIGURATION
# =============================================================================
INFONLINE_API_KEY = os.environ.get("INFONLINE_API_KEY", "")
AIRTABLE_API_KEY = os.environ.get("AIRTABLE_API_KEY", "")
AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID", "appTIeod85xnBy7Vn")

# Sites Konfiguration
SITES = [
    {"name": "VOL.AT Web", "site_id": "at_w_atvol", "brand": "VOL", "surface": "Web"},
    {"name": "VIENNA.AT Web", "site_id": "at_w_atvienna", "brand": "Vienna", "surface": "Web"},
]

METRICS = ["pageimpressions", "visits"]
METRICS_MAP = {
    "pageimpressions": "Page Impressions",
    "visits": "Visits"
}


def fetch_infonline_data(site_id: str, metric: str, target_date: date) -> dict:
    """Ruft Daten von der INFOnline API ab"""
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
            return {"success": True, "data": response.json()}
        else:
            return {"success": False, "error": f"HTTP {response.status_code}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_existing_keys(airtable_api_key: str, base_id: str) -> set:
    """Holt alle existierenden Unique Keys aus Airtable"""
    url = f"https://api.airtable.com/v0/{base_id}/Measurements"
    headers = {"Authorization": f"Bearer {airtable_api_key}"}
    
    existing_keys = set()
    offset = None
    
    while True:
        params = {"fields[]": "Unique Key", "pageSize": 100}
        if offset:
            params["offset"] = offset
            
        response = requests.get(url, headers=headers, params=params, timeout=30)
        if response.status_code != 200:
            print(f"⚠️ Fehler beim Abrufen existierender Keys: {response.status_code}")
            break
            
        data = response.json()
        for record in data.get("records", []):
            key = record.get("fields", {}).get("Unique Key")
            if key:
                existing_keys.add(key)
        
        offset = data.get("offset")
        if not offset:
            break
    
    return existing_keys


def save_to_airtable(records: list, airtable_api_key: str, base_id: str) -> dict:
    """Speichert Records in Airtable (Batch-Insert)"""
    url = f"https://api.airtable.com/v0/{base_id}/Measurements"
    headers = {
        "Authorization": f"Bearer {airtable_api_key}",
        "Content-Type": "application/json"
    }
    
    results = {"created": 0, "errors": []}
    
    # Batch-Insert (max 10 pro Request)
    for i in range(0, len(records), 10):
        batch = records[i:i+10]
        try:
            response = requests.post(
                url,
                headers=headers,
                json={"records": batch},
                timeout=30
            )
            if response.status_code in (200, 201):
                results["created"] += len(batch)
            else:
                error_msg = response.text[:200]
                results["errors"].append(f"Batch {i//10 + 1}: {error_msg}")
        except Exception as e:
            results["errors"].append(f"Batch {i//10 + 1}: {str(e)}")
        
        # Rate limiting: kurze Pause zwischen Batches
        sleep(0.2)
    
    return results


def run_backfill(days: int = 30):
    """Führt den Backfill für die letzten X Tage aus"""
    print("=" * 70)
    print(f"🔄 ÖWA BACKFILL - Letzte {days} Tage")
    print("=" * 70)
    
    # Konfiguration prüfen
    if not INFONLINE_API_KEY:
        print("❌ INFONLINE_API_KEY nicht gesetzt!")
        return
    if not AIRTABLE_API_KEY:
        print("❌ AIRTABLE_API_KEY nicht gesetzt!")
        return
    
    # Existierende Keys holen (für Deduplizierung)
    print("\n📋 Prüfe existierende Datensätze in Airtable...")
    existing_keys = get_existing_keys(AIRTABLE_API_KEY, AIRTABLE_BASE_ID)
    print(f"   → {len(existing_keys)} existierende Datensätze gefunden")
    
    # Datumsliste erstellen (von gestern rückwärts)
    today = date.today()
    dates = [today - timedelta(days=i) for i in range(1, days + 1)]
    
    print(f"\n📅 Zeitraum: {dates[-1]} bis {dates[0]}")
    print(f"📊 Sites: {', '.join([s['name'] for s in SITES])}")
    print(f"📈 Metriken: {', '.join(METRICS_MAP.values())}")
    print()
    
    all_records = []
    skipped = 0
    errors = []
    
    # Für jeden Tag Daten abrufen
    for target_date in dates:
        print(f"\n📅 {target_date.isoformat()}")
        
        for site in SITES:
            for metric_key in METRICS:
                metric_name = METRICS_MAP.get(metric_key, metric_key)
                unique_key = f"{target_date.isoformat()}_{site['brand']}_{site['surface']}_{metric_name}"
                
                # Skip wenn bereits existiert
                if unique_key in existing_keys:
                    skipped += 1
                    continue
                
                # API abrufen
                result = fetch_infonline_data(site["site_id"], metric_key, target_date)
                
                if result["success"]:
                    data = result["data"]
                    
                    # Wert extrahieren
                    value_field = "pis" if metric_key == "pageimpressions" else "visits"
                    iom_total = None
                    preliminary = True
                    
                    if isinstance(data, dict) and "data" in data:
                        api_data = data["data"]
                        if "iom" in api_data and len(api_data["iom"]) > 0:
                            iom_entry = api_data["iom"][0]
                            iom_total = iom_entry.get(value_field)
                            preliminary = iom_entry.get("preliminary", True)
                    
                    if iom_total is not None:
                        all_records.append({
                            "fields": {
                                "Datum": target_date.isoformat(),
                                "Brand": site["brand"],
                                "Plattform": site["surface"],
                                "Metrik": metric_name,
                                "Wert": iom_total,
                                "Site ID": site["site_id"],
                                "Vorläufig": preliminary,
                                "Erfasst am": datetime.utcnow().isoformat(),
                                "Unique Key": unique_key
                            }
                        })
                        print(f"   ✅ {site['name']} - {metric_name}: {iom_total:,}")
                    else:
                        errors.append(f"{target_date} {site['name']}/{metric_name}: Kein Wert")
                        print(f"   ⚠️ {site['name']} - {metric_name}: Kein Wert")
                else:
                    errors.append(f"{target_date} {site['name']}/{metric_name}: {result['error']}")
                    print(f"   ❌ {site['name']} - {metric_name}: {result['error']}")
                
                # Rate limiting für API
                sleep(0.1)
    
    # Zusammenfassung
    print("\n" + "=" * 70)
    print("📊 ZUSAMMENFASSUNG")
    print("=" * 70)
    print(f"   Neue Datensätze:     {len(all_records)}")
    print(f"   Übersprungen:        {skipped} (bereits vorhanden)")
    print(f"   Fehler:              {len(errors)}")
    
    # In Airtable speichern
    if all_records:
        print(f"\n💾 Speichere {len(all_records)} Datensätze in Airtable...")
        save_result = save_to_airtable(all_records, AIRTABLE_API_KEY, AIRTABLE_BASE_ID)
        print(f"   ✅ Erstellt: {save_result['created']}")
        if save_result["errors"]:
            for err in save_result["errors"]:
                print(f"   ❌ {err}")
    else:
        print("\n✅ Keine neuen Datensätze zu speichern.")
    
    print("\n" + "=" * 70)
    print("✅ BACKFILL ABGESCHLOSSEN")
    print("=" * 70)
    
    return {
        "new_records": len(all_records),
        "skipped": skipped,
        "errors": len(errors)
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ÖWA Backfill - Historische Daten laden")
    parser.add_argument("--days", type=int, default=30, help="Anzahl der Tage (default: 30)")
    args = parser.parse_args()
    
    run_backfill(days=args.days)

