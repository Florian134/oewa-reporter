#!/usr/bin/env python3
"""
Weekly Report Script
====================
Erstellt einen wöchentlichen Bericht mit:
- Zusammenfassung der Wochendaten
- Anomalie-Erkennung (Z-Score)
- GPT-generierte Analyse
- Teams-Benachrichtigung mit Diagrammen (PNG)

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
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False
    print("⚠️ Plotly nicht verfügbar - keine Diagramme möglich")

# =============================================================================
# KONFIGURATION
# =============================================================================
AIRTABLE_API_KEY = os.environ.get("AIRTABLE_API_KEY", "")
AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID", "appTleod85xnBy7Vn")
TEAMS_WEBHOOK_URL = os.environ.get("TEAMS_WEBHOOK_URL", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

# Anomalie-Schwellenwerte
WARNING_ZSCORE = 2.0
CRITICAL_ZSCORE = 2.5
WARNING_PCT = 0.15  # 15%
CRITICAL_PCT = 0.20  # 20%

# Brand-Farben (wie in Streamlit)
BRAND_COLORS = {"VOL": "#3B82F6", "Vienna": "#8B5CF6"}

# =============================================================================
# DIAGRAMM-FUNKTIONEN
# =============================================================================

def create_weekday_chart(data: Dict, metric: str = "Page Impressions") -> Optional[bytes]:
    """
    Erstellt ein Wochentags-Balkendiagramm als PNG.
    
    Args:
        data: Dict mit Wochentags-Daten pro Brand
        metric: "Page Impressions" oder "Visits"
    
    Returns:
        PNG als bytes oder None wenn Plotly nicht verfügbar
    """
    if not PLOTLY_AVAILABLE:
        return None
    
    weekday_names = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
    
    # Daten für das Chart vorbereiten
    chart_data = []
    for brand in ["VOL", "Vienna"]:
        if brand in data and metric in data[brand]:
            weekday_values = data[brand][metric].get("weekday_avg", {})
            for day_idx, day_name in enumerate(weekday_names):
                if day_idx in weekday_values:
                    chart_data.append({
                        "wochentag": day_name,
                        "wert": weekday_values[day_idx],
                        "brand": brand
                    })
    
    if not chart_data:
        return None
    
    # Plotly Chart erstellen
    import pandas as pd
    df = pd.DataFrame(chart_data)
    
    fig = px.bar(
        df,
        x="wochentag",
        y="wert",
        color="brand",
        barmode="group",
        title=f"Ø {metric} pro Wochentag",
        color_discrete_map=BRAND_COLORS
    )
    
    fig.update_layout(
        yaxis=dict(tickformat=","),
        xaxis_title="",
        legend_title="Property",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        width=800,
        height=400
    )
    
    # Als PNG exportieren
    img_bytes = fig.to_image(format="png", scale=2)
    return img_bytes


def create_trend_chart(data: Dict, metric: str = "Page Impressions") -> Optional[bytes]:
    """
    Erstellt ein Trend-Liniendiagramm als PNG.
    
    Args:
        data: Dict mit täglichen Werten pro Brand
        metric: "Page Impressions" oder "Visits"
    
    Returns:
        PNG als bytes oder None wenn Plotly nicht verfügbar
    """
    if not PLOTLY_AVAILABLE:
        return None
    
    import pandas as pd
    
    # Daten für das Chart vorbereiten
    chart_data = []
    for brand in ["VOL", "Vienna"]:
        if brand in data and metric in data[brand]:
            daily_values = data[brand][metric].get("daily", {})
            for datum, wert in daily_values.items():
                chart_data.append({
                    "datum": datum,
                    "wert": wert,
                    "brand": brand
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
        color="brand",
        title=f"{metric} - Tagestrend",
        color_discrete_map=BRAND_COLORS
    )
    
    fig.update_layout(
        yaxis=dict(tickformat=","),
        xaxis=dict(tickformat="%d.%m."),
        xaxis_title="Datum",
        legend_title="Property",
        width=800,
        height=400
    )
    
    img_bytes = fig.to_image(format="png", scale=2)
    return img_bytes


def upload_to_imgur(image_bytes: bytes) -> Optional[str]:
    """
    Lädt ein Bild anonym zu Imgur hoch.
    
    Args:
        image_bytes: PNG als bytes
    
    Returns:
        URL des hochgeladenen Bildes oder None bei Fehler
    """
    if not image_bytes:
        return None
    
    # Imgur anonymer Upload (Client-ID für anonyme Uploads)
    # Das ist ein öffentlicher Client-ID für anonyme Uploads
    IMGUR_CLIENT_ID = "546c25a59c58ad7"  # Öffentlicher anonymer Client
    
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


def calculate_statistics(values: List[float]) -> Dict:
    """Berechnet Statistiken für eine Werteliste"""
    if not values or len(values) < 3:
        return {"valid": False}
    
    mean = statistics.mean(values)
    median = statistics.median(values)
    stdev = statistics.stdev(values) if len(values) > 1 else 0
    
    # MAD (Median Absolute Deviation)
    mad = statistics.median([abs(x - median) for x in values])
    mad_scaled = mad * 1.4826  # Skalierungsfaktor für Normalverteilung
    
    return {
        "valid": True,
        "mean": mean,
        "median": median,
        "stdev": stdev,
        "mad": mad,
        "mad_scaled": mad_scaled,
        "min": min(values),
        "max": max(values),
        "count": len(values)
    }


def detect_anomaly(value: float, stats: Dict) -> Dict:
    """Erkennt Anomalien basierend auf Z-Score und Prozentabweichung"""
    if not stats.get("valid"):
        return {"is_anomaly": False, "severity": None}
    
    # Z-Score berechnen (robust mit MAD)
    mad_scaled = stats["mad_scaled"]
    if mad_scaled < 0.001:
        mad_scaled = 0.001  # Minimum um Division durch 0 zu vermeiden
    
    zscore = (value - stats["median"]) / mad_scaled
    zscore = max(-10, min(10, zscore))  # Clamp
    
    # Prozentabweichung
    if stats["median"] > 0:
        pct_delta = (value - stats["median"]) / stats["median"]
    else:
        pct_delta = 0
    
    # Severity bestimmen
    severity = None
    if abs(zscore) >= CRITICAL_ZSCORE and abs(pct_delta) >= CRITICAL_PCT:
        severity = "critical"
    elif abs(zscore) >= WARNING_ZSCORE and abs(pct_delta) >= WARNING_PCT:
        severity = "warning"
    
    return {
        "is_anomaly": severity is not None,
        "severity": severity,
        "zscore": round(zscore, 2),
        "pct_delta": round(pct_delta * 100, 1),
        "median": stats["median"]
    }


def generate_gpt_summary(data: Dict) -> str:
    """Generiert eine GPT-Zusammenfassung des Wochenberichts"""
    if not OPENAI_API_KEY:
        return "GPT-Zusammenfassung nicht verfügbar (API Key fehlt)"
    
    # Veränderungen formatieren (None → "nicht verfügbar")
    vol_pi_change = f"{data.get('vol_pi_change')}%" if data.get('vol_pi_change') is not None else "nicht verfügbar (unvollständige Vorwochendaten)"
    vol_visits_change = f"{data.get('vol_visits_change')}%" if data.get('vol_visits_change') is not None else "nicht verfügbar (unvollständige Vorwochendaten)"
    vienna_pi_change = f"{data.get('vienna_pi_change')}%" if data.get('vienna_pi_change') is not None else "nicht verfügbar (unvollständige Vorwochendaten)"
    vienna_visits_change = f"{data.get('vienna_visits_change')}%" if data.get('vienna_visits_change') is not None else "nicht verfügbar (unvollständige Vorwochendaten)"
    
    # Datenqualitätshinweis
    data_quality = data.get('data_quality_note', '')
    data_quality_section = f"\nDATENQUALITÄT:\n{data_quality}\n" if data_quality else ""
    
    # Aktuelles Datum für Kontext (Saisonalität, Feiertage)
    from datetime import datetime
    current_month = datetime.now().strftime("%B")
    current_week = datetime.now().isocalendar()[1]
    
    # Beste Performance identifizieren für Highlight
    changes = {
        "VOL.AT Page Impressions": data.get('vol_pi_change'),
        "VOL.AT Visits": data.get('vol_visits_change'),
        "VIENNA.AT Page Impressions": data.get('vienna_pi_change'),
        "VIENNA.AT Visits": data.get('vienna_visits_change')
    }
    valid_changes = {k: v for k, v in changes.items() if v is not None}
    best_performer = max(valid_changes.items(), key=lambda x: x[1]) if valid_changes else ("N/A", 0)
    worst_performer = min(valid_changes.items(), key=lambda x: x[1]) if valid_changes else ("N/A", 0)
    
    prompt = f"""Du bist ein erfahrener Web-Analytics-Experte und Kommunikationsprofi für österreichische Medienunternehmen.
