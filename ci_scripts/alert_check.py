#!/usr/bin/env python3
"""
Alert Check Script - Tägliches Alarming
========================================
Prüft nach dem Daily Ingest ob kritische Schwellenwerte unterschritten wurden.

Schwellenwerte:
- Absolute Mindestwerte pro Tag
- Prozentuale Abweichung vs. Vorwoche
- Z-Score basierte Anomalie-Erkennung

Bei Alarm:
- GPT analysiert den Trendverlauf der letzten 7 Tage
- Erstellt professionellen Alarm-Report
- Sendet an MS Teams

Nutzung:
    python ci_scripts/alert_check.py
    python ci_scripts/alert_check.py --date 2025-12-02
"""

import os
import json
import requests
import statistics
from datetime import date, datetime, timedelta
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import argparse

# =============================================================================
# KONFIGURATION
# =============================================================================
AIRTABLE_API_KEY = os.environ.get("AIRTABLE_API_KEY", "")
AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID", "appTIeod85xnBy7Vn")
TEAMS_WEBHOOK_URL = os.environ.get("TEAMS_WEBHOOK_URL", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

# =============================================================================
# SCHWELLENWERTE - Angepasst an VOL.AT / VIENNA.AT Daten
# =============================================================================

@dataclass
class ThresholdConfig:
    """Schwellenwert-Konfiguration für eine Metrik"""
    # Absolute Mindestwerte (Tagesbasis)
    min_warning: int      # Unter diesem Wert: Warning
    min_critical: int     # Unter diesem Wert: Critical
    min_emergency: int    # Unter diesem Wert: Emergency (Totalausfall?)
    
    # Prozentuale Abweichung vs. Vorwoche (negativ = Rückgang)
    pct_warning: float    # z.B. -0.15 = -15%
    pct_critical: float   # z.B. -0.25 = -25%
    pct_emergency: float  # z.B. -0.40 = -40%


# Schwellenwerte für VOL.AT (größere Site)
THRESHOLDS_VOL = {
    "Page Impressions": ThresholdConfig(
        min_warning=600000,     # < 600.000 PI/Tag
        min_critical=400000,    # < 400.000 PI/Tag
        min_emergency=200000,   # < 200.000 PI/Tag
        pct_warning=-0.15,      # -15%
        pct_critical=-0.25,     # -25%
        pct_emergency=-0.40     # -40%
    ),
    "Visits": ThresholdConfig(
        min_warning=200000,     # < 200.000 Visits/Tag
        min_critical=150000,    # < 150.000 Visits/Tag
        min_emergency=80000,    # < 80.000 Visits/Tag
        pct_warning=-0.15,
        pct_critical=-0.25,
        pct_emergency=-0.40
    )
}

# Schwellenwerte für VIENNA.AT (kleinere Site)
THRESHOLDS_VIENNA = {
    "Page Impressions": ThresholdConfig(
        min_warning=150000,     # < 150.000 PI/Tag
        min_critical=100000,    # < 100.000 PI/Tag
        min_emergency=50000,    # < 50.000 PI/Tag
        pct_warning=-0.15,
        pct_critical=-0.25,
        pct_emergency=-0.40
    ),
    "Visits": ThresholdConfig(
        min_warning=60000,      # < 60.000 Visits/Tag
        min_critical=40000,     # < 40.000 Visits/Tag
        min_emergency=20000,    # < 20.000 Visits/Tag
        pct_warning=-0.15,
        pct_critical=-0.25,
        pct_emergency=-0.40
    )
}

# Z-Score Schwellenwerte
ZSCORE_WARNING = 2.0
ZSCORE_CRITICAL = 2.5
ZSCORE_EMERGENCY = 3.0


@dataclass
class Alert:
    """Ein einzelner Alarm"""
    severity: str           # "warning", "critical", "emergency"
    alert_type: str         # "absolute", "percentage", "zscore"
    brand: str
    metric: str
    date: date
    actual_value: int
    threshold_value: float
    comparison_value: Optional[int] = None
    pct_change: Optional[float] = None
    zscore: Optional[float] = None
    message: str = ""


# =============================================================================
# AIRTABLE CLIENT
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
            
        try:
            response = requests.get(url, headers=headers, params=params, timeout=30)
            if response.status_code != 200:
                print(f"⚠️ Airtable Fehler: {response.status_code}")
                break
                
            data = response.json()
            records.extend(data.get("records", []))
            
            offset = data.get("offset")
            if not offset:
                break
        except Exception as e:
            print(f"⚠️ Airtable Fehler: {e}")
            break
    
    return records


def parse_measurements(records: List[Dict]) -> Dict[str, Dict[str, Dict[date, int]]]:
    """
    Parst Airtable Records in strukturierte Daten.
    
    HINWEIS: Unique Clients sind vom Alerting ausgeschlossen, da sie 2 Tage
    verzögert in der INFOnline API verfügbar sind.
    
    Returns:
        {brand: {metric: {date: value}}}
    """
    data = {
        "VOL": {"Page Impressions": {}, "Visits": {}},
        "Vienna": {"Page Impressions": {}, "Visits": {}}
    }
    # KEIN Unique Clients - diese sind 2 Tage verzögert und würden falsche Alerts auslösen
    
    for record in records:
        fields = record.get("fields", {})
        datum_str = fields.get("Datum")
        brand = fields.get("Brand")
        metric = fields.get("Metrik")
        wert = fields.get("Wert")
        
        if not all([datum_str, brand, metric, wert]):
            continue
        
        try:
            datum = date.fromisoformat(datum_str)
        except:
            continue
        
        if brand in data and metric in data[brand]:
            data[brand][metric][datum] = wert
    
    return data


# =============================================================================
# ANOMALIE-ERKENNUNG
# =============================================================================

def calculate_zscore(value: float, values: List[float]) -> float:
    """Berechnet robusten Z-Score mit MAD"""
    if len(values) < 3:
        return 0.0
    
    median = statistics.median(values)
    mad = statistics.median([abs(x - median) for x in values])
    mad_scaled = mad * 1.4826  # Skalierung für Normalverteilung
    
    if mad_scaled < 0.001:
        mad_scaled = 0.001
    
    zscore = (value - median) / mad_scaled
    return max(-10, min(10, zscore))  # Clamp


def check_thresholds(
    brand: str,
    metric: str,
    current_value: int,
    prev_week_value: Optional[int],
    historical_values: List[int],
    target_date: date
) -> List[Alert]:
    """
    Prüft alle Schwellenwerte für eine Brand/Metrik Kombination.
    
    Returns:
        Liste der ausgelösten Alerts
    """
    alerts = []
    thresholds = THRESHOLDS_VOL if brand == "VOL" else THRESHOLDS_VIENNA
    config = thresholds.get(metric)
    
    if not config:
        return alerts
    
    # 1. ABSOLUTE SCHWELLENWERTE
    if current_value < config.min_emergency:
        alerts.append(Alert(
            severity="emergency",
            alert_type="absolute",
            brand=brand,
            metric=metric,
            date=target_date,
            actual_value=current_value,
            threshold_value=config.min_emergency,
            message=f"🚨 EMERGENCY: {brand} {metric} extrem niedrig! "
                   f"Aktuell: {current_value:,} (Min: {config.min_emergency:,})"
        ))
    elif current_value < config.min_critical:
        alerts.append(Alert(
            severity="critical",
            alert_type="absolute",
            brand=brand,
            metric=metric,
            date=target_date,
            actual_value=current_value,
            threshold_value=config.min_critical,
            message=f"🔴 CRITICAL: {brand} {metric} unter kritischem Minimum! "
                   f"Aktuell: {current_value:,} (Min: {config.min_critical:,})"
        ))
    elif current_value < config.min_warning:
        alerts.append(Alert(
            severity="warning",
            alert_type="absolute",
            brand=brand,
            metric=metric,
            date=target_date,
            actual_value=current_value,
            threshold_value=config.min_warning,
            message=f"🟡 WARNING: {brand} {metric} unter Minimum! "
                   f"Aktuell: {current_value:,} (Min: {config.min_warning:,})"
        ))
    
    # 2. PROZENTUALE ABWEICHUNG VS. VORWOCHE
    if prev_week_value and prev_week_value > 0:
        pct_change = (current_value - prev_week_value) / prev_week_value
        
        if pct_change <= config.pct_emergency:
            alerts.append(Alert(
                severity="emergency",
                alert_type="percentage",
                brand=brand,
                metric=metric,
                date=target_date,
                actual_value=current_value,
                threshold_value=config.pct_emergency,
                comparison_value=prev_week_value,
                pct_change=pct_change,
                message=f"🚨 EMERGENCY: {brand} {metric} massiver Einbruch! "
                       f"{pct_change*100:+.1f}% vs. Vorwoche"
            ))
        elif pct_change <= config.pct_critical:
            alerts.append(Alert(
                severity="critical",
                alert_type="percentage",
                brand=brand,
                metric=metric,
                date=target_date,
                actual_value=current_value,
                threshold_value=config.pct_critical,
                comparison_value=prev_week_value,
                pct_change=pct_change,
                message=f"🔴 CRITICAL: {brand} {metric} starker Rückgang! "
                       f"{pct_change*100:+.1f}% vs. Vorwoche"
            ))
        elif pct_change <= config.pct_warning:
            alerts.append(Alert(
                severity="warning",
                alert_type="percentage",
                brand=brand,
                metric=metric,
                date=target_date,
                actual_value=current_value,
                threshold_value=config.pct_warning,
                comparison_value=prev_week_value,
                pct_change=pct_change,
                message=f"🟡 WARNING: {brand} {metric} Rückgang! "
                       f"{pct_change*100:+.1f}% vs. Vorwoche"
            ))
    
    # 3. Z-SCORE ANOMALIE
    if len(historical_values) >= 5:
        zscore = calculate_zscore(current_value, historical_values)
        
        if zscore <= -ZSCORE_EMERGENCY:
            alerts.append(Alert(
                severity="emergency",
                alert_type="zscore",
                brand=brand,
                metric=metric,
                date=target_date,
                actual_value=current_value,
                threshold_value=-ZSCORE_EMERGENCY,
                zscore=zscore,
                message=f"🚨 EMERGENCY: {brand} {metric} statistische Anomalie! "
                       f"Z-Score: {zscore:.1f}"
            ))
        elif zscore <= -ZSCORE_CRITICAL:
            alerts.append(Alert(
                severity="critical",
                alert_type="zscore",
                brand=brand,
                metric=metric,
                date=target_date,
                actual_value=current_value,
                threshold_value=-ZSCORE_CRITICAL,
                zscore=zscore,
                message=f"🔴 CRITICAL: {brand} {metric} Anomalie erkannt! "
                       f"Z-Score: {zscore:.1f}"
            ))
        elif zscore <= -ZSCORE_WARNING:
            alerts.append(Alert(
                severity="warning",
                alert_type="zscore",
                brand=brand,
                metric=metric,
                date=target_date,
                actual_value=current_value,
                threshold_value=-ZSCORE_WARNING,
                zscore=zscore,
                message=f"🟡 WARNING: {brand} {metric} leichte Anomalie! "
                       f"Z-Score: {zscore:.1f}"
            ))
    
    return alerts


# =============================================================================
# GPT ALERT INTERPRETATION
# =============================================================================

def generate_alert_analysis(alerts: List[Alert], trend_data: Dict, target_date: date) -> str:
    """
    Generiert eine GPT-basierte Analyse der Alerts mit Trendverlauf.
    
    Args:
        alerts: Liste der erkannten Alerts
        trend_data: Wochendaten für Kontext
        target_date: Datum der Abweichung
        
    Returns:
        GPT-generierter Analyse-Text
    """
    if not OPENAI_API_KEY:
        return "⚠️ GPT-Analyse nicht verfügbar (API Key fehlt)"
    
    weekday_names = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
    weekday_name = weekday_names[target_date.weekday()]
    
    # Alerts formatieren - MIT GENAUEN DATEN
    alert_text = "\n".join([
        f"- {a.severity.upper()}: {a.brand} {a.metric}\n"
        f"  📅 Abweichungsdatum: {a.date.strftime('%d.%m.%Y')} ({weekday_name})\n"
        f"  📊 {a.message}"
        for a in alerts
    ])
    
    # Trend-Daten formatieren
    trend_text = ""
    for brand in ["VOL", "Vienna"]:
        if brand in trend_data:
            trend_text += f"\n{brand}:\n"
            for metric in ["Page Impressions", "Visits"]:
                if metric in trend_data[brand]:
                    values = trend_data[brand][metric]
                    if values:
                        trend_text += f"  {metric} (letzte 7 Tage): {', '.join(f'{v:,}' for v in values[-7:])}\n"
    
    prompt = f"""Du bist ein erfahrener Web-Analytics-Experte für österreichische Medienunternehmen.

KONTEXT:
Berichtsdatum: {datetime.now().strftime('%d.%m.%Y %H:%M')} Uhr
Analysiertes Datum (Abweichung): {target_date.strftime('%d.%m.%Y')} ({weekday_name})

ERKANNTE ALERTS:
{alert_text}

TRENDVERLAUF DER LETZTEN 7 TAGE:
{trend_text}

Aufgaben:
1. Analysiere die Alerts und den Trendverlauf - nenne das konkrete Abweichungsdatum!
2. Identifiziere mögliche Ursachen (Feiertage, technische Probleme, saisonale Effekte, etc.)
3. Bewerte die Kritikalität für das Geschäft
4. Gib eine klare Handlungsempfehlung

FORMAT (max. 200 Wörter):
**🔍 ANALYSE**
[Nenne das konkrete Datum der Abweichung und ordne sie ein]

**📊 TREND-BEWERTUNG**
[Basierend auf den letzten 7 Tagen]

**💡 EMPFEHLUNG**
[Konkrete Handlungsempfehlung]
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
        else:
            return f"⚠️ GPT-Fehler: {response.status_code}"
    except Exception as e:
        return f"⚠️ GPT-Fehler: {str(e)}"


# =============================================================================
# TEAMS NOTIFICATION
# =============================================================================

def send_alert_to_teams(alerts: List[Alert], analysis: str, target_date: date):
    """Sendet Alarm-Report an Teams"""
    if not TEAMS_WEBHOOK_URL:
        print("⚠️ TEAMS_WEBHOOK_URL nicht konfiguriert")
        return
    
    # Höchsten Severity bestimmen
    severities = [a.severity for a in alerts]
    if "emergency" in severities:
        color = "8B0000"  # Dunkelrot
        icon = "🚨"
        title = "EMERGENCY ALERT"
    elif "critical" in severities:
        color = "DC3545"  # Rot
        icon = "🔴"
        title = "CRITICAL ALERT"
    else:
        color = "FFC107"  # Gelb
        icon = "🟡"
        title = "WARNING ALERT"
    
    # Alerts gruppieren - MIT GENAUEN DATEN
    alert_lines = []
    for a in alerts:
        sev_icon = "🚨" if a.severity == "emergency" else "🔴" if a.severity == "critical" else "🟡"
        alert_lines.append(
            f"{sev_icon} **{a.brand} {a.metric}**\n"
            f"   📅 Abweichungsdatum: **{a.date.strftime('%d.%m.%Y')}**\n"
            f"   {a.message}"
        )
    
    # Facts - mit klarer Unterscheidung
    weekday_names = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
    weekday_name = weekday_names[target_date.weekday()]
    
    facts = [
        {"name": "📅 Abweichungsdatum", "value": f"**{target_date.strftime('%d.%m.%Y')}** ({weekday_name})"},
        {"name": "⏰ Bericht erstellt", "value": datetime.now().strftime('%d.%m.%Y %H:%M') + " Uhr"},
        {"name": "🔔 Anzahl Alerts", "value": str(len(alerts))},
        {"name": "⚠️ Höchster Level", "value": max(severities).upper()},
    ]
    
    # Card erstellen
    card = {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "summary": f"ÖWA {title} - Abweichungen am {target_date.strftime('%d.%m.%Y')}",
        "themeColor": color,
        "sections": [
            {
                "activityTitle": f"{icon} ÖWA {title}",
                "activitySubtitle": f"Anomalien am {target_date.strftime('%d.%m.%Y')} erkannt",
                "facts": facts,
                "markdown": True
            },
            {
                "title": "📋 Erkannte Probleme (mit Datum)",
                "text": "\n\n".join(alert_lines),
                "markdown": True
            },
            {
                "title": "🤖 KI-Analyse & Empfehlung",
                "text": analysis,
                "markdown": True
            }
        ],
        "potentialAction": [{
            "@type": "OpenUri",
            "name": "📈 Dashboard öffnen",
            "targets": [{"os": "default", "uri": "https://oewa-reporter-ucgucmpvryylvvkhefxyeq.streamlit.app"}]
        }]
    }
    
    try:
        response = requests.post(TEAMS_WEBHOOK_URL, json=card, timeout=10)
        if response.status_code == 200:
            print("✅ Alert-Report an Teams gesendet")
        else:
            print(f"⚠️ Teams Fehler: {response.status_code}")
    except Exception as e:
        print(f"⚠️ Teams Fehler: {e}")


# =============================================================================
# MAIN
# =============================================================================

def run_alert_check(target_date: date = None):
    """Hauptfunktion für den Alert-Check"""
    print("=" * 70)
    print("🚨 ÖWA ALERT CHECK")
    print("=" * 70)
    
    if not AIRTABLE_API_KEY:
        print("❌ AIRTABLE_API_KEY nicht gesetzt!")
        return
    
    target_date = target_date or (date.today() - timedelta(days=1))
    prev_week_date = target_date - timedelta(days=7)
    
    print(f"\n📅 Prüfe Datum: {target_date.isoformat()}")
    print(f"📅 Vergleich mit: {prev_week_date.isoformat()}")
    
    # Daten laden
    print("\n📥 Lade Daten aus Airtable...")
    records = get_measurements(days=14)
    print(f"   → {len(records)} Datensätze geladen")
    
    if not records:
        print("❌ Keine Daten gefunden!")
        return
    
    # Daten parsen
    data = parse_measurements(records)
    
    # Alerts sammeln
    all_alerts = []
    trend_data = {"VOL": {}, "Vienna": {}}
    
    print("\n🔍 Prüfe Schwellenwerte...")
    
    for brand in ["VOL", "Vienna"]:
        for metric in ["Page Impressions", "Visits"]:
            # Werte holen
            metric_data = data[brand][metric]
            
            current_value = metric_data.get(target_date)
            prev_week_value = metric_data.get(prev_week_date)
            
            # Historische Werte (ohne aktuellen Tag)
            historical = [v for d, v in sorted(metric_data.items()) if d < target_date]
            
            # Trend-Daten speichern
            trend_data[brand][metric] = historical[-7:] if historical else []
            
            if current_value is None:
                print(f"   ⚠️ {brand} {metric}: Keine Daten für {target_date}")
                continue
            
            # Schwellenwerte prüfen
            alerts = check_thresholds(
                brand=brand,
                metric=metric,
                current_value=current_value,
                prev_week_value=prev_week_value,
                historical_values=historical,
                target_date=target_date
            )
            
            if alerts:
                for a in alerts:
                    print(f"   {a.message}")
                all_alerts.extend(alerts)
            else:
                print(f"   ✅ {brand} {metric}: {current_value:,} - OK")
    
    # Ergebnis
    print("\n" + "=" * 70)
    
    if not all_alerts:
        print("✅ KEINE ALERTS - Alle Werte im normalen Bereich")
        return
    
    # Alerts nach Severity sortieren
    severity_order = {"emergency": 0, "critical": 1, "warning": 2}
    all_alerts.sort(key=lambda a: severity_order.get(a.severity, 99))
    
    print(f"⚠️ {len(all_alerts)} ALERTS ERKANNT")
    
    # GPT-Analyse
    print("\n🤖 Generiere KI-Analyse...")
    analysis = generate_alert_analysis(all_alerts, trend_data, target_date)
    print(f"   → {len(analysis)} Zeichen generiert")
    
    # An Teams senden
    print("\n📤 Sende Alert-Report an Teams...")
    send_alert_to_teams(all_alerts, analysis, target_date)
    
    print("\n" + "=" * 70)
    print("✅ ALERT CHECK ABGESCHLOSSEN")
    print("=" * 70)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ÖWA Alert Check")
    parser.add_argument("--date", type=str, help="Datum im Format YYYY-MM-DD")
    args = parser.parse_args()
    
    target_date = None
    if args.date:
        target_date = date.fromisoformat(args.date)
    
    run_alert_check(target_date)

