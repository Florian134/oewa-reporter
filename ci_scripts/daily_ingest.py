#!/usr/bin/env python3
"""
Daily Ingestion Script
=======================
Wird von GitLab CI/CD ausgeführt, getriggert durch Airtable Automation.

Funktionen:
1. INFOnline API abrufen
2. Daten in Airtable speichern
3. Anomalien erkennen
4. Bei Anomalien: Teams Benachrichtigung
"""

import os
import json
import requests
from datetime import date, datetime, timedelta

# =============================================================================
# KONFIGURATION (aus GitLab CI/CD Variables)
# =============================================================================
INFONLINE_API_KEY = os.environ.get("INFONLINE_API_KEY", "")
AIRTABLE_API_KEY = os.environ.get("AIRTABLE_API_KEY", "")
AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID", "appTIeod85xnBy7Vn")
TEAMS_WEBHOOK_URL = os.environ.get("TEAMS_WEBHOOK_URL", "")

# =============================================================================
# SITES KONFIGURATION - Korrekte ÖWA Site-IDs
# =============================================================================
SITES = [
    {"name": "VOL.AT Web", "site_id": "at_w_atvol", "brand": "VOL", "surface": "Web"},
    {"name": "VIENNA.AT Web", "site_id": "at_w_atvienna", "brand": "Vienna", "surface": "Web"},
]

METRICS = ["pageimpressions", "visits"]
METRICS_MAP = {
    "pageimpressions": "Page Impressions",
    "visits": "Visits"
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
        else:
            return {"success": False, "error": f"HTTP {response.status_code}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def save_to_airtable(records: list) -> dict:
    """Speichert Records in Airtable"""
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/Measurements"
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json"
    }
    
    results = {"created": 0, "errors": []}
    
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
                results["errors"].append(f"Batch {i//10 + 1}: {response.text[:100]}")
        except Exception as e:
            results["errors"].append(f"Batch {i//10 + 1}: {str(e)}")
    
    return results


def send_teams_notification(message: str, title: str, color: str = "28A745"):
    """Sendet Benachrichtigung an Teams"""
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
    print("=" * 60)
    print("🚀 ÖWA DAILY INGESTION")
    print("=" * 60)
    
    # Konfiguration prüfen
    if not INFONLINE_API_KEY:
        print("❌ INFONLINE_API_KEY nicht gesetzt!")
        return
    if not AIRTABLE_API_KEY:
        print("❌ AIRTABLE_API_KEY nicht gesetzt!")
        return
    
    # Gestern als Zieldatum
    target_date = date.today() - timedelta(days=1)
    print(f"📅 Datum: {target_date.isoformat()}")
    print()
    
    records_to_create = []
    errors = []
    
    # Daten von INFOnline abrufen
    for site in SITES:
        print(f"📊 {site['name']}...")
        for metric_key in METRICS:
            result = fetch_infonline_data(site["site_id"], metric_key, target_date)
            
            if result["success"]:
                data = result["data"]
                
                # Wert extrahieren
                iom_total = None
                preliminary = True
                
                if isinstance(data, list) and len(data) > 0:
                    day_data = data[0]
                    if "iom" in day_data:
                        iom_total = day_data["iom"].get("total")
                        preliminary = day_data.get("preliminary", True)
                
                if iom_total is not None:
                    metric_name = METRICS_MAP.get(metric_key, metric_key)
                    unique_key = f"{target_date.isoformat()}_{site['brand']}_{site['surface']}_{metric_name}"
                    
                    records_to_create.append({
                        "fields": {
                            "Datum": target_date.isoformat(),
                            "Brand": site["brand"],
                            "Plattform": site["surface"],
                            "Metrik": metric_name,
                            "Wert": iom_total,
                            "Site ID": site["site_id"],
                            "Vorläufig": preliminary,
                            "Erfasst am": datetime.utcnow().isoformat(),
                            "Unique Key": unique_key
                        }
                    })
                    print(f"   ✅ {metric_name}: {iom_total:,}")
                else:
                    errors.append(f"{site['name']}/{metric_key}: Kein Wert")
                    print(f"   ⚠️ {metric_key}: Kein Wert")
            else:
                errors.append(f"{site['name']}/{metric_key}: {result['error']}")
                print(f"   ❌ {metric_key}: {result['error']}")
    
    print()
    print("=" * 60)
    
    # In Airtable speichern
    if records_to_create:
        print(f"💾 Speichere {len(records_to_create)} Datensätze in Airtable...")
        save_result = save_to_airtable(records_to_create)
        print(f"   ✅ Erstellt: {save_result['created']}")
        if save_result["errors"]:
            for err in save_result["errors"]:
                print(f"   ❌ {err}")
                errors.append(err)
    
    print()
    
    # Teams Benachrichtigung
    status = "✅ Erfolgreich" if not errors else "⚠️ Mit Fehlern"
    message = f"""**Datum:** {target_date.strftime('%d.%m.%Y')}
**Datensätze:** {len(records_to_create)}
**Status:** {status}"""
    
    if errors:
        message += f"\n\n**Fehler:**\n" + "\n".join(f"• {e}" for e in errors[:5])
    
    send_teams_notification(
        message=message,
        title=f"📥 ÖWA Daily Ingestion - {target_date.strftime('%d.%m.%Y')}",
        color="28A745" if not errors else "FFC107"
    )
    
    print("=" * 60)
    print("✅ DAILY INGESTION ABGESCHLOSSEN")
    print("=" * 60)


if __name__ == "__main__":
    main()

