#!/usr/bin/env python3
"""
Analyse: Daten ab 31.12.2025 - Vergleich Airtable vs. ÖWA API
=============================================================
"""

import os
import requests
from datetime import date, timedelta

AIRTABLE_API_KEY = os.environ.get("AIRTABLE_API_KEY", "")
AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID", "appTIeod85xnBy7Vn")
INFONLINE_API_KEY = os.environ.get("INFONLINE_API_KEY", "")

def main():
    print("=" * 70)
    print("ANALYSE: Daten ab 31.12.2025 - Airtable vs. ÖWA API")
    print("=" * 70)
    
    if not AIRTABLE_API_KEY:
        print("FEHLER: AIRTABLE_API_KEY nicht gesetzt!")
        return
    
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/Measurements"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    
    # =========================================================================
    # 1. Airtable-Daten für VOL Web PI ab 30.12.2025
    # =========================================================================
    print("\n1. VOL Web Page Impressions in Airtable (ab 30.12.2025):")
    print("-" * 70)
    
    params = {
        "filterByFormula": "AND(IS_AFTER({Datum}, '2025-12-29'), {Brand} = 'VOL', {Plattform} = 'Web', {Metrik} = 'Page Impressions', FIND('_MONTH_', {Unique Key}) = 0)",
        "sort[0][field]": "Datum",
        "sort[0][direction]": "asc"
    }
    
    response = requests.get(url, headers=headers, params=params, timeout=30)
    records = response.json().get("records", [])
    
    print(f"{'Datum':<12} | {'Wert':>12} | {'Site ID':<15} | {'Erfasst am':<20}")
    print("-" * 70)
    
    airtable_values = {}
    for r in records:
        f = r.get("fields", {})
        datum = f.get("Datum", "")
        wert = f.get("Wert", 0)
        site_id = f.get("Site ID", "")
        erfasst = f.get("Erfasst am", "N/A")[:19]
        print(f"{datum:<12} | {wert:>12,} | {site_id:<15} | {erfasst:<20}")
        airtable_values[datum] = wert
    
    # =========================================================================
    # 2. Direkt von INFOnline API abrufen zum Vergleich
    # =========================================================================
    if INFONLINE_API_KEY:
        print("\n2. Direkte API-Abfrage (INFOnline) fuer VOL Web PI:")
        print("-" * 70)
        print(f"{'Datum':<12} | {'API-Wert':>12} | {'Airtable':>12} | {'Differenz':>10}")
        print("-" * 70)
        
        # Prüfe die letzten 7 Tage
        today = date.today()
        for i in range(7, 0, -1):
            target_date = today - timedelta(days=i)
            
            api_url = "https://reportingapi.infonline.de/api/v1/pageimpressions"
            params = {
                "site": "at_w_atvol",
                "date": target_date.isoformat(),
                "aggregation": "DAY"
            }
            api_headers = {
                "authorization": INFONLINE_API_KEY,
                "Accept": "application/json"
            }
            
            try:
                resp = requests.get(api_url, params=params, headers=api_headers, timeout=30)
                if resp.status_code == 200:
                    data = resp.json()
                    if "data" in data and "iom" in data["data"] and len(data["data"]["iom"]) > 0:
                        api_value = data["data"]["iom"][0].get("pis", 0)
                        preliminary = data["data"]["iom"][0].get("preliminary", False)
                    else:
                        api_value = None
                        preliminary = None
                elif resp.status_code == 404:
                    api_value = "KEINE DATEN"
                    preliminary = None
                else:
                    api_value = f"HTTP {resp.status_code}"
                    preliminary = None
            except Exception as e:
                api_value = f"ERROR: {e}"
                preliminary = None
            
            airtable_val = airtable_values.get(target_date.isoformat(), "-")
            
            if isinstance(api_value, int) and isinstance(airtable_val, int):
                diff = airtable_val - api_value
                diff_str = f"{diff:+,}"
            else:
                diff_str = "-"
            
            api_str = f"{api_value:,}" if isinstance(api_value, int) else str(api_value)
            at_str = f"{airtable_val:,}" if isinstance(airtable_val, int) else str(airtable_val)
            
            prelim_str = " (vorl.)" if preliminary else ""
            print(f"{target_date.isoformat():<12} | {api_str:>12}{prelim_str} | {at_str:>12} | {diff_str:>10}")
    
    # =========================================================================
    # 3. Prüfe Site-IDs
    # =========================================================================
    print("\n3. Verwendete Site-IDs:")
    print("-" * 70)
    print("   Unser System:     at_w_atvol (VOL.AT Web Einzelangebot)")
    print("   OeWA Dashboard:   BE000071 (VOL.AT - Gesamt Web Belegungseinheit)")
    print()
    print("   HINWEIS: Diese koennten unterschiedliche Werte liefern!")
    
    # =========================================================================
    # 4. Diagnose
    # =========================================================================
    print("\n" + "=" * 70)
    print("DIAGNOSE")
    print("=" * 70)
    
    print("""
MOEGLICHE URSACHEN fuer falsche Daten ab 31.12.:

1. API-VERZOEGERUNG
   - INFOnline API hat 2-Tage-Delay fuer finale Daten
   - Heute ist 05.01.2026, also sollten Daten bis 03.01. verfuegbar sein
   - ABER: Die API koennte trotzdem 0 oder keine Daten liefern

2. FEHLERHAFTE IMPORT-DATEN
   - Der Backfill hat moeglicherweise vorlaeuige/falsche Daten importiert
   - Diese sollten geloescht und neu importiert werden

3. SITE-ID DISKREPANZ
   - OeWA Dashboard zeigt BE000071 (Belegungseinheit)
   - Wir verwenden at_w_atvol (Einzelangebot)
   - Diese koennten unterschiedliche Werte haben

LOESUNG:
   -> Alle Daten ab 31.12.2025 loeschen
   -> Warten bis die API finale Daten liefert
   -> Oder: Site-ID BE000071 testen
""")
    
    print("=" * 70)


if __name__ == "__main__":
    main()

