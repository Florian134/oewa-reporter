#!/usr/bin/env python3
"""
Weekly Report Script v4.0
==========================
Erstellt einen wöchentlichen Bericht mit:
- NUR VOL.AT (Vienna ausgeschlossen)
- 6-Wochen-Vergleich (aktuelle Woche vs. letzte 6 Wochen)
- Prozentuelle Veränderungen für alle KPIs
- GPT-generierte Executive Summary (BULLETPOINT-FORMAT)
- Teams-Benachrichtigung mit PROMINENTER SUMMARY
- 6 Diagramme (analog Monthly Report)

v4.0 ÄNDERUNGEN (Angleichung an Monthly Report):
- GPT-Prompt: 200 Wörter, 5 Sektionen, Bulletpoints
- Teams-Struktur: Prominente Summary, Trenner, gruppierte Metriken
- Diagramme: +2 neue (Multi-Metrik %, Plattform-Anteil)
- Upload: Robuster mit 3 Retries

Nutzung:
    python ci_scripts/weekly_report.py
"""

import os
import json
import requests
import statistics
import base64
import io
import time
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
AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID", "")  # Muss in CI/CD Variables gesetzt sein
TEAMS_WEBHOOK_URL = os.environ.get("TEAMS_WEBHOOK_URL", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
IMGBB_API_KEY = os.environ.get("IMGBB_API_KEY", "")

# Chart-Größe (ERHÖHT für bessere Lesbarkeit in Teams)
CHART_WIDTH = 1600
CHART_HEIGHT = 800
CHART_SCALE = 2  # Retina-Qualität

# Daten-Verzögerung (Tage) - INFOnline API liefert erst nach ~2 Tagen finale Daten
REPORT_DELAY_DAYS = 2

# Farben - NUR VOL (Vienna ausgeschlossen)
# NEU: iOS und Android werden zu "App" aggregiert
BRAND_COLORS = {
    "VOL Web": "#3B82F6",      # Blau
    "VOL App": "#60A5FA",      # Hellblau (iOS + Android aggregiert)
    "VOL iOS": "#10B981",      # Grün
    "VOL Android": "#F59E0B",  # Orange
}

# Plattformen, die als "App" zusammengefasst werden
APP_PLATFORMS = ["iOS", "Android"]

# Metriken-Konfiguration
METRICS = ["Page Impressions", "Visits", "Unique Clients", "Homepage PI"]

# Anzahl der Vergleichswochen
COMPARISON_WEEKS = 6

# Plattform-Farben
PLATFORM_COLORS = {
    "Web": "#3B82F6",
    "App": "#10B981",
}


# =============================================================================
# HILFSFUNKTIONEN
# =============================================================================

def format_number(n: float) -> str:
    """Formatiert große Zahlen lesbar (z.B. 5.5M, 789K)."""
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    elif n >= 1_000:
        return f"{n/1_000:.0f}K"
    return f"{n:,.0f}"


def format_change(change: Optional[float], prefix: str = "") -> str:
    """Formatiert prozentuale Änderung."""
    if change is None:
        return "N/A"
    return f"{prefix}{change*100:+.1f}%"


# =============================================================================
# ROBUSTER IMAGE UPLOAD (mit Retry - analog Monthly Report)
# =============================================================================

def upload_to_imgbb_robust(image_bytes: bytes, max_retries: int = 3) -> Optional[str]:
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
                    "expiration": 0
                },
                timeout=90
            )
            
            if response.status_code == 200:
                url = response.json()["data"]["url"]
                print(f"   ✅ Upload erfolgreich: {url[:50]}...")
                return url
            else:
                print(f"   ⚠️ HTTP {response.status_code}")
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
# DIAGRAMM-FUNKTIONEN (erweitert für v4.0)
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


