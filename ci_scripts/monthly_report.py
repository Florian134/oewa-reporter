#!/usr/bin/env python3
"""
Monthly Report Script v1.0
===========================
Erstellt einen monatlichen Bericht mit:
- Zusammenfassung aller KPIs (PI, Visits, UC, HP-PI)
- Web + App Properties
- MoM-Vergleich (Month-over-Month)
- GPT-generierte Executive Summary
- Teams-Benachrichtigung mit großen Diagrammen (1600x800 PNG)

Wird am 1. jedes Monats ausgeführt (Airtable Automation).

Nutzung:
    python ci_scripts/monthly_report.py
    python ci_scripts/monthly_report.py --month 2025-11  # Spezifischer Monat
"""

import os
import json
import requests
import statistics
import base64
import argparse
from datetime import date, datetime, timedelta
from typing import List, Dict, Optional
from calendar import monthrange

# Plotly für Diagramme
try:
    import plotly.express as px
    import plotly.graph_objects as go
    import pandas as pd
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False
    print("⚠️ Plotly nicht verfügbar - keine Diagramme möglich")

# =============================================================================
# KONFIGURATION
# =============================================================================
AIRTABLE_API_KEY = os.environ.get("AIRTABLE_API_KEY", "")
AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID", "appTIeod85xnBy7Vn")
TEAMS_WEBHOOK_URL = os.environ.get("TEAMS_WEBHOOK_URL", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
IMGUR_CLIENT_ID = os.environ.get("IMGUR_CLIENT_ID", "")

# Chart-Größe
CHART_WIDTH = 1600
CHART_HEIGHT = 800
CHART_SCALE = 2

# Farben
BRAND_COLORS = {
    "VOL Web": "#3B82F6",
    "VOL App": "#60A5FA",
    "Vienna Web": "#8B5CF6",
    "Vienna App": "#A78BFA"
}

METRICS = ["Page Impressions", "Visits", "Unique Clients", "Homepage PI"]


# =============================================================================
# HILFSFUNKTIONEN
# =============================================================================

def get_month_dates(year: int, month: int) -> tuple:
    """Gibt Start- und Enddatum eines Monats zurück."""
    start = date(year, month, 1)
    _, last_day = monthrange(year, month)
    end = date(year, month, last_day)
    return start, end


def get_previous_month(year: int, month: int) -> tuple:
    """Gibt Jahr und Monat des Vormonats zurück."""
    if month == 1:
        return year - 1, 12
    return year, month - 1


# =============================================================================
# DIAGRAMM-FUNKTIONEN
# =============================================================================

def create_monthly_comparison_chart(data: Dict, metric: str = "Page Impressions") -> Optional[bytes]:
    """Erstellt ein Monatsvergleichs-Balkendiagramm."""
    if not PLOTLY_AVAILABLE:
        return None
    
    chart_data = []
    
    for key in data:
        if metric in data[key]:
            m = data[key][metric]
            
            chart_data.append({
                "property": key.replace("_", " "),
                "wert": m.get("current_sum", 0),
                "periode": "Aktueller Monat"
            })
            
            chart_data.append({
                "property": key.replace("_", " "),
                "wert": m.get("prev_sum", 0),
                "periode": "Vormonat"
            })
    
    if not chart_data:
        return None
    
    df = pd.DataFrame(chart_data)
    
    fig = px.bar(
        df,
        x="property",
        y="wert",
        color="periode",
        barmode="group",
        title=f"📊 {metric} - Monatsvergleich (MoM)",
        color_discrete_map={
            "Aktueller Monat": "#3B82F6",
            "Vormonat": "#93C5FD"
        }
    )
    
    fig.update_layout(
        yaxis=dict(tickformat=",", title=""),
        xaxis_title="",
        legend_title="",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        width=CHART_WIDTH,
        height=CHART_HEIGHT,
        font=dict(size=14),
        title_font_size=20
    )
    
    return fig.to_image(format="png", scale=CHART_SCALE)


def create_daily_trend_chart(data: Dict, metric: str = "Page Impressions") -> Optional[bytes]:
    """Erstellt ein Tages-Trend-Liniendiagramm für den ganzen Monat."""
    if not PLOTLY_AVAILABLE:
        return None
    
    chart_data = []
    
    for key in data:
        if metric in data[key]:
            daily = data[key][metric].get("daily", {})
            for datum, wert in daily.items():
                chart_data.append({
                    "datum": datum,
                    "wert": wert,
                    "property": key.replace("_", " ")
                })
    
    if not chart_data:
        return None
    
    df = pd.DataFrame(chart_data)
    df["datum"] = pd.to_datetime(df["datum"])
    df = df.sort_values("datum")
    
    fig = px.line(
        df,
        x="datum",
        y="wert",
        color="property",
        title=f"📈 {metric} - Monatstrend",
        color_discrete_map=BRAND_COLORS,
        markers=True
    )
    
    fig.update_layout(
        yaxis=dict(tickformat=",", title=""),
        xaxis=dict(tickformat="%d.%m.", title=""),
        legend_title="",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        width=CHART_WIDTH,
        height=CHART_HEIGHT,
        font=dict(size=14),
        title_font_size=20
    )
    
    return fig.to_image(format="png", scale=CHART_SCALE)


def upload_to_imgur(image_bytes: bytes) -> Optional[str]:
    """Lädt ein Bild zu Imgur hoch."""
    if not image_bytes or not IMGUR_CLIENT_ID:
        return None
    
    try:
        headers = {"Authorization": f"Client-ID {IMGUR_CLIENT_ID}"}
        data = {"image": base64.b64encode(image_bytes).decode("utf-8")}
        
        response = requests.post(
            "https://api.imgur.com/3/image",
            headers=headers,
            data=data,
            timeout=30
        )
        
        if response.status_code == 200:
            return response.json()["data"]["link"]
        return None
    except:
        return None


# =============================================================================
# DATEN-FUNKTIONEN
# =============================================================================

def get_measurements_for_month(year: int, month: int) -> List[Dict]:
    """Holt alle Measurements für einen spezifischen Monat."""
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/Measurements"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    
    start, end = get_month_dates(year, month)
    
    records = []
    offset = None
    
    while True:
        params = {
            "filterByFormula": f"AND(IS_AFTER({{Datum}}, '{(start - timedelta(days=1)).isoformat()}'), IS_BEFORE({{Datum}}, '{(end + timedelta(days=1)).isoformat()}'))",
            "pageSize": 100
        }
        if offset:
            params["offset"] = offset
            
        response = requests.get(url, headers=headers, params=params, timeout=30)
        if response.status_code != 200:
            break
            
        data = response.json()
        records.extend(data.get("records", []))
        
        offset = data.get("offset")
        if not offset:
            break
    
    return records


def process_monthly_data(current_records: List[Dict], prev_records: List[Dict]) -> Dict:
    """Verarbeitet Records für Monatsvergleich."""
    data = {}
    
    # Aktuelle Monatsdaten
    for record in current_records:
        fields = record.get("fields", {})
        datum_str = fields.get("Datum")
        brand = fields.get("Brand")
        surface = fields.get("Plattform", "Web")
        metric = fields.get("Metrik")
        wert = fields.get("Wert")
        
        if not all([datum_str, brand, metric, wert]):
            continue
        
        key = f"{brand}_{surface}"
        
        if key not in data:
            data[key] = {}
        if metric not in data[key]:
            data[key][metric] = {
                "current_sum": 0,
                "prev_sum": 0,
                "current_days": 0,
                "prev_days": 0,
                "daily": {}
            }
        
        data[key][metric]["current_sum"] += wert
        data[key][metric]["current_days"] += 1
        data[key][metric]["daily"][datum_str] = wert
    
    # Vormonatsdaten
    for record in prev_records:
        fields = record.get("fields", {})
        brand = fields.get("Brand")
        surface = fields.get("Plattform", "Web")
        metric = fields.get("Metrik")
        wert = fields.get("Wert")
        
        if not all([brand, metric, wert]):
            continue
        
        key = f"{brand}_{surface}"
        
        if key in data and metric in data[key]:
            data[key][metric]["prev_sum"] += wert
            data[key][metric]["prev_days"] += 1
    
    # MoM berechnen
    for key in data:
        for metric in data[key]:
            m = data[key][metric]
            if m["prev_sum"] > 0:
                m["mom_change"] = (m["current_sum"] - m["prev_sum"]) / m["prev_sum"]
            else:
                m["mom_change"] = None
            
            m["current_avg"] = m["current_sum"] / max(1, m["current_days"])
            m["prev_avg"] = m["prev_sum"] / max(1, m["prev_days"])
    
    return data


# =============================================================================
# GPT SUMMARY
# =============================================================================

def generate_monthly_gpt_summary(data: Dict, current_month: str, prev_month: str) -> str:
    """Generiert eine GPT-Zusammenfassung für den Monatsbericht."""
    if not OPENAI_API_KEY:
        return "GPT-Zusammenfassung nicht verfügbar (API Key fehlt)"
    
    # Daten aufbereiten
    kpi_text = ""
    for key in ["VOL_Web", "VOL_App", "Vienna_Web", "Vienna_App"]:
        if key in data:
            kpi_text += f"\n**{key.replace('_', ' ')}:**\n"
            for metric in METRICS:
                if metric in data[key]:
                    m = data[key][metric]
                    mom = f"{m['mom_change']*100:+.1f}%" if m.get('mom_change') is not None else "N/A"
                    kpi_text += f"  - {metric}: {m['current_sum']:,} (MoM: {mom})\n"
    
    # Beste/Schlechteste Performance
    changes = []
    for key in data:
        for metric in data[key]:
            m = data[key][metric]
            if m.get("mom_change") is not None:
                changes.append({
                    "name": f"{key.replace('_', ' ')} {metric}",
                    "change": m["mom_change"]
                })
    
    if changes:
        best = max(changes, key=lambda x: x["change"])
        worst = min(changes, key=lambda x: x["change"])
        highlight_text = f"🏆 TOP: {best['name']} ({best['change']*100:+.1f}%)\n📉 LOW: {worst['name']} ({worst['change']*100:+.1f}%)"
    else:
        highlight_text = "Keine Vergleichsdaten verfügbar"
    
    prompt = f"""Du bist ein Senior-Web-Analytics-Experte für österreichische Medienunternehmen.
Erstelle einen klaren, kompakten EXECUTIVE SUMMARY für das Management von Russmedia.

═══════════════════════════════════════════════════════════════
📅 MONATSBERICHT: {current_month}
📊 VERGLEICH MIT: {prev_month}
═══════════════════════════════════════════════════════════════

KPI-DATEN (MONATSSUMMEN):
{kpi_text}

PERFORMANCE-ÜBERSICHT:
{highlight_text}

═══════════════════════════════════════════════════════════════

Erstelle folgende Struktur (EXAKT einhalten):

**📈 HIGHLIGHT DES MONATS**
[1 Satz – wichtigste Erkenntnis, z.B. stärkste Steigerung oder kritischster Rückgang.]

**📊 MONTH-OVER-MONTH (MoM)**
[2–3 Sätze – Entwicklung der KPIs (Visits, UC, PI, HP-PI).
Formuliere aktiv: "Visits steigen um +3,2%". Hebe wesentliche Trends hervor.
Vergleiche Web vs. App Performance.]

**🧭 KONTEXT & EINORDNUNG**
[1–2 Sätze – saisonale Muster (Sommerloch, Advent, Ferien, News-Lage),
Abweichungen aufgrund externer Faktoren.]

**✅ GESAMTBEWERTUNG**
[1 Satz – Gesamtentwicklung des Monats (positiv/stabil/leicht rückläufig/kritisch).]

STILVORGABEN:
- Professionell, prägnant, datengetrieben
- Keine Aufzählung von Rohdaten – nur Erkenntnisse
- Fokus auf: Was bedeutet das für das Management?
- Maximal 200 Wörter
"""

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
                "max_tokens": 600,
                "temperature": 0.7
            },
            timeout=60
        )
        
        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"]
        return f"GPT-Fehler: {response.status_code}"
    except Exception as e:
        return f"GPT-Fehler: {str(e)}"


