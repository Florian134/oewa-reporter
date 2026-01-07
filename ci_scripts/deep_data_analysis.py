#!/usr/bin/env python3
"""
TIEFGREIFENDE DATENANALYSE
==========================
Vergleicht unsere ÖWA-Daten mit den Aussagen des internen Analysten.

Der Analyst sagt:
- Direct-Traffic ist RÜCKLÄUFIG (niedrigster Wert seit Aufzeichnung)
- Im Vorjahresvergleich ~700k Sitzungen weniger
- Aber: Search (+) und Discover (+) wachsen

Unser Report sagt:
- Page Impressions +12% YoY
- Visits +9-12% YoY

Ziel: Herausfinden, ob unsere Daten korrekt sind.
"""

import os
import sys
import requests
from datetime import date
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from monthly_data_utils import get_monthly_data

AIRTABLE_API_KEY = os.environ.get("AIRTABLE_API_KEY", "")
AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID", "")  # Muss in CI/CD Variables gesetzt sein
INFONLINE_API_KEY = os.environ.get("INFONLINE_API_KEY", "")

# VOL.AT Site IDs
SITES = {
    "VOL_Web": "at_w_atvol",
    "VOL_iOS": "at_i_volat",
    "VOL_Android": "at_a_volat",
}


def fetch_from_api(site_id: str, metric: str, year: int, month: int) -> int:
    """Holt Monatsdaten direkt von der INFOnline API."""
    if not INFONLINE_API_KEY:
        return None
    
    url = f"https://reportingapi.infonline.de/api/v1/{metric}"
    params = {
        "site": site_id,
        "date": f"{year}-{month:02d}-01",
        "aggregation": "MONTH"
    }
    headers = {"Authorization": f"Bearer {INFONLINE_API_KEY}"}
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=30)
        if response.status_code == 200:
            data = response.json()
            if metric == "pageimpressions":
                return data.get("pis", 0)
            elif metric == "visits":
                return data.get("visits", 0)
        return None
    except:
        return None


