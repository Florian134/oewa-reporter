#!/usr/bin/env python3
"""
Unified Backfill Script v3.0
============================
Ganzheitlicher Backfill für alle ÖWA-Metriken mit korrekter UC-Behandlung.

KRITISCHE PUNKTE:
- Unique Clients (UC) sind erst nach ~3 Tagen in der API verfügbar
- UC-Werte von 0 werden NICHT importiert (noch nicht finalisiert)
- Strikte Duplikat-Prüfung via Unique Key
- Rate Limiting für API-Stabilität

Metriken:
- Page Impressions (PI): Sofort verfügbar (gestern)
- Visits: Sofort verfügbar (gestern)
- Unique Clients (UC): 3 Tage Verzögerung!
- Homepage PI: Sofort verfügbar (gestern)

Nutzung:
    python ci_scripts/unified_backfill.py                    # 90 Tage
    python ci_scripts/unified_backfill.py --days 30          # 30 Tage
    python ci_scripts/unified_backfill.py --dry-run          # Nur simulieren
    python ci_scripts/unified_backfill.py --start 2025-09-01 --end 2025-12-14
"""

import os
import sys
import json
import requests
import argparse
from datetime import date, datetime, timedelta
from time import sleep
from typing import Tuple, Optional, Dict, List, Set

# =============================================================================
# KONFIGURATION
# =============================================================================
INFONLINE_API_KEY = os.environ.get("INFONLINE_API_KEY", "")
AIRTABLE_API_KEY = os.environ.get("AIRTABLE_API_KEY", "")
AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID", "appTIeod85xnBy7Vn")

# Unique Clients Verzögerung (Tage)
UC_DELAY_DAYS = 3

# Rate Limiting
API_DELAY = 0.15  # Sekunden zwischen API-Calls
BATCH_DELAY = 0.25  # Sekunden zwischen Airtable-Batches

# =============================================================================
# SITES KONFIGURATION
# =============================================================================

# Standard Sites (Web + App)
SITES = [
    {"name": "VOL.AT Web", "site_id": "at_w_atvol", "brand": "VOL", "surface": "Web"},
    {"name": "VIENNA.AT Web", "site_id": "at_w_atvienna", "brand": "Vienna", "surface": "Web"},
    {"name": "VOL.AT App", "site_id": "EA000004_mobile_app", "brand": "VOL", "surface": "App"},
    {"name": "VIENNA.AT App", "site_id": "EA000003_mobile_app", "brand": "Vienna", "surface": "App"},
]

# Homepage Sites (nur für Homepage PI)
HOMEPAGE_SITES = [
    {"name": "VOL.AT Homepage", "site_id": "BE000072", "brand": "VOL", "surface": "Web"},
    {"name": "VIENNA.AT Homepage", "site_id": "BE000043", "brand": "Vienna", "surface": "Web"},
]

# Metriken-Mapping
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


def get_existing_keys(dry_run: bool = False) -> Set[str]:
    """Holt alle existierenden Unique Keys aus Airtable"""
    if dry_run:
        print("   [DRY-RUN] Überspringe Airtable-Abfrage")
        return set()
    
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/Measurements"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    
    existing_keys = set()
    offset = None
    
    print("   Lade existierende Keys aus Airtable...")
    while True:
        params = {"fields[]": "Unique Key", "pageSize": 100}
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
        
        print(f"   ... {len(existing_keys)} Keys geladen", end="\r")
        sleep(0.1)
    
    print(f"   ✓ {len(existing_keys)} existierende Keys gefunden")
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
    
    print()  # Neue Zeile
    return results


# =============================================================================
# HAUPTFUNKTION
# =============================================================================

