#!/usr/bin/env python3
"""
Test Script für alle Teams Webhook + GPT Funktionen
====================================================
Testet alle Benachrichtigungs-Use-Cases:

1. Daily Ingest Notification (ohne GPT)
2. Weekly Report mit GPT-Zusammenfassung
3. Alert Check mit GPT-Analyse

Nutzung:
    python ci_scripts/test_all_notifications.py --all
    python ci_scripts/test_all_notifications.py --daily
    python ci_scripts/test_all_notifications.py --weekly
    python ci_scripts/test_all_notifications.py --alert
    python ci_scripts/test_all_notifications.py --gpt-only

Wichtig: Setzt echte Daten an Teams! Nur für Tests verwenden.
"""

import os
import json
import requests
import argparse
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

# =============================================================================
# KONFIGURATION
# =============================================================================
TEAMS_WEBHOOK_URL = os.environ.get("TEAMS_WEBHOOK_URL", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

# Test-Daten (simuliert)
TEST_DATA = {
    "date": date.today().isoformat(),
    "vol_pi": 874938,
    "vol_visits": 312456,
    "vienna_pi": 156234,
    "vienna_visits": 67890,
    "vol_pi_change": -12.5,
    "vol_visits_change": +3.2,
    "vienna_pi_change": -18.7,
    "vienna_visits_change": -5.1,
}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def check_config():
    """Prüft ob alle notwendigen Konfigurationen gesetzt sind"""
    print("\n🔧 Konfiguration prüfen...")
    
    issues = []
    
    if not TEAMS_WEBHOOK_URL:
        issues.append("❌ TEAMS_WEBHOOK_URL nicht gesetzt")
    else:
        print(f"   ✅ TEAMS_WEBHOOK_URL: ...{TEAMS_WEBHOOK_URL[-30:]}")
    
    if not OPENAI_API_KEY:
        issues.append("⚠️ OPENAI_API_KEY nicht gesetzt (GPT-Tests werden übersprungen)")
    else:
        print(f"   ✅ OPENAI_API_KEY: sk-...{OPENAI_API_KEY[-8:]}")
    
    if issues:
        for issue in issues:
            print(f"   {issue}")
    
    return len([i for i in issues if i.startswith("❌")]) == 0


def send_teams_card(card: dict, test_name: str) -> bool:
    """Sendet eine Teams Card und gibt Erfolg zurück"""
    if not TEAMS_WEBHOOK_URL:
        print(f"   ❌ {test_name}: TEAMS_WEBHOOK_URL nicht gesetzt")
        return False
    
    try:
        response = requests.post(TEAMS_WEBHOOK_URL, json=card, timeout=10)
        if response.status_code == 200:
            print(f"   ✅ {test_name}: Erfolgreich gesendet")
            return True
        else:
            print(f"   ❌ {test_name}: HTTP {response.status_code}")
            return False
    except Exception as e:
        print(f"   ❌ {test_name}: {str(e)}")
        return False


def call_gpt(prompt: str, test_name: str) -> Optional[str]:
    """Ruft GPT API auf und gibt Antwort zurück"""
    if not OPENAI_API_KEY:
        print(f"   ⚠️ {test_name}: OPENAI_API_KEY nicht gesetzt - übersprungen")
        return None
    
    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 500,
                "temperature": 0.7
            },
            timeout=60
        )
        
        if response.status_code == 200:
            content = response.json()["choices"][0]["message"]["content"]
            print(f"   ✅ {test_name}: GPT Response ({len(content)} Zeichen)")
            return content
        else:
            print(f"   ❌ {test_name}: GPT HTTP {response.status_code}")
            error = response.json().get("error", {}).get("message", "Unknown error")
            print(f"      → {error[:100]}")
            return None
    except Exception as e:
        print(f"   ❌ {test_name}: {str(e)}")
        return None


# =============================================================================
# TEST 1: DAILY INGEST NOTIFICATION
# =============================================================================

