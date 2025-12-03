#!/usr/bin/env python3
"""
Weekly Report Script
====================
Wird von GitLab CI/CD ausgeführt, getriggert durch Airtable Automation.
Generiert einen wöchentlichen KI-Report und sendet ihn an Teams.
"""

import os
import json
import requests
from datetime import date, datetime, timedelta

# =============================================================================
# KONFIGURATION
# =============================================================================
AIRTABLE_API_KEY = os.environ.get("AIRTABLE_API_KEY", "")
AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID", "appTIeod85xnBy7Vn")
TEAMS_WEBHOOK_URL = os.environ.get("TEAMS_WEBHOOK_URL", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")


def get_weekly_data() -> dict:
    """Holt Wochendaten aus Airtable"""
    # Woche berechnen (letzte volle Woche)
    today = date.today()
    week_end = today - timedelta(days=today.weekday() + 1)  # Letzter Sonntag
    week_start = week_end - timedelta(days=6)
    
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/Measurements"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    
    # Filter für die Woche
    params = {
        "filterByFormula": f"AND(IS_AFTER({{Datum}}, '{(week_start - timedelta(days=1)).isoformat()}'), IS_BEFORE({{Datum}}, '{(week_end + timedelta(days=1)).isoformat()}'))"
    }
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        if response.status_code == 200:
            records = response.json().get("records", [])
            return {
                "success": True,
                "records": records,
                "week_start": week_start,
                "week_end": week_end
            }
        else:
            return {"success": False, "error": f"HTTP {response.status_code}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def aggregate_data(records: list) -> dict:
    """Aggregiert die Wochendaten"""
    metrics = {
        "web_pi": 0,
        "app_pi": 0,
        "web_visits": 0,
        "app_visits": 0
    }
    
    for record in records:
        fields = record.get("fields", {})
        plattform = fields.get("Plattform", "")
        metrik = fields.get("Metrik", "")
        wert = fields.get("Wert", 0) or 0
        
        if metrik == "Page Impressions":
            if "Web" in plattform:
                metrics["web_pi"] += wert
            elif plattform == "App":
                metrics["app_pi"] += wert
        elif metrik == "Visits":
            if "Web" in plattform:
                metrics["web_visits"] += wert
            elif plattform == "App":
                metrics["app_visits"] += wert
    
    metrics["total_pi"] = metrics["web_pi"] + metrics["app_pi"]
    metrics["total_visits"] = metrics["web_visits"] + metrics["app_visits"]
    
    return metrics


def generate_ai_summary(metrics: dict, week_start: date, week_end: date) -> str:
    """Generiert KI-Zusammenfassung mit OpenAI"""
    if not OPENAI_API_KEY:
        return "KI-Zusammenfassung nicht verfügbar (API Key fehlt)"
    
    prompt = f"""Analysiere diese Wochen-Daten für VOL.at und erstelle eine kurze Management-Zusammenfassung (max. 150 Wörter, auf Deutsch):

Zeitraum: {week_start.strftime('%d.%m.')} - {week_end.strftime('%d.%m.%Y')}

Metriken:
- Web Page Impressions: {metrics['web_pi']:,}
- App Page Impressions: {metrics['app_pi']:,}
- Gesamt PI: {metrics['total_pi']:,}
- Web Visits: {metrics['web_visits']:,}
- App Visits: {metrics['app_visits']:,}

Erstelle eine prägnante Zusammenfassung mit:
1. Kernaussage (1 Satz)
2. Trend-Bewertung
3. Handlungsempfehlung (falls nötig)"""

    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": "Du bist ein Digital-Analyst für Russmedia. Schreibe prägnante, professionelle Zusammenfassungen auf Deutsch."},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": 400,
                "temperature": 0.7
            },
            timeout=30
        )
        
        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"]
        else:
            return f"KI-Fehler: {response.status_code}"
    except Exception as e:
        return f"KI-Fehler: {str(e)}"


def send_teams_report(metrics: dict, ai_summary: str, week_start: date, week_end: date):
    """Sendet den Wochenbericht an Teams"""
    if not TEAMS_WEBHOOK_URL:
        print("⚠️ TEAMS_WEBHOOK_URL nicht konfiguriert")
        return
    
    kw = week_start.isocalendar()[1]
    
    card = {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "summary": f"ÖWA Wochenbericht KW{kw}",
        "themeColor": "0078D7",
        "sections": [
            {
                "activityTitle": f"📊 ÖWA Wochenbericht KW{kw}",
                "activitySubtitle": f"{week_start.strftime('%d.%m.')} - {week_end.strftime('%d.%m.%Y')}",
                "facts": [
                    {"name": "Web PI", "value": f"{metrics['web_pi']:,}".replace(",", ".")},
                    {"name": "App PI", "value": f"{metrics['app_pi']:,}".replace(",", ".")},
                    {"name": "Gesamt PI", "value": f"{metrics['total_pi']:,}".replace(",", ".")},
                    {"name": "Web Visits", "value": f"{metrics['web_visits']:,}".replace(",", ".")},
                    {"name": "App Visits", "value": f"{metrics['app_visits']:,}".replace(",", ".")},
                ],
                "markdown": True
            },
            {
                "activityTitle": "🤖 KI-Analyse",
                "text": ai_summary,
                "markdown": True
            }
        ]
    }
    
    try:
        response = requests.post(TEAMS_WEBHOOK_URL, json=card, timeout=10)
        if response.status_code == 200:
            print("✅ Wochenbericht an Teams gesendet")
        else:
            print(f"⚠️ Teams Fehler: {response.status_code}")
    except Exception as e:
        print(f"⚠️ Teams Fehler: {e}")


def main():
    print("=" * 60)
    print("📊 ÖWA WEEKLY REPORT")
    print("=" * 60)
    
    # Daten abrufen
    print("📥 Hole Wochendaten aus Airtable...")
    data = get_weekly_data()
    
    if not data["success"]:
        print(f"❌ Fehler: {data['error']}")
        return
    
    week_start = data["week_start"]
    week_end = data["week_end"]
    records = data["records"]
    
    print(f"📅 Zeitraum: {week_start.strftime('%d.%m.')} - {week_end.strftime('%d.%m.%Y')}")
    print(f"📊 Datensätze: {len(records)}")
    print()
    
    # Daten aggregieren
    metrics = aggregate_data(records)
    print(f"📈 Web PI: {metrics['web_pi']:,}")
    print(f"📱 App PI: {metrics['app_pi']:,}")
    print(f"📊 Gesamt: {metrics['total_pi']:,}")
    print()
    
    # KI-Zusammenfassung
    print("🤖 Generiere KI-Zusammenfassung...")
    ai_summary = generate_ai_summary(metrics, week_start, week_end)
    print(ai_summary)
    print()
    
    # An Teams senden
    print("📨 Sende an Teams...")
    send_teams_report(metrics, ai_summary, week_start, week_end)
    
    print("=" * 60)
    print("✅ WEEKLY REPORT ABGESCHLOSSEN")
    print("=" * 60)


if __name__ == "__main__":
    main()

