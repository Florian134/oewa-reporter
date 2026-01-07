#!/usr/bin/env python3
"""
Data Integrity Check & Repair Tool v1.0
=======================================
Prüft und repariert Datenintegrität in Airtable:
- Erkennt Duplikate anhand von Unique Keys
- Vergleicht Werte mit ÖWA API (optional)
- Entfernt Duplikate bei Bestätigung
- Erstellt Bericht über Datenqualität

WICHTIG: Dieses Script sollte regelmäßig ausgeführt werden um Datenintegrität sicherzustellen!

Nutzung:
    python ci_scripts/data_integrity_check.py                    # Nur prüfen
    python ci_scripts/data_integrity_check.py --fix              # Duplikate entfernen
    python ci_scripts/data_integrity_check.py --date 2025-12-20  # Spezifisches Datum
    python ci_scripts/data_integrity_check.py --days 7           # Letzte 7 Tage
    python ci_scripts/data_integrity_check.py --verify-api       # Mit API-Vergleich
"""

import os
import sys
import json
import requests
import argparse
from datetime import date, datetime, timedelta
from collections import defaultdict
from typing import Dict, List, Set, Optional, Tuple

# =============================================================================
# KONFIGURATION
# =============================================================================
INFONLINE_API_KEY = os.environ.get("INFONLINE_API_KEY", "")
AIRTABLE_API_KEY = os.environ.get("AIRTABLE_API_KEY", "")
AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID", "")  # Muss in CI/CD Variables gesetzt sein

# Site-Konfiguration (für API-Vergleich)
SITES = {
    "VOL_Web": {"site_id": "at_w_atvol", "brand": "VOL", "surface": "Web"},
    "VOL_iOS": {"site_id": "at_i_volat", "brand": "VOL", "surface": "iOS"},
    "VOL_Android": {"site_id": "at_a_volat", "brand": "VOL", "surface": "Android"},
    "Vienna_Web": {"site_id": "at_w_atvienna", "brand": "Vienna", "surface": "Web"},
    "Vienna_iOS": {"site_id": "at_i_viennaat", "brand": "Vienna", "surface": "iOS"},
    "Vienna_Android": {"site_id": "at_a_viennaat", "brand": "Vienna", "surface": "Android"},
}

METRICS_MAP = {
    "Page Impressions": {"api": "pageimpressions", "field": "pis"},
    "Visits": {"api": "visits", "field": "visits"},
    "Unique Clients": {"api": "uniqueclients", "field": "uclients"},
}


# =============================================================================
# AIRTABLE FUNKTIONEN
# =============================================================================

def fetch_all_records(start_date: date = None, end_date: date = None) -> List[Dict]:
    """Holt alle Records aus Airtable (optional gefiltert nach Datum)"""
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/Measurements"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    
    all_records = []
    offset = None
    
    print("📥 Lade Daten aus Airtable...")
    
    while True:
        params = {"pageSize": 100}
        
        if start_date and end_date:
            # Filter nach Datumsbereich
            formula = f"AND({{Datum}} >= '{start_date.isoformat()}', {{Datum}} <= '{end_date.isoformat()}')"
            params["filterByFormula"] = formula
        elif start_date:
            params["filterByFormula"] = f"{{Datum}} = '{start_date.isoformat()}'"
            
        if offset:
            params["offset"] = offset
            
        try:
            response = requests.get(url, headers=headers, params=params, timeout=30)
            if response.status_code != 200:
                print(f"❌ Airtable Fehler: {response.status_code}")
                print(response.text[:500])
                break
                
            data = response.json()
            records = data.get("records", [])
            
            for record in records:
                fields = record.get("fields", {})
                all_records.append({
                    "id": record["id"],
                    "datum": fields.get("Datum"),
                    "brand": fields.get("Brand"),
                    "plattform": fields.get("Plattform"),
                    "metrik": fields.get("Metrik"),
                    "wert": fields.get("Wert"),
                    "site_id": fields.get("Site ID"),
                    "unique_key": fields.get("Unique Key"),
                    "erfasst_am": fields.get("Erfasst am"),
                })
            
            offset = data.get("offset")
            if not offset:
                break
                
            print(f"   ... {len(all_records)} Records geladen", end="\r")
            
        except Exception as e:
            print(f"❌ Fehler: {e}")
            break
    
    print(f"✓ {len(all_records)} Records geladen")
    return all_records