def test_daily_ingest_notification():
    """
    Testet die Daily Ingest Benachrichtigung.
    Diese verwendet KEIN GPT, nur eine Status-Meldung.
    """
    print("\n" + "=" * 70)
    print("📥 TEST 1: Daily Ingest Notification")
    print("=" * 70)
    
    message = f"""**🧪 TEST - Daily Ingest**

**Datum:** {TEST_DATA['date']}
**Datensätze:** 4

**Ergebnisse:**
• VOL.AT Page Impressions: {TEST_DATA['vol_pi']:,}
• VOL.AT Visits: {TEST_DATA['vol_visits']:,}
• VIENNA.AT Page Impressions: {TEST_DATA['vienna_pi']:,}
• VIENNA.AT Visits: {TEST_DATA['vienna_visits']:,}

**Status:** ✅ Erfolgreich (TEST)"""

    card = {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "summary": "🧪 TEST - ÖWA Daily Ingest",
        "themeColor": "28A745",  # Grün
        "sections": [{
            "activityTitle": "📥 ÖWA Daily Ingest - TEST",
            "activitySubtitle": "⚠️ Dies ist ein Testlauf",
            "text": message,
            "markdown": True
        }]
    }
    
    return send_teams_card(card, "Daily Ingest")


# =============================================================================
# TEST 2: WEEKLY REPORT MIT GPT
# =============================================================================

def test_weekly_report_with_gpt():
    """
    Testet den Weekly Report mit GPT-Zusammenfassung.
    """
    print("\n" + "=" * 70)
    print("📊 TEST 2: Weekly Report mit GPT-Zusammenfassung")
    print("=" * 70)
    
    # GPT Prompt für Weekly Report
    prompt = f"""Du bist ein Web-Analytics-Experte für österreichische Medienunternehmen.
Erstelle eine kurze, professionelle Zusammenfassung der folgenden ÖWA-Wochendaten auf Deutsch.

DATEN DER LETZTEN WOCHE:

VOL.AT:
- Page Impressions: {TEST_DATA['vol_pi'] * 7:,} (Woche)
- Visits: {TEST_DATA['vol_visits'] * 7:,} (Woche)
- Veränderung PI vs. Vorwoche: {TEST_DATA['vol_pi_change']:+.1f}%
- Veränderung Visits vs. Vorwoche: {TEST_DATA['vol_visits_change']:+.1f}%

VIENNA.AT:
- Page Impressions: {TEST_DATA['vienna_pi'] * 7:,} (Woche)
- Visits: {TEST_DATA['vienna_visits'] * 7:,} (Woche)
- Veränderung PI vs. Vorwoche: {TEST_DATA['vienna_pi_change']:+.1f}%
- Veränderung Visits vs. Vorwoche: {TEST_DATA['vienna_visits_change']:+.1f}%

ANOMALIEN:
- VIENNA.AT Page Impressions: Rückgang von {abs(TEST_DATA['vienna_pi_change']):.1f}% (Z-Score: -2.3)

Erstelle eine Zusammenfassung mit:
1. Überblick der Wochenperformance (2-3 Sätze)
2. Wichtige Veränderungen oder Auffälligkeiten
3. Kurze Einschätzung/Empfehlung

Halte die Zusammenfassung prägnant (max. 100 Wörter).
"""

    print("\n   📤 Rufe GPT API auf...")
    gpt_summary = call_gpt(prompt, "Weekly Report GPT")
    
    if not gpt_summary:
        gpt_summary = "⚠️ GPT-Zusammenfassung nicht verfügbar (TEST)"
    
    # Teams Card erstellen
    facts = [
        {"name": "📅 Zeitraum", "value": f"KW {date.today().isocalendar()[1]} (TEST)"},
        {"name": "📊 VOL.AT PI", "value": f"{TEST_DATA['vol_pi'] * 7:,}"},
        {"name": "👥 VOL.AT Visits", "value": f"{TEST_DATA['vol_visits'] * 7:,}"},
        {"name": "📊 VIENNA.AT PI", "value": f"{TEST_DATA['vienna_pi'] * 7:,}"},
        {"name": "👥 VIENNA.AT Visits", "value": f"{TEST_DATA['vienna_visits'] * 7:,}"},
    ]
    
    anomaly_text = f"""
⚠️ **Anomalien:**
• 🟡 VIENNA.AT Page Impressions: {TEST_DATA['vienna_pi_change']:+.1f}% (Z=-2.3)
"""

    card = {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "summary": "🧪 TEST - ÖWA Wochenbericht",
        "themeColor": "FFC107",  # Gelb (wegen Anomalie)
        "sections": [
            {
                "activityTitle": "📊 ÖWA Wochenbericht - TEST",
                "activitySubtitle": "⚠️ Dies ist ein Testlauf mit simulierten Daten",
                "facts": facts,
                "markdown": True
            },
            {
                "text": f"**🤖 KI-Analyse:**\n\n{gpt_summary}{anomaly_text}",
                "markdown": True
            }
        ]
    }
    
    print("\n   📤 Sende an Teams...")
    return send_teams_card(card, "Weekly Report")


