#!/usr/bin/env python3
"""
Monthly Report Script
=====================
Wird von GitLab CI/CD ausgeführt, getriggert durch Airtable Automation.
Generiert einen monatlichen KI-Report und sendet ihn an Teams.
"""

import os
import json
import requests
from datetime import date, datetime, timedelta
import calendar

# =============================================================================
# KONFIGURATION
# =============================================================================
AIRTABLE_API_KEY = os.environ.get("AIRTABLE_API_KEY", "")
AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID", "appTIeod85xnBy7Vn")
TEAMS_WEBHOOK_URL = os.environ.get("TEAMS_WEBHOOK_URL", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

MONTH_NAMES = ["", "Januar", "Februar", "März", "April", "Mai", "Juni",
               "Juli", "August", "September", "Oktober", "November", "Dezember"]


def get_monthly_data() -> dict:
    """Holt Monatsdaten aus Airtable"""
    today = date.today()
    
    # Vormonat berechnen
    if today.month == 1:
        year, month = today.year - 1, 12
    else:
        year, month = today.year, today.month - 1
    
    _, last_day = calendar.monthrange(year, month)
    month_start = date(year, month, 1)
    month_end = date(year, month, last_day)
    month_name = MONTH_NAMES[month]
    
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/Measurements"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    
    params = {
        "filterByFormula": f"AND(IS_AFTER({{Datum}}, '{(month_start - timedelta(days=1)).isoformat()}'), IS_BEFORE({{Datum}}, '{(month_end + timedelta(days=1)).isoformat()}'))"
    }
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        if response.status_code == 200:
            records = response.json().get("records", [])
            return {
                "success": True,
                "records": records,
                "month_start": month_start,
                "month_end": month_end,
                "month_name": month_name,
                "year": year
            }
        else:
            return {"success": False, "error": f"HTTP {response.status_code}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def aggregate_data(records: list, days_in_month: int) -> dict:
    """Aggregiert die Monatsdaten"""
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
    metrics["avg_daily_pi"] = metrics["total_pi"] // days_in_month if days_in_month > 0 else 0
    
    # Anteile berechnen
    if metrics["total_pi"] > 0:
        metrics["web_share"] = round(metrics["web_pi"] / metrics["total_pi"] * 100, 1)
        metrics["app_share"] = round(metrics["app_pi"] / metrics["total_pi"] * 100, 1)
    else:
        metrics["web_share"] = 0
        metrics["app_share"] = 0
    
    return metrics


def generate_ai_summary(metrics: dict, month_name: str, year: int) -> str:
    """Generiert KI-Zusammenfassung mit OpenAI"""
    if not OPENAI_API_KEY:
        return "KI-Zusammenfassung nicht verfügbar (API Key fehlt)"
    
    prompt = f"""Analysiere diese Monats-Daten für VOL.at und erstelle einen Management-Report (max. 200 Wörter, auf Deutsch):

Monat: {month_name} {year}

Metriken:
- Gesamt Page Impressions: {metrics['total_pi']:,}
- Web PI: {metrics['web_pi']:,} ({metrics['web_share']}%)
- App PI: {metrics['app_pi']:,} ({metrics['app_share']}%)
- Ø PI pro Tag: {metrics['avg_daily_pi']:,}
- Gesamt Visits: {metrics['total_visits']:,}

Erstelle einen professionellen Monatsbericht mit:
1. Executive Summary (2-3 Sätze)
2. Performance-Highlight
3. Plattform-Entwicklung (Web vs. App)
4. Strategische Empfehlung"""

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
                    {"role": "system", "content": "Du bist ein erfahrener Digital-Analyst für Russmedia. Erstelle professionelle Monatsberichte auf Deutsch."},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": 500,
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


def send_teams_report(metrics: dict, ai_summary: str, month_name: str, year: int):
    """Sendet den Monatsbericht an Teams"""
    if not TEAMS_WEBHOOK_URL:
        print("⚠️ TEAMS_WEBHOOK_URL nicht konfiguriert")
        return
    
    card = {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "summary": f"ÖWA Monatsbericht {month_name} {year}",
        "themeColor": "17A2B8",
        "sections": [
            {
                "activityTitle": f"📊 ÖWA Monatsbericht",
                "activitySubtitle": f"{month_name} {year}",
                "facts": [
                    {"name": "Gesamt PI", "value": f"{metrics['total_pi']:,}".replace(",", ".")},
                    {"name": "Ø PI/Tag", "value": f"{metrics['avg_daily_pi']:,}".replace(",", ".")},
                    {"name": "Web / App", "value": f"{metrics['web_share']}% / {metrics['app_share']}%"},
                    {"name": "Gesamt Visits", "value": f"{metrics['total_visits']:,}".replace(",", ".")},
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
            print("✅ Monatsbericht an Teams gesendet")
        else:
            print(f"⚠️ Teams Fehler: {response.status_code}")
    except Exception as e:
        print(f"⚠️ Teams Fehler: {e}")


def main():
    print("=" * 60)
    print("📈 ÖWA MONTHLY REPORT")
    print("=" * 60)
    
    # Daten abrufen
    print("📥 Hole Monatsdaten aus Airtable...")
    data = get_monthly_data()
    
    if not data["success"]:
        print(f"❌ Fehler: {data['error']}")
        return
    
    month_name = data["month_name"]
    year = data["year"]
    records = data["records"]
    month_start = data["month_start"]
    month_end = data["month_end"]
    days_in_month = (month_end - month_start).days + 1
    
    print(f"📅 Monat: {month_name} {year}")
    print(f"📊 Datensätze: {len(records)}")
    print()
    
    # Daten aggregieren
    metrics = aggregate_data(records, days_in_month)
    print(f"📈 Gesamt PI: {metrics['total_pi']:,}")
    print(f"📊 Web: {metrics['web_pi']:,} ({metrics['web_share']}%)")
    print(f"📱 App: {metrics['app_pi']:,} ({metrics['app_share']}%)")
    print(f"📆 Ø pro Tag: {metrics['avg_daily_pi']:,}")
    print()
    
    # KI-Zusammenfassung
    print("🤖 Generiere KI-Zusammenfassung...")
    ai_summary = generate_ai_summary(metrics, month_name, year)
    print(ai_summary)
    print()
    
    # An Teams senden
    print("📨 Sende an Teams...")
    send_teams_report(metrics, ai_summary, month_name, year)
    
    print("=" * 60)
    print("✅ MONTHLY REPORT ABGESCHLOSSEN")
    print("=" * 60)


if __name__ == "__main__":
    main()