def run_unified_backfill(days: int = 90, start_date: date = None, end_date: date = None, dry_run: bool = False):
    """
    Führt den ganzheitlichen Backfill durch.
    
    Args:
        days: Anzahl der Tage (wenn start/end nicht angegeben)
        start_date: Optionales Startdatum
        end_date: Optionales Enddatum
        dry_run: Wenn True, nur simulieren
    """
    print("=" * 70)
    print("🔄 ÖWA UNIFIED BACKFILL v3.0")
    print("   Ganzheitlicher Import mit korrekter UC-Behandlung")
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
    
    # Datumsbereiche berechnen
    today = date.today()
    
    if start_date and end_date:
        # Benutzerdefinierter Zeitraum
        standard_end = min(end_date, today - timedelta(days=1))
        standard_start = start_date
        uc_end = min(end_date, today - timedelta(days=UC_DELAY_DAYS))
        uc_start = start_date
    else:
        # Standard: X Tage zurück
        standard_end = today - timedelta(days=1)  # Gestern
        standard_start = today - timedelta(days=days)
        uc_end = today - timedelta(days=UC_DELAY_DAYS)  # Vor 3 Tagen
        uc_start = today - timedelta(days=days)
    
    # Datumslisten erstellen
    standard_dates = []
    d = standard_start
    while d <= standard_end:
        standard_dates.append(d)
        d += timedelta(days=1)
    
    uc_dates = []
    d = uc_start
    while d <= uc_end:
        uc_dates.append(d)
        d += timedelta(days=1)
    
    print(f"\n📅 ZEITRÄUME:")
    print(f"   Standard-Metriken (PI, Visits, HP-PI): {standard_start} → {standard_end} ({len(standard_dates)} Tage)")
    print(f"   Unique Clients (verzögert):           {uc_start} → {uc_end} ({len(uc_dates)} Tage)")
    print(f"\n📊 SITES:")
    print(f"   Standard: {len(SITES)} (Web + App)")
    print(f"   Homepage: {len(HOMEPAGE_SITES)}")
    
    # Erwartete Records berechnen
    expected_standard = len(standard_dates) * len(SITES) * 2  # PI + Visits
    expected_homepage = len(standard_dates) * len(HOMEPAGE_SITES)
    expected_uc = len(uc_dates) * len(SITES)
    expected_total = expected_standard + expected_homepage + expected_uc
    
    print(f"\n📈 ERWARTETE RECORDS:")
    print(f"   PI + Visits:  ~{expected_standard}")
    print(f"   Homepage PI:  ~{expected_homepage}")
    print(f"   Unique Clients: ~{expected_uc}")
    print(f"   ─────────────────")
    print(f"   TOTAL:        ~{expected_total}")
    
    # Existierende Keys laden
    print(f"\n📋 DUPLIKAT-PRÜFUNG:")
    existing_keys = get_existing_keys(dry_run)
    
    # Statistiken
    stats = {
        "fetched": 0,
        "created": 0,
        "skipped_duplicate": 0,
        "skipped_uc_zero": 0,
        "skipped_no_data": 0,
        "errors": []
    }
    
    all_records = []
    
    # =========================================================================
    # PHASE 1: Standard-Metriken (PI, Visits) für alle Sites
    # =========================================================================
    print("\n" + "=" * 70)
    print("📊 PHASE 1: Page Impressions + Visits (Web + App)")
    print("=" * 70)
    
    phase1_total = len(standard_dates) * len(SITES) * 2
    phase1_current = 0
    
    for target_date in standard_dates:
        for site in SITES:
            for metric_key in ["pageimpressions", "visits"]:
                phase1_current += 1
                metric_name = METRICS_MAP[metric_key]
                unique_key = f"{target_date.isoformat()}_{site['brand']}_{site['surface']}_{metric_name}"
                
                # Fortschritt
                print(f"\r   [{phase1_current}/{phase1_total}] {target_date} {site['name']} {metric_name}...", end="")
                
                # Duplikat-Check
                if unique_key in existing_keys:
                    stats["skipped_duplicate"] += 1
                    continue
                
                # API abrufen
                result = fetch_infonline_data(site["site_id"], metric_key, target_date)
                sleep(API_DELAY)
                
                if result["success"]:
                    value, preliminary = extract_value(result["data"], metric_key)
                    
                    if value is not None:
                        stats["fetched"] += 1
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
                        stats["skipped_no_data"] += 1
                else:
                    if "Keine Daten" not in result.get("error", ""):
                        stats["errors"].append(f"{target_date} {site['name']}/{metric_name}: {result['error']}")
                    else:
                        stats["skipped_no_data"] += 1
    
    print(f"\n   ✓ Phase 1 abgeschlossen: {stats['fetched']} Records gesammelt")
    
    # =========================================================================
    # PHASE 2: Homepage Page Impressions
    # =========================================================================
    print("\n" + "=" * 70)
    print("🏠 PHASE 2: Homepage Page Impressions")
    print("=" * 70)
    
    phase2_total = len(standard_dates) * len(HOMEPAGE_SITES)
    phase2_current = 0
    phase2_fetched = 0
    
    for target_date in standard_dates:
        for site in HOMEPAGE_SITES:
            phase2_current += 1
            metric_name = "Homepage PI"
            unique_key = f"{target_date.isoformat()}_{site['brand']}_{site['surface']}_{metric_name}"
            
            print(f"\r   [{phase2_current}/{phase2_total}] {target_date} {site['name']}...", end="")
            
            if unique_key in existing_keys:
                stats["skipped_duplicate"] += 1
                continue
            
            result = fetch_infonline_data(site["site_id"], "pageimpressions", target_date)
            sleep(API_DELAY)
            
            if result["success"]:
                value, preliminary = extract_value(result["data"], "pageimpressions")
                
                if value is not None:
                    stats["fetched"] += 1
                    phase2_fetched += 1
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
                    stats["skipped_no_data"] += 1
            else:
                if "Keine Daten" not in result.get("error", ""):
                    stats["errors"].append(f"{target_date} {site['name']}/Homepage PI: {result['error']}")
                else:
                    stats["skipped_no_data"] += 1
    
    print(f"\n   ✓ Phase 2 abgeschlossen: {phase2_fetched} Records gesammelt")
    
    # =========================================================================
    # PHASE 3: Unique Clients (VERZÖGERT!)
    # =========================================================================
    print("\n" + "=" * 70)
    print(f"👤 PHASE 3: Unique Clients (nur Daten ≥{UC_DELAY_DAYS} Tage alt)")
    print("   ⚠️ UC-Werte von 0 werden übersprungen (noch nicht finalisiert)")
    print("=" * 70)
    
    phase3_total = len(uc_dates) * len(SITES)
    phase3_current = 0
    phase3_fetched = 0
    
    for target_date in uc_dates:
        for site in SITES:
            phase3_current += 1
            metric_name = "Unique Clients"
            unique_key = f"{target_date.isoformat()}_{site['brand']}_{site['surface']}_{metric_name}"
            
            print(f"\r   [{phase3_current}/{phase3_total}] {target_date} {site['name']}...", end="")
            
            if unique_key in existing_keys:
                stats["skipped_duplicate"] += 1
                continue
            
            result = fetch_infonline_data(site["site_id"], "uniqueclients", target_date)
            sleep(API_DELAY)
            
            if result["success"]:
                value, preliminary = extract_value(result["data"], "uniqueclients")
                
                # KRITISCH: UC = 0 bedeutet "noch nicht finalisiert" - NICHT importieren!
                if value is not None and value > 0:
                    stats["fetched"] += 1
                    phase3_fetched += 1
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
                elif value == 0:
                    stats["skipped_uc_zero"] += 1
                else:
                    stats["skipped_no_data"] += 1
            else:
                if "Keine Daten" not in result.get("error", ""):
                    stats["errors"].append(f"{target_date} {site['name']}/UC: {result['error']}")
                else:
                    stats["skipped_no_data"] += 1
    
    print(f"\n   ✓ Phase 3 abgeschlossen: {phase3_fetched} Records gesammelt")
    if stats["skipped_uc_zero"] > 0:
        print(f"   ⚠️ {stats['skipped_uc_zero']} UC-Werte mit 0 übersprungen")
    
    # =========================================================================
    # PHASE 4: In Airtable speichern
    # =========================================================================
    print("\n" + "=" * 70)
    print("💾 PHASE 4: Speichern in Airtable")
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
   │  🚫 UC=0 übersprungen:    {stats['skipped_uc_zero']:>6}       │
   │  ⚠️ Keine Daten:          {stats['skipped_no_data']:>6}       │
   │  ❌ Fehler:               {len(stats['errors']):>6}       │
   └────────────────────────────────────────┘