# =============================================================================
# TEAMS NOTIFICATION
# =============================================================================

def send_monthly_teams_report(title: str, summary: str, data: Dict, current_month: str, prev_month: str, image_urls: Dict = None):
    """Sendet den Monatsbericht an Teams."""
    if not TEAMS_WEBHOOK_URL:
        print("⚠️ TEAMS_WEBHOOK_URL nicht konfiguriert")
        return
    
    # Farbe basierend auf Performance
    total_positive = sum(1 for k in data for m in data[k] if data[k][m].get("mom_change", 0) > 0)
    total_negative = sum(1 for k in data for m in data[k] if data[k][m].get("mom_change", 0) < 0)
    
    if total_positive > total_negative:
        color = "28A745"
    elif total_negative > total_positive:
        color = "FFC107"
    else:
        color = "17A2B8"
    
    # Facts
    facts = [
        {"name": "📅 Berichtsmonat", "value": current_month},
        {"name": "📊 Vergleich mit", "value": prev_month}
    ]
    
    for key in ["VOL_Web", "VOL_App", "Vienna_Web", "Vienna_App"]:
        if key in data and "Page Impressions" in data[key]:
            m = data[key]["Page Impressions"]
            mom = f" ({m['mom_change']*100:+.1f}%)" if m.get('mom_change') is not None else ""
            facts.append({
                "name": f"📊 {key.replace('_', ' ')} PI",
                "value": f"{m['current_sum']:,}{mom}"
            })
    
    sections = [
        {
            "activityTitle": title,
            "facts": facts,
            "markdown": True
        },
        {
            "text": f"**🤖 KI-Analyse:**\n\n{summary}",
            "markdown": True
        }
    ]
    
    if image_urls:
        for chart_name, url in image_urls.items():
            if url:
                sections.append({
                    "title": f"📊 {chart_name}",
                    "text": f"[🔍 Klicken zum Vergrößern]({url})",
                    "images": [{"image": url, "title": chart_name}]
                })
    
    card = {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "summary": title,
        "themeColor": color,
        "sections": sections,
        "potentialAction": [{
            "@type": "OpenUri",
            "name": "📈 Dashboard öffnen",
            "targets": [{"os": "default", "uri": "https://oewa-reporter-ucgucmpvryylvvkhefxyeq.streamlit.app"}]
        }]
    }
    
    try:
        response = requests.post(TEAMS_WEBHOOK_URL, json=card, timeout=30)
        if response.status_code == 200:
            print("✅ Monatsbericht an Teams gesendet")
        else:
            print(f"⚠️ Teams Fehler: {response.status_code}")
    except Exception as e:
        print(f"⚠️ Teams Fehler: {e}")


