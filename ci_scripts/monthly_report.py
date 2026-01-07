#!/usr/bin/env python3
"""
Monthly Report Script v4.2
===========================
Erstellt einen umfassenden monatlichen Bericht mit:
- NUR VOL.AT (Vienna ausgeschlossen)
- Getrennte Darstellung: Web vs. App
- MoM-Vergleich (Month-over-Month)
- YoY-Vergleich (Year-over-Year)
- 12-Monats-Trend
- GPT-generierte Executive Summary (BULLETPOINT-FORMAT)
- Teams-Benachrichtigung mit PROMINENTER SUMMARY + Diagrammen

v4.2 ÄNDERUNGEN:
- Textstil: kürzer, prägnanter, datenorientiert (Bulletpoints)
- Gesamtmetriken prominent im oberen Bereich
- Robusterer imgBB Upload (Retry + Fallback)
- Alle Metriken vollständig dargestellt
- ERWEITERTE DIAGRAMME (analog Weekly Report):
  * MoM-Vergleich PI + Visits
  * YoY-Vergleich PI
  * 12-Monats-Trend PI + Visits
  * Multi-Metrik MoM-Übersicht
  * Plattform-Anteil (Web vs. App)

Nutzung:
    python ci_scripts/monthly_report.py
    python ci_scripts/monthly_report.py --month 2025-12
"""

import os
import sys
import json
import requests
import statistics
import base64
import argparse
import time
from datetime import date, datetime, timedelta
from typing import List, Dict, Optional, Tuple
from calendar import monthrange

# Importiere monthly_data_utils für intelligente Monatsdaten-Abfragen
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from monthly_data_utils import (
        get_monthly_data,
        get_12_month_trend,
        get_yoy_comparison,
        get_previous_month as util_get_previous_month
    )
    MONTHLY_UTILS_AVAILABLE = True