def delete_records(record_ids: List[str], dry_run: bool = True) -> int:
    """Löscht Records aus Airtable"""
    if dry_run:
        print(f"   [DRY-RUN] Würde {len(record_ids)} Records löschen")
        return len(record_ids)
    
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/Measurements"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    
    deleted = 0
    
    # Batch-Delete (max 10 pro Request)
    for i in range(0, len(record_ids), 10):
        batch = record_ids[i:i+10]
        
        try:
            # Airtable Delete erwartet records[] Parameter
            params = "&".join([f"records[]={rid}" for rid in batch])
            response = requests.delete(f"{url}?{params}", headers=headers, timeout=30)
            
            if response.status_code == 200:
                deleted += len(batch)
            else:
                print(f"   ⚠️ Batch-Fehler: {response.status_code}")
                
        except Exception as e:
            print(f"   ❌ Fehler beim Löschen: {e}")
    
    return deleted


# =============================================================================
# API FUNKTIONEN
# =============================================================================

def fetch_api_value(site_id: str, metric_api: str, target_date: date) -> Optional[int]:
    """Holt den Wert direkt von der INFOnline API"""
    if not INFONLINE_API_KEY:
        return None
        
    url = f"https://reportingapi.infonline.de/api/v1/{metric_api}"
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
            if "data" in data and "iom" in data["data"] and len(data["data"]["iom"]) > 0:
                field = METRICS_MAP.get(metric_api, {}).get("field", metric_api)
                # Für API-Metrik den Feldnamen finden
                for m, info in METRICS_MAP.items():
                    if info["api"] == metric_api:
                        field = info["field"]
                        break
                return data["data"]["iom"][0].get(field)
    except:
        pass
    
    return None


# =============================================================================
# ANALYSE FUNKTIONEN
# =============================================================================

def find_duplicates(records: List[Dict]) -> Dict[str, List[Dict]]:
    """Findet Duplikate anhand des Unique Key"""
    key_records = defaultdict(list)
    
    for record in records:
        key = record.get("unique_key")
        if key:
            key_records[key].append(record)
    
    # Nur Duplikate (mehr als 1 Record pro Key)
    duplicates = {k: v for k, v in key_records.items() if len(v) > 1}
    
    return duplicates


def analyze_data_quality(records: List[Dict]) -> Dict:
    """Analysiert Datenqualität und erstellt Bericht"""
    analysis = {
        "total_records": len(records),
        "unique_keys": set(),
        "dates": set(),
        "brands": set(),
        "platforms": set(),
        "metrics": set(),
        "duplicates": {},
        "missing_unique_key": 0,
        "issues": []
    }
    
    for record in records:
        uk = record.get("unique_key")
        if uk:
            analysis["unique_keys"].add(uk)
        else:
            analysis["missing_unique_key"] += 1
            analysis["issues"].append(f"Missing Unique Key: {record['id']}")
        
        if record.get("datum"):
            analysis["dates"].add(record["datum"])
        if record.get("brand"):
            analysis["brands"].add(record["brand"])
        if record.get("plattform"):
            analysis["platforms"].add(record["plattform"])
        if record.get("metrik"):
            analysis["metrics"].add(record["metrik"])
    
    # Duplikate finden
    analysis["duplicates"] = find_duplicates(records)
    
    return analysis