Deine Aufgabe: Erstelle einen EXECUTIVE SUMMARY für die Geschäftsleitung - professionell, aber lebendig und handlungsorientiert.

═══════════════════════════════════════════════════════════════
📅 BERICHTSZEITRAUM: {data.get('period', 'N/A')} (KW {current_week})
📊 Datenbasis: {data.get('current_days', 'N/A')} Tage aktuell, {data.get('prev_days', 'N/A')} Tage Vorwoche
{data_quality_section}
═══════════════════════════════════════════════════════════════

🔵 VOL.AT (Vorarlberg Online):
   • Page Impressions: {data.get('vol_pi_week', 0):,} gesamt ({data.get('vol_pi_avg', 0):,.0f}/Tag)
   • Visits: {data.get('vol_visits_week', 0):,} gesamt ({data.get('vol_visits_avg', 0):,.0f}/Tag)
   • Veränderung PI: {vol_pi_change} | Visits: {vol_visits_change}

🟣 VIENNA.AT (Wien Online):
   • Page Impressions: {data.get('vienna_pi_week', 0):,} gesamt ({data.get('vienna_pi_avg', 0):,.0f}/Tag)
   • Visits: {data.get('vienna_visits_week', 0):,} gesamt ({data.get('vienna_visits_avg', 0):,.0f}/Tag)
   • Veränderung PI: {vienna_pi_change} | Visits: {vienna_visits_change}