except ImportError:
    MONTHLY_UTILS_AVAILABLE = False
    print("⚠️ monthly_data_utils nicht verfügbar - Fallback auf Legacy-Modus")

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
AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID", "")  # Muss in CI/CD Variables gesetzt sein
TEAMS_WEBHOOK_URL = os.environ.get("TEAMS_WEBHOOK_URL", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
IMGBB_API_KEY = os.environ.get("IMGBB_API_KEY", "")

# Chart-Größe (optimiert für Teams)
CHART_WIDTH = 1200  # Reduziert für schnelleren Upload
CHART_HEIGHT = 600
CHART_SCALE = 2  # Retina-Qualität

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

# Metriken ohne YoY (wegen Methodenwechsel)
YOY_EXCLUDED_METRICS = ["Unique Clients"]


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


def format_number(n: float) -> str:
    """Formatiert große Zahlen lesbar (z.B. 35.5M, 12.3M)."""
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    elif n >= 1_000:
        return f"{n/1_000:.0f}K"
    return f"{n:,.0f}"


def format_change(change: Optional[float], prefix: str = "") -> str:
    """Formatiert prozentuale Änderung."""
    if change is None:
        return "N/A"
    return f"{prefix}{change*100:+.2f}%"


# =============================================================================
# ROBUSTER IMAGE UPLOAD (mit Retry)
# =============================================================================

def upload_to_imgbb(image_bytes: bytes, max_retries: int = 3) -> Optional[str]:
    """
    Lädt ein Bild zu imgBB hoch mit Retry-Mechanismus.
    
    Args:
        image_bytes: PNG-Bilddaten
        max_retries: Maximale Anzahl Versuche
    
    Returns:
        URL des hochgeladenen Bildes oder None
    """
    if not image_bytes or not IMGBB_API_KEY:
        if not IMGBB_API_KEY:
            print("   ⚠️ IMGBB_API_KEY nicht konfiguriert")
        return None
    
    for attempt in range(max_retries):
        try:
            print(f"   📤 Upload-Versuch {attempt + 1}/{max_retries} ({len(image_bytes)} bytes)...")
            
            response = requests.post(
                "https://api.imgbb.com/1/upload",
                data={
                    "key": IMGBB_API_KEY,
                    "image": base64.b64encode(image_bytes).decode("utf-8"),
                    "expiration": 0  # Permanent
                },
                timeout=90  # Erhöht für große Bilder
            )
            
            if response.status_code == 200:
                url = response.json()["data"]["url"]
                print(f"   ✅ Upload erfolgreich: {url[:50]}...")
                return url
            else:
                print(f"   ⚠️ HTTP {response.status_code}")
                try:
                    error_info = response.json()
                    if "error" in error_info:
                        print(f"      Fehler: {error_info['error']}")
                except:
                    pass
                
                # Exponential Backoff
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    print(f"   ⏳ Warte {wait_time}s vor erneutem Versuch...")
                    time.sleep(wait_time)
                    
        except requests.exceptions.Timeout:
            print(f"   ⚠️ Timeout bei Versuch {attempt + 1}")
            if attempt < max_retries - 1:
                time.sleep(2)
        except Exception as e:
            print(f"   ⚠️ Fehler: {type(e).__name__}: {e}")
            if attempt < max_retries - 1:
                time.sleep(2)
    
    print("   ❌ Upload nach allen Versuchen fehlgeschlagen")
    return None


# =============================================================================
# DIAGRAMM-FUNKTIONEN
# =============================================================================

def create_summary_chart(data: Dict) -> Optional[bytes]:
    """
    Erstellt ein Gesamt-Übersichts-Balkendiagramm (Web vs. App).
    Zeigt PI und Visits nebeneinander.
    """
    if not PLOTLY_AVAILABLE:
        return None
    
    chart_data = []
    
    for metric in ["Page Impressions", "Visits"]:
        for platform in ["Web", "App"]:
            key = f"VOL_{platform}"
            if key in data and metric in data[key]:
                m = data[key][metric]
                chart_data.append({
                    "metrik": metric,
                    "plattform": platform,
                    "wert": m.get("current_sum", 0),
                    "mom": m.get("mom_change", 0) or 0
                })
    
    if not chart_data:
        return None
    
    df = pd.DataFrame(chart_data)
    
    fig = px.bar(
        df,
        x="metrik",
        y="wert",
        color="plattform",
        barmode="group",
        title="📊 VOL Monatssummary - Web vs. App",
        color_discrete_map=PLATFORM_COLORS,
        text=df["wert"].apply(lambda x: format_number(x))
    )
    
    fig.update_layout(
        yaxis=dict(tickformat=",", title=""),
        xaxis_title="",
        legend_title="",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        width=CHART_WIDTH,
        height=CHART_HEIGHT,
        font=dict(size=14),
        title_font_size=18
    )
    
    fig.update_traces(textposition="outside")
    
    return fig.to_image(format="png", scale=CHART_SCALE)


def create_mom_comparison_chart(data: Dict, metric: str = "Page Impressions", include_ios_android: bool = True) -> Optional[bytes]:
    """
    Erstellt ein MoM-Vergleichs-Balkendiagramm.
    Inkl. iOS/Android wenn include_ios_android=True.
    """
    if not PLOTLY_AVAILABLE:
        return None
    
    chart_data = []
    
    # Basis: Web und App (aggregiert)
    platforms = ["VOL_Web", "VOL_App"]
    
    # Optional: iOS und Android separat
    if include_ios_android:
        platforms.extend(["VOL_iOS", "VOL_Android"])
    
    for key in platforms:
        if key in data and metric in data[key]:
            m = data[key][metric]
            
            # Schönere Labels
            label = key.replace("VOL_", "").replace("_", " ")
            if key == "VOL_App":
                label = "App (Gesamt)"
            
            chart_data.append({
                "property": label,
                "wert": m.get("current_sum", 0),
                "periode": "Aktuell"
            })
            
            chart_data.append({
                "property": label,
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
        title=f"📊 {metric} - MoM Vergleich (Web, App, iOS, Android)",
        color_discrete_map={
            "Aktuell": "#3B82F6",
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
        title_font_size=18
    )
    
    return fig.to_image(format="png", scale=CHART_SCALE)


def create_12_month_trend_chart(trend_data: List[Dict], metric: str = "Page Impressions", 
                                 trend_data_separate: List[Dict] = None) -> Optional[bytes]:
    """
    Erstellt ein 12-Monats-Trend-Liniendiagramm.
    Optional mit iOS/Android wenn trend_data_separate übergeben wird.
    """
    if not PLOTLY_AVAILABLE or not trend_data:
        return None
    
    chart_data = []
    
    # Basis: Web und App (aggregiert)
    for entry in trend_data:
        month_str = entry["month_str"]
        data = entry["data"]
        
        for platform in ["Web", "App"]:
            key = f"VOL_{platform}"
            if key in data and metric in data[key]:
                label = "App (Gesamt)" if platform == "App" else platform
                chart_data.append({
                    "monat": month_str,
                    "wert": data[key][metric],
                    "plattform": label
                })
    
    # Optional: iOS und Android separat
    if trend_data_separate:
        for entry in trend_data_separate:
            month_str = entry["month_str"]
            data = entry["data"]
            
            for platform in ["iOS", "Android"]:
                key = f"VOL_{platform}"
                if key in data and metric in data[key]:
                    chart_data.append({
                        "monat": month_str,
                        "wert": data[key][metric],
                        "plattform": platform
                    })
    
    if not chart_data:
        return None
    
    df = pd.DataFrame(chart_data)
    
    # Erweiterte Farbpalette
    color_map = {
        "Web": "#3B82F6",        # Blau
        "App (Gesamt)": "#60A5FA", # Hellblau
        "iOS": "#10B981",        # Grün
        "Android": "#F59E0B",    # Orange
    }
    
    fig = px.line(
        df,
        x="monat",
        y="wert",
        color="plattform",
        title=f"📈 {metric} - 12-Monats-Trend (inkl. iOS/Android)",
        color_discrete_map=color_map,
        markers=True
    )
    
    fig.update_layout(
        yaxis=dict(tickformat=",", title=""),
        xaxis=dict(title="", tickangle=-45),
        legend_title="",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        width=CHART_WIDTH,
        height=CHART_HEIGHT,
        font=dict(size=14),
        title_font_size=18
    )
    
    return fig.to_image(format="png", scale=CHART_SCALE)


def create_platform_pie_chart(data: Dict, metric: str = "Page Impressions") -> Optional[bytes]:
    """
    Erstellt ein Pie Chart für Web vs. App Anteil.
    """
    if not PLOTLY_AVAILABLE:
        return None
    
    values = []
    labels = []
    
    for platform in ["Web", "App"]:
        key = f"VOL_{platform}"
        if key in data and metric in data[key]:
            m = data[key][metric]
            val = m.get("current_sum", 0)
            if val > 0:
                values.append(val)
                labels.append(platform)
    
    if not values:
        return None
    
    fig = go.Figure(data=[go.Pie(
        labels=labels,
        values=values,
        hole=0.4,
        marker_colors=[PLATFORM_COLORS.get(l, "#666") for l in labels],
        textinfo="label+percent",
        texttemplate="%{label}<br>%{percent:.1%}"
    )])
    
    fig.update_layout(
        title=f"📊 {metric} - Plattform-Anteil",
        width=CHART_WIDTH,
        height=CHART_HEIGHT,
        font=dict(size=14),
        title_font_size=18
    )
    
    return fig.to_image(format="png", scale=CHART_SCALE)


def create_app_split_pie_chart(data: Dict, metric: str = "Page Impressions") -> Optional[bytes]:
    """
    Erstellt ein Pie Chart für iOS vs. Android Anteil innerhalb der App.
    """
    if not PLOTLY_AVAILABLE:
        return None
    
    values = []
    labels = []
    colors = []
    
    platform_config = [
        ("iOS", "VOL_iOS", "#10B981"),       # Grün
        ("Android", "VOL_Android", "#F59E0B") # Orange
    ]
    
    for label, key, color in platform_config:
        if key in data and metric in data[key]:
            m = data[key][metric]
            val = m.get("current_sum", 0)
            if val > 0:
                values.append(val)
                labels.append(label)
                colors.append(color)
    
    if not values:
        return None
    
    fig = go.Figure(data=[go.Pie(
        labels=labels,
        values=values,
        hole=0.4,
        marker_colors=colors,
        textinfo="label+percent",
        texttemplate="%{label}<br>%{percent:.1%}<br>%{value:,.0f}"
    )])
    
    fig.update_layout(
        title=f"📱 App-Aufschlüsselung: iOS vs. Android ({metric})",
        width=CHART_WIDTH,
        height=CHART_HEIGHT,
        font=dict(size=14),
        title_font_size=18
    )
    
    return fig.to_image(format="png", scale=CHART_SCALE)


def create_yoy_comparison_chart(current_data: Dict, yoy_data: Dict, metric: str = "Page Impressions") -> Optional[bytes]:
    """
    Erstellt ein YoY-Vergleichs-Balkendiagramm (Aktuell vs. Vorjahr).
    Analog zum Weekly Report KPI-Vergleich.
    """
    if not PLOTLY_AVAILABLE:
        return None
    
    chart_data = []
    
    current_year = yoy_data.get("current", {}).get("year", 2025)
    prev_year = yoy_data.get("previous_year", {}).get("year", 2024)
    prev_year_data = yoy_data.get("previous_year", {}).get("data", {})
    
    for platform in ["Web", "App"]:
        key = f"VOL_{platform}"
        
        # Aktuelles Jahr
        current_val = current_data.get(key, {}).get(metric, {}).get("current_sum", 0)
        if current_val > 0:
            chart_data.append({
                "property": f"VOL {platform}",
                "wert": current_val,
                "periode": f"{current_year}"
            })
        
        # Vorjahr
        prev_val = prev_year_data.get(key, {}).get(metric, 0)
        if prev_val > 0:
            chart_data.append({
                "property": f"VOL {platform}",
                "wert": prev_val,
                "periode": f"{prev_year}"
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
        title=f"📊 {metric} - YoY Vergleich (Jahr-über-Jahr)",
        color_discrete_map={
            f"{current_year}": "#3B82F6",
            f"{prev_year}": "#93C5FD"
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
        title_font_size=18
    )
    
    return fig.to_image(format="png", scale=CHART_SCALE)


def create_daily_trend_chart(daily_data: Dict, metric: str = "Page Impressions", month_str: str = "") -> Optional[bytes]:
    """
    Erstellt ein Tages-Trend-Liniendiagramm für den gesamten Monat.
    Analog zum Weekly Report Trend-Chart.
    """
    if not PLOTLY_AVAILABLE:
        return None
    
    chart_data = []
    
    for platform in ["Web", "App"]:
        key = f"VOL_{platform}"
        if key in daily_data and metric in daily_data[key]:
            daily = daily_data[key][metric].get("daily", {})
            for datum, wert in daily.items():
                chart_data.append({
                    "datum": datum,
                    "wert": wert,
                    "property": f"VOL {platform}"
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
        title=f"📈 {metric} - Tagestrend {month_str}",
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
        title_font_size=18
    )
    
    return fig.to_image(format="png", scale=CHART_SCALE)


def create_multi_metric_comparison_chart(data: Dict) -> Optional[bytes]:
    """
    Erstellt ein Vergleichsdiagramm für alle Metriken (PI, Visits).
    Zeigt MoM-Änderungen für Web und App.
    """
    if not PLOTLY_AVAILABLE:
        return None
    
    chart_data = []
    
    for metric in ["Page Impressions", "Visits"]:
        for platform in ["Web", "App"]:
            key = f"VOL_{platform}"
            if key in data and metric in data[key]:
                m = data[key][metric]
                mom_change = m.get("mom_change", 0) or 0
                chart_data.append({
                    "metrik": metric.replace("Page Impressions", "PI"),
                    "plattform": f"VOL {platform}",
                    "mom_change": mom_change * 100,  # In Prozent
                    "farbe": "positiv" if mom_change >= 0 else "negativ"
                })
    
    if not chart_data:
        return None
    
    df = pd.DataFrame(chart_data)
    
    fig = px.bar(
        df,
        x="metrik",
        y="mom_change",
        color="plattform",
        barmode="group",
        title="📊 MoM-Änderungen nach Metrik (%)",
        color_discrete_map={
            "VOL Web": "#3B82F6",
            "VOL App": "#10B981"
        },
        text=df["mom_change"].apply(lambda x: f"{x:+.1f}%")
    )
    
    # Nulllinie hinzufügen
    fig.add_hline(y=0, line_dash="dash", line_color="gray")
    
    fig.update_layout(
        yaxis=dict(title="MoM-Änderung (%)"),
        xaxis_title="",
        legend_title="",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        width=CHART_WIDTH,
        height=CHART_HEIGHT,
        font=dict(size=14),
        title_font_size=18
    )
    
    fig.update_traces(textposition="outside")
    
    return fig.to_image(format="png", scale=CHART_SCALE)


# =============================================================================
# GPT SUMMARY (BULLETPOINT-FORMAT)
# =============================================================================

def generate_bulletpoint_summary(data: Dict, current_month: str, prev_month: str, 
                                  yoy_data: Dict, trend_data: List[Dict]) -> str:
    """
    Generiert eine KOMPAKTE GPT-Zusammenfassung im BULLETPOINT-Format.
    Kurz, prägnant, datenorientiert.
    """
    if not OPENAI_API_KEY:
        return "• GPT-Zusammenfassung nicht verfügbar (API Key fehlt)"
    
    # Gesamt-KPIs berechnen
    total_pi = 0
    total_visits = 0
    for key in ["VOL_Web", "VOL_App"]:
        if key in data:
            total_pi += data[key].get("Page Impressions", {}).get("current_sum", 0)
            total_visits += data[key].get("Visits", {}).get("current_sum", 0)
    
    # MoM-Änderungen
    web_pi_mom = data.get("VOL_Web", {}).get("Page Impressions", {}).get("mom_change")
    app_pi_mom = data.get("VOL_App", {}).get("Page Impressions", {}).get("mom_change")
    
    # YoY-Änderungen
    yoy_changes = yoy_data.get("yoy_changes", {})
    web_pi_yoy = yoy_changes.get("VOL_Web", {}).get("Page Impressions")
    app_pi_yoy = yoy_changes.get("VOL_App", {}).get("Page Impressions")
    
    # Web vs. App Anteil
    web_pi = data.get("VOL_Web", {}).get("Page Impressions", {}).get("current_sum", 0)
    app_pi = data.get("VOL_App", {}).get("Page Impressions", {}).get("current_sum", 0)
    web_share = (web_pi / (web_pi + app_pi) * 100) if (web_pi + app_pi) > 0 else 0
    
    # iOS/Android Daten (NEU)
    ios_pi = data.get("VOL_iOS", {}).get("Page Impressions", {}).get("current_sum", 0)
    android_pi = data.get("VOL_Android", {}).get("Page Impressions", {}).get("current_sum", 0)
    ios_pi_mom = data.get("VOL_iOS", {}).get("Page Impressions", {}).get("mom_change")
    android_pi_mom = data.get("VOL_Android", {}).get("Page Impressions", {}).get("mom_change")
    ios_share = (ios_pi / app_pi * 100) if app_pi > 0 else 0
    android_share = (android_pi / app_pi * 100) if app_pi > 0 else 0
    
    # Daten für Prompt aufbereiten
    kpi_summary = f"""
GESAMT:
• PI: {format_number(total_pi)} 
• Visits: {format_number(total_visits)}
• Web-Anteil: {web_share:.0f}%

WEB:
• PI: {format_number(web_pi)} (MoM: {format_change(web_pi_mom)} | YoY: {format_change(web_pi_yoy)})

APP (GESAMT):
• PI: {format_number(app_pi)} (MoM: {format_change(app_pi_mom)} | YoY: {format_change(app_pi_yoy)})

APP-AUFSCHLÜSSELUNG:
• iOS: {format_number(ios_pi)} ({ios_share:.0f}%) (MoM: {format_change(ios_pi_mom)})
• Android: {format_number(android_pi)} ({android_share:.0f}%) (MoM: {format_change(android_pi_mom)})
"""

    prompt = f"""Du bist ein Web-Analytics-Experte. Erstelle eine ULTRAKOMPAKTE Analyse im BULLETPOINT-Format.

═══════════════════════════════════════
📅 MONAT: {current_month} (nur VOL.AT)
═══════════════════════════════════════

{kpi_summary}

═══════════════════════════════════════

WICHTIG:
- Professioneller, eloquenter Stil für Management-Ebene
- Bei Key-Metriken: übersichtliche Bulletpoints mit gut durchdachter Kurzinterpretation
- Interpretationen basieren auf sorgfältiger Analyse der Daten
- KEINE Unique Clients YoY erwähnen (Methodenwechsel Juli 2025)
- MAX 200 WÖRTER GESAMT

FORMAT (EXAKT einhalten):

📈 **HIGHLIGHT DES MONATS**
[2-3 Sätze zur wichtigsten Erkenntnis mit konkreten Zahlen]

📊 **MoM-ENTWICKLUNG (Vormonat)**
• Web: [Trend + Interpretation]
• App (Gesamt): [Trend + Interpretation]

📱 **APP-PLATTFORM-ANALYSE (iOS vs. Android)**
• iOS: [Trend + Anteil + Interpretation]
• Android: [Trend + Anteil + Interpretation]

📈 **12-MONATS-TREND**
[1-2 Sätze zur langfristigen Entwicklung]

🧭 **KONTEXT & EINORDNUNG**
[1-2 Sätze zu saisonalen Faktoren, News-Lage, Besonderheiten]

✅ **GESAMTBEWERTUNG**
[1 prägnanter Satz: positiv/stabil/leicht rückläufig/kritisch + Begründung]
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
                "max_tokens": 400,
                "temperature": 0.5  # Weniger kreativ, mehr fokussiert
            },
            timeout=60
        )
        
        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"]
        return f"• GPT-Fehler: {response.status_code}"
    except Exception as e:
        return f"• GPT-Fehler: {str(e)}"


# =============================================================================
# TEAMS NOTIFICATION (v4.0 - PROMINENTE SUMMARY)
# =============================================================================

def send_monthly_teams_report_v4(title: str, summary: str, data: Dict, 
                                  current_month: str, prev_month: str,
                                  yoy_data: Dict, image_urls: Dict = None):
    """
    Sendet den Monatsbericht an Teams mit PROMINENTER SUMMARY.
    
    v4.0 Format:
    1. GESAMTSUMMARY ganz oben
    2. Plattform-Detail
    3. KI-Analyse (Bulletpoints)
    4. Diagramme
    """
    if not TEAMS_WEBHOOK_URL:
        print("⚠️ TEAMS_WEBHOOK_URL nicht konfiguriert")
        return
    
    # === GESAMT-METRIKEN BERECHNEN ===
    total_pi = 0
    total_visits = 0
    total_pi_prev = 0
    total_visits_prev = 0
    
    for key in ["VOL_Web", "VOL_App"]:
        if key in data:
            total_pi += data[key].get("Page Impressions", {}).get("current_sum", 0)
            total_visits += data[key].get("Visits", {}).get("current_sum", 0)
            total_pi_prev += data[key].get("Page Impressions", {}).get("prev_sum", 0)
            total_visits_prev += data[key].get("Visits", {}).get("prev_sum", 0)
    
    # Gesamt MoM berechnen
    total_pi_mom = ((total_pi - total_pi_prev) / total_pi_prev) if total_pi_prev > 0 else None
    total_visits_mom = ((total_visits - total_visits_prev) / total_visits_prev) if total_visits_prev > 0 else None
    
    # YoY-Daten
    yoy_changes = yoy_data.get("yoy_changes", {})
    
    # Web/App Split
    web_pi = data.get("VOL_Web", {}).get("Page Impressions", {}).get("current_sum", 0)
    app_pi = data.get("VOL_App", {}).get("Page Impressions", {}).get("current_sum", 0)
    web_share = (web_pi / total_pi * 100) if total_pi > 0 else 0
    app_share = (app_pi / total_pi * 100) if total_pi > 0 else 0
    
    # iOS/Android Split (NEU)
    ios_pi = data.get("VOL_iOS", {}).get("Page Impressions", {}).get("current_sum", 0)
    android_pi = data.get("VOL_Android", {}).get("Page Impressions", {}).get("current_sum", 0)
    ios_share = (ios_pi / app_pi * 100) if app_pi > 0 else 0
    android_share = (android_pi / app_pi * 100) if app_pi > 0 else 0
    
    # Farbe basierend auf Performance
    if total_pi_mom and total_pi_mom > 0:
        color = "28A745"  # Grün
    elif total_pi_mom and total_pi_mom < -0.05:
        color = "DC3545"  # Rot
    else:
        color = "17A2B8"  # Blau (neutral)
    
    # === SECTION 1: METADATEN + GESAMTSUMMARY (prominent) ===
    
    # YoY für Gesamt berechnen
    yoy_web_pi = yoy_changes.get("VOL_Web", {}).get("Page Impressions")
    yoy_app_pi = yoy_changes.get("VOL_App", {}).get("Page Impressions")
    yoy_ios_pi = yoy_changes.get("VOL_iOS", {}).get("Page Impressions")
    yoy_android_pi = yoy_changes.get("VOL_Android", {}).get("Page Impressions")
    
    summary_facts = [
        # Metadaten
        {"name": "📅 Berichtsmonat", "value": current_month},
        {"name": "📊 MoM-Vergleich", "value": prev_month},
        {"name": "📅 YoY-Vergleich", "value": f"{current_month.split()[0]} {int(current_month.split()[1]) - 1}"},
        {"name": "═══════════════", "value": "═══════════════"},
        # Gesamt-Performance
        {"name": "📊 **GESAMT PI**", "value": f"**{total_pi:,}** ({format_change(total_pi_mom, 'MoM ')})"},
        {"name": "📊 **GESAMT Visits**", "value": f"**{total_visits:,}** ({format_change(total_visits_mom, 'MoM ')})"},
        {"name": "📱 **Plattform-Split**", "value": f"Web {web_share:.0f}% | App {app_share:.0f}%"},
        {"name": "═══════════════", "value": "═══════════════"},
        # Plattform-Detail
        {"name": "📊 VOL Web PI", "value": f"{web_pi:,} (MoM: {format_change(data.get('VOL_Web', {}).get('Page Impressions', {}).get('mom_change'))} | YoY: {format_change(yoy_web_pi)})"},
        {"name": "📊 VOL App PI", "value": f"{app_pi:,} (MoM: {format_change(data.get('VOL_App', {}).get('Page Impressions', {}).get('mom_change'))} | YoY: {format_change(yoy_app_pi)})"},
        {"name": "═══════════════", "value": "═══════════════"},
        # iOS/Android Detail (NEU)
        {"name": "📱 **APP-AUFSCHLÜSSELUNG**", "value": f"iOS {ios_share:.0f}% | Android {android_share:.0f}%"},
        {"name": "📱 VOL iOS PI", "value": f"{ios_pi:,} (MoM: {format_change(data.get('VOL_iOS', {}).get('Page Impressions', {}).get('mom_change'))} | YoY: {format_change(yoy_ios_pi)})"},
        {"name": "📱 VOL Android PI", "value": f"{android_pi:,} (MoM: {format_change(data.get('VOL_Android', {}).get('Page Impressions', {}).get('mom_change'))} | YoY: {format_change(yoy_android_pi)})"},
    ]
    
    # === SECTION 2: PLATTFORM-DETAIL ===
    detail_text = "**📊 PLATTFORM-DETAIL**\n\n"
    
    for platform, key in [("🌐 VOL Web", "VOL_Web"), ("📱 VOL App (Gesamt)", "VOL_App")]:
        if key in data:
            pi = data[key].get("Page Impressions", {})
            visits = data[key].get("Visits", {})
            
            pi_val = pi.get("current_sum", 0)
            pi_mom = format_change(pi.get("mom_change"))
            pi_yoy = format_change(yoy_changes.get(key, {}).get("Page Impressions"))
            
            visits_val = visits.get("current_sum", 0)
            visits_mom = format_change(visits.get("mom_change"))
            
            detail_text += f"**{platform}**\n"
            detail_text += f"• PI: {pi_val:,} (MoM: {pi_mom} | YoY: {pi_yoy})\n"
            detail_text += f"• Visits: {visits_val:,} (MoM: {visits_mom})\n\n"
    
    # NEU: iOS/Android Detail
    detail_text += "---\n\n**📱 APP-AUFSCHLÜSSELUNG (iOS/Android)**\n\n"
    
    for platform, key in [("🍎 VOL iOS", "VOL_iOS"), ("🤖 VOL Android", "VOL_Android")]:
        if key in data:
            pi = data[key].get("Page Impressions", {})
            visits = data[key].get("Visits", {})
            
            pi_val = pi.get("current_sum", 0)
            pi_mom = format_change(pi.get("mom_change"))
            pi_yoy = format_change(yoy_changes.get(key, {}).get("Page Impressions"))
            
            visits_val = visits.get("current_sum", 0)
            visits_mom = format_change(visits.get("mom_change"))
            
            detail_text += f"**{platform}**\n"
            detail_text += f"• PI: {pi_val:,} (MoM: {pi_mom} | YoY: {pi_yoy})\n"
            detail_text += f"• Visits: {visits_val:,} (MoM: {visits_mom})\n\n"
    
    # Hinweis UC
    detail_text += "_⚠️ UC nicht vergleichbar (Methodenwechsel Juli 2025)_"
    
    # === SECTIONS BAUEN ===
    sections = [
        {
            "activityTitle": title,
            "activitySubtitle": "📢 VOL.AT Monatsbericht v4.0",
            "facts": summary_facts,
            "markdown": True
        },
        {
            "text": detail_text,
            "markdown": True
        },
        {
            "title": "🤖 KI-Analyse",
            "text": summary,
            "markdown": True
        }
    ]
    
    # === DIAGRAMME ===
    if image_urls:
        for chart_name, url in image_urls.items():
            if url:
                sections.append({
                    "title": f"📊 {chart_name}",
                    "text": f"[🔍 Klicken zum Vergrößern]({url})",
                    "images": [{"image": url, "title": chart_name}]
                })
    
    # === CARD BAUEN ===
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
    
    # === SENDEN ===
    try:
        response = requests.post(TEAMS_WEBHOOK_URL, json=card, timeout=30)
        if response.status_code == 200:
            print("✅ Monatsbericht v4.0 an Teams gesendet")
        else:
            print(f"⚠️ Teams Fehler: {response.status_code}")
            print(f"   Response: {response.text[:200]}")
    except Exception as e:
        print(f"⚠️ Teams Fehler: {e}")


# =============================================================================
# MAIN
# =============================================================================

def run_monthly_report(target_year: int = None, target_month: int = None):
    """
    Hauptfunktion für den Monatsbericht v4.0.
    
    v4.0 FEATURES:
    - Prominente Summary mit Gesamtmetriken
    - Bulletpoint-basierte KI-Analyse
    - Robuster Image Upload
    - Vollständige Metrik-Darstellung
    """
    print("=" * 70)
    print("📊 ÖWA MONTHLY REPORT v4.2")
    print("   • Prominente Summary")
    print("   • Bulletpoint-Format")
    print("   • 7 Diagramme (analog Weekly Report)")
    print("   • Robuster Image Upload")
    print("=" * 70)
    
    if not AIRTABLE_API_KEY:
        print("❌ AIRTABLE_API_KEY nicht gesetzt!")
        return
    
    if not MONTHLY_UTILS_AVAILABLE:
        print("❌ monthly_data_utils nicht verfügbar!")
        return
    
    # Monat bestimmen
    today = date.today()
    if target_year and target_month:
        year, month = target_year, target_month
    else:
        year, month = get_previous_month(today.year, today.month)
    
    prev_year, prev_month = get_previous_month(year, month)
    
    month_names = ["", "Januar", "Februar", "März", "April", "Mai", "Juni", 
                   "Juli", "August", "September", "Oktober", "November", "Dezember"]
    
    current_month_str = f"{month_names[month]} {year}"
    prev_month_str = f"{month_names[prev_month]} {prev_year}"
    
    print(f"\n📅 Berichtsmonat: {current_month_str}")
    print(f"📊 MoM-Vergleich: {prev_month_str}")
    print(f"📊 YoY-Vergleich: {month_names[month]} {year - 1}")
    
    # ==========================================================================
    # DATEN LADEN
    # ==========================================================================
    print("\n📥 Lade VOL-Daten...")
    
    # Aggregierte Daten (Web + App)
    current_data = get_monthly_data(year, month, brand_filter="VOL", aggregate_app=True)
    print(f"   → {current_month_str}: {len(current_data)} Gruppen (aggregiert)")
    
    prev_data = get_monthly_data(prev_year, prev_month, brand_filter="VOL", aggregate_app=True)
    print(f"   → {prev_month_str}: {len(prev_data)} Gruppen (aggregiert)")
    
    # NEU: Separate iOS/Android-Daten
    print("\n📱 Lade iOS/Android-Daten (separat)...")
    current_data_separate = get_monthly_data(year, month, brand_filter="VOL", aggregate_app=False)
    prev_data_separate = get_monthly_data(prev_year, prev_month, brand_filter="VOL", aggregate_app=False)
    
    # iOS/Android aus separaten Daten extrahieren
    for platform in ["iOS", "Android"]:
        key = f"VOL_{platform}"
        if key in current_data_separate:
            current_data[key] = current_data_separate[key]
            print(f"   → {key}: {sum(current_data[key].values()):,} PI+Visits+UC")
        if key in prev_data_separate:
            prev_data[key] = prev_data_separate[key]
    
    print("\n📊 Lade YoY-Daten...")
    yoy_data = get_yoy_comparison(year, month, brand_filter="VOL", aggregate_app=True)
    
    # NEU: YoY auch für iOS/Android separat
    yoy_data_separate = get_yoy_comparison(year, month, brand_filter="VOL", aggregate_app=False)
    if "yoy_changes" in yoy_data_separate:
        for platform in ["iOS", "Android"]:
            key = f"VOL_{platform}"
            if key in yoy_data_separate["yoy_changes"]:
                if "yoy_changes" not in yoy_data:
                    yoy_data["yoy_changes"] = {}
                yoy_data["yoy_changes"][key] = yoy_data_separate["yoy_changes"][key]
    
    print("\n📈 Lade 12-Monats-Trend...")
    trend_data = get_12_month_trend(year, month, brand_filter="VOL", aggregate_app=True)
    print(f"   → {len(trend_data)} Monate geladen (aggregiert)")
    
    # NEU: Trend auch für iOS/Android separat
    trend_data_separate = get_12_month_trend(year, month, brand_filter="VOL", aggregate_app=False)
    print(f"   → {len(trend_data_separate)} Monate geladen (iOS/Android separat)")
    
    if not current_data:
        print("❌ Keine Daten für aktuellen Monat!")
        return
    
    # ==========================================================================
    # DATEN VERARBEITEN
    # ==========================================================================
    print("\n📈 Verarbeite Daten...")
    
    data = {}
    for key, metrics in current_data.items():
        data[key] = {}
        for metric, value in metrics.items():
            prev_value = prev_data.get(key, {}).get(metric, 0)
            mom_change = ((value - prev_value) / prev_value) if prev_value > 0 else None
            
            data[key][metric] = {
                "current_sum": value,
                "prev_sum": prev_value,
                "mom_change": mom_change
            }
    
    # Statistiken ausgeben
    print("\n   === GESAMT-ÜBERSICHT ===")
    total_pi = sum(data.get(k, {}).get("Page Impressions", {}).get("current_sum", 0) for k in data)
    total_visits = sum(data.get(k, {}).get("Visits", {}).get("current_sum", 0) for k in data)
    print(f"   • PI Gesamt: {total_pi:,}")
    print(f"   • Visits Gesamt: {total_visits:,}")
    
    for key in sorted(data.keys()):
        print(f"\n   {key}:")
        for metric in sorted(data[key].keys()):
            m = data[key][metric]
            mom = format_change(m.get('mom_change'))
            print(f"      • {metric}: {m['current_sum']:,} (MoM: {mom})")
    
    # YoY ausgeben
    print("\n   === YoY-VERGLEICH ===")
    yoy_changes = yoy_data.get("yoy_changes", {})
    for key in sorted(yoy_changes.keys()):
        print(f"   {key}:")
        for metric, change in yoy_changes[key].items():
            if metric in YOY_EXCLUDED_METRICS:
                print(f"      • {metric}: N/A (Methodenwechsel)")
            else:
                print(f"      • {metric}: {format_change(change)}")
    
    # ==========================================================================
    # DIAGRAMME ERSTELLEN (analog Weekly Report)
    # ==========================================================================
    image_urls = {}
    if PLOTLY_AVAILABLE:
        print("\n📊 Erstelle Diagramme (analog Weekly Report)...")
        
        try:
            # 1. MoM-Vergleich PI (Aktuell vs. Vormonat - wie Weekly KPI-Vergleich)
            mom_pi_chart = create_mom_comparison_chart(data, "Page Impressions")
            if mom_pi_chart:
                print("   → MoM PI-Vergleich erstellt")
                url = upload_to_imgbb(mom_pi_chart)
                if url:
                    image_urls["PI MoM-Vergleich"] = url
            
            # 2. MoM-Vergleich Visits
            mom_visits_chart = create_mom_comparison_chart(data, "Visits")
            if mom_visits_chart:
                print("   → MoM Visits-Vergleich erstellt")
                url = upload_to_imgbb(mom_visits_chart)
                if url:
                    image_urls["Visits MoM-Vergleich"] = url
            
            # 3. YoY-Vergleich PI (Jahr-über-Jahr)
            yoy_chart = create_yoy_comparison_chart(data, yoy_data, "Page Impressions")
            if yoy_chart:
                print("   → YoY PI-Vergleich erstellt")
                url = upload_to_imgbb(yoy_chart)
                if url:
                    image_urls["PI YoY-Vergleich"] = url
            
            # 4. 12-Monats-Trend PI (inkl. iOS/Android)
            trend_pi_chart = create_12_month_trend_chart(trend_data, "Page Impressions", trend_data_separate)
            if trend_pi_chart:
                print("   → 12-Monats-Trend PI erstellt (inkl. iOS/Android)")
                url = upload_to_imgbb(trend_pi_chart)
                if url:
                    image_urls["12-Monats-Trend PI"] = url
            
            # 5. 12-Monats-Trend Visits (inkl. iOS/Android)
            trend_visits_chart = create_12_month_trend_chart(trend_data, "Visits", trend_data_separate)
            if trend_visits_chart:
                print("   → 12-Monats-Trend Visits erstellt (inkl. iOS/Android)")
                url = upload_to_imgbb(trend_visits_chart)
                if url:
                    image_urls["12-Monats-Trend Visits"] = url
            
            # 6. MoM-Änderungen alle Metriken (Übersicht)
            multi_chart = create_multi_metric_comparison_chart(data)
            if multi_chart:
                print("   → Multi-Metrik MoM-Übersicht erstellt")
                url = upload_to_imgbb(multi_chart)
                if url:
                    image_urls["MoM-Übersicht"] = url
            
            # 7. Plattform-Anteil Pie (Web vs. App)
            pie_chart = create_platform_pie_chart(data, "Page Impressions")
            if pie_chart:
                print("   → Plattform-Anteil erstellt")
                url = upload_to_imgbb(pie_chart)
                if url:
                    image_urls["Web vs. App Anteil"] = url
            
            # 8. NEU: App-Split Pie (iOS vs. Android)
            app_split_chart = create_app_split_pie_chart(data, "Page Impressions")
            if app_split_chart:
                print("   → App-Split (iOS/Android) erstellt")
                url = upload_to_imgbb(app_split_chart)
                if url:
                    image_urls["iOS vs. Android Anteil"] = url
            
            print(f"\n   ✅ {len(image_urls)} Diagramme erfolgreich hochgeladen")
                    
        except Exception as e:
            print(f"   ⚠️ Diagramm-Fehler: {e}")
            import traceback
            traceback.print_exc()
    
    # ==========================================================================
    # GPT SUMMARY (Bulletpoints)
    # ==========================================================================
    print("\n🤖 Generiere Bulletpoint-Analyse...")
    summary = generate_bulletpoint_summary(
        data, 
        current_month_str, 
        prev_month_str,
        yoy_data,
        trend_data
    )
    print(f"   → {len(summary)} Zeichen generiert")
    
    # ==========================================================================
    # TEAMS BERICHT
    # ==========================================================================
    print("\n📤 Sende Monatsbericht v4.0 an Teams...")
    title = f"📊 ÖWA Monatsbericht - {current_month_str}"
    send_monthly_teams_report_v4(
        title, 
        summary, 
        data, 
        current_month_str, 
        prev_month_str,
        yoy_data,
        image_urls
    )
    
    print("\n" + "=" * 70)
    print("✅ MONTHLY REPORT v4.0 ABGESCHLOSSEN")
    print("=" * 70)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ÖWA Monthly Report v4.0")
    parser.add_argument("--month", type=str, help="Monat im Format YYYY-MM (z.B. 2025-12)")
    args = parser.parse_args()
    
    if args.month:
        try:
            year, month = map(int, args.month.split("-"))
            run_monthly_report(year, month)
        except:
            print("❌ Ungültiges Datumsformat. Nutze YYYY-MM (z.B. 2025-12)")
    else:
        run_monthly_report()
