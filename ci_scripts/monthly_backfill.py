#!/usr/bin/env python3
"""
Monthly Backfill Script v1.0
============================
Importiert historische MONATS-Daten von der INFOnline API.

WICHTIG: Die INFOnline API hat für Tagesdaten ein 180-Tage-Limit!
Für ältere Daten muss `aggregation=MONTH` verwendet werden.

Dieses Script:
- Lädt Monatsdaten (unbegrenzt verfügbar)
- Importiert ab einem konfigurierbaren Startmonat
- Verwendet Unique Keys für Deduplizierung

Nutzung:
    python ci_scripts/monthly_backfill.py                    # Ab Jan 2024
    python ci_scripts/monthly_backfill.py --start 2023-01    # Ab Jan 2023
    python ci_scripts/monthly_backfill.py --start 2024-01 --end 2024-06
"""

import os
import sys
import requests
import argparse
from datetime import date, datetime
from time import sleep
from typing import Tuple, Optional, Dict, List, Set
from calendar import monthrange

# =============================================================================
# KONFIGURATION
# =============================================================================
INFONLINE_API_KEY = os.environ.get("INFONLINE_API_KEY", "")
AIRTABLE_API_KEY = os.environ.get("AIRTABLE_API_KEY", "")
AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID", "appTIeod85xnBy7Vn")

# Rate Limiting
API_DELAY = 0.2  # Sekunden zwischen API-Calls
BATCH_DELAY = 0.25  # Sekunden zwischen Airtable-Batches

# =============================================================================
# SITES KONFIGURATION
# =============================================================================

# Standard Sites (Web + iOS + Android)
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

# Homepage Sites (nur für Homepage PI)
HOMEPAGE_SITES = [
    {"name": "VOL.AT Homepage", "site_id": "BE000072", "brand": "VOL", "surface": "Web"},
    {"name": "VIENNA.AT Homepage", "site_id": "BE000043", "brand": "Vienna", "surface": "Web"},
]

# Metriken-Mapping
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
    "uniqueclients": "uclients"
}


# =============================================================================
# API FUNKTIONEN
# =============================================================================

def fetch_monthly_data(site_id: str, metric: str, year: int, month: int) -> dict:
    """
    Ruft MONATSDATEN von der INFOnline API ab.
    
    Verwendet aggregation=MONTH für unbegrenzte historische Daten.
    """
    # Erster Tag des Monats als Datum
    target_date = date(year, month, 1)
    
    url = f"https://reportingapi.infonline.de/api/v1/{metric}"
    params = {
        "site": site_id,
        "date": target_date.isoformat(),
        "aggregation": "MONTH"  # WICHTIG: Monatsdaten!
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
    """Extrahiert den Wert aus der API-Response (IOM-Daten)"""
    if not isinstance(data, dict) or "data" not in data:
        return None, True
    
    api_data = data["data"]
    value_field = VALUE_FIELDS.get(metric_key, metric_key)
    
    # IOM-Daten (hochgerechnet) verwenden
    if "iom" in api_data and len(api_data["iom"]) > 0:
        iom_entry = api_data["iom"][0]
        value = iom_entry.get(value_field)
        preliminary = iom_entry.get("preliminary", True)
        return value, preliminary
    
    return None, True


def get_existing_monthly_keys(dry_run: bool = False) -> Set[str]:
    """Holt alle existierenden Monthly Unique Keys aus Airtable"""
    if dry_run:
        print("   [DRY-RUN] Überspringe Airtable-Abfrage")
        return set()
    
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/Measurements"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    
    existing_keys = set()
    offset = None
    
    print("   Lade existierende Keys aus Airtable...")
    while True:
        params = {
            "filterByFormula": "FIND('_MONTH', {Unique Key}) > 0",
            "fields[]": "Unique Key",
            "pageSize": 100
        }
        if offset:
            params["offset"] = offset
            
        response = requests.get(url, headers=headers, params=params, timeout=30)
        if response.status_code != 200:
            print(f"   ⚠️ Airtable Fehler: {response.status_code}")
            break
            
        data = response.json()
        for record in data.get("records", []):
            key = record.get("fields", {}).get("Unique Key")
            if key:
                existing_keys.add(key)
        
        offset = data.get("offset")
        if not offset:
            break
        
        sleep(0.1)
    
    print(f"   ✓ {len(existing_keys)} existierende Monats-Keys gefunden")
    return existing_keys


def save_to_airtable(records: List[dict], dry_run: bool = False) -> dict:
    """Speichert Records in Airtable (Batch-Insert)"""
    results = {"created": 0, "errors": []}
    
    if not records:
        return results
    
    if dry_run:
        print(f"   [DRY-RUN] Würde {len(records)} Records speichern")
        results["created"] = len(records)
        return results
    
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/Measurements"
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json"
    }
    
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
        
        sleep(BATCH_DELAY)
        print(f"   ... {results['created']}/{len(records)} gespeichert", end="\r")
    
    print()
    return results


