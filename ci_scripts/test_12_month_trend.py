#!/usr/bin/env python3
"""Test: 12-Monats-Trend"""

import os
import sys

# Füge ci_scripts zum Pfad hinzu
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from monthly_data_utils import get_12_month_trend

def main():
    print("=" * 70)
    print("12-MONATS-TREND: Januar 2025 - Dezember 2025")
    print("=" * 70)
    
    trend = get_12_month_trend(2025, 12, brand_filter="VOL", aggregate_app=True)
    
    print(f"\nGefunden: {len(trend)} Monate")
    print()
    print(f"{'Monat':<12} | {'Web PI':>15} | {'App PI':>15} | {'Gesamt':>15}")
    print("-" * 65)
    
    for entry in trend:
        month_str = entry["month_str"]
        data = entry["data"]
        
        web_pi = data.get("VOL_Web", {}).get("Page Impressions", 0)
        app_pi = data.get("VOL_App", {}).get("Page Impressions", 0)
        total = web_pi + app_pi
        
        print(f"{month_str:<12} | {web_pi:>15,} | {app_pi:>15,} | {total:>15,}")
    
    print("=" * 70)


if __name__ == "__main__":
    main()