def main():
    print("=" * 80)
    print("TIEFGREIFENDE DATENANALYSE: ÖWA vs. Analyst-Report")
    print("=" * 80)
    
    # ==========================================================================
    # 1. Lade unsere Airtable-Daten
    # ==========================================================================
    print("\n1. UNSERE AIRTABLE-DATEN")
    print("-" * 80)
    
    dec_2024 = get_monthly_data(2024, 12, brand_filter="VOL", aggregate_app=True)
    dec_2025 = get_monthly_data(2025, 12, brand_filter="VOL", aggregate_app=True)
    nov_2025 = get_monthly_data(2025, 11, brand_filter="VOL", aggregate_app=True)
    
    print("\n   Dezember 2024:")
    for key in sorted(dec_2024.keys()):
        pi = dec_2024[key].get("Page Impressions", 0)
        visits = dec_2024[key].get("Visits", 0)
        print(f"      {key}: PI={pi:,} | Visits={visits:,}")
    
    print("\n   November 2025:")
    for key in sorted(nov_2025.keys()):
        pi = nov_2025[key].get("Page Impressions", 0)
        visits = nov_2025[key].get("Visits", 0)
        print(f"      {key}: PI={pi:,} | Visits={visits:,}")
    
    print("\n   Dezember 2025:")
    for key in sorted(dec_2025.keys()):
        pi = dec_2025[key].get("Page Impressions", 0)
        visits = dec_2025[key].get("Visits", 0)
        print(f"      {key}: PI={pi:,} | Visits={visits:,}")
    
    # ==========================================================================
    # 2. Berechne Änderungen
    # ==========================================================================
    print("\n2. BERECHNETE ÄNDERUNGEN")
    print("-" * 80)
    
    # Gesamt (Web + App)
    total_dec_2024_pi = sum(dec_2024.get(k, {}).get("Page Impressions", 0) for k in dec_2024)
    total_dec_2025_pi = sum(dec_2025.get(k, {}).get("Page Impressions", 0) for k in dec_2025)
    total_nov_2025_pi = sum(nov_2025.get(k, {}).get("Page Impressions", 0) for k in nov_2025)
    
    total_dec_2024_visits = sum(dec_2024.get(k, {}).get("Visits", 0) for k in dec_2024)
    total_dec_2025_visits = sum(dec_2025.get(k, {}).get("Visits", 0) for k in dec_2025)
    total_nov_2025_visits = sum(nov_2025.get(k, {}).get("Visits", 0) for k in nov_2025)
    
    yoy_pi = (total_dec_2025_pi - total_dec_2024_pi) / total_dec_2024_pi * 100 if total_dec_2024_pi > 0 else 0
    yoy_visits = (total_dec_2025_visits - total_dec_2024_visits) / total_dec_2024_visits * 100 if total_dec_2024_visits > 0 else 0
    mom_pi = (total_dec_2025_pi - total_nov_2025_pi) / total_nov_2025_pi * 100 if total_nov_2025_pi > 0 else 0
    mom_visits = (total_dec_2025_visits - total_nov_2025_visits) / total_nov_2025_visits * 100 if total_nov_2025_visits > 0 else 0
    
    print("\n   GESAMT VOL (Web + App):")
    print(f"      Page Impressions:")
    print(f"         Dez 2024: {total_dec_2024_pi:,}")
    print(f"         Nov 2025: {total_nov_2025_pi:,}")
    print(f"         Dez 2025: {total_dec_2025_pi:,}")
    print(f"         MoM: {mom_pi:+.2f}%")
    print(f"         YoY: {yoy_pi:+.2f}%")
    
    print(f"\n      Visits:")
    print(f"         Dez 2024: {total_dec_2024_visits:,}")
    print(f"         Nov 2025: {total_nov_2025_visits:,}")
    print(f"         Dez 2025: {total_dec_2025_visits:,}")
    print(f"         MoM: {mom_visits:+.2f}%")
    print(f"         YoY: {yoy_visits:+.2f}%")
    
    # ==========================================================================
    # 3. Vergleiche mit INFOnline API (falls verfügbar)
    # ==========================================================================
    print("\n3. DIREKTER API-VERGLEICH")
    print("-" * 80)
    
    if INFONLINE_API_KEY:
        print("\n   Hole Daten direkt von INFOnline API...")
        
        for site_name, site_id in SITES.items():
            print(f"\n   {site_name} ({site_id}):")
            
            for year, month, label in [(2024, 12, "Dez 2024"), (2025, 12, "Dez 2025")]:
                pi = fetch_from_api(site_id, "pageimpressions", year, month)
                visits = fetch_from_api(site_id, "visits", year, month)
                
                if pi is not None:
                    print(f"      {label}: PI={pi:,} | Visits={visits:,}")
                else:
                    print(f"      {label}: API-Fehler oder keine Daten")
    else:
        print("   ⚠️ INFONLINE_API_KEY nicht gesetzt - API-Vergleich nicht möglich")
    
    # ==========================================================================
    # 4. Vergleich mit Analyst-Aussagen
    # ==========================================================================
    print("\n4. VERGLEICH MIT ANALYST-AUSSAGEN")
    print("-" * 80)
    
    print("""
   ANALYST SAGT (Traffic-Source-Analyse):
   ─────────────────────────────────────
   • Direct-Traffic: RÜCKLÄUFIG (niedrigster Wert seit Aufzeichnung)
     - Dez 2025: 1,547,155 Sitzungen
     - YoY: ~700k weniger = ca. -31%
     - Relativer Anteil: 21.77%
   
   • Search-Traffic: STEIGEND
     - Relativer Anteil: 44%
   
   • Discover-Traffic: STEIGEND
     - Relativer Anteil: ~30%
   
   UNSER REPORT SAGT (ÖWA-Daten):
   ─────────────────────────────
   • Page Impressions: +12% YoY
   • Visits: +9-12% YoY
   
   MÖGLICHE ERKLÄRUNGEN:
   ────────────────────
   1. VERSCHIEDENE METRIKEN: Sessions ≠ Visits ≠ Page Impressions
   2. VERSCHIEDENE DATENQUELLEN: Google Analytics vs. ÖWA/INFOnline
   3. TEILMENGE vs. GESAMT: Direct ist nur 21% des Traffics
      - Wenn Direct -31%, aber Search/Discover wachsen,
        kann Gesamt-Traffic trotzdem steigen!
   4. DATENFEHLER: Unsere Dez 2024 oder Dez 2025 Daten könnten falsch sein
   """)
    
    # ==========================================================================
    # 5. Lade Monatsdaten aus Airtable zum Vergleich
    # ==========================================================================
    print("\n5. HISTORISCHE DATEN (letztes halbes Jahr)")
    print("-" * 80)
    
    months_to_check = [
        (2024, 10), (2024, 11), (2024, 12),
        (2025, 10), (2025, 11), (2025, 12)
    ]
    
    print("\n   VOL Web Page Impressions:")
    for year, month in months_to_check:
        data = get_monthly_data(year, month, brand_filter="VOL", aggregate_app=True)
        pi = data.get("VOL_Web", {}).get("Page Impressions", 0)
        visits = data.get("VOL_Web", {}).get("Visits", 0)
        print(f"      {year}-{month:02d}: PI={pi:,} | Visits={visits:,}")
    
    print("\n" + "=" * 80)
    print("FAZIT")
    print("=" * 80)
    
    print("""
   Die Diskrepanz könnte erklärbar sein durch:
   
   1. VERSCHIEDENE DATENQUELLEN:
      - Analyst nutzt Google Analytics (Sessions, Traffic-Sources)
      - Wir nutzen ÖWA/INFOnline (Page Impressions, Visits)
      
   2. VERSCHIEDENE METRIKEN:
      - "Sitzungen" (GA) ≠ "Visits" (ÖWA)
      - GA misst Browser-Sessions, ÖWA misst Server-Requests
      
   3. TEILMENGE vs. GESAMT:
      - Direct-Traffic ist nur ~22% des Gesamttraffics
      - Search (44%) + Discover (30%) = 74% wachsen!
      - Gesamt kann trotz sinkendem Direct steigen
      
   EMPFEHLUNG:
   ──────────
   - Manuelle Prüfung der ÖWA-Daten im Original-Dashboard
   - Vergleich mit Google Analytics Gesamt-Sessions
   """)
    
    print("=" * 80)


if __name__ == "__main__":
    main()

