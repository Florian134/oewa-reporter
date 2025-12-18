#!/usr/bin/env python3
"""
Weekly Report Script v2.0
==========================
Erstellt einen wöchentlichen Bericht mit:
- Zusammenfassung aller KPIs (PI, Visits, UC, HP-PI)
- Web + App Properties
- WoW-Vergleich (Week-over-Week)
- GPT-generierte Executive Summary
- Teams-Benachrichtigung mit großen Diagrammen (1600x800 PNG)

Nutzung:
    python ci_scripts/weekly_report.py
"""

import os
import json
import requests
import statistics
import base64
import io
from datetime import date, datetime, timedelta
from typing import List, Dict, Optional, Tuple

# Plotly für Diagramme (optional, mit Fallback)
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

# Chart-Größe (ERHÖHT für bessere Lesbarkeit in Teams)
CHART_WIDTH = 1600
CHART_HEIGHT = 800
CHART_SCALE = 2  # Retina-Qualität

# Daten-Verzögerung (Tage) - INFOnline API liefert erst nach ~2 Tagen finale Daten
REPORT_DELAY_DAYS = 2

# Farben
BRAND_COLORS = {
    "VOL Web": "#3B82F6",      # Blau
    "VOL App": "#60A5FA",      # Hellblau
    "Vienna Web": "#8B5CF6",   # Lila
    "Vienna App": "#A78BFA"    # Helllila
}

# Metriken-Konfiguration
METRICS = ["Page Impressions", "Visits", "Unique Clients", "Homepage PI"]


# =============================================================================
# DIAGRAMM-FUNKTIONEN (Größere PNGs)
# =============================================================================

