#!/usr/bin/env python3
"""
Vergleich: at_w_atvol vs. BE000071 (ÖWA Dashboard Site-ID)
==========================================================
"""

import os
import requests
from datetime import date, timedelta

INFONLINE_API_KEY = os.environ.get("INFONLINE_API_KEY", "")

def main():
    print("=" * 70)
    print("VERGLEICH: at_w_atvol vs. BE000071 (OeWA Dashboard)")
    print("=" * 70)
    
    if not INFONLINE_API_KEY:
        print("FEHLER: INFONLINE_API_KEY nicht gesetzt!")
        return
    
    site_ids = {
        "at_w_atvol": "VOL.AT Web (Einzelangebot - UNSERE QUELLE)",
        "BE000071": "VOL.AT Gesamt Web (OeWA Dashboard Kennung)"
    }
    
    today = date.today()
    
    print()
    header = f"{'Datum':<12} | {'at_w_atvol':>12} | {'BE000071':>12} | Anmerkung"
    print(header)
    print("-" * 70)
    
    for i in range(10, 0, -1):
        target_date = today - timedelta(days=i)
        
        values = {}
        for site_id in site_ids.keys():
            api_url = "https://reportingapi.infonline.de/api/v1/pageimpressions"
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
                resp = requests.get(api_url, params=params, headers=headers, timeout=30)
                if resp.status_code == 200:
                    data = resp.json()
                    if "data" in data and "iom" in data["data"] and len(data["data"]["iom"]) > 0:
                        values[site_id] = data["data"]["iom"][0].get("pis", 0)
                    else:
                        values[site_id] = "KEINE"
                elif resp.status_code == 404:
                    values[site_id] = "404"
                else:
                    values[site_id] = f"ERR{resp.status_code}"
            except Exception as e:
                values[site_id] = "ERROR"
        
        v1 = values.get("at_w_atvol", "-")
        v2 = values.get("BE000071", "-")
        
        v1_str = f"{v1:,}" if isinstance(v1, int) else str(v1)
        v2_str = f"{v2:,}" if isinstance(v2, int) else str(v2)
        
        note = ""
        if v2 in ["KEINE", "404"] and isinstance(v1, int):
            note = "<- DISKREPANZ!"
        elif isinstance(v1, int) and isinstance(v2, int) and v1 != v2:
            diff_pct = (v1 - v2) / v2 * 100 if v2 > 0 else 0
            note = f"Diff: {diff_pct:+.1f}%"
        
        print(f"{target_date.isoformat():<12} | {v1_str:>12} | {v2_str:>12} | {note}")
    
    print()
    print("=" * 70)
    print("FAZIT:")
    print("-" * 70)
    print("  at_w_atvol = INFOnline Einzelangebot-Kennung (unsere Quelle)")
    print("  BE000071   = OeWA Belegungseinheit-Kennung (OeWA Dashboard)")
    print()
    print("  Diese zwei Kennungen sind UNTERSCHIEDLICHE Datenquellen!")
    print("  Das erklaert, warum das OeWA Dashboard andere/keine Daten zeigt.")
    print("=" * 70)


if __name__ == "__main__":
    main()

