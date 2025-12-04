#!/usr/bin/env python3
"""
Debug-Skript: Analysiert die Airtable-Daten für den Weekly Report
"""

import os
import requests
from datetime import date, timedelta
from collections import defaultdict

# Konfiguration - ersetze mit deinen Werten falls nicht in Umgebungsvariablen
AIRTABLE_API_KEY = os.environ.get("AIRTABLE_API_KEY", "")
AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID", "appTleod85xnBy7Vn")

def get_measurements(days: int = 30):
    """Holt Measurements der letzten X Tage aus Airtable"""
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/Measurements"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    
    cutoff_date = (date.today() - timedelta(days=days)).isoformat()
    
    records = []
    offset = None
    
    while True:
        params = {
            "filterByFormula": f"IS_AFTER({{Datum}}, '{cutoff_date}')",
            "pageSize": 100
        }
        if offset:
            params["offset"] = offset
            
        response = requests.get(url, headers=headers, params=params, timeout=30)
        if response.status_code != 200:
            print(f"❌ Airtable Fehler: {response.status_code}")
            print(response.text)
            break
            
        data = response.json()
        records.extend(data.get("records", []))
        
        offset = data.get("offset")
        if not offset:
            break
    
    return records

def analyze_data():
    """Analysiert die Daten für den Weekly Report"""
    
    if not AIRTABLE_API_KEY:
        print("❌ AIRTABLE_API_KEY nicht gesetzt!")
        print("   Setze die Variable: set AIRTABLE_API_KEY=dein_key")
        return
    
    print("=" * 70)
    print("📊 AIRTABLE DATEN-ANALYSE")
    print("=" * 70)
    
    # Daten laden
    print("\n📥 Lade Daten aus Airtable (letzte 30 Tage)...")
    records = get_measurements(days=30)
    print(f"   → {len(records)} Datensätze geladen")
    
    if not records:
        print("❌ Keine Daten gefunden!")
        return
    
    # Zeiträume definieren
    today = date.today()
    week_start = today - timedelta(days=7)
    prev_week_start = today - timedelta(days=14)
    prev_week_end = week_start - timedelta(days=1)
    
    print(f"\n📅 Zeiträume:")
    print(f"   Heute: {today}")
    print(f"   Aktuelle Woche: {week_start} bis {today}")
    print(f"   Vorwoche: {prev_week_start} bis {prev_week_end}")
    
    # Daten gruppieren
    data_by_date = defaultdict(lambda: defaultdict(dict))
    all_dates = set()
    
    for record in records:
        fields = record.get("fields", {})
        datum_str = fields.get("Datum")
        brand = fields.get("Brand")
        metric = fields.get("Metrik")
        wert = fields.get("Wert")
        
        if not all([datum_str, brand, metric, wert]):
            continue
        
        try:
            datum = date.fromisoformat(datum_str)
        except:
            continue
        
        all_dates.add(datum)
        data_by_date[datum][brand][metric] = wert
    
    # Sortierte Datenliste
    sorted_dates = sorted(all_dates)
    
    print(f"\n📆 Verfügbare Daten:")
    print(f"   Frühestes Datum: {min(sorted_dates) if sorted_dates else 'N/A'}")
    print(f"   Letztes Datum: {max(sorted_dates) if sorted_dates else 'N/A'}")
    print(f"   Anzahl Tage mit Daten: {len(sorted_dates)}")
    
    # Detaillierte Tagesübersicht
    print("\n" + "=" * 70)
    print("📊 TÄGLICHE WERTE")
    print("=" * 70)
    print(f"{'Datum':<12} {'Woche':<10} {'VOL PI':>12} {'VOL Visits':>12} {'Vienna PI':>12} {'Vienna Vis':>12}")
    print("-" * 70)
    
    current_week_data = {"VOL": {"PI": [], "Visits": []}, "Vienna": {"PI": [], "Visits": []}}
    prev_week_data = {"VOL": {"PI": [], "Visits": []}, "Vienna": {"PI": [], "Visits": []}}
    
    for datum in sorted_dates:
        # Woche bestimmen
        if datum >= week_start:
            week_label = "AKTUELL"
            target = current_week_data
        elif datum >= prev_week_start:
            week_label = "VORWOCHE"
            target = prev_week_data
        else:
            week_label = "ÄLTER"
            target = None
        
        vol_pi = data_by_date[datum].get("VOL", {}).get("Page Impressions", 0)
        vol_visits = data_by_date[datum].get("VOL", {}).get("Visits", 0)
        vienna_pi = data_by_date[datum].get("Vienna", {}).get("Page Impressions", 0)
        vienna_visits = data_by_date[datum].get("Vienna", {}).get("Visits", 0)
        
        if target:
            if vol_pi: target["VOL"]["PI"].append(vol_pi)
            if vol_visits: target["VOL"]["Visits"].append(vol_visits)
            if vienna_pi: target["Vienna"]["PI"].append(vienna_pi)
            if vienna_visits: target["Vienna"]["Visits"].append(vienna_visits)
        
        print(f"{datum}   {week_label:<10} {vol_pi:>12,} {vol_visits:>12,} {vienna_pi:>12,} {vienna_visits:>12,}")
    
    # Zusammenfassung
    print("\n" + "=" * 70)
    print("📈 ZUSAMMENFASSUNG")
    print("=" * 70)
    
    print("\n🔹 AKTUELLE WOCHE:")
    print(f"   VOL PI:      {len(current_week_data['VOL']['PI'])} Tage, Summe: {sum(current_week_data['VOL']['PI']):>12,}")
    print(f"   VOL Visits:  {len(current_week_data['VOL']['Visits'])} Tage, Summe: {sum(current_week_data['VOL']['Visits']):>12,}")
    print(f"   Vienna PI:   {len(current_week_data['Vienna']['PI'])} Tage, Summe: {sum(current_week_data['Vienna']['PI']):>12,}")
    print(f"   Vienna Vis:  {len(current_week_data['Vienna']['Visits'])} Tage, Summe: {sum(current_week_data['Vienna']['Visits']):>12,}")
    
    print("\n🔹 VORWOCHE:")
    print(f"   VOL PI:      {len(prev_week_data['VOL']['PI'])} Tage, Summe: {sum(prev_week_data['VOL']['PI']):>12,}")
    print(f"   VOL Visits:  {len(prev_week_data['VOL']['Visits'])} Tage, Summe: {sum(prev_week_data['VOL']['Visits']):>12,}")
    print(f"   Vienna PI:   {len(prev_week_data['Vienna']['PI'])} Tage, Summe: {sum(prev_week_data['Vienna']['PI']):>12,}")
    print(f"   Vienna Vis:  {len(prev_week_data['Vienna']['Visits'])} Tage, Summe: {sum(prev_week_data['Vienna']['Visits']):>12,}")
    
    # Veränderungen berechnen
    print("\n🔹 VERÄNDERUNGEN (Summen-Vergleich):")
    
    def calc_change(current, prev):
        if not prev or sum(prev) == 0:
            return "N/A"
        return f"{((sum(current) - sum(prev)) / sum(prev) * 100):+.1f}%"
    
    print(f"   VOL PI:      {calc_change(current_week_data['VOL']['PI'], prev_week_data['VOL']['PI'])}")
    print(f"   VOL Visits:  {calc_change(current_week_data['VOL']['Visits'], prev_week_data['VOL']['Visits'])}")
    print(f"   Vienna PI:   {calc_change(current_week_data['Vienna']['PI'], prev_week_data['Vienna']['PI'])}")
    print(f"   Vienna Vis:  {calc_change(current_week_data['Vienna']['Visits'], prev_week_data['Vienna']['Visits'])}")
    
    # Durchschnitts-Vergleich (fairer)
    print("\n🔹 VERÄNDERUNGEN (Durchschnitts-Vergleich - FAIRER!):")
    
    def calc_avg_change(current, prev):
        if not prev or not current:
            return "N/A"
        avg_current = sum(current) / len(current)
        avg_prev = sum(prev) / len(prev)
        if avg_prev == 0:
            return "N/A"
        return f"{((avg_current - avg_prev) / avg_prev * 100):+.1f}%"
    
    print(f"   VOL PI:      {calc_avg_change(current_week_data['VOL']['PI'], prev_week_data['VOL']['PI'])}")
    print(f"   VOL Visits:  {calc_avg_change(current_week_data['VOL']['Visits'], prev_week_data['VOL']['Visits'])}")
    print(f"   Vienna PI:   {calc_avg_change(current_week_data['Vienna']['PI'], prev_week_data['Vienna']['PI'])}")
    print(f"   Vienna Vis:  {calc_avg_change(current_week_data['Vienna']['Visits'], prev_week_data['Vienna']['Visits'])}")
    
    print("\n" + "=" * 70)
    print("✅ ANALYSE ABGESCHLOSSEN")
    print("=" * 70)

if __name__ == "__main__":
    analyze_data()