🏆 TOP-PERFORMER: {best_performer[0]} mit {best_performer[1]:+.1f}%
📉 BEOBACHTEN: {worst_performer[0]} mit {worst_performer[1]:+.1f}%

⚠️ ANOMALIEN:
{data.get('anomalies_text', 'Keine statistischen Anomalien erkannt.')}

═══════════════════════════════════════════════════════════════

DEINE AUFGABE - Erstelle eine Zusammenfassung mit EXAKT dieser Struktur:

**📈 HIGHLIGHT DER WOCHE**
[1 Satz: Was ist die wichtigste positive Nachricht? Beginne mit einer Zahl oder einem starken Statement.]

**🎯 ZUSAMMENFASSUNG**
[2-3 Sätze: Kernbotschaft der Wochenperformance. Vergleiche beide Properties. Nutze konkrete Zahlen.]

**🔍 KONTEXT & EINORDNUNG**
[1-2 Sätze: Ordne die Zahlen ein. Berücksichtige: Dezember = Adventzeit, erhöhter Medienkonsum. 
Wochenenden typischerweise schwächer. Feiertage können Ausreißer verursachen.]

**✅ BEWERTUNG**
[1 Satz: Gesamteinschätzung - ist die Entwicklung positiv/stabil/besorgniserregend?]

STILRICHTLINIEN:
- Schreibe wie ein Analyst, der vor dem Vorstand präsentiert
- Beginne mit dem Wichtigsten (Inverted Pyramid)
- Nutze aktive Sprache: "VIENNA.AT legte um 28% zu" statt "Es wurde ein Wachstum von 28% verzeichnet"
- Bei positiven Zahlen: enthusiastisch aber professionell
- Bei negativen Zahlen: sachlich, lösungsorientiert
- Keine leeren Floskeln wie "es bleibt abzuwarten"
- Max. 180 Wörter insgesamt
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


