#!/usr/bin/env python3
"""
Backfill Script - Erweiterte Version v2.0
==========================================
Lädt ÖWA-Daten für die letzten X Tage und speichert sie in Airtable.

Unterstützt:
- Web + App Properties
- Alle Metriken (PI, Visits, UC, Homepage PI)
- Duplikat-Prüfung

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
from typing import Tuple, Optional

# =============================================================================
# KONFIGURATION
# =============================================================================
INFONLINE_API_KEY = os.environ.get("INFONLINE_API_KEY", "")
AIRTABLE_API_KEY = os.environ.get("AIRTABLE_API_KEY", "")
AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID", "")  # Muss in CI/CD Variables gesetzt sein

# =============================================================================
# SITES KONFIGURATION - Erweitert für Web + iOS + Android
# =============================================================================
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

# Homepage Sites (nur Web, Belegungseinheiten)
HOMEPAGE_SITES = [
    {"name": "VOL.AT Homepage", "site_id": "BE000072", "brand": "VOL", "surface": "Web"},
    {"name": "VIENNA.AT Homepage", "site_id": "BE000043", "brand": "Vienna", "surface": "Web"},
]

# Standard-Metriken für alle Sites
METRICS = ["pageimpressions", "visits", "uniqueclients"]
METRICS_MAP = {
    "pageimpressions": "Page Impressions",
    "visits": "Visits",
    "uniqueclients": "Unique Clients"
}

# API-Feldnamen für Wert-Extraktion
VALUE_FIELDS = {
    "pageimpressions": "pis",
    "visits": "visits",
    "uniqueclients": "uclients"  # KORRIGIERT: war "unique_clients", richtig ist "uclients"
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
        elif response.status_code == 404:
            return {"success": False, "error": "Keine Daten"}
        else:
            return {"success": False, "error": f"HTTP {response.status_code}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def extract_value(data: dict, metric_key: str) -> Tuple[Optional[int], bool]:
    """Extrahiert den Wert aus der API-Response."""
    if not isinstance(data, dict) or "data" not in data:
        return None, True
    
    api_data = data["data"]
    value_field = VALUE_FIELDS.get(metric_key, metric_key)
    
    if "iom" in api_data and len(api_data["iom"]) > 0:
        iom_entry = api_data["iom"][0]
        value = iom_entry.get(value_field)
        preliminary = iom_entry.get("preliminary", True)
        return value, preliminary
    
    return None, True


def get_existing_keys(airtable_api_key: str, base_id: str) -> set:
    """Holt alle existierenden Unique Keys aus Airtable"""
    url = f"https://api.airtable.com/v0/{base_id}/Measurements"
    headers = {"Authorization": f"Bearer {airtable_api_key}"}
    
    existing_keys = set()
    offset = None
    
    print("   Lade existierende Keys...")
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
        
        # Fortschritt anzeigen
        print(f"   ... {len(existing_keys)} Keys geladen", end="\r")
    
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
        
        # Fortschritt
        print(f"   ... {results['created']}/{len(records)} gespeichert", end="\r")
    
    print()  # Neue Zeile nach Fortschritt
    return results


def run_backfill(days: int = 30):
    """Führt den Backfill für die letzten X Tage aus"""
    print("=" * 70)
    print(f"🔄 ÖWA BACKFILL v2.0 - Letzte {days} Tage")
    print("   Web + App | PI + Visits + UC + Homepage PI")
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
    print(f"📊 Sites: {len(SITES)} Standard + {len(HOMEPAGE_SITES)} Homepage")
    print(f"📈 Metriken: {', '.join(METRICS_MAP.values())} + Homepage PI")
    print()
    
    all_records = []
    skipped = 0
    errors = []
    
    total_combinations = len(dates) * (len(SITES) * len(METRICS) + len(HOMEPAGE_SITES))
    current = 0
    
    # ==========================================================================
    # PHASE 1: Standard-Metriken für alle Sites
    # ==========================================================================
    print("=" * 70)
    print("📊 PHASE 1: Standard-Metriken (PI, Visits, UC)")
    print("=" * 70)
    
    for target_date in dates:
        for site in SITES:
            for metric_key in METRICS:
                current += 1
                metric_name = METRICS_MAP.get(metric_key, metric_key)
                unique_key = f"{target_date.isoformat()}_{site['brand']}_{site['surface']}_{metric_name}"
                
                # Fortschritt
                print(f"\r   [{current}/{total_combinations}] {target_date} {site['name']} {metric_name}...", end="")
                
                # Skip wenn bereits existiert
                if unique_key in existing_keys:
                    skipped += 1
                    continue
                
                # API abrufen
                result = fetch_infonline_data(site["site_id"], metric_key, target_date)
                
                if result["success"]:
                    value, preliminary = extract_value(result["data"], metric_key)
                    
                    if value is not None:
                        all_records.append({
                            "fields": {
                                "Datum": target_date.isoformat(),
                                "Brand": site["brand"],
                                "Plattform": site["surface"],
                                "Metrik": metric_name,
                                "Wert": value,
                                "Site ID": site["site_id"],
                                "Vorläufig": preliminary,
                                "Erfasst am": datetime.utcnow().isoformat(),
                                "Unique Key": unique_key
                            }
                        })
                    else:
                        errors.append(f"{target_date} {site['name']}/{metric_name}: Kein Wert")
                else:
                    if "Keine Daten" not in result["error"]:
                        errors.append(f"{target_date} {site['name']}/{metric_name}: {result['error']}")
                
                # Rate limiting für API
                sleep(0.1)
    
    print()  # Neue Zeile
    
    # ==========================================================================
    # PHASE 2: Homepage Page Impressions
    # ==========================================================================
    print("\n" + "=" * 70)
    print("🏠 PHASE 2: Homepage Page Impressions")
    print("=" * 70)
    
    for target_date in dates:
        for site in HOMEPAGE_SITES:
            current += 1
            metric_name = "Homepage PI"
            unique_key = f"{target_date.isoformat()}_{site['brand']}_{site['surface']}_{metric_name}"
            
            # Fortschritt
            print(f"\r   [{current}/{total_combinations}] {target_date} {site['name']}...", end="")
            
            # Skip wenn bereits existiert
            if unique_key in existing_keys:
                skipped += 1
                continue
            
            # API abrufen
            result = fetch_infonline_data(site["site_id"], "pageimpressions", target_date)
            
            if result["success"]:
                value, preliminary = extract_value(result["data"], "pageimpressions")
                
                if value is not None:
                    all_records.append({
                        "fields": {
                            "Datum": target_date.isoformat(),
                            "Brand": site["brand"],
                            "Plattform": site["surface"],
                            "Metrik": metric_name,
                            "Wert": value,
                            "Site ID": site["site_id"],
                            "Vorläufig": preliminary,
                            "Erfasst am": datetime.utcnow().isoformat(),
                            "Unique Key": unique_key
                        }
                    })
                else:
                    errors.append(f"{target_date} {site['name']}: Kein Wert")
            else:
                if "Keine Daten" not in result["error"]:
                    errors.append(f"{target_date} {site['name']}: {result['error']}")
            
            sleep(0.1)
    
    print()  # Neue Zeile
    
    # ==========================================================================
    # Zusammenfassung & Speichern
    # ==========================================================================
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
            for err in save_result["errors"][:5]:
                print(f"   ❌ {err}")
    else:
        print("\n✅ Keine neuen Datensätze zu speichern.")
    
    # Fehler anzeigen (max 10)
    if errors:
        print(f"\n⚠️ Fehler ({len(errors)} gesamt, erste 10):")
        for err in errors[:10]:
            print(f"   • {err}")
    
    print("\n" + "=" * 70)
    print("✅ BACKFILL v2.0 ABGESCHLOSSEN")
    print("=" * 70)
    
    return {
        "new_records": len(all_records),
        "skipped": skipped,
        "errors": len(errors)
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ÖWA Backfill v2.0 - Historische Daten laden")
    parser.add_argument("--days", type=int, default=30, help="Anzahl der Tage (default: 30)")
    args = parser.parse_args()
    
    run_backfill(days=args.days)