# =============================================================================
# TEST 3: ALERT CHECK MIT GPT
# =============================================================================

def test_alert_check_with_gpt():
    """
    Testet den Alert Check mit GPT-Analyse.
    Simuliert einen kritischen Alert.
    """
    print("\n" + "=" * 70)
    print("🚨 TEST 3: Alert Check mit GPT-Analyse")
    print("=" * 70)
    
    # Simulierte Alerts
    test_alerts = [
        {
            "severity": "critical",
            "brand": "VOL",
            "metric": "Page Impressions",
            "message": f"Starker Rückgang: {TEST_DATA['vol_pi_change']:+.1f}% vs. Vorwoche",
            "actual": TEST_DATA['vol_pi'],
            "threshold": -15.0
        },
        {
            "severity": "warning",
            "brand": "Vienna",
            "metric": "Page Impressions",
            "message": f"Unter Minimum: {TEST_DATA['vienna_pi']:,} (Min: 150.000)",
            "actual": TEST_DATA['vienna_pi'],
            "threshold": 150000
        }
    ]
    
    # Trend-Daten simulieren (7 Tage)
    vol_trend = [850000, 870000, 820000, 890000, 860000, 830000, TEST_DATA['vol_pi']]
    vienna_trend = [160000, 155000, 158000, 152000, 148000, 145000, TEST_DATA['vienna_pi']]
    
    # GPT Prompt für Alert-Analyse
    alert_text = "\n".join([
        f"- {a['severity'].upper()}: {a['brand']} {a['metric']} - {a['message']}"
        for a in test_alerts
    ])
    
    prompt = f"""Du bist ein erfahrener Web-Analytics-Experte für österreichische Medienunternehmen.

Es wurden kritische Alerts für die ÖWA-Metriken von VOL.AT und VIENNA.AT erkannt:

ALERTS:
{alert_text}

TRENDVERLAUF DER LETZTEN 7 TAGE:
VOL.AT Page Impressions: {', '.join(f'{v:,}' for v in vol_trend)}
VIENNA.AT Page Impressions: {', '.join(f'{v:,}' for v in vienna_trend)}

Aufgaben:
1. Analysiere die Alerts und den Trendverlauf
2. Identifiziere mögliche Ursachen (Feiertage, technische Probleme, saisonale Effekte, etc.)
3. Bewerte die Kritikalität für das Geschäft
4. Gib eine klare Handlungsempfehlung

Formatiere deine Antwort als kurzen, professionellen Alarm-Report (max. 150 Wörter).
"""

    print("\n   📤 Rufe GPT API auf...")
    gpt_analysis = call_gpt(prompt, "Alert Check GPT")
    
    if not gpt_analysis:
        gpt_analysis = "⚠️ GPT-Analyse nicht verfügbar (TEST)"
    
    # Alert-Lines für Card
    alert_lines = []
    for a in test_alerts:
        icon = "🔴" if a["severity"] == "critical" else "🟡"
        alert_lines.append(f"{icon} **{a['brand']} {a['metric']}**: {a['message']}")
    
    # Teams Card
    card = {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "summary": "🧪 TEST - ÖWA CRITICAL ALERT",
        "themeColor": "DC3545",  # Rot
        "sections": [
            {
                "activityTitle": "🚨 ÖWA CRITICAL ALERT - TEST",
                "activitySubtitle": "⚠️ Dies ist ein Testlauf mit simulierten Daten",
                "facts": [
                    {"name": "📅 Datum", "value": TEST_DATA['date']},
                    {"name": "🔔 Anzahl Alerts", "value": str(len(test_alerts))},
                    {"name": "⚠️ Höchster Level", "value": "CRITICAL"},
                ],
                "markdown": True
            },
            {
                "title": "📋 Erkannte Probleme",
                "text": "\n".join(alert_lines),
                "markdown": True
            },
            {
                "title": "🤖 KI-Analyse & Empfehlung",
                "text": gpt_analysis,
                "markdown": True
            }
        ]
    }
    
    print("\n   📤 Sende an Teams...")
    return send_teams_card(card, "Alert Check")


