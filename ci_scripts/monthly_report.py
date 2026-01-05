#!/usr/bin/env python3
"""
Monthly Report Script v2.0
===========================
Erstellt einen monatlichen Bericht mit:
- NUR VOL.AT (Vienna ausgeschlossen)
- Getrennte Darstellung: Web vs. App
- MoM-Vergleich (Month-over-Month)
- GPT-generierte Executive Summary
- Teams-Benachrichtigung mit Diagrammen (klickbar/vergrößerbar)

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
IMGBB_API_KEY = os.environ.get("IMGBB_API_KEY", "")

# Chart-Größe
CHART_WIDTH = 1600
CHART_HEIGHT = 800
CHART_SCALE = 2

# Farben - NUR VOL (Vienna ausgeschlossen)
BRAND_COLORS = {
    "VOL Web": "#3B82F6",      # Blau
    "VOL App": "#60A5FA",      # Hellblau (iOS + Android aggregiert)
    "VOL iOS": "#10B981",      # Grün
    "VOL Android": "#F59E0B",  # Orange
}

METRICS = ["Page Impressions", "Visits", "Unique Clients", "Homepage PI"]

# Plattform-Farben für getrennte Darstellung
PLATFORM_COLORS = {
    "Web": "#3B82F6",      # Blau
    "App": "#10B981",      # Grün (iOS + Android aggregiert)
    "iOS": "#10B981",      # Grün
    "Android": "#F59E0B",  # Orange
}

# Plattformen, die als "App" zusammengefasst werden
APP_PLATFORMS = ["iOS", "Android"]


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
    """
    Erstellt ein Monatsvergleichs-Balkendiagramm.
    NUR VOL mit Web/App Trennung.
    """
    if not PLOTLY_AVAILABLE:
        return None
    
    chart_data = []
    
    # NUR VOL
    for key in ["VOL_Web", "VOL_App"]:
        if key in data and metric in data[key]:
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
        title=f"📊 VOL {metric} - Monatsvergleich (MoM)",
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


def create_web_vs_app_chart(data: Dict, metric: str = "Page Impressions") -> Optional[bytes]:
    """
    Erstellt ein Vergleichsdiagramm Web vs. App für VOL.
    """
    if not PLOTLY_AVAILABLE:
        return None
    
    chart_data = []
    
    for platform in ["Web", "App"]:
        key = f"VOL_{platform}"
        if key in data and metric in data[key]:
            m = data[key][metric]
            chart_data.append({
                "plattform": platform,
                "wert": m.get("current_sum", 0),
                "mom_change": m.get("mom_change", 0) or 0
            })
    
    if not chart_data:
        return None
    
    df = pd.DataFrame(chart_data)
    
    # Pie Chart für Anteil
    fig = go.Figure()
    
    fig.add_trace(go.Pie(
        labels=df["plattform"],
        values=df["wert"],
        hole=0.4,
        marker_colors=[PLATFORM_COLORS.get(p, "#666") for p in df["plattform"]],
        textinfo="label+percent+value",
        texttemplate="%{label}<br>%{value:,.0f}<br>(%{percent})"
    ))
    
    fig.update_layout(
        title=f"📊 VOL {metric} - Web vs. App Anteil",
        width=CHART_WIDTH,
        height=CHART_HEIGHT,
        font=dict(size=14),
        title_font_size=20
    )
    
    return fig.to_image(format="png", scale=CHART_SCALE)


def create_daily_trend_chart(data: Dict, metric: str = "Page Impressions") -> Optional[bytes]:
    """
    Erstellt ein Tages-Trend-Liniendiagramm für den ganzen Monat.
    NUR VOL mit Web/App Trennung.
    """
    if not PLOTLY_AVAILABLE:
        return None
    
    chart_data = []
    
    # NUR VOL
    for key in ["VOL_Web", "VOL_App"]:
        if key in data and metric in data[key]:
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
        title=f"📈 VOL {metric} - Monatstrend (Web vs. App)",
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


def upload_to_imgbb(image_bytes: bytes) -> Optional[str]:
    """
    Lädt ein Bild zu imgBB hoch.
    
    Vorteile von imgBB:
    - Kostenlos (32MB pro Bild)
    - Permanente Speicherung (keine Löschung)
    - Einfache API
    """
    if not image_bytes or not IMGBB_API_KEY:
        if not IMGBB_API_KEY:
            print("   ⚠️ IMGBB_API_KEY nicht konfiguriert")
        return None
    
    try:
        response = requests.post(
            "https://api.imgbb.com/1/upload",
            data={
                "key": IMGBB_API_KEY,
                "image": base64.b64encode(image_bytes).decode("utf-8")
            },
            timeout=60
        )
        
        if response.status_code == 200:
            url = response.json()["data"]["url"]
            print(f"   ✅ imgBB Upload: {url}")
            return url
        else:
            print(f"   ⚠️ imgBB Upload fehlgeschlagen: {response.status_code}")
            return None
    except Exception as e:
        print(f"   ⚠️ imgBB Fehler: {e}")
        return None


# =============================================================================
# DATEN-FUNKTIONEN
# =============================================================================

def get_measurements_for_month(year: int, month: int) -> List[Dict]:
    """
    Holt alle Measurements für einen spezifischen Monat.
    NUR VOL-Daten (Vienna ausgeschlossen) und nur Tagesdaten.
    """
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/Measurements"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    
    start, end = get_month_dates(year, month)
    
    records = []
    offset = None
    
    while True:
        params = {
            # NUR VOL + nur Tagesdaten (keine monatlichen)
            "filterByFormula": f"AND(IS_AFTER({{Datum}}, '{(start - timedelta(days=1)).isoformat()}'), IS_BEFORE({{Datum}}, '{(end + timedelta(days=1)).isoformat()}'), {{Brand}} = 'VOL', FIND('_MONTH_', {{Unique Key}}) = 0)",
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
        
        # NEU: iOS und Android werden als "App" aggregiert
        if surface in APP_PLATFORMS:
            surface = "App"
        
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
        
        # NEU: iOS und Android werden als "App" aggregiert
        if surface in APP_PLATFORMS:
            surface = "App"
        
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
    """
    Generiert eine GPT-Zusammenfassung für den Monatsbericht.
    NUR VOL mit Web/App Trennung.
    """
    if not OPENAI_API_KEY:
        return "GPT-Zusammenfassung nicht verfügbar (API Key fehlt)"
    
    # Daten aufbereiten - NUR VOL
    kpi_text = ""
    
    # Gesamt-KPIs (Web + App kombiniert)
    total_kpis = {}
    for metric in METRICS:
        total = 0
        total_prev = 0
        for key in ["VOL_Web", "VOL_App"]:
            if key in data and metric in data[key]:
                total += data[key][metric].get("current_sum", 0)
                total_prev += data[key][metric].get("prev_sum", 0)
        if total > 0:
            mom = ((total - total_prev) / total_prev * 100) if total_prev > 0 else 0
            total_kpis[metric] = {"total": total, "mom": mom}
    
    kpi_text += "\n**VOL GESAMT (Web + App):**\n"
    for metric, vals in total_kpis.items():
        kpi_text += f"  - {metric}: {vals['total']:,} (MoM: {vals['mom']:+.1f}%)\n"
    
    # Getrennt nach Web/App
    for key in ["VOL_Web", "VOL_App"]:
        if key in data:
            kpi_text += f"\n**{key.replace('_', ' ')}:**\n"
            for metric in METRICS:
                if metric in data[key]:
                    m = data[key][metric]
                    mom = f"{m['mom_change']*100:+.1f}%" if m.get('mom_change') is not None else "N/A"
                    kpi_text += f"  - {metric}: {m['current_sum']:,} (MoM: {mom})\n"
    
    # Web vs. App Anteil berechnen
    web_pi = data.get("VOL_Web", {}).get("Page Impressions", {}).get("current_sum", 0)
    app_pi = data.get("VOL_App", {}).get("Page Impressions", {}).get("current_sum", 0)
    total_pi = web_pi + app_pi
    web_share = (web_pi / total_pi * 100) if total_pi > 0 else 0
    app_share = (app_pi / total_pi * 100) if total_pi > 0 else 0
    
    platform_text = f"📱 Web-Anteil: {web_share:.1f}% | App-Anteil: {app_share:.1f}%"
    
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

WICHTIG: Dieser Bericht betrifft NUR VOL.AT. Vienna ist NICHT enthalten.

═══════════════════════════════════════════════════════════════
📅 MONATSBERICHT: {current_month} (nur VOL.AT)
📊 VERGLEICH MIT: {prev_month}
═══════════════════════════════════════════════════════════════

KPI-DATEN (MONATSSUMMEN):
{kpi_text}

PLATTFORM-VERTEILUNG:
{platform_text}

PERFORMANCE-ÜBERSICHT:
{highlight_text}

═══════════════════════════════════════════════════════════════

Erstelle folgende Struktur (EXAKT einhalten):

**📈 HIGHLIGHT DES MONATS**
[1 Satz – wichtigste Erkenntnis für VOL.AT, z.B. stärkste Steigerung oder kritischster Rückgang.]

**📊 WEB vs. APP ANALYSE**
[2–3 Sätze – Vergleiche die Performance von Web vs. App.
Welche Plattform wächst stärker? Gibt es Verschiebungen?]

**📊 MONTH-OVER-MONTH (MoM)**
[2–3 Sätze – Entwicklung der Gesamt-KPIs (Visits, UC, PI).
Formuliere aktiv: "Visits steigen um +3,2%".]

**🧭 KONTEXT & EINORDNUNG**
[1–2 Sätze – saisonale Muster (Sommerloch, Advent, Ferien, News-Lage).]

**✅ GESAMTBEWERTUNG**
[1 Satz – Gesamtentwicklung des Monats für VOL.AT (positiv/stabil/leicht rückläufig/kritisch).]

STILVORGABEN:
- Professionell, prägnant, datengetrieben
- Keine Aufzählung von Rohdaten – nur Erkenntnisse
- Fokus auf: Was bedeutet das für das Management?
- Maximal 220 Wörter
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
                "max_tokens": 700,
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
    """
    Sendet den Monatsbericht an Teams.
    NUR VOL mit Web/App Trennung.
    """
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
    
    # Web/App Anteil berechnen
    web_pi = data.get("VOL_Web", {}).get("Page Impressions", {}).get("current_sum", 0)
    app_pi = data.get("VOL_App", {}).get("Page Impressions", {}).get("current_sum", 0)
    total_pi = web_pi + app_pi
    web_share = (web_pi / total_pi * 100) if total_pi > 0 else 0
    app_share = (app_pi / total_pi * 100) if total_pi > 0 else 0
    
    # Facts - NUR VOL
    facts = [
        {"name": "📅 Berichtsmonat", "value": current_month},
        {"name": "📊 Vergleich mit", "value": prev_month},
        {"name": "📱 Plattform-Verteilung", "value": f"Web: {web_share:.0f}% | App: {app_share:.0f}%"}
    ]
    
    # Gesamt VOL
    total_pi_val = web_pi + app_pi
    web_mom = data.get("VOL_Web", {}).get("Page Impressions", {}).get("mom_change")
    app_mom = data.get("VOL_App", {}).get("Page Impressions", {}).get("mom_change")
    
    facts.append({
        "name": "📊 VOL GESAMT PI",
        "value": f"{total_pi_val:,}"
    })
    
    # Web und App separat
    for key in ["VOL_Web", "VOL_App"]:
        if key in data and "Page Impressions" in data[key]:
            m = data[key]["Page Impressions"]
            mom = f" ({m['mom_change']*100:+.1f}%)" if m.get('mom_change') is not None else ""
            facts.append({
                "name": f"  └─ {key.replace('VOL_', '')} PI",
                "value": f"{m['current_sum']:,}{mom}"
            })
    
    sections = [
        {
            "activityTitle": title,
            "activitySubtitle": "📢 Nur VOL.AT (Vienna ausgeschlossen)",
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
            print("✅ Monatsbericht an Teams gesendet")
        else:
            print(f"⚠️ Teams Fehler: {response.status_code}")
    except Exception as e:
        print(f"⚠️ Teams Fehler: {e}")


# =============================================================================
# MAIN
# =============================================================================

def run_monthly_report(target_year: int = None, target_month: int = None):
    """
    Hauptfunktion für den Monatsbericht.
    NUR VOL.AT mit Web/App Trennung.
    """
    print("=" * 70)
    print("📊 ÖWA MONTHLY REPORT v2.0")
    print("   NUR VOL.AT (Web + App getrennt)")
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
    print(f"📢 Property: NUR VOL.AT (Vienna ausgeschlossen)")
    
    # Daten laden - NUR VOL
    print("\n📥 Lade VOL-Daten aus Airtable...")
    current_records = get_measurements_for_month(year, month)
    prev_records = get_measurements_for_month(prev_year, prev_month)
    print(f"   → {len(current_records)} Records für {current_month_str} (nur VOL)")
    print(f"   → {len(prev_records)} Records für {prev_month_str} (nur VOL)")
    
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
    
    # Web vs. App Anteil
    web_pi = data.get("VOL_Web", {}).get("Page Impressions", {}).get("current_sum", 0)
    app_pi = data.get("VOL_App", {}).get("Page Impressions", {}).get("current_sum", 0)
    total_pi = web_pi + app_pi
    if total_pi > 0:
        print(f"\n   📱 Plattform-Verteilung (PI):")
        print(f"      Web: {web_pi:,} ({web_pi/total_pi*100:.1f}%)")
        print(f"      App: {app_pi:,} ({app_pi/total_pi*100:.1f}%)")
    
    # Diagramme erstellen
    image_urls = {}
    if PLOTLY_AVAILABLE:
        print("\n📊 Erstelle Diagramme...")
        
        try:
            # MoM Vergleich (Web + App)
            chart_bytes = create_monthly_comparison_chart(data, "Page Impressions")
            if chart_bytes:
                url = upload_to_imgbb(chart_bytes)
                if url:
                    image_urls["VOL MoM Vergleich PI"] = url
                    print(f"   → MoM-Vergleich (PI) hochgeladen")
            
            # MoM Vergleich Visits
            visits_chart = create_monthly_comparison_chart(data, "Visits")
            if visits_chart:
                url = upload_to_imgbb(visits_chart)
                if url:
                    image_urls["VOL MoM Vergleich Visits"] = url
                    print(f"   → MoM-Vergleich (Visits) hochgeladen")
            
            # Web vs. App Pie Chart
            pie_chart = create_web_vs_app_chart(data, "Page Impressions")
            if pie_chart:
                url = upload_to_imgbb(pie_chart)
                if url:
                    image_urls["VOL Web vs. App Anteil"] = url
                    print(f"   → Web/App-Anteil hochgeladen")
            
            # Monatstrend (Web vs. App Linien)
            trend_bytes = create_daily_trend_chart(data, "Page Impressions")
            if trend_bytes:
                url = upload_to_imgbb(trend_bytes)
                if url:
                    image_urls["VOL Monatstrend PI (Web vs. App)"] = url
                    print(f"   → Monatstrend hochgeladen")
                    
        except Exception as e:
            print(f"   ⚠️ Diagramm-Fehler: {e}")
    
    # GPT Summary
    print("\n🤖 Generiere KI-Zusammenfassung...")
    summary = generate_monthly_gpt_summary(data, current_month_str, prev_month_str)
    print(f"   → {len(summary)} Zeichen generiert")
    
    # Teams Bericht
    print("\n📤 Sende Monatsbericht an Teams...")
    title = f"📊 ÖWA Monatsbericht VOL.AT - {current_month_str}"
    send_monthly_teams_report(title, summary, data, current_month_str, prev_month_str, image_urls)
    
    print("\n" + "=" * 70)
    print("✅ MONTHLY REPORT v2.0 ABGESCHLOSSEN")
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
