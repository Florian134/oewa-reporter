#!/usr/bin/env python3
"""
Analyse: Datenstruktur - Tagesdaten vs. Monatsdaten

Prüft für jeden Monat:
- Sind Tagesdaten vorhanden?
- Sind Monatsdaten (_MONTH_) vorhanden?
- Wie viele Tage sind abgedeckt?

Dies hilft bei der Strategie für den Monatsreport:
- Monate MIT Tagesdaten: Aggregieren zur Laufzeit
- Monate OHNE Tagesdaten: _MONTH_ Records direkt verwenden
"""

import os
import requests
from collections import defaultdict
from datetime import date

AIRTABLE_API_KEY = os.environ.get("AIRTABLE_API_KEY", "")
AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID", "appTIeod85xnBy7Vn")


def get_all_measurements():
    """Holt alle Measurements aus Airtable."""
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/Measurements"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    
    all_records = []
    offset = None
    
    while True:
        params = {"pageSize": 100}
        if offset:
            params["offset"] = offset
        
        response = requests.get(url, headers=headers, params=params, timeout=30)
        if response.status_code != 200:
            print(f"FEHLER: {response.status_code}")
            break
        
        data = response.json()
        all_records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break
        
        if len(all_records) % 500 == 0:
            print(f"   ... {len(all_records)} Records geladen ...")
    
    return all_records


def main():
    print("=" * 80)
    print("ANALYSE: Datenstruktur - Tagesdaten vs. Monatsdaten")
    print("=" * 80)
    
    if not AIRTABLE_API_KEY:
        print("FEHLER: AIRTABLE_API_KEY nicht gesetzt!")
        return
    
    print("\n1. Lade alle Measurements aus Airtable...")
    records = get_all_measurements()
    print(f"   Geladen: {len(records)} Records")
    
    # Struktur: monat -> {"daily_dates": set(), "monthly_exists": bool, "daily_count": int}
    month_data = defaultdict(lambda: {
        "daily_dates": set(),
        "monthly_exists": False,
        "daily_count": 0,
        "monthly_count": 0,
        "brands": set()
    })
    
    for record in records:
        fields = record.get("fields", {})
        unique_key = fields.get("Unique Key", "")
        datum = fields.get("Datum", "")
        brand = fields.get("Brand", "")
        
        if not datum:
            continue
        
        # Extrahiere Jahr-Monat aus Datum
        try:
            d = date.fromisoformat(datum)
            month_str = f"{d.year}-{d.month:02d}"
        except:
            continue
        
        month_data[month_str]["brands"].add(brand)
        
        if "_MONTH_" in unique_key:
            # Dies ist ein Monatsdaten-Record
            month_data[month_str]["monthly_exists"] = True
            month_data[month_str]["monthly_count"] += 1
        else:
            # Dies ist ein Tagesdaten-Record
            month_data[month_str]["daily_dates"].add(datum)
            month_data[month_str]["daily_count"] += 1
    
    # Ausgabe
    print("\n2. Uebersicht nach Monat:")
    print("-" * 80)
    print(f"{'Monat':<10} | {'Tage':>5} | {'Daily':>8} | {'Monthly':>8} | {'Typ':^15} | Brands")
    print("-" * 80)
    
    for month in sorted(month_data.keys()):
        data = month_data[month]
        days_count = len(data["daily_dates"])
        daily_count = data["daily_count"]
        monthly_count = data["monthly_count"]
        monthly_exists = data["monthly_exists"]
        brands = ", ".join(sorted(data["brands"]))
        
        # Bestimme Typ
        if days_count > 0 and monthly_exists:
            typ = "BEIDE"
        elif days_count > 0:
            typ = "NUR DAILY"
        elif monthly_exists:
            typ = "NUR MONTHLY"
        else:
            typ = "KEINE"
        
        print(f"{month:<10} | {days_count:>5} | {daily_count:>8} | {monthly_count:>8} | {typ:^15} | {brands}")
    
    # Strategie-Empfehlung
    print("\n" + "=" * 80)
    print("STRATEGIE-EMPFEHLUNG")
    print("=" * 80)
    
    daily_only = []
    monthly_only = []
    both = []
    
    for month in sorted(month_data.keys()):
        data = month_data[month]
        days = len(data["daily_dates"])
        monthly = data["monthly_exists"]
        
        if days > 0 and not monthly:
            daily_only.append(month)
        elif monthly and days == 0:
            monthly_only.append(month)
        elif days > 0 and monthly:
            both.append(month)
    
    print(f"\n   Monate NUR mit Tagesdaten (aggregieren zur Laufzeit):")
    if daily_only:
        print(f"      {', '.join(daily_only)}")
    else:
        print("      (keine)")
    
    print(f"\n   Monate NUR mit Monatsdaten (direkt verwenden):")
    if monthly_only:
        print(f"      {', '.join(monthly_only)}")
    else:
        print("      (keine)")
    
    print(f"\n   Monate mit BEIDEN (Tagesdaten priorisieren, Monatsdaten als Backup):")
    if both:
        print(f"      {', '.join(both)}")
    else:
        print("      (keine)")
    
    print("\n" + "=" * 80)
    print("EMPFEHLUNG FUER MONATSREPORT:")
    print("=" * 80)
    print("""
    1. Funktion: get_monthly_data(year, month)
       
       WENN Tagesdaten fuer den Monat vorhanden:
         -> Aggregiere alle Tagesdaten zur Laufzeit
         -> Gruppiere nach Brand, Plattform, Metrik
         -> Berechne Summe
       
       SONST (nur Monatsdaten vorhanden):
         -> Lade _MONTH_ Records direkt
         -> Verwende gespeicherte Monatssummen
    
    2. Fuer 12-Monats-Trend:
       - Aeltere Monate: Monatsdaten-Records
       - Aktuelle Monate: Tagesdaten aggregieren
       - Einheitliches Interface fuer beide
    """)
    
    print("=" * 80)


if __name__ == "__main__":
    main()

