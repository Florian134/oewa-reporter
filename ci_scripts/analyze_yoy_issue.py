#!/usr/bin/env python3
"""
Analyse: Warum zeigen VOL Web und VOL App exakt gleiche YoY-Steigerung?
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from monthly_data_utils import get_monthly_data, get_yoy_comparison

def main():
    print("=" * 80)
    print("ANALYSE: YoY-Steigerung Web vs. App")
    print("=" * 80)
    
    # Lade Dezember 2024 und 2025
    print("\n1. Lade Rohdaten...")
    
    dec_2024 = get_monthly_data(2024, 12, brand_filter="VOL", aggregate_app=True)
    dec_2025 = get_monthly_data(2025, 12, brand_filter="VOL", aggregate_app=True)
    
    print("\n2. Dezember 2024 (Vorjahr):")
    print("-" * 80)
    for key in sorted(dec_2024.keys()):
        print(f"   {key}:")
        for metric, value in sorted(dec_2024[key].items()):
            print(f"      {metric}: {value:,}")
    
    print("\n3. Dezember 2025 (Aktuell):")
    print("-" * 80)
    for key in sorted(dec_2025.keys()):
        print(f"   {key}:")
        for metric, value in sorted(dec_2025[key].items()):
            print(f"      {metric}: {value:,}")
    
    # Manuelle YoY-Berechnung
    print("\n4. Manuelle YoY-Berechnung:")
    print("-" * 80)
    
    for key in sorted(dec_2025.keys()):
        if key in dec_2024:
            print(f"\n   {key}:")
            for metric in ["Page Impressions", "Visits"]:
                val_2024 = dec_2024.get(key, {}).get(metric, 0)
                val_2025 = dec_2025.get(key, {}).get(metric, 0)
                
                if val_2024 > 0:
                    yoy = (val_2025 - val_2024) / val_2024 * 100
                    print(f"      {metric}:")
                    print(f"         2024: {val_2024:,}")
                    print(f"         2025: {val_2025:,}")
                    print(f"         YoY:  {yoy:+.2f}%")
                else:
                    print(f"      {metric}: Keine 2024-Daten")
    
    # Prüfe auch die YoY-Funktion
    print("\n5. get_yoy_comparison() Ergebnis:")
    print("-" * 80)
    
    yoy_data = get_yoy_comparison(2025, 12, brand_filter="VOL", aggregate_app=True)
    
    yoy_changes = yoy_data.get("yoy_changes", {})
    for key in sorted(yoy_changes.keys()):
        print(f"\n   {key}:")
        for metric, change in sorted(yoy_changes[key].items()):
            if change is not None:
                print(f"      {metric}: {change*100:+.2f}%")
            else:
                print(f"      {metric}: N/A")
    
    # Fazit
    print("\n" + "=" * 80)
    print("FAZIT")
    print("=" * 80)
    
    # Prüfe ob Werte identisch sind
    web_pi_2024 = dec_2024.get("VOL_Web", {}).get("Page Impressions", 0)
    web_pi_2025 = dec_2025.get("VOL_Web", {}).get("Page Impressions", 0)
    app_pi_2024 = dec_2024.get("VOL_App", {}).get("Page Impressions", 0)
    app_pi_2025 = dec_2025.get("VOL_App", {}).get("Page Impressions", 0)
    
    web_yoy = (web_pi_2025 - web_pi_2024) / web_pi_2024 * 100 if web_pi_2024 > 0 else 0
    app_yoy = (app_pi_2025 - app_pi_2024) / app_pi_2024 * 100 if app_pi_2024 > 0 else 0
    
    print(f"\n   Web PI YoY: {web_yoy:+.4f}%")
    print(f"   App PI YoY: {app_yoy:+.4f}%")
    print(f"   Differenz:  {abs(web_yoy - app_yoy):.4f}%")
    
    if abs(web_yoy - app_yoy) < 0.1:
        print("\n   ⚠️ Die YoY-Werte sind nahezu identisch!")
        print("   Das kann Zufall sein ODER auf ein Datenproblem hindeuten.")
    
    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()