def send_teams_report(title: str, summary: str, data: Dict, anomalies: List[Dict], image_urls: Dict[str, str] = None):
    """
    Sendet den Wochenbericht an Teams mit optionalen Diagrammen.
    
    Args:
        title: Titel des Berichts
        summary: GPT-generierte Zusammenfassung
        data: Statistik-Daten
        anomalies: Liste erkannter Anomalien
        image_urls: Dict mit Bild-URLs (optional)
    """
    if not TEAMS_WEBHOOK_URL:
        print("⚠️ TEAMS_WEBHOOK_URL nicht konfiguriert")
        return
    
    # Farbe basierend auf Anomalien
    if any(a["severity"] == "critical" for a in anomalies):
        color = "DC3545"  # Rot
    elif any(a["severity"] == "warning" for a in anomalies):
        color = "FFC107"  # Gelb
    else:
        color = "28A745"  # Grün
    
    # Veränderungen formatieren (nur anzeigen wenn valide)
    def format_change(change_val):
        if change_val is None:
            return ""
        return f" ({change_val:+.1f}%)"
    
    # Facts für die Karte - mit Durchschnittswerten
    facts = [
        {"name": "📅 Zeitraum", "value": data.get("period", "N/A")},
        {"name": "📊 VOL.AT PI", "value": f"{data.get('vol_pi_week', 0):,}{format_change(data.get('vol_pi_change'))}"},
        {"name": "📈 VOL.AT Ø/Tag", "value": f"{data.get('vol_pi_avg', 0):,.0f}"},
        {"name": "👥 VOL.AT Visits", "value": f"{data.get('vol_visits_week', 0):,}{format_change(data.get('vol_visits_change'))}"},
        {"name": "📊 VIENNA.AT PI", "value": f"{data.get('vienna_pi_week', 0):,}{format_change(data.get('vienna_pi_change'))}"},
        {"name": "📈 VIENNA.AT Ø/Tag", "value": f"{data.get('vienna_pi_avg', 0):,.0f}"},
        {"name": "👥 VIENNA.AT Visits", "value": f"{data.get('vienna_visits_week', 0):,}{format_change(data.get('vienna_visits_change'))}"},
    ]
    
    # Datenqualitäts-Hinweis wenn nötig
    data_quality_note = data.get("data_quality_note")
    
    # Anomalien-Text - verbesserte Darstellung
    anomaly_text = ""
    if anomalies:
        anomaly_text = "\n\n**⚠️ Tageswert-Anomalien:**\n"
        for a in anomalies[:5]:  # Max 5 anzeigen
            icon = "🔴" if a["severity"] == "critical" else "🟡"
            direction = "über" if a['pct_delta'] > 0 else "unter"
            anomaly_text += f"- {icon} {a['brand']} {a['metric']}: Letzter Tag {abs(a['pct_delta']):.1f}% {direction} Median\n"
    
    # Datenqualitätshinweis formatieren
    quality_text = f"\n\n**📋 Datenhinweis:** {data_quality_note}" if data_quality_note else ""
    
    # Sections aufbauen
    sections = [
        {
            "activityTitle": title,
            "facts": facts,
            "markdown": True
        },
        {
            "text": f"**🤖 KI-Analyse:**\n\n{summary}{anomaly_text}{quality_text}",
            "markdown": True
        }
    ]
    
    # Bilder hinzufügen wenn verfügbar
    if image_urls:
        for chart_name, url in image_urls.items():
            if url:
                sections.append({
                    "title": f"📊 {chart_name}",
                    "images": [{"image": url, "title": chart_name}]
                })
    
    # Dashboard-Link hinzufügen
    potential_action = {
        "@type": "OpenUri",
        "name": "📈 Dashboard öffnen",
        "targets": [
            {"os": "default", "uri": "https://oewa-reporter-ucgucmpvryylvvkhefxyeq.streamlit.app"}
        ]
    }
    
    card = {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "summary": title,
        "themeColor": color,
        "sections": sections,
        "potentialAction": [potential_action]
    }
    
    try:
        response = requests.post(TEAMS_WEBHOOK_URL, json=card, timeout=30)
        if response.status_code == 200:
            print("✅ Teams Bericht gesendet")
        else:
            print(f"⚠️ Teams Fehler: {response.status_code} - {response.text[:200]}")
    except Exception as e:
        print(f"⚠️ Teams Fehler: {e}")