# =============================================================================
# TEST 4: NUR GPT API (ohne Teams)
# =============================================================================

def test_gpt_only():
    """
    Testet nur die GPT API Verbindung ohne Teams.
    """
    print("\n" + "=" * 70)
    print("🤖 TEST 4: GPT API Verbindung")
    print("=" * 70)
    
    prompt = """Antworte mit genau einem Satz: 
    "Die GPT API Verbindung für das ÖWA Reporting System funktioniert einwandfrei."
    """
    
    print("\n   📤 Rufe GPT API auf...")
    response = call_gpt(prompt, "GPT Connection Test")
    
    if response:
        print(f"\n   📝 GPT Antwort:")
        print(f"      {response}")
        return True
    else:
        return False


# =============================================================================
# TEST 5: EMERGENCY ALERT (höchste Priorität)
# =============================================================================

def test_emergency_alert():
    """
    Testet einen Emergency Alert (höchste Priorität).
    """
    print("\n" + "=" * 70)
    print("🚨 TEST 5: Emergency Alert (Höchste Priorität)")
    print("=" * 70)
    
    # Simulierter Emergency: Massiver Einbruch
    emergency_data = {
        "brand": "VOL",
        "metric": "Page Impressions",
        "actual": 180000,  # Unter Emergency-Schwelle von 200.000
        "threshold": 200000,
        "pct_change": -45.2,  # Über -40% Emergency-Schwelle
    }
    
    # GPT Prompt für Emergency
    prompt = f"""DRINGEND: Es wurde ein kritischer Alarm für das ÖWA Web-Analytics System erkannt.

EMERGENCY ALERT:
- Site: VOL.AT
- Metrik: Page Impressions
- Aktueller Wert: {emergency_data['actual']:,} (extrem niedrig!)
- Schwellenwert: {emergency_data['threshold']:,}
- Veränderung: {emergency_data['pct_change']:+.1f}% vs. Vorwoche

Dies deutet auf ein schwerwiegendes Problem hin (möglicherweise technischer Ausfall, Tracking-Fehler, oder massiver Traffic-Einbruch).

Erstelle eine kurze, dringende Handlungsempfehlung (max. 100 Wörter):
1. Was sollte sofort geprüft werden?
2. Wer sollte informiert werden?
3. Welche Sofortmaßnahmen sind nötig?
"""

    print("\n   📤 Rufe GPT API auf...")
    gpt_analysis = call_gpt(prompt, "Emergency GPT")
    
    if not gpt_analysis:
        gpt_analysis = "⚠️ GPT-Analyse nicht verfügbar - SOFORTIGE MANUELLE PRÜFUNG ERFORDERLICH!"
    
    # Teams Card (dunkelrot)
    card = {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "summary": "🚨🚨🚨 TEST - ÖWA EMERGENCY ALERT",
        "themeColor": "8B0000",  # Dunkelrot
        "sections": [
            {
                "activityTitle": "🚨🚨🚨 EMERGENCY ALERT - TEST",
                "activitySubtitle": "⚠️ Dies ist ein Testlauf - KEIN ECHTER NOTFALL",
                "facts": [
                    {"name": "📅 Datum", "value": TEST_DATA['date']},
                    {"name": "🌐 Site", "value": "VOL.AT"},
                    {"name": "📊 Metrik", "value": "Page Impressions"},
                    {"name": "📉 Aktuell", "value": f"{emergency_data['actual']:,}"},
                    {"name": "⚠️ Minimum", "value": f"{emergency_data['threshold']:,}"},
                    {"name": "📊 Veränderung", "value": f"{emergency_data['pct_change']:+.1f}%"},
                ],
                "markdown": True
            },
            {
                "title": "🚨 SOFORTMASSNAHMEN ERFORDERLICH",
                "text": gpt_analysis,
                "markdown": True
            }
        ]
    }
    
    print("\n   📤 Sende an Teams...")
    return send_teams_card(card, "Emergency Alert")


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Teste alle Teams + GPT Funktionen")
    parser.add_argument("--all", action="store_true", help="Alle Tests ausführen")
    parser.add_argument("--daily", action="store_true", help="Daily Ingest Test")
    parser.add_argument("--weekly", action="store_true", help="Weekly Report Test")
    parser.add_argument("--alert", action="store_true", help="Alert Check Test")
    parser.add_argument("--emergency", action="store_true", help="Emergency Alert Test")
    parser.add_argument("--gpt-only", action="store_true", help="Nur GPT API Test")
    
    args = parser.parse_args()
    
    # Default: Alle Tests wenn keine spezifische Option
    run_all = args.all or not any([args.daily, args.weekly, args.alert, args.emergency, args.gpt_only])
    
    print("=" * 70)
    print("🧪 ÖWA NOTIFICATION TESTS")
    print("=" * 70)
    print(f"📅 Datum: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}")
    
    # Konfiguration prüfen
    if not check_config():
        print("\n❌ Konfigurationsfehler - Tests abgebrochen")
        return
    
    results = {}
    
    # Tests ausführen
    if run_all or args.gpt_only:
        results["GPT API"] = test_gpt_only()
    
    if run_all or args.daily:
        results["Daily Ingest"] = test_daily_ingest_notification()
    
    if run_all or args.weekly:
        results["Weekly Report"] = test_weekly_report_with_gpt()
    
    if run_all or args.alert:
        results["Alert Check"] = test_alert_check_with_gpt()
    
    if run_all or args.emergency:
        results["Emergency Alert"] = test_emergency_alert()
    
    # Zusammenfassung
    print("\n" + "=" * 70)
    print("📋 ZUSAMMENFASSUNG")
    print("=" * 70)
    
    success = 0
    failed = 0
    
    for test_name, result in results.items():
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"   {test_name}: {status}")
        if result:
            success += 1
        else:
            failed += 1
    
    print("\n" + "-" * 70)
    print(f"   Gesamt: {success}/{success + failed} Tests erfolgreich")
    
    if failed == 0:
        print("\n🎉 Alle Tests erfolgreich! Prüfe deine Teams-Channel für die Nachrichten.")
    else:
        print(f"\n⚠️ {failed} Test(s) fehlgeschlagen. Prüfe die Konfiguration.")
    
    print("=" * 70)


if __name__ == "__main__":
    main()