""")
    
    if stats["errors"]:
        print(f"\n⚠️ FEHLER ({len(stats['errors'])} gesamt, erste 10):")
        for err in stats["errors"][:10]:
            print(f"   • {err}")
    
    if dry_run:
        print("\n" + "=" * 70)
        print("⚠️  DRY-RUN ABGESCHLOSSEN - Keine Daten wurden geschrieben!")
        print("=" * 70)
    else:
        print("\n" + "=" * 70)
        print("✅ UNIFIED BACKFILL v3.0 ERFOLGREICH ABGESCHLOSSEN")
        print("=" * 70)
    
    return stats


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="ÖWA Unified Backfill v3.0 - Ganzheitlicher Datenimport",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Beispiele:
  python unified_backfill.py                     # 90 Tage (Standard)
  python unified_backfill.py --days 30           # 30 Tage
  python unified_backfill.py --dry-run           # Nur simulieren
  python unified_backfill.py --start 2025-09-01 --end 2025-12-14
        """
    )
    parser.add_argument("--days", type=int, default=90, help="Anzahl der Tage (default: 90)")
    parser.add_argument("--start", type=str, help="Startdatum (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, help="Enddatum (YYYY-MM-DD)")
    parser.add_argument("--dry-run", action="store_true", help="Nur simulieren, keine Daten schreiben")
    
    args = parser.parse_args()
    
    start_date = None
    end_date = None
    
    if args.start and args.end:
        start_date = date.fromisoformat(args.start)
        end_date = date.fromisoformat(args.end)
    elif args.start or args.end:
        print("❌ Bitte sowohl --start als auch --end angeben, oder keines von beiden.")
        sys.exit(1)
    
    run_unified_backfill(
        days=args.days,
        start_date=start_date,
        end_date=end_date,
        dry_run=args.dry_run
    )

