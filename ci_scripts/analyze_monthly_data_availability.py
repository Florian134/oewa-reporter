#!/usr/bin/env python3
"""
Analyse: Verfügbare Monatsdaten für erweiterten Vergleich
==========================================================
Prüft ob wir Daten für:
- Letzte 12 Monate (für Trend)
- Vorjahresmonat (für YoY-Vergleich)
haben.
"""

import os
import requests
from collections import defaultdict

AIRTABLE_API_KEY = os.environ.get("AIRTABLE_API_KEY", "")
AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID", "")  # Muss in CI/CD Variables gesetzt sein

def main():
    print("=" * 70)
    print("ANALYSE: Verfuegbare Monatsdaten fuer erweiterten Vergleich")
    print("=" * 70)
    
    if not AIRTABLE_API_KEY:
        print("FEHLER: AIRTABLE_API_KEY nicht gesetzt!")
        return
    
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/Measurements"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    
    # =========================================================================
    # 1. Lade alle Monatsdaten (haben _MONTH_ im Unique Key)
    # =========================================================================
    print("\n1. Lade alle Monatsdaten aus Airtable...")
    
    all_records = []
    offset = None
    
    while True:
        params = {
            "filterByFormula": "FIND('_MONTH_', {Unique Key}) > 0",
            "pageSize": 100
        }
        if offset:
            params["offset"] = offset
        
        response = requests.get(url, headers=headers, params=params, timeout=30)
        if response.status_code != 200:
            print(f"   FEHLER: {response.status_code}")
            break
        
        data = response.json()
        all_records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break
    
    print(f"   -> {len(all_records)} Monatsdaten-Records gefunden")
    
    # =========================================================================
    # 2. Gruppiere nach Monat und Brand
    # =========================================================================
    monthly_data = defaultdict(lambda: defaultdict(dict))
    
    for record in all_records:
        fields = record.get("fields", {})
        unique_key = fields.get("Unique Key", "")
        brand = fields.get("Brand", "")
        platform = fields.get("Plattform", "")
        metric = fields.get("Metrik", "")
        value = fields.get("Wert", 0)
        
        # Extrahiere Monat aus Unique Key (Format: YYYY-MM_MONTH_...)
        if "_MONTH_" in unique_key:
            month_str = unique_key.split("_MONTH_")[0]
            key = f"{platform}_{metric}"
            monthly_data[month_str][brand][key] = value
    
    # =========================================================================
    # 3. Übersicht der verfügbaren Monate
    # =========================================================================
    months_sorted = sorted(monthly_data.keys())
    
    print("\n2. Uebersicht verfuegbarer Monate:")
    print("-" * 70)
    print(f"   Aeltester Monat: {months_sorted[0] if months_sorted else 'N/A'}")
    print(f"   Neuester Monat:  {months_sorted[-1] if months_sorted else 'N/A'}")
    print(f"   Anzahl Monate:   {len(months_sorted)}")
    print(f"   Monate: {', '.join(months_sorted)}")
    
    # =========================================================================
    # 4. VOL Page Impressions pro Monat
    # =========================================================================
    print("\n3. VOL Page Impressions pro Monat (Web + App):")
    print("-" * 70)
    print(f"Monat      | Web PI          | App PI          | Gesamt")
    print("-" * 70)
    
    for month in months_sorted:
        vol_data = monthly_data.get(month, {}).get("VOL", {})
        web_pi = vol_data.get("Web_Page Impressions", 0)
        ios_pi = vol_data.get("iOS_Page Impressions", 0)
        android_pi = vol_data.get("Android_Page Impressions", 0)
        # Fallback auf alte "App"-Kennung
        old_app_pi = vol_data.get("App_Page Impressions", 0)
        app_pi = ios_pi + android_pi if (ios_pi + android_pi) > 0 else old_app_pi
        gesamt = web_pi + app_pi
        
        print(f"{month:<10} | {web_pi:>15,} | {app_pi:>15,} | {gesamt:>15,}")
    
    # =========================================================================
    # 5. Prüfe benötigte Monate für erweiterten Report
    # =========================================================================
    print("\n4. Pruefe benoetigte Monate fuer erweiterten Report:")
    print("-" * 70)
    
    # Für Dezember 2025 Report:
    # - 12 Vormonate: Dez 2024 bis Nov 2025
    # - Vorjahresmonat: Dez 2024
    
    required_months = [
        "2024-01", "2024-02", "2024-03", "2024-04", "2024-05", "2024-06",
        "2024-07", "2024-08", "2024-09", "2024-10", "2024-11", "2024-12",
        "2025-01", "2025-02", "2025-03", "2025-04", "2025-05", "2025-06",
        "2025-07", "2025-08", "2025-09", "2025-10", "2025-11"
    ]
    
    print("   Fuer 12-Monats-Trend (Jan 2024 - Nov 2025):")
    missing = []
    for month in required_months:
        if month in monthly_data:
            vol_data = monthly_data[month].get("VOL", {})
            web_pi = vol_data.get("Web_Page Impressions", 0)
            status = "OK" if web_pi > 0 else "KEINE DATEN"
        else:
            status = "FEHLT"
            missing.append(month)
        print(f"      {month}: {status}")
    
    print()
    print("   Vorjahresmonat (Dez 2024):")
    if "2024-12" in monthly_data:
        vol_dec24 = monthly_data["2024-12"].get("VOL", {})
        web_pi = vol_dec24.get("Web_Page Impressions", 0)
        print(f"      Web PI: {web_pi:,}")
        print(f"      STATUS: {'OK' if web_pi > 0 else 'KEINE DATEN'}")
    else:
        print("      STATUS: FEHLT")
        missing.append("2024-12")
    
    # =========================================================================
    # 6. Fazit
    # =========================================================================
    print("\n" + "=" * 70)
    print("FAZIT")
    print("=" * 70)
    
    if not missing:
        print("\n   ALLE benoetigten Monatsdaten sind vorhanden!")
        print("   -> 12-Monats-Trend: MOEGLICH")
        print("   -> YoY-Vergleich (Dez 2025 vs. Dez 2024): MOEGLICH")
    else:
        print(f"\n   FEHLENDE Monate: {', '.join(missing)}")
        print("   -> Erweiterte Analyse TEILWEISE moeglich")
    
    print("\n" + "=" * 70)
    
    return monthly_data, months_sorted


if __name__ == "__main__":
    main()