def run_weekly_report():
    """Hauptfunktion für den Wochenbericht"""
    print("=" * 70)
    print("📊 ÖWA WEEKLY REPORT")
    print("=" * 70)
    
    if not AIRTABLE_API_KEY:
        print("❌ AIRTABLE_API_KEY nicht gesetzt!")
        return
    
    # Daten der letzten 14 Tage holen (für Vergleich)
    print("\n📥 Lade Daten aus Airtable...")
    records = get_measurements(days=14)
    print(f"   → {len(records)} Datensätze geladen")
    
    if not records:
        print("❌ Keine Daten gefunden!")
        return
    
    # Daten nach Brand/Metrik gruppieren
    today = date.today()
    week_start = today - timedelta(days=7)
    prev_week_start = today - timedelta(days=14)
    
    # Daten aufbereiten - erweitert für Diagramme
    current_week = {"VOL": {"Page Impressions": [], "Visits": []}, 
                    "Vienna": {"Page Impressions": [], "Visits": []}}
    prev_week = {"VOL": {"Page Impressions": [], "Visits": []}, 
                 "Vienna": {"Page Impressions": [], "Visits": []}}
    
    # Erweiterte Datenstruktur für Diagramme
    chart_data = {
        "VOL": {
            "Page Impressions": {"daily": {}, "weekday_avg": {}},
            "Visits": {"daily": {}, "weekday_avg": {}}
        },
        "Vienna": {
            "Page Impressions": {"daily": {}, "weekday_avg": {}},
            "Visits": {"daily": {}, "weekday_avg": {}}
        }
    }
    weekday_counts = {
        "VOL": {"Page Impressions": {}, "Visits": {}},
        "Vienna": {"Page Impressions": {}, "Visits": {}}
    }
    
    for record in records:
        fields = record.get("fields", {})
        datum_str = fields.get("Datum")
        if not datum_str:
            continue
        
        try:
            datum = date.fromisoformat(datum_str)
        except:
            continue
        
        brand = fields.get("Brand")
        metric = fields.get("Metrik")
        wert = fields.get("Wert")
        
        if not all([brand, metric, wert]):
            continue
        
        if brand not in current_week or metric not in current_week[brand]:
            continue
        
        # Für Wochen-Vergleich
        if datum >= week_start:
            current_week[brand][metric].append(wert)
            
            # Für Diagramme: Tägliche Werte speichern
            chart_data[brand][metric]["daily"][datum_str] = wert
            
            # Für Wochentags-Analyse
            weekday = datum.weekday()
            if weekday not in weekday_counts[brand][metric]:
                weekday_counts[brand][metric][weekday] = []
            weekday_counts[brand][metric][weekday].append(wert)
            
        elif datum >= prev_week_start:
            prev_week[brand][metric].append(wert)
    
    # Wochentags-Durchschnitte berechnen
    for brand in ["VOL", "Vienna"]:
        for metric in ["Page Impressions", "Visits"]:
            for weekday, values in weekday_counts[brand][metric].items():
                if values:
                    chart_data[brand][metric]["weekday_avg"][weekday] = sum(values) / len(values)
    
    # Statistiken berechnen
    print("\n📈 Berechne Statistiken...")
    
    # Anzahl der Tage pro Woche zählen (für Datenqualitätsprüfung)
    current_days_vol = len(current_week["VOL"]["Page Impressions"])
    current_days_vienna = len(current_week["Vienna"]["Page Impressions"])
    prev_days_vol = len(prev_week["VOL"]["Page Impressions"])
    prev_days_vienna = len(prev_week["Vienna"]["Page Impressions"])
    
    # DEBUG: Detaillierte Datenanalyse
    print(f"\n   🔍 DEBUG - Datenanalyse:")
    print(f"   Zeitraum aktuell: {week_start} bis {today} ({current_days_vol} Tage VOL, {current_days_vienna} Vienna)")
    print(f"   Zeitraum Vorwoche: {prev_week_start} bis {week_start - timedelta(days=1)} ({prev_days_vol} Tage VOL, {prev_days_vienna} Vienna)")
    
    print(f"\n   VOL Page Impressions:")
    print(f"   - Aktuelle Woche: {current_week['VOL']['Page Impressions']}")
    print(f"   - Vorwoche: {prev_week['VOL']['Page Impressions']}")
    print(f"   - Summe aktuell: {sum(current_week['VOL']['Page Impressions']):,}")
    print(f"   - Summe Vorwoche: {sum(prev_week['VOL']['Page Impressions']):,}")
    
    print(f"\n   VOL Visits:")
    print(f"   - Aktuelle Woche: {current_week['VOL']['Visits']}")
    print(f"   - Vorwoche: {prev_week['VOL']['Visits']}")
    print(f"   - Summe aktuell: {sum(current_week['VOL']['Visits']):,}")
    print(f"   - Summe Vorwoche: {sum(prev_week['VOL']['Visits']):,}")
    
    data = {
        "period": f"{week_start.strftime('%d.%m.')} - {today.strftime('%d.%m.%Y')}",
        "vol_pi_week": sum(current_week["VOL"]["Page Impressions"]),
        "vol_pi_avg": sum(current_week["VOL"]["Page Impressions"]) / max(1, current_days_vol),
        "vol_visits_week": sum(current_week["VOL"]["Visits"]),
        "vol_visits_avg": sum(current_week["VOL"]["Visits"]) / max(1, current_days_vol),
        "vienna_pi_week": sum(current_week["Vienna"]["Page Impressions"]),
        "vienna_pi_avg": sum(current_week["Vienna"]["Page Impressions"]) / max(1, current_days_vienna),
        "vienna_visits_week": sum(current_week["Vienna"]["Visits"]),
        "vienna_visits_avg": sum(current_week["Vienna"]["Visits"]) / max(1, current_days_vienna),
        # Datenqualität
        "current_days": current_days_vol,
        "prev_days": prev_days_vol,
    }
    
    # Veränderungen berechnen - NUR wenn beide Wochen vergleichbare Datenmenge haben
    prev_vol_pi = sum(prev_week["VOL"]["Page Impressions"])
    prev_vol_visits = sum(prev_week["VOL"]["Visits"])
    prev_vienna_pi = sum(prev_week["Vienna"]["Page Impressions"])
    prev_vienna_visits = sum(prev_week["Vienna"]["Visits"])
    
    # Datenqualitätsprüfung: Mindestens 5 Tage in beiden Wochen für validen Vergleich
    data_quality_ok = prev_days_vol >= 5 and current_days_vol >= 5
    
    if data_quality_ok and prev_vol_pi > 0:
        data["vol_pi_change"] = round((data["vol_pi_week"] - prev_vol_pi) / prev_vol_pi * 100, 1)
    else:
        data["vol_pi_change"] = None
        
    if data_quality_ok and prev_vol_visits > 0:
        data["vol_visits_change"] = round((data["vol_visits_week"] - prev_vol_visits) / prev_vol_visits * 100, 1)
    else:
        data["vol_visits_change"] = None
        
    if data_quality_ok and prev_vienna_pi > 0:
        data["vienna_pi_change"] = round((data["vienna_pi_week"] - prev_vienna_pi) / prev_vienna_pi * 100, 1)
    else:
        data["vienna_pi_change"] = None
        
    if data_quality_ok and prev_vienna_visits > 0:
        data["vienna_visits_change"] = round((data["vienna_visits_week"] - prev_vienna_visits) / prev_vienna_visits * 100, 1)
    else:
        data["vienna_visits_change"] = None
    
    # Datenqualitäts-Hinweis
    if not data_quality_ok:
        data["data_quality_note"] = f"⚠️ Eingeschränkte Vergleichbarkeit: Aktuelle Woche {current_days_vol} Tage, Vorwoche {prev_days_vol} Tage"
        print(f"   ⚠️ Datenqualität: Aktuelle Woche {current_days_vol} Tage, Vorwoche {prev_days_vol} Tage")
    else:
        data["data_quality_note"] = None
    
    vol_pi_str = f"{data['vol_pi_change']:+.1f}%" if data['vol_pi_change'] is not None else "N/A (Daten unvollständig)"
    vol_visits_str = f"{data['vol_visits_change']:+.1f}%" if data['vol_visits_change'] is not None else "N/A (Daten unvollständig)"
    vienna_pi_str = f"{data['vienna_pi_change']:+.1f}%" if data['vienna_pi_change'] is not None else "N/A (Daten unvollständig)"
    vienna_visits_str = f"{data['vienna_visits_change']:+.1f}%" if data['vienna_visits_change'] is not None else "N/A (Daten unvollständig)"
    
    print(f"   VOL.AT PI: {data['vol_pi_week']:,} ({vol_pi_str})")
    print(f"   VOL.AT Visits: {data['vol_visits_week']:,} ({vol_visits_str})")
    print(f"   VIENNA.AT PI: {data['vienna_pi_week']:,} ({vienna_pi_str})")
    print(f"   VIENNA.AT Visits: {data['vienna_visits_week']:,} ({vienna_visits_str})")
    
    # Anomalie-Erkennung (basierend auf Tageswerten)
    print("\n🔍 Anomalie-Erkennung (letzter Tageswert vs. historischer Median)...")
    anomalies = []
    
    for brand in ["VOL", "Vienna"]:
        for metric in ["Page Impressions", "Visits"]:
            all_values = current_week[brand][metric] + prev_week[brand][metric]
            if len(all_values) >= 5:
                stats = calculate_statistics(all_values[:-1])  # Alle außer dem letzten
                if current_week[brand][metric]:
                    latest = current_week[brand][metric][-1]
                    anomaly = detect_anomaly(latest, stats)
                    if anomaly["is_anomaly"]:
                        anomaly["brand"] = brand
                        anomaly["metric"] = metric
                        anomaly["latest_value"] = latest
                        anomaly["median_value"] = stats["median"]
                        anomalies.append(anomaly)
                        print(f"   ⚠️ {brand} {metric}: {anomaly['severity'].upper()}")
                        print(f"      Letzter Tag: {latest:,.0f} | Median: {stats['median']:,.0f} | Abweichung: {anomaly['pct_delta']:+.1f}%")
    
    if not anomalies:
        print("   ✅ Keine Anomalien erkannt")
    
    # Anomalien-Text für GPT - präzisere Beschreibung
    if anomalies:
        anomaly_lines = []
        for a in anomalies:
            direction = "über" if a['pct_delta'] > 0 else "unter"
            anomaly_lines.append(
                f"- {a['brand']} {a['metric']}: Der letzte Tageswert ({a['latest_value']:,.0f}) liegt {abs(a['pct_delta']):.1f}% {direction} dem historischen Median ({a['median_value']:,.0f}). Z-Score: {a['zscore']}"
            )
        data["anomalies_text"] = "\n".join(anomaly_lines)
    else:
        data["anomalies_text"] = "Keine Anomalien erkannt."
    
    # Diagramme erstellen und hochladen
    image_urls = {}
    if PLOTLY_AVAILABLE:
        print("\n📊 Erstelle Diagramme...")
        
        try:
            # Wochentags-Analyse Chart
            weekday_png = create_weekday_chart(chart_data, "Page Impressions")
            if weekday_png:
                print("   → Wochentags-Analyse erstellt")
                url = upload_to_imgur(weekday_png)
                if url:
                    image_urls["Wochentags-Analyse (PI)"] = url
                    print(f"   → Hochgeladen: {url[:50]}...")
            
            # Trend Chart
            trend_png = create_trend_chart(chart_data, "Page Impressions")
            if trend_png:
                print("   → Trend-Diagramm erstellt")
                url = upload_to_imgur(trend_png)
                if url:
                    image_urls["7-Tage-Trend (PI)"] = url
                    print(f"   → Hochgeladen: {url[:50]}...")
        except Exception as e:
            print(f"   ⚠️ Diagramm-Erstellung fehlgeschlagen: {e}")
            print("   → Bericht wird ohne Diagramme gesendet")
    else:
        print("\n⚠️ Plotly nicht verfügbar - keine Diagramme erstellt")
    
    # GPT-Zusammenfassung
    print("\n🤖 Generiere KI-Zusammenfassung...")
    summary = generate_gpt_summary(data)
    print(f"   → {len(summary)} Zeichen generiert")
    
    # Teams-Bericht senden
    print("\n📤 Sende Teams-Bericht...")
    title = f"📊 ÖWA Wochenbericht - KW {today.isocalendar()[1]}"
    send_teams_report(title, summary, data, anomalies, image_urls)
    
    print("\n" + "=" * 70)
    print("✅ WEEKLY REPORT ABGESCHLOSSEN")
    print("=" * 70)


if __name__ == "__main__":
    run_weekly_report()
