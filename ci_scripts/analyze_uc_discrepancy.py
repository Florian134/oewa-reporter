#!/usr/bin/env python3
"""
Analyse: Unique Clients Diskrepanz YoY

Prüft warum die Unique Clients einen unrealistischen YoY-Wert von +1543% zeigen.
"""

import os
import sys
import requests
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from monthly_data_utils import get_monthly_data, get_12_month_trend

AIRTABLE_API_KEY = os.environ.get("AIRTABLE_API_KEY", "")
AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID", "")  # Muss in CI/CD Variables gesetzt sein


def main():
    print("=" * 80)
    print("ANALYSE: Unique Clients Diskrepanz")
    print("=" * 80)
    
    # 1. Lade Daten für Dezember 2024 und 2025
    print("\n1. Vergleiche Unique Clients Dezember 2024 vs. 2025:")
    print("-" * 80)
    
    dec_2024 = get_monthly_data(2024, 12, brand_filter="VOL", aggregate_app=True)
    dec_2025 = get_monthly_data(2025, 12, brand_filter="VOL", aggregate_app=True)
    
    print("\n   Dezember 2024:")
    for key in sorted(dec_2024.keys()):
        uc = dec_2024[key].get("Unique Clients", 0)
        pi = dec_2024[key].get("Page Impressions", 0)
        visits = dec_2024[key].get("Visits", 0)
        print(f"      {key}: UC={uc:,} | PI={pi:,} | Visits={visits:,}")
    
    print("\n   Dezember 2025:")
    for key in sorted(dec_2025.keys()):
        uc = dec_2025[key].get("Unique Clients", 0)
        pi = dec_2025[key].get("Page Impressions", 0)
        visits = dec_2025[key].get("Visits", 0)
        print(f"      {key}: UC={uc:,} | PI={pi:,} | Visits={visits:,}")
    
    # 2. Berechne Verhältnisse
    print("\n2. Verhältnisanalyse (PI/UC und Visits/UC):")
    print("-" * 80)
    
    for key in sorted(dec_2024.keys()):
        if key in dec_2025:
            uc_2024 = dec_2024[key].get("Unique Clients", 0)
            pi_2024 = dec_2024[key].get("Page Impressions", 0)
            uc_2025 = dec_2025[key].get("Unique Clients", 0)
            pi_2025 = dec_2025[key].get("Page Impressions", 0)
            
            ratio_2024 = pi_2024 / uc_2024 if uc_2024 > 0 else 0
            ratio_2025 = pi_2025 / uc_2025 if uc_2025 > 0 else 0
            
            print(f"\n   {key}:")
            print(f"      2024: PI/UC = {ratio_2024:.1f} (UC={uc_2024:,})")
            print(f"      2025: PI/UC = {ratio_2025:.1f} (UC={uc_2025:,})")
    
    # 3. Prüfe 12-Monats-Trend für UC
    print("\n3. 12-Monats-Trend Unique Clients:")
    print("-" * 80)
    
    trend = get_12_month_trend(2025, 12, brand_filter="VOL", aggregate_app=True)
    
    print(f"\n   {'Monat':<12} | {'Web UC':>15} | {'App UC':>15}")
    print("   " + "-" * 50)
    
    for entry in trend:
        web_uc = entry["data"].get("VOL_Web", {}).get("Unique Clients", 0)
        app_uc = entry["data"].get("VOL_App", {}).get("Unique Clients", 0)
        print(f"   {entry['month_str']:<12} | {web_uc:>15,} | {app_uc:>15,}")
    
    # 4. Prüfe auch 2024
    print("\n4. 2024 Unique Clients Trend:")
    print("-" * 80)
    
    trend_2024 = get_12_month_trend(2024, 12, brand_filter="VOL", aggregate_app=True)
    
    print(f"\n   {'Monat':<12} | {'Web UC':>15} | {'App UC':>15}")
    print("   " + "-" * 50)
    
    for entry in trend_2024:
        web_uc = entry["data"].get("VOL_Web", {}).get("Unique Clients", 0)
        app_uc = entry["data"].get("VOL_App", {}).get("Unique Clients", 0)
        print(f"   {entry['month_str']:<12} | {web_uc:>15,} | {app_uc:>15,}")
    
    # 5. Fazit
    print("\n" + "=" * 80)
    print("FAZIT")
    print("=" * 80)
    
    dec_2024_web_uc = dec_2024.get("VOL_Web", {}).get("Unique Clients", 0)
    dec_2024_app_uc = dec_2024.get("VOL_App", {}).get("Unique Clients", 0)
    dec_2025_web_uc = dec_2025.get("VOL_Web", {}).get("Unique Clients", 0)
    dec_2025_app_uc = dec_2025.get("VOL_App", {}).get("Unique Clients", 0)
    
    web_yoy = ((dec_2025_web_uc - dec_2024_web_uc) / dec_2024_web_uc * 100) if dec_2024_web_uc > 0 else 0
    app_yoy = ((dec_2025_app_uc - dec_2024_app_uc) / dec_2024_app_uc * 100) if dec_2024_app_uc > 0 else 0
    
    print(f"\n   VOL Web UC: {dec_2024_web_uc:,} -> {dec_2025_web_uc:,} ({web_yoy:+.1f}%)")
    print(f"   VOL App UC: {dec_2024_app_uc:,} -> {dec_2025_app_uc:,} ({app_yoy:+.1f}%)")
    
    # Prüfe auf Messmethodenwechsel
    if web_yoy > 100 or app_yoy > 100:
        print("\n   ⚠️ WARNUNG: Extreme YoY-Änderungen bei Unique Clients!")
        print("   Mögliche Ursachen:")
        print("      1. Messmethodenwechsel bei ÖWA zwischen 2024 und 2025")
        print("      2. Datenqualitätsproblem in den 2024-Daten")
        print("      3. Unterschiedliche UC-Definition (Daily vs. Monthly UC)")
    
    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()