def create_multi_metric_chart(data: Dict) -> Optional[bytes]:
    """
    Erstellt ein Übersichts-Balkendiagramm mit allen Metrik-Änderungen (%).
    NEU in v4.0 - analog Monthly Report.
    """
    if not PLOTLY_AVAILABLE:
        return None
    
    chart_data = []
    
    for metric in ["Page Impressions", "Visits"]:
        for platform in ["Web", "App"]:
            key = f"VOL_{platform}"
            if key in data and metric in data[key]:
                m = data[key][metric]
                pct_change = m.get("pct_change", 0) or 0
                chart_data.append({
                    "metrik": metric.replace("Page Impressions", "PI"),
                    "plattform": f"VOL {platform}",
                    "pct_change": pct_change * 100,
                })
    
    if not chart_data:
        return None
    
    df = pd.DataFrame(chart_data)
    
    fig = px.bar(
        df,
        x="metrik",
        y="pct_change",
        color="plattform",
        barmode="group",
        title="📊 Änderungen vs. 6-Wochen-Ø (%)",
        color_discrete_map={
            "VOL Web": "#3B82F6",
            "VOL App": "#10B981"
        },
        text=df["pct_change"].apply(lambda x: f"{x:+.1f}%")
    )
    
    fig.add_hline(y=0, line_dash="dash", line_color="gray")
    
    fig.update_layout(
        yaxis=dict(title="Änderung (%)"),
        xaxis_title="",
        legend_title="",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        width=CHART_WIDTH,
        height=CHART_HEIGHT,
        font=dict(size=14),
        title_font_size=20
    )
    
    fig.update_traces(textposition="outside")
    
    return fig.to_image(format="png", scale=CHART_SCALE)