# =============================================================================
# MAIN
# =============================================================================

def run_monthly_report(target_year: int = None, target_month: int = None):
    """Hauptfunktion für den Monatsbericht."""
    print("=" * 70)
    print("📊 ÖWA MONTHLY REPORT v1.0")
    print("   Web + App | PI + Visits + UC + HP-PI")
    print("=" * 70)
    
    if not AIRTABLE_API_KEY:
        print("❌ AIRTABLE_API_KEY nicht gesetzt!")
        return
    
    # Monat bestimmen (Standard: Vormonat)
    today = date.today()
    if target_year and target_month:
        year, month = target_year, target_month
    else:
        # Am 1. des Monats: Bericht für Vormonat
        year, month = get_previous_month(today.year, today.month)
    
    prev_year, prev_month = get_previous_month(year, month)
    
    month_names = ["", "Januar", "Februar", "März", "April", "Mai", "Juni", 
                   "Juli", "August", "September", "Oktober", "November", "Dezember"]
    
    current_month_str = f"{month_names[month]} {year}"
    prev_month_str = f"{month_names[prev_month]} {prev_year}"
    
    print(f"\n📅 Berichtsmonat: {current_month_str}")
    print(f"📊 Vergleich mit: {prev_month_str}")
    
    # Daten laden
    print("\n📥 Lade Daten aus Airtable...")
    current_records = get_measurements_for_month(year, month)
    prev_records = get_measurements_for_month(prev_year, prev_month)
    print(f"   → {len(current_records)} Records für {current_month_str}")
    print(f"   → {len(prev_records)} Records für {prev_month_str}")
    
    if not current_records:
        print("❌ Keine Daten für aktuellen Monat gefunden!")
        return
    
    # Daten verarbeiten
    print("\n📈 Verarbeite Daten...")
    data = process_monthly_data(current_records, prev_records)
    
    # Statistiken ausgeben
    for key in data:
        print(f"\n   {key}:")
        for metric in data[key]:
            m = data[key][metric]
            mom = f"{m['mom_change']*100:+.1f}%" if m.get('mom_change') is not None else "N/A"
            print(f"      {metric}: {m['current_sum']:,} (MoM: {mom})")
    
    # Diagramme erstellen
    image_urls = {}
    if PLOTLY_AVAILABLE:
        print("\n📊 Erstelle Diagramme...")
        
        try:
            # MoM Vergleich
            chart_bytes = create_monthly_comparison_chart(data, "Page Impressions")
            if chart_bytes:
                url = upload_to_imgur(chart_bytes)
                if url:
                    image_urls["MoM Vergleich PI"] = url
                    print(f"   → MoM-Vergleich hochgeladen")
            
            # Monatstrend
            trend_bytes = create_daily_trend_chart(data, "Page Impressions")
            if trend_bytes:
                url = upload_to_imgur(trend_bytes)
                if url:
                    image_urls["Monatstrend PI"] = url
                    print(f"   → Monatstrend hochgeladen")
                    
        except Exception as e:
            print(f"   ⚠️ Diagramm-Fehler: {e}")
    
    # GPT Summary
    print("\n🤖 Generiere KI-Zusammenfassung...")
    summary = generate_monthly_gpt_summary(data, current_month_str, prev_month_str)
    print(f"   → {len(summary)} Zeichen generiert")
    
    # Teams Bericht
    print("\n📤 Sende Monatsbericht an Teams...")
    title = f"📊 ÖWA Monatsbericht - {current_month_str}"
    send_monthly_teams_report(title, summary, data, current_month_str, prev_month_str, image_urls)
    
    print("\n" + "=" * 70)
    print("✅ MONTHLY REPORT v1.0 ABGESCHLOSSEN")
    print("=" * 70)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ÖWA Monthly Report")
    parser.add_argument("--month", type=str, help="Monat im Format YYYY-MM (z.B. 2025-11)")
    args = parser.parse_args()
    
    if args.month:
        try:
            year, month = map(int, args.month.split("-"))
            run_monthly_report(year, month)
        except:
            print("❌ Ungültiges Datumsformat. Nutze YYYY-MM (z.B. 2025-11)")
    else:
        run_monthly_report()
