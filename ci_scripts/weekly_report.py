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
    
    try:
        # Kaleido für PNG-Export importieren
        import kaleido
    except ImportError:
        print("⚠️ Kaleido nicht verfügbar - keine PNG-Exports möglich")
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
    
    try:
        import kaleido
    except ImportError:
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
    
    prompt = f"""Du bist ein Web-Analytics-Experte für österreichische Medienunternehmen.
Analysiere die folgenden ÖWA-Daten für VOL.AT und VIENNA.AT und erstelle eine kurze, professionelle Zusammenfassung auf Deutsch.

DATEN DER LETZTEN WOCHE:

VOL.AT:
- Page Impressions: {data.get('vol_pi_week', 'N/A'):,} (Durchschnitt/Tag: {data.get('vol_pi_avg', 'N/A'):,.0f})
- Visits: {data.get('vol_visits_week', 'N/A'):,} (Durchschnitt/Tag: {data.get('vol_visits_avg', 'N/A'):,.0f})
- Veränderung vs. Vorwoche PI: {data.get('vol_pi_change', 'N/A')}%
- Veränderung vs. Vorwoche Visits: {data.get('vol_visits_change', 'N/A')}%

VIENNA.AT:
- Page Impressions: {data.get('vienna_pi_week', 'N/A'):,} (Durchschnitt/Tag: {data.get('vienna_pi_avg', 'N/A'):,.0f})
- Visits: {data.get('vienna_visits_week', 'N/A'):,} (Durchschnitt/Tag: {data.get('vienna_visits_avg', 'N/A'):,.0f})
- Veränderung vs. Vorwoche PI: {data.get('vienna_pi_change', 'N/A')}%
- Veränderung vs. Vorwoche Visits: {data.get('vienna_visits_change', 'N/A')}%

ANOMALIEN:
{data.get('anomalies_text', 'Keine Anomalien erkannt.')}

Erstelle eine Zusammenfassung mit:
1. Überblick der Wochenperformance (2-3 Sätze)
2. Wichtige Veränderungen oder Auffälligkeiten
3. Kurze Einschätzung/Empfehlung

Halte die Zusammenfassung prägnant (max. 150 Wörter).
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
    
    # Facts für die Karte
    facts = [
        {"name": "📅 Zeitraum", "value": data.get("period", "N/A")},
        {"name": "📊 VOL.AT PI", "value": f"{data.get('vol_pi_week', 0):,}"},
        {"name": "👥 VOL.AT Visits", "value": f"{data.get('vol_visits_week', 0):,}"},
        {"name": "📊 VIENNA.AT PI", "value": f"{data.get('vienna_pi_week', 0):,}"},
        {"name": "👥 VIENNA.AT Visits", "value": f"{data.get('vienna_visits_week', 0):,}"},
    ]
    
    # Anomalien-Text
    anomaly_text = ""
    if anomalies:
        anomaly_text = "\n\n**⚠️ Anomalien:**\n"
        for a in anomalies[:5]:  # Max 5 anzeigen
            icon = "🔴" if a["severity"] == "critical" else "🟡"
            anomaly_text += f"- {icon} {a['brand']} {a['metric']}: {a['pct_delta']:+.1f}% (Z={a['zscore']:.1f})\n"
    
    # Sections aufbauen
    sections = [
        {
            "activityTitle": title,
            "facts": facts,
            "markdown": True
        },
        {
            "text": f"**🤖 KI-Analyse:**\n\n{summary}{anomaly_text}",
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
    
    data = {
        "period": f"{week_start.strftime('%d.%m.')} - {today.strftime('%d.%m.%Y')}",
        "vol_pi_week": sum(current_week["VOL"]["Page Impressions"]),
        "vol_pi_avg": sum(current_week["VOL"]["Page Impressions"]) / max(1, len(current_week["VOL"]["Page Impressions"])),
        "vol_visits_week": sum(current_week["VOL"]["Visits"]),
        "vol_visits_avg": sum(current_week["VOL"]["Visits"]) / max(1, len(current_week["VOL"]["Visits"])),
        "vienna_pi_week": sum(current_week["Vienna"]["Page Impressions"]),
        "vienna_pi_avg": sum(current_week["Vienna"]["Page Impressions"]) / max(1, len(current_week["Vienna"]["Page Impressions"])),
        "vienna_visits_week": sum(current_week["Vienna"]["Visits"]),
        "vienna_visits_avg": sum(current_week["Vienna"]["Visits"]) / max(1, len(current_week["Vienna"]["Visits"])),
    }
    
    # Veränderungen berechnen
    prev_vol_pi = sum(prev_week["VOL"]["Page Impressions"])
    prev_vol_visits = sum(prev_week["VOL"]["Visits"])
    prev_vienna_pi = sum(prev_week["Vienna"]["Page Impressions"])
    prev_vienna_visits = sum(prev_week["Vienna"]["Visits"])
    
    data["vol_pi_change"] = round((data["vol_pi_week"] - prev_vol_pi) / max(1, prev_vol_pi) * 100, 1) if prev_vol_pi else 0
    data["vol_visits_change"] = round((data["vol_visits_week"] - prev_vol_visits) / max(1, prev_vol_visits) * 100, 1) if prev_vol_visits else 0
    data["vienna_pi_change"] = round((data["vienna_pi_week"] - prev_vienna_pi) / max(1, prev_vienna_pi) * 100, 1) if prev_vienna_pi else 0
    data["vienna_visits_change"] = round((data["vienna_visits_week"] - prev_vienna_visits) / max(1, prev_vienna_visits) * 100, 1) if prev_vienna_visits else 0
    
    print(f"   VOL.AT PI: {data['vol_pi_week']:,} ({data['vol_pi_change']:+.1f}%)")
    print(f"   VOL.AT Visits: {data['vol_visits_week']:,} ({data['vol_visits_change']:+.1f}%)")
    print(f"   VIENNA.AT PI: {data['vienna_pi_week']:,} ({data['vienna_pi_change']:+.1f}%)")
    print(f"   VIENNA.AT Visits: {data['vienna_visits_week']:,} ({data['vienna_visits_change']:+.1f}%)")
    
    # Anomalie-Erkennung
    print("\n🔍 Anomalie-Erkennung...")
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
                        anomalies.append(anomaly)
                        print(f"   ⚠️ {brand} {metric}: {anomaly['severity'].upper()} (Z={anomaly['zscore']}, {anomaly['pct_delta']:+.1f}%)")
    
    if not anomalies:
        print("   ✅ Keine Anomalien erkannt")
    
    # Anomalien-Text für GPT
    if anomalies:
        data["anomalies_text"] = "\n".join([
            f"- {a['brand']} {a['metric']}: {a['severity'].upper()}, Z-Score={a['zscore']}, Abweichung={a['pct_delta']:+.1f}%"
            for a in anomalies
        ])
    else:
        data["anomalies_text"] = "Keine Anomalien erkannt."
    
    # Diagramme erstellen und hochladen
    image_urls = {}
    if PLOTLY_AVAILABLE:
        print("\n📊 Erstelle Diagramme...")
        
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