def generate_months(start_year: int, start_month: int, end_year: int, end_month: int) -> List[Tuple[int, int]]:
    """Generiert Liste von (year, month) Tupeln"""
    months = []
    year, month = start_year, start_month
    
    while (year, month) <= (end_year, end_month):
        months.append((year, month))
        month += 1
        if month > 12:
            month = 1
            year += 1
    
    return months


# =============================================================================
# HAUPTFUNKTION
# =============================================================================

def run_monthly_backfill(start_year: int, start_month: int, end_year: int = None, end_month: int = None, dry_run: bool = False):
    """
    Führt den monatlichen Backfill durch.
    """
    print("=" * 70)
    print("📅 ÖWA MONTHLY BACKFILL v1.0")
    print("   Historische Monatsdaten (unbegrenzt verfügbar)")
    if dry_run:
        print("   ⚠️  DRY-RUN MODUS - Keine Daten werden geschrieben!")
    print("=" * 70)
    
    # API Keys prüfen
    if not INFONLINE_API_KEY:
        print("❌ INFONLINE_API_KEY nicht gesetzt!")
        return
    if not AIRTABLE_API_KEY:
        print("❌ AIRTABLE_API_KEY nicht gesetzt!")
        return
    
    # End-Datum: Vormonat (aktueller Monat ist noch nicht komplett)
    today = date.today()
    if end_year is None or end_month is None:
        if today.month == 1:
            end_year = today.year - 1
            end_month = 12
        else:
            end_year = today.year
            end_month = today.month - 1
    
    # Monate generieren
    months = generate_months(start_year, start_month, end_year, end_month)
    
    print(f"\n📅 ZEITRAUM:")
    print(f"   Von: {start_year}-{start_month:02d}")
    print(f"   Bis: {end_year}-{end_month:02d}")
    print(f"   Monate: {len(months)}")
    
    print(f"\n📊 SITES:")
    print(f"   Standard: {len(SITES)} (Web + App)")
    print(f"   Homepage: {len(HOMEPAGE_SITES)}")
    
    # Erwartete Records
    expected_standard = len(months) * len(SITES) * len(METRICS)
    expected_homepage = len(months) * len(HOMEPAGE_SITES)
    expected_total = expected_standard + expected_homepage
    
    print(f"\n📈 ERWARTETE RECORDS:")
    print(f"   Standard (PI, Visits, UC): ~{expected_standard}")
    print(f"   Homepage PI: ~{expected_homepage}")
    print(f"   TOTAL: ~{expected_total}")
    
    # Existierende Keys laden
    print(f"\n📋 DUPLIKAT-PRÜFUNG:")
    existing_keys = get_existing_monthly_keys(dry_run)
    
    # Statistiken
    stats = {
        "fetched": 0,
        "created": 0,
        "skipped_duplicate": 0,
        "skipped_no_data": 0,
        "errors": []
    }
    
    all_records = []
    
    # =========================================================================
    # PHASE 1: Standard-Metriken (PI, Visits, UC) für alle Sites
    # =========================================================================
    print("\n" + "=" * 70)
    print("📊 PHASE 1: Standard-Metriken (Monatsdaten)")
    print("=" * 70)
    
    phase1_total = len(months) * len(SITES) * len(METRICS)
    phase1_current = 0
    
    for year, month in months:
        month_str = f"{year}-{month:02d}"
        # Letzter Tag des Monats als Datum für Airtable
        last_day = monthrange(year, month)[1]
        record_date = date(year, month, last_day)
        
        for site in SITES:
            for metric_key in METRICS:
                phase1_current += 1
                metric_name = METRICS_MAP[metric_key]
                # Unique Key mit _MONTH Suffix zur Unterscheidung
                unique_key = f"{month_str}_MONTH_{site['brand']}_{site['surface']}_{metric_name}"
                
                print(f"\r   [{phase1_current}/{phase1_total}] {month_str} {site['name']} {metric_name}...", end="")
                
                # Duplikat-Check
                if unique_key in existing_keys:
                    stats["skipped_duplicate"] += 1
                    continue
                
                # API abrufen
                result = fetch_monthly_data(site["site_id"], metric_key, year, month)
                sleep(API_DELAY)
                
                if result["success"]:
                    value, preliminary = extract_value(result["data"], metric_key)
                    
                    if value is not None and value > 0:
                        stats["fetched"] += 1
                        all_records.append({
                            "fields": {
                                "Datum": record_date.isoformat(),
                                "Brand": site["brand"],
                                "Plattform": site["surface"],
                                "Metrik": metric_name,  # Standard-Name ohne "(Monat)" Suffix
                                "Wert": value,
                                "Site ID": site["site_id"],
                                "Vorläufig": preliminary,
                                "Erfasst am": datetime.utcnow().isoformat(),
                                "Unique Key": unique_key  # Enthält _MONTH_ zur Unterscheidung
                            }
                        })
                    else:
                        stats["skipped_no_data"] += 1
                else:
                    error_msg = result.get("error", "Unbekannter Fehler")
                    if "Keine Daten" not in error_msg:
                        stats["errors"].append(f"{month_str} {site['name']}/{metric_name}: {error_msg}")
                    else:
                        stats["skipped_no_data"] += 1
    
    print(f"\n   ✓ Phase 1 abgeschlossen: {stats['fetched']} Records gesammelt")
    
    # =========================================================================
    # PHASE 2: Homepage Page Impressions
    # =========================================================================
    print("\n" + "=" * 70)
    print("🏠 PHASE 2: Homepage Page Impressions (Monatsdaten)")
    print("=" * 70)
    
    phase2_total = len(months) * len(HOMEPAGE_SITES)
    phase2_current = 0
    phase2_fetched = 0
    
    for year, month in months:
        month_str = f"{year}-{month:02d}"
        last_day = monthrange(year, month)[1]
        record_date = date(year, month, last_day)
        
        for site in HOMEPAGE_SITES:
            phase2_current += 1
            metric_name = "Homepage PI"
            unique_key = f"{month_str}_MONTH_{site['brand']}_{site['surface']}_{metric_name}"
            
            print(f"\r   [{phase2_current}/{phase2_total}] {month_str} {site['name']}...", end="")
            
            if unique_key in existing_keys:
                stats["skipped_duplicate"] += 1
                continue
            
            result = fetch_monthly_data(site["site_id"], "pageimpressions", year, month)
            sleep(API_DELAY)
            
            if result["success"]:
                value, preliminary = extract_value(result["data"], "pageimpressions")
                
                if value is not None and value > 0:
                    stats["fetched"] += 1
                    phase2_fetched += 1
                    all_records.append({
                        "fields": {
                            "Datum": record_date.isoformat(),
                            "Brand": site["brand"],
                            "Plattform": site["surface"],
                            "Metrik": metric_name,  # "Homepage PI" ohne Suffix
                            "Wert": value,
                            "Site ID": site["site_id"],
                            "Vorläufig": preliminary,
                            "Erfasst am": datetime.utcnow().isoformat(),
                            "Unique Key": unique_key  # Enthält _MONTH_ zur Unterscheidung
                        }
                    })
                else:
                    stats["skipped_no_data"] += 1
            else:
                if "Keine Daten" not in result.get("error", ""):
                    stats["errors"].append(f"{month_str} {site['name']}/Homepage PI: {result['error']}")
                else:
                    stats["skipped_no_data"] += 1
    
    print(f"\n   ✓ Phase 2 abgeschlossen: {phase2_fetched} Records gesammelt")
    
    # =========================================================================
    # PHASE 3: In Airtable speichern
    # =========================================================================
    print("\n" + "=" * 70)
    print("💾 PHASE 3: Speichern in Airtable")
    print("=" * 70)
    
    if all_records:
        print(f"\n   💾 Speichere {len(all_records)} Records...")
        save_result = save_to_airtable(all_records, dry_run)
        stats["created"] = save_result["created"]
        stats["errors"].extend(save_result["errors"])
        print(f"   ✓ {save_result['created']} Records erfolgreich gespeichert")
    else:
        print("\n   ℹ️ Keine neuen Records zu speichern")
    
    # =========================================================================
    # ZUSAMMENFASSUNG
    # =========================================================================
    print("\n" + "=" * 70)
    print("📋 ZUSAMMENFASSUNG")
    print("=" * 70)
    print(f"""
   ┌────────────────────────────────────────┐
   │  📊 Von API abgerufen:    {stats['fetched']:>6}       │
   │  ✅ In Airtable erstellt: {stats['created']:>6}       │
   │  ⏭️ Duplikate übersprungen: {stats['skipped_duplicate']:>4}       │
   │  ⚠️ Keine Daten:          {stats['skipped_no_data']:>6}       │
   │  ❌ Fehler:               {len(stats['errors']):>6}       │
   └────────────────────────────────────────┘
""")
    
    if stats["errors"]:
        print(f"\n⚠️ FEHLER ({len(stats['errors'])} gesamt, erste 10):")
        for err in stats["errors"][:10]:
            print(f"   • {err}")
    
    print("\n" + "=" * 70)
    print("✅ MONTHLY BACKFILL v1.0 ABGESCHLOSSEN")
    print("=" * 70)
    
    return stats


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="ÖWA Monthly Backfill v1.0 - Historische Monatsdaten",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--start", type=str, default="2024-01", help="Startmonat (YYYY-MM, default: 2024-01)")
    parser.add_argument("--end", type=str, help="Endmonat (YYYY-MM, default: Vormonat)")
    parser.add_argument("--dry-run", action="store_true", help="Nur simulieren")
    
    args = parser.parse_args()
    
    # Parse Start
    start_parts = args.start.split("-")
    start_year = int(start_parts[0])
    start_month = int(start_parts[1])
    
    # Parse End
    end_year = None
    end_month = None
    if args.end:
        end_parts = args.end.split("-")
        end_year = int(end_parts[0])
        end_month = int(end_parts[1])
    
    run_monthly_backfill(
        start_year=start_year,
        start_month=start_month,
        end_year=end_year,
        end_month=end_month,
        dry_run=args.dry_run
    )