def create_platform_pie_chart(data: Dict, metric: str = "Page Impressions") -> Optional[bytes]:
    """
    Erstellt ein Pie Chart für Web vs. App Anteil.
    NEU in v4.0 - analog Monthly Report.
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
        title=f"📊 {metric} - Web vs. App Anteil",
        width=CHART_WIDTH,
        height=CHART_HEIGHT,
        font=dict(size=14),
        title_font_size=20
    )
    
    return fig.to_image(format="png", scale=CHART_SCALE)


# Alias für Rückwärtskompatibilität
def upload_to_imgbb(image_bytes: bytes) -> Optional[str]:
    """Wrapper für robuste Upload-Funktion."""
    return upload_to_imgbb_robust(image_bytes)


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
    
    # Hilfsfunktion: Metrik-Datenstruktur initialisieren
    def init_metric_data():
        return {
            "current_sum": 0,
            "current_days": 0,
            "daily": {},
            "weekly_values": [{"label": w["label"], "value": 0, "days": 0, "is_current": w["is_current"]} for w in weeks],
            "weeks_with_data": 0
        }
    
    # Hilfsfunktion: Wert zu Metrik hinzufügen
    def add_to_metric(key: str, metric: str, datum: date, datum_str: str, wert: int, week_idx: int):
        if key not in data:
            data[key] = {}
        if metric not in data[key]:
            data[key][metric] = init_metric_data()
        
        data[key][metric]["weekly_values"][week_idx]["value"] += wert
        data[key][metric]["weekly_values"][week_idx]["days"] += 1
        
        # Aktuelle Woche separat tracken
        if week_idx == 0:
            data[key][metric]["current_sum"] += wert
            data[key][metric]["current_days"] += 1
            data[key][metric]["daily"][datum_str] = data[key][metric]["daily"].get(datum_str, 0) + wert
    
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
        
        # Welche Woche?
        week_idx = None
        for idx, week in enumerate(weeks):
            if week["start"] <= datum <= week["end"]:
                week_idx = idx
                break
        
        if week_idx is None:
            continue
        
        # IMMER: Originale Plattform speichern (iOS, Android, Web)
        original_key = f"{brand}_{surface}"
        add_to_metric(original_key, metric, datum, datum_str, wert, week_idx)
        
        # ZUSÄTZLICH: iOS und Android auch zu "App" aggregieren
        if surface in APP_PLATFORMS:
            app_key = f"{brand}_App"
            add_to_metric(app_key, metric, datum, datum_str, wert, week_idx)
    
    # Berechnungen: 6-Wochen-Durchschnitt und prozentuelle Änderungen
    # WICHTIG: Für faire Vergleiche bei unterschiedlicher Tagesanzahl
    # werden TAGESDURCHSCHNITTE verglichen, nicht Summen!
    for key in data:
        for metric in data[key]:
            m = data[key][metric]
            
            # Tagesdurchschnitt aktuelle Woche
            m["current_avg"] = m["current_sum"] / max(1, m["current_days"])
            
            # 6-Wochen-Durchschnitt (ohne aktuelle Woche)
            prev_weeks = m["weekly_values"][1:]  # Index 1-6
            weeks_with_data = [w for w in prev_weeks if w["value"] > 0 and w["days"] > 0]
            
            if weeks_with_data:
                # KORRIGIERT: Tagesdurchschnitte statt Summen für fairen Vergleich
                # (wichtig wegen UC 3-Tage-Delay - aktuelle Woche hat oft weniger Tage)
                daily_avgs = [w["value"] / w["days"] for w in weeks_with_data]
                m["avg_daily_6_weeks"] = sum(daily_avgs) / len(daily_avgs)
                
                # Für Rückwärts-Kompatibilität: auch Wochen-Summen-Durchschnitt behalten
                m["avg_6_weeks"] = sum(w["value"] for w in weeks_with_data) / len(weeks_with_data)
                m["weeks_with_data"] = len(weeks_with_data)
                
                # Prozentuelle Änderung: TAGESDURCHSCHNITT vs TAGESDURCHSCHNITT
                # Das ist ein fairer Vergleich auch wenn Wochen unterschiedliche Tage haben!
                if m["avg_daily_6_weeks"] > 0:
                    m["pct_change"] = (m["current_avg"] - m["avg_daily_6_weeks"]) / m["avg_daily_6_weeks"]
                else:
                    m["pct_change"] = None
                
                # NEU: vs_prev_week (Vergleich mit Vorwoche)
                # Index 1 = Vorwoche (KW-1)
                prev_week = m["weekly_values"][1] if len(m["weekly_values"]) > 1 else None
                if prev_week and prev_week["days"] > 0:
                    prev_week_avg = prev_week["value"] / prev_week["days"]
                    if prev_week_avg > 0:
                        m["vs_prev_week"] = (m["current_avg"] - prev_week_avg) / prev_week_avg
                    else:
                        m["vs_prev_week"] = None
                else:
                    m["vs_prev_week"] = None
            else:
                m["avg_6_weeks"] = 0
                m["avg_daily_6_weeks"] = 0
                m["pct_change"] = None
                m["vs_prev_week"] = None
    
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
    # PROFESSIONELL: Tagesdurchschnitte für fairen Vergleich
    kpi_text = ""
    for key in ["VOL_Web", "VOL_App"]:
        if key in data:
            kpi_text += f"\n**{key.replace('_', ' ')}:**\n"
            for metric in METRICS:
                if metric in data[key]:
                    m = data[key][metric]
                    pct = f"{m['pct_change']*100:+.1f}%" if m.get('pct_change') is not None else "N/A"
                    daily_avg = m.get('current_avg', 0)
                    prev_daily_avg = m.get('avg_daily_6_weeks', 0)
                    kpi_text += f"  - {metric}: Ø {daily_avg:,.0f}/Tag (vs. 6-Wochen-Ø {prev_daily_avg:,.0f}/Tag: {pct})\n"
    
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
WICHTIG: Alle KPIs sind als TAGESDURCHSCHNITTE angegeben für fairen Vergleich!

═══════════════════════════════════════════════════════════════
📅 BERICHTSZEITRAUM: {period}
📊 VERGLEICH: Ø pro Tag vs. Ø pro Tag der letzten 6 Wochen
═══════════════════════════════════════════════════════════════

KPI-DATEN (nur VOL.AT):
{kpi_text}

PERFORMANCE-ÜBERSICHT:
{highlight_text}

═══════════════════════════════════════════════════════════════

WICHTIG:
- Professioneller, eloquenter Stil für Management-Ebene
- Bei Key-Metriken: übersichtliche Bulletpoints mit gut durchdachter Kurzinterpretation
- Interpretationen basieren auf sorgfältiger Analyse der Daten
- MAX 200 WÖRTER GESAMT

FORMAT (EXAKT einhalten):

📈 **HIGHLIGHT DER WOCHE**
[2-3 Sätze zur wichtigsten Erkenntnis mit konkreten Zahlen]

📊 **6-WOCHEN-VERGLEICH**
• Web: [Trend + kurze Interpretation]
• App: [Trend + kurze Interpretation]

📈 **7-TAGE-TREND**
[1-2 Sätze zur Entwicklung innerhalb der Woche - Peak-Tage, Muster]

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
    Sendet den Wochenbericht an Teams mit strukturierter KPI-Übersicht.
    
    v5.0 Format - 5 KPI-Sektionen (analog Monthly Report):
    1. GESAMTENTWICKLUNG (Web + App)
    2. WEB-ENTWICKLUNG
    3. APP-ENTWICKLUNG (Gesamt)
    4. APP-ENTWICKLUNG (iOS)
    5. APP-ENTWICKLUNG (Android)
    
    Jede Sektion: Visits, PI, UC, (HPPI nur bei Web/Gesamt)
    Format: Metrik WERT (vs Vorwoche: ±X.XX%, vs 6W-Ø: ±X.XX%)
    """
    if not TEAMS_WEBHOOK_URL:
        print("⚠️ TEAMS_WEBHOOK_URL nicht konfiguriert")
        return
    
    # === HILFSFUNKTION: Metrik-Zeile formatieren ===
    def format_metric_line(label: str, current: int, vs_prev_week: float, vs_avg: float) -> str:
        """Formatiert eine Metrik-Zeile für Weekly Report"""
        prev_str = format_change(vs_prev_week)
        avg_str = format_change(vs_avg)
        return f"{label} **{current:,}** (vs Vorwoche: {prev_str}, vs {COMPARISON_WEEKS}W-Ø: {avg_str})"
    
    # === DATEN EXTRAHIEREN ===
    def get_platform_metrics(key: str) -> Dict:
        """Extrahiert alle Metriken für eine Plattform"""
        platform_data = data.get(key, {})
        
        return {
            "visits": int(platform_data.get("Visits", {}).get("current_sum", 0)),
            "visits_vs_avg": platform_data.get("Visits", {}).get("pct_change"),
            "visits_vs_prev": platform_data.get("Visits", {}).get("vs_prev_week"),
            "pi": int(platform_data.get("Page Impressions", {}).get("current_sum", 0)),
            "pi_vs_avg": platform_data.get("Page Impressions", {}).get("pct_change"),
            "pi_vs_prev": platform_data.get("Page Impressions", {}).get("vs_prev_week"),
            "uc": int(platform_data.get("Unique Clients", {}).get("current_sum", 0)),
            "uc_vs_avg": platform_data.get("Unique Clients", {}).get("pct_change"),
            "uc_vs_prev": platform_data.get("Unique Clients", {}).get("vs_prev_week"),
            "hppi": int(platform_data.get("Homepage PI", {}).get("current_sum", 0)),
            "hppi_vs_avg": platform_data.get("Homepage PI", {}).get("pct_change"),
            "hppi_vs_prev": platform_data.get("Homepage PI", {}).get("vs_prev_week"),
        }
    
    # Plattform-Daten laden
    web = get_platform_metrics("VOL_Web")
    app = get_platform_metrics("VOL_App")
    ios = get_platform_metrics("VOL_iOS")
    android = get_platform_metrics("VOL_Android")
    
    # === GESAMT berechnen (Web + App) ===
    total_visits = web["visits"] + app["visits"]
    total_pi = web["pi"] + app["pi"]
    total_uc = web["uc"] + app["uc"]
    total_hppi = web["hppi"]  # HPPI nur Web
    
    # Gesamt-Änderungen (gewichteter Durchschnitt basierend auf Werten)
    def weighted_avg_change(val1: int, change1: float, val2: int, change2: float) -> float:
        """Berechnet gewichteten Durchschnitt der Änderungen"""
        if change1 is None and change2 is None:
            return None
        total = val1 + val2
        if total == 0:
            return None
        c1 = change1 if change1 is not None else 0
        c2 = change2 if change2 is not None else 0
        return (val1 * c1 + val2 * c2) / total
    
    total_visits_vs_avg = weighted_avg_change(web["visits"], web["visits_vs_avg"], app["visits"], app["visits_vs_avg"])
    total_visits_vs_prev = weighted_avg_change(web["visits"], web["visits_vs_prev"], app["visits"], app["visits_vs_prev"])
    total_pi_vs_avg = weighted_avg_change(web["pi"], web["pi_vs_avg"], app["pi"], app["pi_vs_avg"])
    total_pi_vs_prev = weighted_avg_change(web["pi"], web["pi_vs_prev"], app["pi"], app["pi_vs_prev"])
    total_uc_vs_avg = weighted_avg_change(web["uc"], web["uc_vs_avg"], app["uc"], app["uc_vs_avg"])
    total_uc_vs_prev = weighted_avg_change(web["uc"], web["uc_vs_prev"], app["uc"], app["uc_vs_prev"])
    
    # Farbe basierend auf Gesamtperformance
    if total_pi_vs_avg and total_pi_vs_avg > 0:
        color = "28A745"  # Grün
    elif total_pi_vs_avg and total_pi_vs_avg < -0.05:
        color = "FFC107"  # Gelb
    else:
        color = "17A2B8"  # Blau (neutral)
    
    # === KPI-SEKTIONEN BAUEN ===
    
    # Metadaten
    kpi_text = f"**📅 Berichtszeitraum:** {period}\n"
    kpi_text += f"**📊 Vergleich mit:** Ø der letzten {COMPARISON_WEEKS} Wochen\n\n"
    kpi_text += "---\n\n"
    
    # 1. GESAMTENTWICKLUNG
    kpi_text += "**📊 GESAMTENTWICKLUNG**\n\n"
    kpi_text += f"• {format_metric_line('Visits', total_visits, total_visits_vs_prev, total_visits_vs_avg)}\n"
    kpi_text += f"• {format_metric_line('PI', total_pi, total_pi_vs_prev, total_pi_vs_avg)}\n"
    kpi_text += f"• {format_metric_line('UC', total_uc, total_uc_vs_prev, total_uc_vs_avg)}\n"
    kpi_text += f"• {format_metric_line('HPPI', total_hppi, web['hppi_vs_prev'], web['hppi_vs_avg'])}\n\n"
    
    # 2. WEB-ENTWICKLUNG
    kpi_text += "**🌐 WEB-ENTWICKLUNG**\n\n"
    kpi_text += f"• {format_metric_line('Visits', web['visits'], web['visits_vs_prev'], web['visits_vs_avg'])}\n"
    kpi_text += f"• {format_metric_line('PI', web['pi'], web['pi_vs_prev'], web['pi_vs_avg'])}\n"
    kpi_text += f"• {format_metric_line('UC', web['uc'], web['uc_vs_prev'], web['uc_vs_avg'])}\n"
    kpi_text += f"• {format_metric_line('HPPI', web['hppi'], web['hppi_vs_prev'], web['hppi_vs_avg'])}\n\n"
    
    # 3. APP-ENTWICKLUNG (Gesamt)
    kpi_text += "**📱 APP-ENTWICKLUNG (Gesamt)**\n\n"
    kpi_text += f"• {format_metric_line('Visits', app['visits'], app['visits_vs_prev'], app['visits_vs_avg'])}\n"
    kpi_text += f"• {format_metric_line('PI', app['pi'], app['pi_vs_prev'], app['pi_vs_avg'])}\n"
    kpi_text += f"• {format_metric_line('UC', app['uc'], app['uc_vs_prev'], app['uc_vs_avg'])}\n\n"
    
    # 4. APP-ENTWICKLUNG (iOS)
    kpi_text += "**🍎 APP-ENTWICKLUNG (iOS)**\n\n"
    kpi_text += f"• {format_metric_line('Visits', ios['visits'], ios['visits_vs_prev'], ios['visits_vs_avg'])}\n"
    kpi_text += f"• {format_metric_line('PI', ios['pi'], ios['pi_vs_prev'], ios['pi_vs_avg'])}\n"
    kpi_text += f"• {format_metric_line('UC', ios['uc'], ios['uc_vs_prev'], ios['uc_vs_avg'])}\n\n"
    
    # 5. APP-ENTWICKLUNG (Android)
    kpi_text += "**🤖 APP-ENTWICKLUNG (Android)**\n\n"
    kpi_text += f"• {format_metric_line('Visits', android['visits'], android['visits_vs_prev'], android['visits_vs_avg'])}\n"
    kpi_text += f"• {format_metric_line('PI', android['pi'], android['pi_vs_prev'], android['pi_vs_avg'])}\n"
    kpi_text += f"• {format_metric_line('UC', android['uc'], android['uc_vs_prev'], android['uc_vs_avg'])}\n"
    
    # === SECTIONS BAUEN ===
    sections = [
        {
            "activityTitle": title,
            "activitySubtitle": "📢 VOL.AT Wochenbericht v5.0",
            "markdown": True
        },
        {
            "text": kpi_text,
            "markdown": True
        },
        {
            "title": "🤖 KI-Analyse",
            "text": summary,
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
            print("✅ Wochenbericht v5.0 an Teams gesendet")
        else:
            print(f"⚠️ Teams Fehler: {response.status_code}")
    except Exception as e:
        print(f"⚠️ Teams Fehler: {e}")


# =============================================================================
# MAIN
# =============================================================================

def run_weekly_report():
    """
    Hauptfunktion für den Wochenbericht v4.0.
    NUR VOL.AT mit 6-Wochen-Vergleich.
    
    v4.0 FEATURES:
    - Prominente Summary
    - 5-Sektionen GPT-Analyse mit Bulletpoints
    - 6 Diagramme (analog Monthly Report)
    - Robuster Image Upload
    """
    print("=" * 70)
    print("📊 ÖWA WEEKLY REPORT v4.0")
    print("   • Prominente Summary")
    print("   • Bulletpoint-Format")
    print("   • 6 Diagramme (analog Monthly Report)")
    print(f"   • Vergleich: Aktuelle Woche vs. {COMPARISON_WEEKS}-Wochen-Ø")
    print("=" * 70)
    
    # Konfigurationsstatus ausgeben
    print("\n🔧 KONFIGURATION:")
    print(f"   AIRTABLE_API_KEY: {'✅' if AIRTABLE_API_KEY else '❌'}")
    print(f"   TEAMS_WEBHOOK_URL: {'✅' if TEAMS_WEBHOOK_URL else '❌'}")
    print(f"   OPENAI_API_KEY: {'✅' if OPENAI_API_KEY else '⚠️'}")
    print(f"   IMGBB_API_KEY: {'✅' if IMGBB_API_KEY else '❌'}")
    print(f"   PLOTLY_AVAILABLE: {'✅' if PLOTLY_AVAILABLE else '❌'}")
    
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
            days = m.get('current_days', 0)
            daily_avg = m.get('current_avg', 0)
            prev_daily_avg = m.get('avg_daily_6_weeks', 0)
            print(f"      {metric}: {m['current_sum']:,} ({days} Tage, Ø {daily_avg:,.0f}/Tag)")
            print(f"               vs. 6-Wochen-Ø {prev_daily_avg:,.0f}/Tag → {pct}")
    
    # ==========================================================================
    # DIAGRAMME ERSTELLEN (v4.0 - 6 Charts analog Monthly Report)
    # ==========================================================================
    image_urls = {}
    if PLOTLY_AVAILABLE:
        print("\n📊 Erstelle Diagramme (v4.0 - 6 Charts)...")
        
        try:
            # 1. PI Vergleich (Aktuell vs. 6-Wochen-Ø)
            chart_bytes = create_kpi_comparison_chart(data, "Page Impressions")
            if chart_bytes:
                print("   → PI-Vergleich erstellt")
                url = upload_to_imgbb(chart_bytes)
                if url:
                    image_urls["PI vs. 6-Wochen-Ø"] = url
            
            # 2. Visits Vergleich
            visits_chart = create_kpi_comparison_chart(data, "Visits")
            if visits_chart:
                print("   → Visits-Vergleich erstellt")
                url = upload_to_imgbb(visits_chart)
                if url:
                    image_urls["Visits vs. 6-Wochen-Ø"] = url
            
            # 3. 7-Tage Trend Chart
            trend_bytes = create_trend_chart(data, "Page Impressions")
            if trend_bytes:
                print("   → 7-Tage-Trend erstellt")
                url = upload_to_imgbb(trend_bytes)
                if url:
                    image_urls["7-Tage-Trend PI"] = url
            
            # 4. 7-Wochen-Übersicht
            week_chart = create_6week_comparison_chart(data, "Page Impressions")
            if week_chart:
                print("   → 7-Wochen-Übersicht erstellt")
                url = upload_to_imgbb(week_chart)
                if url:
                    image_urls["7-Wochen-Übersicht PI"] = url
            
            # 5. Multi-Metrik Übersicht (NEU - analog Monthly)
            multi_chart = create_multi_metric_chart(data)
            if multi_chart:
                print("   → Multi-Metrik Übersicht erstellt")
                url = upload_to_imgbb(multi_chart)
                if url:
                    image_urls["Änderungen-Übersicht (%)"] = url
            
            # 6. Plattform-Anteil Pie (NEU - analog Monthly)
            pie_chart = create_platform_pie_chart(data, "Page Impressions")
            if pie_chart:
                print("   → Plattform-Anteil erstellt")
                url = upload_to_imgbb(pie_chart)
                if url:
                    image_urls["Web vs. App Anteil"] = url
            
            print(f"\n   ✅ {len(image_urls)} Diagramme erfolgreich hochgeladen")
                    
        except Exception as e:
            print(f"   ⚠️ Diagramm-Erstellung fehlgeschlagen: {e}")
            import traceback
            traceback.print_exc()
    
    # GPT Summary
    print("\n🤖 Generiere KI-Zusammenfassung...")
    summary = generate_gpt_summary(data, period)
    print(f"   → {len(summary)} Zeichen generiert")
    
    # Teams Bericht
    print("\n📤 Sende Teams-Bericht...")
    title = f"📊 ÖWA Wochenbericht VOL.AT - KW {data_end.isocalendar()[1]}"
    send_teams_report(title, summary, data, period, image_urls)
    
    print("\n" + "=" * 70)
    print("✅ WEEKLY REPORT v4.0 ABGESCHLOSSEN")
    print("=" * 70)


if __name__ == "__main__":
    run_weekly_report()
