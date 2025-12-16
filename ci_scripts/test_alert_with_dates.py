#!/usr/bin/env python3
"""
Test Script für den neuen Alert mit genauen Abweichungsdaten
============================================================
Testet das neue Format mit:
- Abweichungsdatum vs. Berichtsdatum
- Historische Vergleichswerte MIT Datum
"""

import os
import requests
from datetime import date, datetime, timedelta

# Konfiguration
TEAMS_WEBHOOK_URL = os.environ.get("TEAMS_WEBHOOK_URL", "")

def main():
    print("=" * 70)
    print("🧪 TEST: Neues Alert-Format mit Abweichungsdaten")
    print("=" * 70)
    
    if not TEAMS_WEBHOOK_URL:
        print("❌ TEAMS_WEBHOOK_URL nicht gesetzt!")
        print("\nBitte setze die Variable:")
        print('$env:TEAMS_WEBHOOK_URL = "https://..."')
        return
    
    # Simulierte Daten
    abweichungs_datum = date.today() - timedelta(days=1)  # Gestern
    bericht_datum = datetime.now()
    
    weekday_names = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
    weekday_name = weekday_names[abweichungs_datum.weekday()]
    
    # Simulierte historische Daten (letzte 6 gleiche Wochentage)
    historical_data = [
        {"date": abweichungs_datum - timedelta(weeks=1), "value": 780000},
        {"date": abweichungs_datum - timedelta(weeks=2), "value": 795000},
        {"date": abweichungs_datum - timedelta(weeks=3), "value": 810000},
        {"date": abweichungs_datum - timedelta(weeks=4), "value": 765000},
        {"date": abweichungs_datum - timedelta(weeks=5), "value": 800000},
        {"date": abweichungs_datum - timedelta(weeks=6), "value": 790000},
    ]
    
    # Aktueller Wert und Berechnung
    current_value = 680000
    avg = sum(h["value"] for h in historical_data) / len(historical_data)
    pct_change = (current_value - avg) / avg
    
    # Historische Daten formatieren
    hist_str = " | ".join([
        f"{h['date'].strftime('%d.%m.')}: {h['value']:,}"
        for h in historical_data
    ])
    
    # Alert-Details
    alert_lines = [
        f"📉 **VOL Web - Page Impressions**\n"
        f"   📅 **{abweichungs_datum.strftime('%d.%m.%Y')}**: {current_value:,} ({pct_change*100:+.1f}%)\n"
        f"   📊 Vergleich: {hist_str}",
        
        f"📈 **Vienna Web - Visits**\n"
        f"   📅 **{abweichungs_datum.strftime('%d.%m.%Y')}**: 95.000 (+12.3%)\n"
        f"   📊 Vergleich: {(abweichungs_datum - timedelta(weeks=1)).strftime('%d.%m.')}: 84.000 | "
        f"{(abweichungs_datum - timedelta(weeks=2)).strftime('%d.%m.')}: 82.000 | "
        f"{(abweichungs_datum - timedelta(weeks=3)).strftime('%d.%m.')}: 86.000"
    ]
    
    # Facts mit klarer Unterscheidung
    facts = [
        {"name": "📅 Abweichungsdatum", "value": f"**{abweichungs_datum.strftime('%d.%m.%Y')}** ({weekday_name})"},
        {"name": "⏰ Bericht erstellt", "value": bericht_datum.strftime('%d.%m.%Y %H:%M') + " Uhr"},
        {"name": "🔔 Anzahl Abweichungen", "value": "2"},
        {"name": "📊 Vergleichsbasis", "value": f"Letzte 6 {weekday_name}e"},
    ]
    
    # GPT-Analyse simulieren
    analysis = f"""**🔍 ANALYSE**
Am **{abweichungs_datum.strftime('%d.%m.%Y')}** ({weekday_name}) zeigt VOL.AT einen signifikanten Rückgang der Page Impressions um {pct_change*100:.1f}% gegenüber dem 6-Wochen-Durchschnitt. Vienna.AT verzeichnet hingegen eine positive Entwicklung bei den Visits.

**📊 TREND-BEWERTUNG**
Der Verlauf zeigt: {historical_data[0]['date'].strftime('%d.%m.')}: {historical_data[0]['value']:,} → {historical_data[1]['date'].strftime('%d.%m.')}: {historical_data[1]['value']:,} → aktuell: {current_value:,}. Der Trend ist leicht rückläufig.

**💡 EMPFEHLUNG**
Content-Performance und technisches Tracking für VOL.AT prüfen."""
    
    # Teams Card
    card = {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "summary": f"🧪 TEST - ÖWA Alert mit Abweichungsdaten",
        "themeColor": "FFC107",
        "sections": [
            {
                "activityTitle": f"🧪 TEST: ÖWA WOCHENTAGS-ALERT",
                "activitySubtitle": f"⚠️ TESTDATEN - Abweichungen am {abweichungs_datum.strftime('%d.%m.%Y')} erkannt",
                "facts": facts,
                "markdown": True
            },
            {
                "title": "📋 Erkannte Abweichungen (mit Vergleichsdaten)",
                "text": "\n\n".join(alert_lines),
                "markdown": True
            },
            {
                "title": "🤖 KI-Analyse",
                "text": analysis,
                "markdown": True
            }
        ],
        "potentialAction": [{
            "@type": "OpenUri",
            "name": "📈 Dashboard öffnen",
            "targets": [{"os": "default", "uri": "https://oewa-reporter-ucgucmpvryylvvkhefxyeq.streamlit.app"}]
        }]
    }
    
    print(f"\n📅 Abweichungsdatum: {abweichungs_datum.strftime('%d.%m.%Y')} ({weekday_name})")
    print(f"⏰ Bericht erstellt: {bericht_datum.strftime('%d.%m.%Y %H:%M')} Uhr")
    print(f"📊 Simulierte Abweichung: {pct_change*100:+.1f}%")
    print(f"\n📤 Sende Test-Alert an Teams...")
    
    try:
        response = requests.post(TEAMS_WEBHOOK_URL, json=card, timeout=10)
        if response.status_code == 200:
            print("✅ Test-Alert erfolgreich gesendet!")
            print("\n🔍 Prüfe deinen Teams-Channel für die Nachricht.")
        else:
            print(f"❌ Fehler: HTTP {response.status_code}")
            print(f"   Response: {response.text[:200]}")
    except Exception as e:
        print(f"❌ Fehler: {e}")
    
    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()

