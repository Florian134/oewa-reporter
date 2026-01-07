#!/usr/bin/env python3
"""
Daily Ingestion Script - Erweiterte Version
=============================================
Wird von GitLab CI/CD ausgeführt, getriggert durch Airtable Automation.

Funktionen:
1. INFOnline API abrufen (Web + App, alle Metriken)
2. Daten in Airtable speichern
3. Wochentags-Alerting (±10% Schwelle)
4. Bei Anomalien: Teams Benachrichtigung mit GPT-Analyse

Neue Properties (v2.0):
- VOL.AT Web + App
- VIENNA.AT Web + App
- Homepage PI (nur Web)
- Unique Clients (alle)
"""

import os
import json
import requests
import statistics
from datetime import date, datetime, timedelta
from typing import List, Dict, Optional, Tuple

# =============================================================================
# KONFIGURATION (aus GitLab CI/CD Variables)
# =============================================================================
INFONLINE_API_KEY = os.environ.get("INFONLINE_API_KEY", "")
AIRTABLE_API_KEY = os.environ.get("AIRTABLE_API_KEY", "")
AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID", "")  # Muss in CI/CD Variables gesetzt sein
TEAMS_WEBHOOK_URL = os.environ.get("TEAMS_WEBHOOK_URL", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

# Alerting-Schwellenwert (±10%)
ALERT_THRESHOLD_PCT = 0.10

# Daten-Verzögerung (Tage) - INFOnline API liefert erst nach ~2 Tagen finale Daten
STANDARD_DELAY_DAYS = 2  # PI, Visits, Homepage PI

# =============================================================================
# SITES KONFIGURATION - Erweitert für Web + iOS + Android
# =============================================================================
SITES = [
    # === WEB ===
    {"name": "VOL.AT Web", "site_id": "at_w_atvol", "brand": "VOL", "surface": "Web"},
    {"name": "VIENNA.AT Web", "site_id": "at_w_atvienna", "brand": "Vienna", "surface": "Web"},
    
    # === iOS ===
    {"name": "VOL.AT iOS", "site_id": "at_i_volat", "brand": "VOL", "surface": "iOS"},
    {"name": "VIENNA.AT iOS", "site_id": "at_i_viennaat", "brand": "Vienna", "surface": "iOS"},
    
    # === Android ===
    {"name": "VOL.AT Android", "site_id": "at_a_volat", "brand": "VOL", "surface": "Android"},
    {"name": "VIENNA.AT Android", "site_id": "at_a_viennaat", "brand": "Vienna", "surface": "Android"},
]

# Homepage Sites (nur Web, Belegungseinheiten)
HOMEPAGE_SITES = [
    {"name": "VOL.AT Homepage", "site_id": "BE000072", "brand": "VOL", "surface": "Web"},
    {"name": "VIENNA.AT Homepage", "site_id": "BE000043", "brand": "Vienna", "surface": "Web"},
]

# Standard-Metriken für alle Sites
# HINWEIS: Unique Clients sind erst nach ~2 Tagen in der API verfügbar!
METRICS_STANDARD = ["pageimpressions", "visits"]  # Für gestern verfügbar
METRICS_DELAYED = ["uniqueclients"]  # Brauchen 2-3 Tage Verzögerung
UC_DELAY_DAYS = 3  # Unique Clients werden 3 Tage verzögert importiert

METRICS_MAP = {
    "pageimpressions": "Page Impressions",
    "visits": "Visits",
    "uniqueclients": "Unique Clients"
}

# API-Feldnamen für Wert-Extraktion
VALUE_FIELDS = {
    "pageimpressions": "pis",
    "visits": "visits",
    "uniqueclients": "uclients"  # KORRIGIERT: war "unique_clients", richtig ist "uclients"
}


def fetch_infonline_data(site_id: str, metric: str, target_date: date) -> dict:
    """Ruft Daten von der INFOnline API ab"""
    url = f"https://reportingapi.infonline.de/api/v1/{metric}"
    params = {
        "site": site_id,
        "date": target_date.isoformat(),
        "aggregation": "DAY"
    }
    headers = {
        "authorization": INFONLINE_API_KEY,
        "Accept": "application/json"
    }
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=30)
        if response.status_code == 200:
            return {"success": True, "data": response.json()}
        elif response.status_code == 404:
            return {"success": False, "error": "Keine Daten verfügbar"}
        else:
            return {"success": False, "error": f"HTTP {response.status_code}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def extract_value(data: dict, metric_key: str) -> Tuple[Optional[int], bool]:
    """
    Extrahiert den Wert aus der API-Response.
    
    Returns:
        Tuple[value, preliminary]
    """
    if not isinstance(data, dict) or "data" not in data:
        return None, True
    
    api_data = data["data"]
    value_field = VALUE_FIELDS.get(metric_key, metric_key)
    
    # IOM-Daten (hochgerechnet)
    if "iom" in api_data and len(api_data["iom"]) > 0:
        iom_entry = api_data["iom"][0]
        value = iom_entry.get(value_field)
        preliminary = iom_entry.get("preliminary", True)
        return value, preliminary
    
    return None, True


def check_existing_records(target_date: date) -> set:
    """Prüft welche Records für ein Datum bereits in Airtable existieren"""
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/Measurements"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    
    existing_keys = set()
    offset = None
    
    try:
        while True:
            params = {
                "filterByFormula": f"{{Datum}} = '{target_date.isoformat()}'",
                "fields[]": ["Unique Key"],
                "pageSize": 100
            }
            if offset:
                params["offset"] = offset
                
            response = requests.get(url, headers=headers, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                for record in data.get("records", []):
                    unique_key = record.get("fields", {}).get("Unique Key")
                    if unique_key:
                        existing_keys.add(unique_key)
                
                offset = data.get("offset")
                if not offset:
                    break
            else:
                break
                
        print(f"   → {len(existing_keys)} existierende Records für {target_date} gefunden")
    except Exception as e:
        print(f"   ⚠️ Fehler beim Prüfen existierender Records: {e}")
    
    return existing_keys


def check_key_exists(unique_key: str) -> bool:
    """
    Prüft ob ein spezifischer Unique Key bereits in Airtable existiert.
    
    Diese Funktion wird als LETZTE Absicherung vor dem Insert verwendet,
    um Race Conditions zwischen parallelen Pipelines zu verhindern.
    """
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/Measurements"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    
    try:
        # Escape single quotes in the key for Airtable formula
        escaped_key = unique_key.replace("'", "\\'")
        params = {
            "filterByFormula": f"{{Unique Key}} = '{escaped_key}'",
            "fields[]": ["Unique Key"],
            "maxRecords": 1
        }
        
        response = requests.get(url, headers=headers, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            return len(data.get("records", [])) > 0
    except Exception:
        pass
    
    return False


def save_to_airtable(records: list, existing_keys: set = None, double_check: bool = True) -> dict:
    """
    Speichert Records in Airtable mit robuster Duplikat-Prüfung.
    
    Args:
        records: Liste von Records zum Speichern
        existing_keys: Set von bereits bekannten Unique Keys (erste Prüfebene)
        double_check: Wenn True, wird jeder Key nochmal einzeln geprüft (zweite Prüfebene)
    
    Die doppelte Prüfung verhindert Duplikate bei parallelen Pipeline-Läufen:
    1. Erste Prüfung: Gegen existing_keys Set (schnell, aber evtl. veraltet)
    2. Zweite Prüfung: Direkt gegen Airtable vor jedem Insert (langsamer, aber aktuell)
    """
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/Measurements"
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json"
    }
    
    results = {"created": 0, "skipped": 0, "skipped_double_check": 0, "errors": []}
    
    # ERSTE PRÜFUNG: Gegen existing_keys Set filtern
    if existing_keys:
        new_records = []
        for record in records:
            unique_key = record.get("fields", {}).get("Unique Key")
            if unique_key and unique_key in existing_keys:
                results["skipped"] += 1
            else:
                new_records.append(record)
        records = new_records
    
    if not records:
        print("   ℹ️ Keine neuen Records zum Speichern")
        return results
    
    # ZWEITE PRÜFUNG (optional): Jeden Key nochmal einzeln prüfen vor dem Insert
    # Dies verhindert Duplikate bei parallelen Pipeline-Läufen
    if double_check:
        verified_records = []
        for record in records:
            unique_key = record.get("fields", {}).get("Unique Key")
            if unique_key and check_key_exists(unique_key):
                results["skipped_double_check"] += 1
                print(f"   ⚠️ Double-Check: {unique_key} existiert bereits - übersprungen")
            else:
                verified_records.append(record)
        records = verified_records
    
    if not records:
        print("   ℹ️ Nach Double-Check: Keine neuen Records zum Speichern")
        return results
    
    # Batch-Insert (max 10 pro Request)
    for i in range(0, len(records), 10):
        batch = records[i:i+10]
        try:
            response = requests.post(
                url,
                headers=headers,
                json={"records": batch},
                timeout=30
            )
            if response.status_code in (200, 201):
                results["created"] += len(batch)
            else:
                # Bei Fehler prüfen ob es ein Duplikat-Fehler ist
                error_text = response.text[:200]
                results["errors"].append(f"Batch {i//10 + 1}: {error_text}")
        except Exception as e:
            results["errors"].append(f"Batch {i//10 + 1}: {str(e)}")
    
    return results


def get_historical_data(brand: str, surface: str, metric: str, weekday: int, weeks: int = 6) -> List[Dict]:
    """
    Holt historische Daten für den gleichen Wochentag der letzten X Wochen.
    
    WICHTIG: Schließt Monatsdaten (_MONTH_ im Unique Key) aus, da diese aggregierte
    Werte enthalten und den Wochentags-Vergleich verfälschen würden.
    
    Args:
        brand: "VOL" oder "Vienna"
        surface: "Web" oder "App"
        metric: "Page Impressions", "Visits", etc.
        weekday: 0=Montag, 6=Sonntag
        weeks: Anzahl der Wochen zurück
    
    Returns:
        Liste von Dicts mit {"date": date, "value": int}
    """
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/Measurements"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    
    # Formel für Airtable: Brand + Plattform + Metrik
    # WICHTIG: Monatsdaten ausschließen! Diese haben "_MONTH_" im Unique Key
    # und verfälschen den Wochentags-Vergleich (z.B. 30.11. = Sonntag hat sowohl
    # Tagesdaten ~670k als auch Monatssumme ~24 Mio)
    formula = f"AND({{Brand}} = '{brand}', {{Plattform}} = '{surface}', {{Metrik}} = '{metric}', SEARCH('_MONTH_', {{Unique Key}}) = 0)"
    
    try:
        params = {
            "filterByFormula": formula,
            "fields[]": ["Datum", "Wert"],
            "sort[0][field]": "Datum",
            "sort[0][direction]": "desc",
            "pageSize": 100
        }
        
        response = requests.get(url, headers=headers, params=params, timeout=30)
        
        if response.status_code != 200:
            return []
        
        data = response.json()
        records = data.get("records", [])
        
        # Nur gleiche Wochentage filtern - MIT DATUM
        matching_data = []
        for record in records:
            fields = record.get("fields", {})
            datum_str = fields.get("Datum")
            wert = fields.get("Wert")
            
            if datum_str and wert:
                try:
                    datum = date.fromisoformat(datum_str)
                    if datum.weekday() == weekday:
                        matching_data.append({"date": datum, "value": wert})
                        if len(matching_data) >= weeks:
                            break
                except:
                    continue
        
        return matching_data
        
    except Exception as e:
        print(f"   ⚠️ Fehler beim Laden historischer Daten: {e}")
        return []


def check_weekday_alert(current_value: int, current_date: date, historical_data: List[Dict], threshold: float = 0.10) -> Optional[Dict]:
    """
    Prüft ob der aktuelle Wert die Schwelle im Vergleich zum historischen Durchschnitt überschreitet.
    
    Args:
        current_value: Aktueller Tageswert
        current_date: Datum des aktuellen Wertes
        historical_data: Liste von {"date": date, "value": int} der letzten 6 gleichen Wochentage
        threshold: Schwellenwert (0.10 = ±10%)
    
    Returns:
        Alert-Dict wenn Schwelle überschritten, sonst None
    """
    if len(historical_data) < 3:
        return None  # Nicht genug historische Daten
    
    historical_values = [d["value"] for d in historical_data]
    avg = statistics.mean(historical_values)
    if avg == 0:
        return None
    
    pct_change = (current_value - avg) / avg
    
    if abs(pct_change) >= threshold:
        return {
            "current_value": current_value,
            "current_date": current_date,
            "historical_avg": avg,
            "pct_change": pct_change,
            "direction": "up" if pct_change > 0 else "down",
            "historical_data": historical_data  # Jetzt mit Datum!
        }
    
    return None


def generate_alert_gpt_analysis(alerts: List[Dict], target_date: date) -> str:
    """Generiert GPT-Analyse für die erkannten Alerts"""
    if not OPENAI_API_KEY:
        return "⚠️ GPT-Analyse nicht verfügbar (API Key fehlt)"
    
    weekday_names = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
    weekday_name = weekday_names[target_date.weekday()]
    
    # Alerts formatieren - MIT GENAUEN DATEN
    alert_details = []
    for a in alerts:
        direction_icon = "📈" if a["direction"] == "up" else "📉"
        direction_text = "über" if a["direction"] == "up" else "unter"
        
        # Historische Daten mit Datum formatieren
        historical_with_dates = []
        for h in a.get("historical_data", [])[:6]:
            hist_date = h["date"].strftime("%d.%m.")
            hist_value = f"{h['value']:,}"
            historical_with_dates.append(f"{hist_date}: {hist_value}")
        
        alert_details.append(
            f"- {direction_icon} **{a['brand']} {a['surface']} {a['metric']}**\n"
            f"  📅 Abweichungsdatum: **{a['current_date'].strftime('%d.%m.%Y')}** ({weekday_name})\n"
            f"  📊 Aktueller Wert: **{a['current_value']:,}** ({a['pct_change']*100:+.1f}% {direction_text} Durchschnitt)\n"
            f"  📈 Historische Vergleichswerte:\n     " + " | ".join(historical_with_dates)
        )
    
    prompt = f"""Du bist ein erfahrener Web-Analytics-Experte für österreichische Medienunternehmen.

KONTEXT:
Berichtsdatum: {datetime.now().strftime('%d.%m.%Y %H:%M')} Uhr
Analysiertes Datum: {target_date.strftime('%d.%m.%Y')} ({weekday_name})
Es wurden signifikante Abweichungen (±10%) im Vergleich zu den letzten 6 gleichen Wochentagen erkannt.

ERKANNTE ABWEICHUNGEN:
{chr(10).join(alert_details)}

DEINE AUFGABE:
1. Analysiere die Abweichungen im Kontext (Saisonalität, Feiertage, Wochenende-Effekte)
2. Bewerte ob der Trend (↑/↓) sich fortsetzt oder mildert basierend auf den historischen Daten
3. Identifiziere mögliche Ursachen
4. Gib eine kurze Handlungsempfehlung

FORMAT (max. 150 Wörter):
**🔍 ANALYSE**
[2-3 Sätze zur Einordnung der Abweichung - nenne das konkrete Datum!]

**📊 TREND-BEWERTUNG**
[1-2 Sätze zum Trend basierend auf den historischen Daten]

**💡 EMPFEHLUNG**
[1 Satz Handlungsempfehlung]
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


def send_alert_notification(alerts: List[Dict], analysis: str, target_date: date):
    """Sendet Alert-Benachrichtigung an Teams"""
    if not TEAMS_WEBHOOK_URL:
        print("⚠️ TEAMS_WEBHOOK_URL nicht konfiguriert")
        return
    
    weekday_names = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
    weekday_name = weekday_names[target_date.weekday()]
    
    # Farbe basierend auf Schwere
    has_critical = any(abs(a["pct_change"]) >= 0.20 for a in alerts)
    color = "DC3545" if has_critical else "FFC107"  # Rot oder Gelb
    
    # Alert-Details formatieren - MIT GENAUEN DATEN
    alert_lines = []
    for a in alerts:
        icon = "📈" if a["direction"] == "up" else "📉"
        
        # Historische Daten mit Datum formatieren
        hist_dates = []
        for h in a.get("historical_data", [])[:6]:
            hist_dates.append(f"{h['date'].strftime('%d.%m.')}: {h['value']:,}")
        hist_str = " | ".join(hist_dates) if hist_dates else "N/A"
        
        alert_lines.append(
            f"{icon} **{a['brand']} {a['surface']} - {a['metric']}**\n"
            f"   📅 **{a['current_date'].strftime('%d.%m.%Y')}**: {a['current_value']:,} ({a['pct_change']*100:+.1f}%)\n"
            f"   📊 Vergleich: {hist_str}"
        )
    
    # Facts mit genauem Abweichungsdatum
    facts = [
        {"name": "📅 Abweichungsdatum", "value": f"**{target_date.strftime('%d.%m.%Y')}** ({weekday_name})"},
        {"name": "⏰ Bericht erstellt", "value": datetime.now().strftime('%d.%m.%Y %H:%M') + " Uhr"},
        {"name": "🔔 Anzahl Abweichungen", "value": str(len(alerts))},
        {"name": "📊 Vergleichsbasis", "value": f"Letzte 6 {weekday_name}e"},
    ]
    
    card = {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "summary": f"ÖWA Alert - Abweichungen am {target_date.strftime('%d.%m.%Y')}",
        "themeColor": color,
        "sections": [
            {
                "activityTitle": f"⚠️ ÖWA WOCHENTAGS-ALERT",
                "activitySubtitle": f"Abweichungen über ±10% Schwelle am {target_date.strftime('%d.%m.%Y')} erkannt",
                "facts": facts,
                "markdown": True
            },
            {
                "title": "📋 Erkannte Abweichungen (mit Vergleichsdaten)",
                "text": "\n\n".join(alert_lines),
                "markdown": True
            },
            {
                "title": "🤖 KI-Analyse",
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
            print("✅ Alert-Benachrichtigung an Teams gesendet")
        else:
            print(f"⚠️ Teams Fehler: {response.status_code}")
    except Exception as e:
        print(f"⚠️ Teams Fehler: {e}")


def send_teams_notification(message: str, title: str, color: str = "28A745"):
    """Sendet einfache Benachrichtigung an Teams"""
    if not TEAMS_WEBHOOK_URL:
        print("⚠️ TEAMS_WEBHOOK_URL nicht konfiguriert")
        return
    
    card = {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "summary": title,
        "themeColor": color,
        "sections": [{
            "activityTitle": title,
            "text": message,
            "markdown": True
        }]
    }
    
    try:
        response = requests.post(TEAMS_WEBHOOK_URL, json=card, timeout=10)
        if response.status_code == 200:
            print("✅ Teams Benachrichtigung gesendet")
        else:
            print(f"⚠️ Teams Fehler: {response.status_code}")
    except Exception as e:
        print(f"⚠️ Teams Fehler: {e}")


def main():
    print("=" * 70)
    print("🚀 ÖWA DAILY INGESTION v2.0")
    print("   Web + App | PI + Visits + UC + Homepage PI")
    print("=" * 70)
    
    # Konfiguration prüfen
    if not INFONLINE_API_KEY:
        print("❌ INFONLINE_API_KEY nicht gesetzt!")
        return
    if not AIRTABLE_API_KEY:
        print("❌ AIRTABLE_API_KEY nicht gesetzt!")
        return
    
    # Zieldaten: Vor 2 Tagen für Standard-Metriken (API liefert erst dann finale Daten!)
    # Vor 3 Tagen für UC (zusätzliche Verzögerung für Unique Clients)
    target_date = date.today() - timedelta(days=STANDARD_DELAY_DAYS)
    uc_target_date = date.today() - timedelta(days=UC_DELAY_DAYS)
    
    print(f"\n📅 Standard-Metriken Datum: {target_date.isoformat()} (vor {STANDARD_DELAY_DAYS} Tagen)")
    print(f"📅 Unique Clients Datum: {uc_target_date.isoformat()} (vor {UC_DELAY_DAYS} Tagen)")
    print(f"   ℹ️ Daten werden verzögert abgerufen um finale API-Werte zu erhalten")
    print()
    
    records_to_create = []
    errors = []
    ingested_data = []  # Für Alerting (nur Standard-Metriken)
    
    # ==========================================================================
    # PHASE 1a: Standard-Metriken (PI, Visits) für GESTERN
    # ==========================================================================
    print("=" * 70)
    print(f"📊 PHASE 1a: Standard-Metriken (PI, Visits) - {target_date.isoformat()}")
    print("=" * 70)
    
    for site in SITES:
        print(f"\n📊 {site['name']}...")
        for metric_key in METRICS_STANDARD:
            result = fetch_infonline_data(site["site_id"], metric_key, target_date)
            
            if result["success"]:
                value, preliminary = extract_value(result["data"], metric_key)
                
                if value is not None:
                    metric_name = METRICS_MAP.get(metric_key, metric_key)
                    unique_key = f"{target_date.isoformat()}_{site['brand']}_{site['surface']}_{metric_name}"
                    
                    records_to_create.append({
                        "fields": {
                            "Datum": target_date.isoformat(),
                            "Brand": site["brand"],
                            "Plattform": site["surface"],
                            "Metrik": metric_name,
                            "Wert": value,
                            "Site ID": site["site_id"],
                            "Vorläufig": preliminary,
                            "Erfasst am": datetime.utcnow().isoformat(),
                            "Unique Key": unique_key
                        }
                    })
                    
                    # Für Alerting speichern (nur Standard-Metriken)
                    ingested_data.append({
                        "brand": site["brand"],
                        "surface": site["surface"],
                        "metric": metric_name,
                        "value": value,
                        "date": target_date
                    })
                    
                    print(f"   ✅ {metric_name}: {value:,}")
                else:
                    errors.append(f"{site['name']}/{metric_key}: Kein Wert")
                    print(f"   ⚠️ {metric_key}: Kein Wert")
            else:
                errors.append(f"{site['name']}/{metric_key}: {result['error']}")
                print(f"   ❌ {metric_key}: {result['error']}")
    
    # ==========================================================================
    # PHASE 1b: Unique Clients für VOR 3 TAGEN (verzögerte Verfügbarkeit)
    # ==========================================================================
    print("\n" + "=" * 70)
    print(f"👤 PHASE 1b: Unique Clients - {uc_target_date.isoformat()} (verzögert)")
    print("=" * 70)
    
    for site in SITES:
        print(f"\n👤 {site['name']}...")
        for metric_key in METRICS_DELAYED:
            result = fetch_infonline_data(site["site_id"], metric_key, uc_target_date)
            
            if result["success"]:
                value, preliminary = extract_value(result["data"], metric_key)
                
                # WICHTIG: UC-Wert von 0 bedeutet "noch nicht verfügbar" - nicht importieren!
                if value is not None and value > 0:
                    metric_name = METRICS_MAP.get(metric_key, metric_key)
                    unique_key = f"{uc_target_date.isoformat()}_{site['brand']}_{site['surface']}_{metric_name}"
                    
                    records_to_create.append({
                        "fields": {
                            "Datum": uc_target_date.isoformat(),
                            "Brand": site["brand"],
                            "Plattform": site["surface"],
                            "Metrik": metric_name,
                            "Wert": value,
                            "Site ID": site["site_id"],
                            "Vorläufig": preliminary,
                            "Erfasst am": datetime.utcnow().isoformat(),
                            "Unique Key": unique_key
                        }
                    })
                    
                    print(f"   ✅ {metric_name}: {value:,}")
                elif value == 0:
                    print(f"   ⚠️ {metric_key}: 0 (noch nicht finalisiert - übersprungen)")
                else:
                    errors.append(f"{site['name']}/{metric_key}: Kein Wert")
                    print(f"   ⚠️ {metric_key}: Kein Wert")
            else:
                errors.append(f"{site['name']}/{metric_key}: {result['error']}")
                print(f"   ❌ {metric_key}: {result['error']}")
    
    # ==========================================================================
    # PHASE 2: Homepage Page Impressions (nur Web)
    # ==========================================================================
    print("\n" + "=" * 70)
    print("🏠 PHASE 2: Homepage Page Impressions")
    print("=" * 70)
    
    for site in HOMEPAGE_SITES:
        print(f"\n🏠 {site['name']}...")
        result = fetch_infonline_data(site["site_id"], "pageimpressions", target_date)
        
        if result["success"]:
            value, preliminary = extract_value(result["data"], "pageimpressions")
            
            if value is not None:
                metric_name = "Homepage PI"
                unique_key = f"{target_date.isoformat()}_{site['brand']}_{site['surface']}_{metric_name}"
                
                records_to_create.append({
                    "fields": {
                        "Datum": target_date.isoformat(),
                        "Brand": site["brand"],
                        "Plattform": site["surface"],
                        "Metrik": metric_name,
                        "Wert": value,
                        "Site ID": site["site_id"],
                        "Vorläufig": preliminary,
                        "Erfasst am": datetime.utcnow().isoformat(),
                        "Unique Key": unique_key
                    }
                })
                
                # Für Alerting speichern
                ingested_data.append({
                    "brand": site["brand"],
                    "surface": site["surface"],
                    "metric": metric_name,
                    "value": value
                })
                
                print(f"   ✅ Homepage PI: {value:,}")
            else:
                errors.append(f"{site['name']}/Homepage PI: Kein Wert")
                print(f"   ⚠️ Homepage PI: Kein Wert")
        else:
            errors.append(f"{site['name']}/Homepage PI: {result['error']}")
            print(f"   ❌ Homepage PI: {result['error']}")
    
    # ==========================================================================
    # PHASE 3: In Airtable speichern
    # ==========================================================================
    print("\n" + "=" * 70)
    print("💾 PHASE 3: Airtable-Speicherung")
    print("=" * 70)
    
    # WICHTIG: Prüfe existierende Daten für BEIDE Zieldaten (Standard + UC)
    print(f"\n🔍 Prüfe existierende Daten für {target_date} (Standard)...")
    existing_keys = check_existing_records(target_date)
    
    print(f"🔍 Prüfe existierende Daten für {uc_target_date} (UC)...")
    existing_keys_uc = check_existing_records(uc_target_date)
    existing_keys = existing_keys.union(existing_keys_uc)  # Kombiniere beide Sets
    
    if records_to_create:
        print(f"\n💾 Speichere {len(records_to_create)} Datensätze in Airtable...")
        print(f"   ℹ️ Double-Check aktiviert: Jeder Key wird vor Insert nochmal geprüft")
        save_result = save_to_airtable(records_to_create, existing_keys, double_check=True)
        print(f"   ✅ Erstellt: {save_result['created']}")
        if save_result.get("skipped", 0) > 0:
            print(f"   ⏭️ Übersprungen (1. Prüfung): {save_result['skipped']}")
        if save_result.get("skipped_double_check", 0) > 0:
            print(f"   ⏭️ Übersprungen (Double-Check): {save_result['skipped_double_check']}")
        if save_result["errors"]:
            for err in save_result["errors"]:
                print(f"   ❌ {err}")
                errors.append(err)
    
    # ==========================================================================
    # PHASE 4: Wochentags-Alerting (nur für Standard-Metriken, nicht UC)
    # ==========================================================================
    print("\n" + "=" * 70)
    print("🔔 PHASE 4: Wochentags-Alerting (±10% Schwelle)")
    print("   ℹ️ Unique Clients sind vom Alerting ausgeschlossen (2 Tage verzögert)")
    print("=" * 70)
    
    all_alerts = []
    
    for data_point in ingested_data:
        # Nur Standard-Metriken alerten (nicht Unique Clients)
        if data_point["metric"] == "Unique Clients":
            print(f"   ⏭️ {data_point['brand']} {data_point['surface']} {data_point['metric']}: Übersprungen (verzögert)")
            continue
        
        alert_date = data_point.get("date", target_date)
        weekday = alert_date.weekday()
        
        # Historische Daten für gleichen Wochentag laden (jetzt mit Datum!)
        historical = get_historical_data(
            brand=data_point["brand"],
            surface=data_point["surface"],
            metric=data_point["metric"],
            weekday=weekday,
            weeks=6
        )
        
        if len(historical) >= 3:
            alert = check_weekday_alert(
                current_value=data_point["value"],
                current_date=alert_date,
                historical_data=historical,
                threshold=ALERT_THRESHOLD_PCT
            )
            
            if alert:
                alert["brand"] = data_point["brand"]
                alert["surface"] = data_point["surface"]
                alert["metric"] = data_point["metric"]
                all_alerts.append(alert)
                
                direction = "↑" if alert["direction"] == "up" else "↓"
                print(f"   ⚠️ {data_point['brand']} {data_point['surface']} {data_point['metric']}: "
                      f"{alert['pct_change']*100:+.1f}% {direction}")
            else:
                print(f"   ✅ {data_point['brand']} {data_point['surface']} {data_point['metric']}: OK")
        else:
            print(f"   ℹ️ {data_point['brand']} {data_point['surface']} {data_point['metric']}: "
                  f"Nicht genug historische Daten ({len(historical)}/3)")
    
    # ==========================================================================
    # PHASE 5: Alert-Benachrichtigung (nur wenn Schwelle überschritten)
    # ==========================================================================
    if all_alerts:
        print("\n" + "=" * 70)
        print(f"🚨 {len(all_alerts)} ABWEICHUNGEN ERKANNT - Sende Alert")
        print("=" * 70)
        
        # GPT-Analyse generieren
        print("\n🤖 Generiere KI-Analyse...")
        analysis = generate_alert_gpt_analysis(all_alerts, target_date)
        print(f"   → {len(analysis)} Zeichen generiert")
        
        # Alert an Teams senden
        print("\n📤 Sende Alert an Teams...")
        send_alert_notification(all_alerts, analysis, target_date)
    else:
        print("\n✅ Keine Abweichungen über ±10% - Kein Alert nötig")
    
    # ==========================================================================
    # PHASE 6: Zusammenfassung
    # ==========================================================================
    print("\n" + "=" * 70)
    print("📋 ZUSAMMENFASSUNG")
    print("=" * 70)
    
    status = "✅ Erfolgreich" if not errors else "⚠️ Mit Fehlern"
    
    # Nur einfache Status-Nachricht (kein Alert-Inhalt)
    message = f"""**Datum:** {target_date.strftime('%d.%m.%Y')}
**Datensätze:** {len(records_to_create)}
**Erstellt:** {save_result.get('created', 0)} | **Übersprungen:** {save_result.get('skipped', 0)}
**Alerts:** {len(all_alerts)} Abweichungen erkannt
**Status:** {status}"""
    
    if errors:
        message += f"\n\n**Fehler:**\n" + "\n".join(f"• {e}" for e in errors[:5])
    
    send_teams_notification(
        message=message,
        title=f"📥 ÖWA Daily Ingestion - {target_date.strftime('%d.%m.%Y')}",
        color="28A745" if not errors else "FFC107"
    )
    
    print("\n" + "=" * 70)
    print("✅ DAILY INGESTION v2.0 ABGESCHLOSSEN")
    print("=" * 70)


if __name__ == "__main__":
    main()
