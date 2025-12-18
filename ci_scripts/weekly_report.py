#!/usr/bin/env python3
"""
Weekly Report Script v3.0
==========================
Erstellt einen wöchentlichen Bericht mit:
- NUR VOL.AT (Vienna ausgeschlossen gemäß Anforderung)
- 6-Wochen-Vergleich (aktuelle Woche vs. letzte 6 Wochen)
- Prozentuelle Veränderungen für alle KPIs
- Streamlit-Diagramme als klickbare Bilder
- GPT-generierte Executive Summary
- Teams-Benachrichtigung

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

# Farben - NUR VOL (Vienna ausgeschlossen)
BRAND_COLORS = {
    "VOL Web": "#3B82F6",      # Blau
    "VOL App": "#60A5FA",      # Hellblau
}

# Metriken-Konfiguration
METRICS = ["Page Impressions", "Visits", "Unique Clients", "Homepage PI"]

# Anzahl der Vergleichswochen
COMPARISON_WEEKS = 6


# =============================================================================
# DIAGRAMM-FUNKTIONEN (Größere PNGs)
# =============================================================================

def create_kpi_comparison_chart(data: Dict, metric: str = "Page Impressions") -> Optional[bytes]:
    """
    Erstellt ein KPI-Vergleichs-Balkendiagramm (Aktuell vs. 6-Wochen-Durchschnitt) als großes PNG.
    NUR VOL (Vienna ausgeschlossen).
    """
    if not PLOTLY_AVAILABLE:
        return None
    
    chart_data = []
    
    # NUR VOL - Vienna ausgeschlossen
    for surface in ["Web", "App"]:
        key = f"VOL_{surface}"
        if key in data and metric in data[key]:
            metric_data = data[key][metric]
            
            # Aktuelle Woche
            chart_data.append({
                "property": f"VOL {surface}",
                "wert": metric_data.get("current_sum", 0),
                "periode": "Aktuelle Woche"
            })
            
            # 6-Wochen-Durchschnitt
            chart_data.append({
                "property": f"VOL {surface}",
                "wert": metric_data.get("avg_6_weeks", 0),
                "periode": "Ø 6 Wochen"
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
        title=f"📊 {metric} - Aktuelle Woche vs. 6-Wochen-Ø (nur VOL)",
        color_discrete_map={
            "Aktuelle Woche": "#3B82F6",
            "Ø 6 Wochen": "#93C5FD"
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
    NUR VOL (Vienna ausgeschlossen).
    """
    if not PLOTLY_AVAILABLE:
        return None
    
    chart_data = []
    
    # NUR VOL - Vienna ausgeschlossen
    for surface in ["Web", "App"]:
        key = f"VOL_{surface}"
        if key in data and metric in data[key]:
            daily = data[key][metric].get("daily", {})
            for datum, wert in daily.items():
                chart_data.append({
                    "datum": datum,
                    "wert": wert,
                    "property": f"VOL {surface}"
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
        title=f"📈 {metric} - 7-Tage-Trend (nur VOL)",
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


def create_6week_comparison_chart(weekly_data: Dict, metric: str = "Page Impressions") -> Optional[bytes]:
    """
    Erstellt ein Balkendiagramm mit 7 Wochen (aktuelle + 6 Vorwochen).
    Zeigt die prozentuelle Veränderung.
    """
    if not PLOTLY_AVAILABLE:
        return None
    
    chart_data = []
    
    # Daten für Web und App
    for surface in ["Web", "App"]:
        key = f"VOL_{surface}"
        if key in weekly_data:
            weeks_data = weekly_data[key].get(metric, {}).get("weekly_values", [])
            for week_info in weeks_data:
                chart_data.append({
                    "woche": week_info["label"],
                    "wert": week_info["value"],
                    "property": f"VOL {surface}",
                    "is_current": week_info.get("is_current", False)
                })
    
    if not chart_data:
        return None
    
    df = pd.DataFrame(chart_data)
    
    fig = go.Figure()
    
    for surface in ["Web", "App"]:
        surface_data = df[df["property"] == f"VOL {surface}"]
        if not surface_data.empty:
            colors = [BRAND_COLORS.get(f"VOL {surface}", "#3B82F6") if row["is_current"] 
                     else "#93C5FD" for _, row in surface_data.iterrows()]
            
            fig.add_trace(go.Bar(
                x=surface_data["woche"],
                y=surface_data["wert"],
                name=f"VOL {surface}",
                marker_color=colors,
                text=surface_data["wert"].apply(lambda x: f"{x:,.0f}".replace(",", ".")),
                textposition="outside"
            ))
    
    fig.update_layout(
        title=f"📊 {metric} - 7-Wochen-Übersicht (nur VOL)",
        yaxis=dict(tickformat=",", title=""),
        xaxis_title="",
        barmode="group",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        width=CHART_WIDTH,
        height=CHART_HEIGHT,
        font=dict(size=14),
        title_font_size=20
    )
    
    return fig.to_image(format="png", scale=CHART_SCALE)


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

def get_measurements(days: int = 56) -> List[Dict]:
    """
    Holt Measurements der letzten X Tage aus Airtable.
    Standard: 56 Tage (8 Wochen) für 6-Wochen-Vergleich.
    
    FILTER: Nur VOL-Daten (Vienna ausgeschlossen)
    """
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/Measurements"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    
    cutoff_date = (date.today() - timedelta(days=days)).isoformat()
    
    records = []
    offset = None
    
    while True:
        params = {
            # NUR VOL-Daten laden + Tagesdaten (keine monatlichen)
            "filterByFormula": f"AND(IS_AFTER({{Datum}}, '{cutoff_date}'), {{Brand}} = 'VOL', FIND('_MONTH_', {{Unique Key}}) = 0)",
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


def process_data(records: List[Dict], week_start: date, week_end: date = None) -> Dict:
    """
    Verarbeitet Airtable-Records in strukturierte Daten für den Bericht.
    
    ERWEITERT: Berechnet 6-Wochen-Vergleich statt nur Vorwoche.
    NUR VOL-Daten (Vienna wird bereits beim Laden gefiltert).
    
    Args:
        week_start: Beginn der aktuellen Woche
        week_end: Ende der aktuellen Woche (für Delay-Handling)
    
    Returns:
        Dict mit Struktur: {brand_surface: {metric: {current_sum, avg_6_weeks, weekly_values, pct_change}}}
    """
    # Definiere alle 7 Wochen (aktuelle + 6 Vorwochen)
    weeks = []
    for i in range(COMPARISON_WEEKS + 1):  # 0 = aktuelle Woche, 1-6 = Vorwochen
        w_start = week_start - timedelta(weeks=i)
        w_end = w_start + timedelta(days=6)
        if i == 0 and week_end:
            w_end = week_end  # Aktuelle Woche mit Delay-Enddatum
        weeks.append({
            "start": w_start,
            "end": w_end,
            "label": f"KW{w_start.isocalendar()[1]}",
            "is_current": i == 0
        })
    
    # Datenstruktur initialisieren
    data = {}
    
    # Records nach Datum zuordnen
    for record in records:
        fields = record.get("fields", {})
        datum_str = fields.get("Datum")
        brand = fields.get("Brand")
        surface = fields.get("Plattform", "Web")
        metric = fields.get("Metrik")
        wert = fields.get("Wert")
        
        if not all([datum_str, brand, metric, wert]):
            continue
        
        # NUR VOL (wird bereits beim Laden gefiltert, aber sicherheitshalber)
        if brand != "VOL":
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
                "current_days": 0,
                "daily": {},
                "weekly_values": [{"label": w["label"], "value": 0, "days": 0, "is_current": w["is_current"]} for w in weeks],
                "weeks_with_data": 0
            }
        
        # Welche Woche?
        for idx, week in enumerate(weeks):
            if week["start"] <= datum <= week["end"]:
                data[key][metric]["weekly_values"][idx]["value"] += wert
                data[key][metric]["weekly_values"][idx]["days"] += 1
                
                # Aktuelle Woche separat tracken
                if idx == 0:
                    data[key][metric]["current_sum"] += wert
                    data[key][metric]["current_days"] += 1
                    data[key][metric]["daily"][datum_str] = wert
                break
    
    # Berechnungen: 6-Wochen-Durchschnitt und prozentuelle Änderungen
    for key in data:
        for metric in data[key]:
            m = data[key][metric]
            
            # 6-Wochen-Durchschnitt (ohne aktuelle Woche)
            prev_weeks = m["weekly_values"][1:]  # Index 1-6
            weeks_with_data = [w for w in prev_weeks if w["value"] > 0]
            
            if weeks_with_data:
                m["avg_6_weeks"] = sum(w["value"] for w in weeks_with_data) / len(weeks_with_data)
                m["weeks_with_data"] = len(weeks_with_data)
                
                # Prozentuelle Änderung vs. 6-Wochen-Durchschnitt
                if m["avg_6_weeks"] > 0:
                    m["pct_change"] = (m["current_sum"] - m["avg_6_weeks"]) / m["avg_6_weeks"]
                else:
                    m["pct_change"] = None
            else:
                m["avg_6_weeks"] = 0
                m["pct_change"] = None
            
            # Durchschnitt pro Tag (aktuelle Woche)
            m["current_avg"] = m["current_sum"] / max(1, m["current_days"])
    
    return data


# =============================================================================
# GPT SUMMARY
# =============================================================================

def generate_gpt_summary(data: Dict, period: str) -> str:
    """
    Generiert eine GPT-Zusammenfassung.
    NUR VOL-Daten mit 6-Wochen-Vergleich.
    """
    if not OPENAI_API_KEY:
        return "GPT-Zusammenfassung nicht verfügbar (API Key fehlt)"
    
    # Daten für den Prompt aufbereiten - NUR VOL
    kpi_text = ""
    for key in ["VOL_Web", "VOL_App"]:
        if key in data:
            kpi_text += f"\n**{key.replace('_', ' ')}:**\n"
            for metric in METRICS:
                if metric in data[key]:
                    m = data[key][metric]
                    pct = f"{m['pct_change']*100:+.1f}%" if m.get('pct_change') is not None else "N/A"
                    avg = m.get('avg_6_weeks', 0)
                    kpi_text += f"  - {metric}: {m['current_sum']:,} (vs. 6-Wochen-Ø {avg:,.0f}: {pct})\n"
    
    # Beste/Schlechteste Performance identifizieren
    changes = []
    for key in data:
        for metric in data[key]:
            m = data[key][metric]
            if m.get("pct_change") is not None:
                changes.append({
                    "name": f"{key.replace('_', ' ')} {metric}",
                    "change": m["pct_change"]
                })
    
    if changes:
        best = max(changes, key=lambda x: x["change"])
        worst = min(changes, key=lambda x: x["change"])
        highlight_text = f"🏆 TOP: {best['name']} ({best['change']*100:+.1f}% vs. 6-Wochen-Ø)\n📉 LOW: {worst['name']} ({worst['change']*100:+.1f}% vs. 6-Wochen-Ø)"
    else:
        highlight_text = "Keine Vergleichsdaten verfügbar"
    
    prompt = f"""Du bist ein Senior-Web-Analytics-Experte für österreichische Medienunternehmen.
Erstelle einen klaren, kompakten EXECUTIVE SUMMARY für das Management von Russmedia.

WICHTIG: Dieser Bericht betrifft NUR VOL.AT (Web + App). Vienna ist NICHT enthalten.

═══════════════════════════════════════════════════════════════
📅 BERICHTSZEITRAUM: {period}
📊 VERGLEICH: Aktuelle Woche vs. Durchschnitt der letzten 6 Wochen
═══════════════════════════════════════════════════════════════

KPI-DATEN (nur VOL.AT):
{kpi_text}

PERFORMANCE-ÜBERSICHT:
{highlight_text}

═══════════════════════════════════════════════════════════════

Erstelle folgende Struktur (EXAKT einhalten):

**📈 HIGHLIGHT DER WOCHE**
[1 Satz – wichtigste Erkenntnis, z.B. stärkste Steigerung oder kritischster Rückgang vs. 6-Wochen-Ø.]

**📊 6-WOCHEN-VERGLEICH**
[2–3 Sätze – Entwicklung der KPIs im Vergleich zum 6-Wochen-Durchschnitt.
Formuliere aktiv: "Visits liegen +3,2% über dem 6-Wochen-Durchschnitt".
Vergleiche Web vs. App Performance bei VOL.]

**🧭 KONTEXT & EINORDNUNG**
[1–2 Sätze – saisonale Muster (Wochenende, Feiertage, News-Lage),
Abweichungen aufgrund externer Faktoren.]

**✅ GESAMTBEWERTUNG**
[1 Satz – Gesamtentwicklung der Woche für VOL.AT (positiv/stabil/leicht rückläufig/kritisch).]

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
    """
    Sendet den Wochenbericht an Teams mit Diagrammen.
    NUR VOL-Daten mit 6-Wochen-Vergleich.
    """
    if not TEAMS_WEBHOOK_URL:
        print("⚠️ TEAMS_WEBHOOK_URL nicht konfiguriert")
        return
    
    # Farbe basierend auf Gesamtperformance (vs. 6-Wochen-Ø)
    total_positive = 0
    total_negative = 0
    for key in data:
        for metric in data[key]:
            m = data[key][metric]
            if m.get("pct_change") is not None:
                if m["pct_change"] > 0:
                    total_positive += 1
                else:
                    total_negative += 1
    
    if total_positive > total_negative:
        color = "28A745"  # Grün
    elif total_negative > total_positive:
        color = "FFC107"  # Gelb
    else:
        color = "17A2B8"  # Blau (neutral)
    
    # Facts aufbauen - NUR VOL
    facts = [
        {"name": "📅 Zeitraum", "value": period},
        {"name": "📊 Vergleich", "value": f"vs. Ø der letzten {COMPARISON_WEEKS} Wochen"}
    ]
    
    for key in ["VOL_Web", "VOL_App"]:
        if key in data:
            for metric in ["Page Impressions", "Visits"]:
                if metric in data[key]:
                    m = data[key][metric]
                    pct = f" ({m['pct_change']*100:+.1f}%)" if m.get('pct_change') is not None else ""
                    facts.append({
                        "name": f"📊 {key.replace('_', ' ')} {metric}",
                        "value": f"{m['current_sum']:,}{pct}"
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
                    "text": f"[🔍 **Klicken zum Vergrößern**]({url})",
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
    """
    Hauptfunktion für den Wochenbericht.
    NUR VOL.AT mit 6-Wochen-Vergleich.
    """
    print("=" * 70)
    print("📊 ÖWA WEEKLY REPORT v3.0")
    print("   NUR VOL.AT (Web + App)")
    print(f"   Vergleich: Aktuelle Woche vs. {COMPARISON_WEEKS}-Wochen-Durchschnitt")
    print("=" * 70)
    
    if not AIRTABLE_API_KEY:
        print("❌ AIRTABLE_API_KEY nicht gesetzt!")
        return
    
    # Zeiträume definieren (mit Delay für finale API-Daten)
    today = date.today()
    data_end = today - timedelta(days=REPORT_DELAY_DAYS)  # Letzte finale Daten
    week_start = data_end - timedelta(days=6)  # 7 Tage inklusive data_end
    period = f"{week_start.strftime('%d.%m.')} - {data_end.strftime('%d.%m.%Y')} (KW {data_end.isocalendar()[1]})"
    
    print(f"\n📅 Berichtszeitraum: {period}")
    print(f"📊 Vergleich mit: Durchschnitt der letzten {COMPARISON_WEEKS} Wochen")
    
    # Daten laden (56 Tage = 8 Wochen für 6-Wochen-Vergleich)
    print("\n📥 Lade VOL-Daten aus Airtable...")
    records = get_measurements(days=56)
    print(f"   → {len(records)} Datensätze geladen (nur VOL)")
    
    if not records:
        print("❌ Keine Daten gefunden!")
        return
    
    # Daten verarbeiten
    print("\n📈 Verarbeite Daten...")
    data = process_data(records, week_start, week_end=data_end)
    
    # Statistiken ausgeben
    for key in data:
        print(f"\n   {key}:")
        for metric in data[key]:
            m = data[key][metric]
            pct = f"{m['pct_change']*100:+.1f}%" if m.get('pct_change') is not None else "N/A"
            avg = m.get('avg_6_weeks', 0)
            print(f"      {metric}: {m['current_sum']:,} (vs. 6-Wochen-Ø {avg:,.0f}: {pct})")
    
    # Diagramme erstellen und hochladen
    image_urls = {}
    if PLOTLY_AVAILABLE:
        print("\n📊 Erstelle Diagramme (1600x800)...")
        
        try:
            # PI Vergleich (Aktuell vs. 6-Wochen-Ø)
            chart_bytes = create_kpi_comparison_chart(data, "Page Impressions")
            if chart_bytes:
                print("   → PI-Vergleich (vs. 6-Wochen-Ø) erstellt")
                url = upload_to_imgur(chart_bytes)
                if url:
                    image_urls["VOL Page Impressions vs. 6-Wochen-Ø"] = url
                    print(f"   → Hochgeladen: {url[:50]}...")
            
            # Visits Vergleich
            visits_chart = create_kpi_comparison_chart(data, "Visits")
            if visits_chart:
                print("   → Visits-Vergleich erstellt")
                url = upload_to_imgur(visits_chart)
                if url:
                    image_urls["VOL Visits vs. 6-Wochen-Ø"] = url
                    print(f"   → Hochgeladen: {url[:50]}...")
            
            # 7-Tage Trend Chart
            trend_bytes = create_trend_chart(data, "Page Impressions")
            if trend_bytes:
                print("   → 7-Tage-Trend erstellt")
                url = upload_to_imgur(trend_bytes)
                if url:
                    image_urls["VOL 7-Tage-Trend PI"] = url
                    print(f"   → Hochgeladen: {url[:50]}...")
            
            # 7-Wochen-Übersicht
            week_chart = create_6week_comparison_chart(data, "Page Impressions")
            if week_chart:
                print("   → 7-Wochen-Übersicht erstellt")
                url = upload_to_imgur(week_chart)
                if url:
                    image_urls["VOL 7-Wochen-Übersicht PI"] = url
                    print(f"   → Hochgeladen: {url[:50]}...")
                    
        except Exception as e:
            print(f"   ⚠️ Diagramm-Erstellung fehlgeschlagen: {e}")
    
    # GPT Summary
    print("\n🤖 Generiere KI-Zusammenfassung...")
    summary = generate_gpt_summary(data, period)
    print(f"   → {len(summary)} Zeichen generiert")
    
    # Teams Bericht
    print("\n📤 Sende Teams-Bericht...")
    title = f"📊 ÖWA Wochenbericht VOL.AT - KW {data_end.isocalendar()[1]}"
    send_teams_report(title, summary, data, period, image_urls)
    
    print("\n" + "=" * 70)
    print("✅ WEEKLY REPORT v3.0 ABGESCHLOSSEN")
    print("=" * 70)


if __name__ == "__main__":
    run_weekly_report()