def compare_with_api(records: List[Dict], date_to_check: date) -> List[Dict]:
    """Vergleicht Airtable-Werte mit API-Werten"""
    if not INFONLINE_API_KEY:
        print("⚠️ INFONLINE_API_KEY nicht gesetzt - API-Vergleich übersprungen")
        return []
    
    print(f"\n🔍 Vergleiche mit ÖWA API für {date_to_check.isoformat()}...")
    
    discrepancies = []
    
    # Aggregiere Airtable-Werte pro Unique Key
    airtable_values = {}
    for record in records:
        if record.get("datum") == date_to_check.isoformat():
            key = record.get("unique_key")
            if key and "_MONTH_" not in key:  # Nur Tagesdaten
                if key not in airtable_values:
                    airtable_values[key] = {"total": 0, "count": 0, "records": []}
                airtable_values[key]["total"] += record.get("wert", 0) or 0
                airtable_values[key]["count"] += 1
                airtable_values[key]["records"].append(record)
    
    # Vergleiche mit API
    for site_name, site_info in SITES.items():
        for metric_name, metric_info in METRICS_MAP.items():
            # Unique Key Format: {Datum}_{Brand}_{Surface}_{Metrik}
            unique_key = f"{date_to_check.isoformat()}_{site_info['brand']}_{site_info['surface']}_{metric_name}"
            
            if unique_key in airtable_values:
                airtable_total = airtable_values[unique_key]["total"]
                record_count = airtable_values[unique_key]["count"]
                
                # API-Wert holen
                api_value = fetch_api_value(site_info["site_id"], metric_info["api"], date_to_check)
                
                if api_value is not None:
                    # Vergleich: Erwarte dass Airtable-Summe == API-Wert
                    # Bei Duplikaten: Airtable-Summe = API-Wert * Anzahl Duplikate
                    expected_api = api_value
                    diff_pct = ((airtable_total - expected_api) / expected_api * 100) if expected_api > 0 else 0
                    
                    if abs(diff_pct) > 1 or record_count > 1:  # Mehr als 1% Abweichung oder Duplikate
                        discrepancies.append({
                            "unique_key": unique_key,
                            "brand": site_info["brand"],
                            "surface": site_info["surface"],
                            "metric": metric_name,
                            "airtable_total": airtable_total,
                            "airtable_count": record_count,
                            "api_value": api_value,
                            "diff_pct": diff_pct,
                            "is_duplicate": record_count > 1,
                            "records": airtable_values[unique_key]["records"]
                        })
                        
                        print(f"   {'❌ DUPLIKAT' if record_count > 1 else '⚠️'} {unique_key}")
                        print(f"      Airtable: {airtable_total:,} ({record_count}x)")
                        print(f"      API:      {api_value:,}")
                        print(f"      Diff:     {diff_pct:+.1f}%")
    
    return discrepancies


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="ÖWA Data Integrity Check & Repair Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--date", type=str, help="Spezifisches Datum prüfen (YYYY-MM-DD)")
    parser.add_argument("--days", type=int, default=7, help="Letzte X Tage prüfen (default: 7)")
    parser.add_argument("--fix", action="store_true", help="Duplikate automatisch entfernen")
    parser.add_argument("--verify-api", action="store_true", help="Mit ÖWA API vergleichen")
    parser.add_argument("--dry-run", action="store_true", help="Nur simulieren, nichts ändern")
    
    args = parser.parse_args()
    
    print("=" * 70)
    print("🔍 ÖWA DATA INTEGRITY CHECK v1.0")
    print("=" * 70)
    
    # API Keys prüfen
    if not AIRTABLE_API_KEY:
        print("❌ AIRTABLE_API_KEY nicht gesetzt!")
        sys.exit(1)
    
    # Datumsbereiche
    if args.date:
        start_date = date.fromisoformat(args.date)
        end_date = start_date
    else:
        end_date = date.today()
        start_date = end_date - timedelta(days=args.days)
    
    print(f"\n📅 Prüfe Zeitraum: {start_date.isoformat()} bis {end_date.isoformat()}")
    
    # Daten laden
    records = fetch_all_records(start_date, end_date)
    
    if not records:
        print("✓ Keine Daten für den Zeitraum gefunden.")
        return
    
    # Analyse durchführen
    print("\n" + "=" * 70)
    print("📊 ANALYSE")
    print("=" * 70)
    
    analysis = analyze_data_quality(records)
    
    print(f"\n📈 STATISTIKEN:")
    print(f"   Total Records:      {analysis['total_records']}")
    print(f"   Unique Keys:        {len(analysis['unique_keys'])}")
    print(f"   Daten ohne Key:     {analysis['missing_unique_key']}")
    print(f"   Duplikate gefunden: {len(analysis['duplicates'])}")
    print(f"   Betroffene Tage:    {len(analysis['dates'])}")
    print(f"   Brands:             {', '.join(sorted(analysis['brands']))}")
    print(f"   Plattformen:        {', '.join(sorted(analysis['platforms']))}")
    print(f"   Metriken:           {', '.join(sorted(analysis['metrics']))}")
    
    # Duplikate anzeigen
    if analysis["duplicates"]:
        print("\n" + "=" * 70)
        print("⚠️  DUPLIKATE GEFUNDEN!")
        print("=" * 70)
        
        total_duplicate_records = 0
        records_to_delete = []
        
        for unique_key, dup_records in sorted(analysis["duplicates"].items()):
            count = len(dup_records)
            total_duplicate_records += count - 1  # -1 weil wir einen behalten wollen
            
            print(f"\n🔑 {unique_key}")
            print(f"   Anzahl: {count} Records (sollte 1 sein)")
            
            # Sortiere nach Erfassungsdatum (behalte ältesten)
            sorted_records = sorted(dup_records, key=lambda x: x.get("erfasst_am") or "")
            
            for i, rec in enumerate(sorted_records):
                wert = rec.get("wert") or 0
                erfasst = rec.get("erfasst_am", "")[:19] if rec.get("erfasst_am") else "?"
                marker = "✅ BEHALTEN" if i == 0 else "❌ LÖSCHEN"
                print(f"   {marker} | ID: {rec['id'][:8]}... | Wert: {wert:,} | Erfasst: {erfasst}")
                
                # Alle außer dem ersten (ältesten) zum Löschen markieren
                if i > 0:
                    records_to_delete.append(rec["id"])
        
        print(f"\n📋 ZUSAMMENFASSUNG:")
        print(f"   Duplikate-Gruppen:     {len(analysis['duplicates'])}")
        print(f"   Records zum Löschen:   {len(records_to_delete)}")
        
        # API-Vergleich (wenn aktiviert)
        if args.verify_api:
            discrepancies = []
            current = start_date
            while current <= end_date:
                disc = compare_with_api(records, current)
                discrepancies.extend(disc)
                current += timedelta(days=1)
            
            if discrepancies:
                print(f"\n⚠️ {len(discrepancies)} Abweichungen zur ÖWA API gefunden!")
        
        # Fix durchführen (wenn --fix angegeben)
        if args.fix and records_to_delete:
            print("\n" + "=" * 70)
            print("🔧 REPARATUR")
            print("=" * 70)
            
            if args.dry_run or not args.fix:
                print(f"\n[DRY-RUN] Würde {len(records_to_delete)} Duplikat-Records löschen:")
                for rid in records_to_delete[:5]:
                    print(f"   • {rid}")
                if len(records_to_delete) > 5:
                    print(f"   ... und {len(records_to_delete) - 5} weitere")
            else:
                print(f"\n🗑️ Lösche {len(records_to_delete)} Duplikat-Records...")
                deleted = delete_records(records_to_delete, dry_run=False)
                print(f"✓ {deleted} Records gelöscht")
        
        elif records_to_delete:
            print("\n💡 Tipp: Führe mit --fix aus, um Duplikate zu entfernen:")
            print(f"   python ci_scripts/data_integrity_check.py --date {start_date.isoformat()} --fix")
    
    else:
        print("\n✅ KEINE DUPLIKATE GEFUNDEN")
        
        # Optional: API-Vergleich auch ohne Duplikate
        if args.verify_api:
            print("\n🔍 Führe API-Vergleich durch...")
            current = start_date
            while current <= end_date:
                compare_with_api(records, current)
                current += timedelta(days=1)
    
    print("\n" + "=" * 70)
    print("✓ INTEGRITY CHECK ABGESCHLOSSEN")
    print("=" * 70)


if __name__ == "__main__":
    main()