def create_kpi_comparison_chart(data: Dict, metric: str = "Page Impressions") -> Optional[bytes]:
    """
    Erstellt ein KPI-Vergleichs-Balkendiagramm (Aktuell vs. Vorwoche) als großes PNG.
    """
    if not PLOTLY_AVAILABLE:
        return None
    
    chart_data = []
    
    for brand in ["VOL", "Vienna"]:
        for surface in ["Web", "App"]:
            key = f"{brand}_{surface}"
            if key in data and metric in data[key]:
                metric_data = data[key][metric]
                
                # Aktuelle Woche
                chart_data.append({
                    "property": f"{brand} {surface}",
                    "wert": metric_data.get("current_sum", 0),
                    "periode": "Aktuelle Woche"
                })
                
                # Vorwoche
                chart_data.append({
                    "property": f"{brand} {surface}",
                    "wert": metric_data.get("prev_sum", 0),
                    "periode": "Vorwoche"
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
        title=f"📊 {metric} - Wochenvergleich",
        color_discrete_map={
            "Aktuelle Woche": "#3B82F6",
            "Vorwoche": "#93C5FD"
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
    
    img_bytes = fig.to_image(format="png", scale=CHART_SCALE)
    return img_bytes


def create_trend_chart(data: Dict, metric: str = "Page Impressions") -> Optional[bytes]:
    """
    Erstellt ein 7-Tage-Trend-Liniendiagramm als großes PNG.
    """
    if not PLOTLY_AVAILABLE:
        return None
    
    chart_data = []
    
    for brand in ["VOL", "Vienna"]:
        for surface in ["Web", "App"]:
            key = f"{brand}_{surface}"
            if key in data and metric in data[key]:
                daily = data[key][metric].get("daily", {})
                for datum, wert in daily.items():
                    chart_data.append({
                        "datum": datum,
                        "wert": wert,
                        "property": f"{brand} {surface}"
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
        title=f"📈 {metric} - 7-Tage-Trend",
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
    
    img_bytes = fig.to_image(format="png", scale=CHART_SCALE)
    return img_bytes


def upload_to_imgur(image_bytes: bytes) -> Optional[str]:
    """Lädt ein Bild anonym zu Imgur hoch."""
    if not image_bytes or not IMGUR_CLIENT_ID:
        if not IMGUR_CLIENT_ID:
            print("⚠️ IMGUR_CLIENT_ID nicht konfiguriert - Chart-Upload übersprungen")
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
            result = response.json()
            return result["data"]["link"]
        else:
            print(f"⚠️ Imgur Upload fehlgeschlagen: {response.status_code}")
            return None
    except Exception as e:
        print(f"⚠️ Imgur Upload Fehler: {e}")
        return None


# =============================================================================
# DATEN-FUNKTIONEN
# =============================================================================

def get_measurements(days: int = 14) -> List[Dict]:
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
            print(f"⚠️ Airtable Fehler: {response.status_code}")
            break
            
        data = response.json()
        records.extend(data.get("records", []))
        
        offset = data.get("offset")
        if not offset:
            break
    
    return records


def process_data(records: List[Dict], week_start: date, prev_week_start: date, week_end: date = None) -> Dict:
    """
    Verarbeitet Airtable-Records in strukturierte Daten für den Bericht.
    
    Args:
        week_start: Beginn der aktuellen Woche
        prev_week_start: Beginn der Vorwoche
        week_end: Ende der aktuellen Woche (optional, für Delay-Handling)
    
    Returns:
        Dict mit Struktur: {brand_surface: {metric: {current_sum, prev_sum, daily, wow_change}}}
    """
    data = {}
    prev_week_end = week_start - timedelta(days=1)
    
    for record in records:
        fields = record.get("fields", {})
        datum_str = fields.get("Datum")
        brand = fields.get("Brand")
        surface = fields.get("Plattform", "Web")
        metric = fields.get("Metrik")
        wert = fields.get("Wert")
        
        if not all([datum_str, brand, metric, wert]):
            continue
        
        try:
            datum = date.fromisoformat(datum_str)
        except:
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
        
        # Aktuelle Woche (mit optionalem Enddatum)
        if datum >= week_start and (week_end is None or datum <= week_end):
            data[key][metric]["current_sum"] += wert
            data[key][metric]["current_days"] += 1
            data[key][metric]["daily"][datum_str] = wert
        # Vorwoche
        elif datum >= prev_week_start and datum <= prev_week_end:
            data[key][metric]["prev_sum"] += wert
            data[key][metric]["prev_days"] += 1
    
    # WoW-Änderungen berechnen
    for key in data:
        for metric in data[key]:
            m = data[key][metric]
            if m["prev_sum"] > 0:
                m["wow_change"] = (m["current_sum"] - m["prev_sum"]) / m["prev_sum"]
            else:
                m["wow_change"] = None
            
            # Durchschnitte
            m["current_avg"] = m["current_sum"] / max(1, m["current_days"])
            m["prev_avg"] = m["prev_sum"] / max(1, m["prev_days"])
    
    return data


# =============================================================================
# GPT SUMMARY
# =============================================================================

def generate_gpt_summary(data: Dict, period: str) -> str:
    """Generiert eine GPT-Zusammenfassung gemäß der neuen Vorlage."""
    if not OPENAI_API_KEY:
        return "GPT-Zusammenfassung nicht verfügbar (API Key fehlt)"
    
    # Daten für den Prompt aufbereiten
    kpi_text = ""
    for key in ["VOL_Web", "VOL_App", "Vienna_Web", "Vienna_App"]:
        if key in data:
            kpi_text += f"\n**{key.replace('_', ' ')}:**\n"
            for metric in METRICS:
                if metric in data[key]:
                    m = data[key][metric]
                    wow = f"{m['wow_change']*100:+.1f}%" if m.get('wow_change') is not None else "N/A"
                    kpi_text += f"  - {metric}: {m['current_sum']:,} (WoW: {wow})\n"
    
    # Beste/Schlechteste Performance identifizieren
    changes = []
    for key in data:
        for metric in data[key]:
            m = data[key][metric]
            if m.get("wow_change") is not None:
                changes.append({
                    "name": f"{key.replace('_', ' ')} {metric}",
                    "change": m["wow_change"]
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
📅 BERICHTSZEITRAUM: {period}
═══════════════════════════════════════════════════════════════

KPI-DATEN:
{kpi_text}

PERFORMANCE-ÜBERSICHT:
{highlight_text}

═══════════════════════════════════════════════════════════════

Erstelle folgende Struktur (EXAKT einhalten):

**📈 HIGHLIGHT DER WOCHE**
[1 Satz – wichtigste Erkenntnis, z.B. stärkste Steigerung oder kritischster Rückgang.]

**📊 WEEK-OVER-WEEK (WoW)**
[2–3 Sätze – Entwicklung der KPIs (Visits, UC, PI, HP-PI).
Formuliere aktiv: "Visits steigen um +3,2%". Hebe wesentliche Trends hervor.
Vergleiche Web vs. App Performance.]

**🧭 KONTEXT & EINORDNUNG**
[1–2 Sätze – saisonale Muster (Wochenende, Feiertage, News-Lage),
Abweichungen aufgrund externer Faktoren. Dezember = Adventzeit.]

**✅ GESAMTBEWERTUNG**
[1 Satz – Gesamtentwicklung der Woche (positiv/stabil/leicht rückläufig/kritisch).]

STILVORGABEN:
- Professionell, prägnant, datengetrieben
- Keine Aufzählung von Rohdaten – nur Erkenntnisse
- Fokus auf: Was bedeutet das für das Management?
- Maximal 180 Wörter
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
                "max_tokens": 500,
                "temperature": 0.7
            },
            timeout=60
        )
        
        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"]
        else:
            return f"GPT-Fehler: {response.status_code}"
    except Exception as e:
        return f"GPT-Fehler: {str(e)}"


# =============================================================================
# TEAMS NOTIFICATION
# =============================================================================

def send_teams_report(title: str, summary: str, data: Dict, period: str, image_urls: Dict[str, str] = None):
    """Sendet den Wochenbericht an Teams mit Diagrammen."""
    if not TEAMS_WEBHOOK_URL:
        print("⚠️ TEAMS_WEBHOOK_URL nicht konfiguriert")
        return
    
    # Farbe basierend auf Gesamtperformance
    total_positive = 0
    total_negative = 0
    for key in data:
        for metric in data[key]:
            m = data[key][metric]
            if m.get("wow_change") is not None:
                if m["wow_change"] > 0:
                    total_positive += 1
                else:
                    total_negative += 1
    
    if total_positive > total_negative:
        color = "28A745"  # Grün
    elif total_negative > total_positive:
        color = "FFC107"  # Gelb
    else:
        color = "17A2B8"  # Blau (neutral)
    
    # Facts aufbauen
    facts = [{"name": "📅 Zeitraum", "value": period}]
    
    for key in ["VOL_Web", "VOL_App", "Vienna_Web", "Vienna_App"]:
        if key in data and "Page Impressions" in data[key]:
            m = data[key]["Page Impressions"]
            wow = f" ({m['wow_change']*100:+.1f}%)" if m.get('wow_change') is not None else ""
            facts.append({
                "name": f"📊 {key.replace('_', ' ')} PI",
                "value": f"{m['current_sum']:,}{wow}"
            })
    
    # Sections
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
    
    # Bilder hinzufügen (mit Link zum Vergrößern)
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
            print("✅ Teams Bericht gesendet")
        else:
            print(f"⚠️ Teams Fehler: {response.status_code}")
    except Exception as e:
        print(f"⚠️ Teams Fehler: {e}")


# =============================================================================
# MAIN
# =============================================================================

def run_weekly_report():
    """Hauptfunktion für den Wochenbericht"""
    print("=" * 70)
    print("📊 ÖWA WEEKLY REPORT v2.0")
    print("   Web + App | PI + Visits + UC + HP-PI")
    print("=" * 70)
    
    if not AIRTABLE_API_KEY:
        print("❌ AIRTABLE_API_KEY nicht gesetzt!")
        return
    
    # Zeiträume definieren (mit Delay für finale API-Daten)
    today = date.today()
    data_end = today - timedelta(days=REPORT_DELAY_DAYS)  # Letzte finale Daten
    week_start = data_end - timedelta(days=6)  # 7 Tage inklusive data_end
    prev_week_start = week_start - timedelta(days=7)
    period = f"{week_start.strftime('%d.%m.')} - {data_end.strftime('%d.%m.%Y')} (KW {data_end.isocalendar()[1]})"
    
    # Daten laden
    print("\n📥 Lade Daten aus Airtable...")
    records = get_measurements(days=14)
    print(f"   → {len(records)} Datensätze geladen")
    
    if not records:
        print("❌ Keine Daten gefunden!")
        return
    
    # Daten verarbeiten
    print("\n📈 Verarbeite Daten...")
    data = process_data(records, week_start, prev_week_start, week_end=data_end)
    
    # Statistiken ausgeben
    for key in data:
        print(f"\n   {key}:")
        for metric in data[key]:
            m = data[key][metric]
            wow = f"{m['wow_change']*100:+.1f}%" if m.get('wow_change') is not None else "N/A"
            print(f"      {metric}: {m['current_sum']:,} (WoW: {wow})")
    
    # Diagramme erstellen und hochladen
    image_urls = {}
    if PLOTLY_AVAILABLE:
        print("\n📊 Erstelle Diagramme (1600x800)...")
        
        try:
            # PI Vergleich
            chart_bytes = create_kpi_comparison_chart(data, "Page Impressions")
            if chart_bytes:
                print("   → PI-Vergleich erstellt")
                url = upload_to_imgur(chart_bytes)
                if url:
                    image_urls["Page Impressions Vergleich"] = url
                    print(f"   → Hochgeladen: {url[:50]}...")
            
            # Trend Chart
            trend_bytes = create_trend_chart(data, "Page Impressions")
            if trend_bytes:
                print("   → Trend-Diagramm erstellt")
                url = upload_to_imgur(trend_bytes)
                if url:
                    image_urls["7-Tage-Trend"] = url
                    print(f"   → Hochgeladen: {url[:50]}...")
                    
        except Exception as e:
            print(f"   ⚠️ Diagramm-Erstellung fehlgeschlagen: {e}")
    
    # GPT Summary
    print("\n🤖 Generiere KI-Zusammenfassung...")
    summary = generate_gpt_summary(data, period)
    print(f"   → {len(summary)} Zeichen generiert")
    
    # Teams Bericht
    print("\n📤 Sende Teams-Bericht...")
    title = f"📊 ÖWA Wochenbericht - KW {today.isocalendar()[1]}"
    send_teams_report(title, summary, data, period, image_urls)
    
    print("\n" + "=" * 70)
    print("✅ WEEKLY REPORT v2.0 ABGESCHLOSSEN")
    print("=" * 70)


if __name__ == "__main__":
    run_weekly_report()
