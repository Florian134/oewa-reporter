"""
Daily Cron Job - Tägliche Daten-Ingestion (Airtable Version)

Ausführung: Täglich um 08:00 UTC via Vercel Cron

Diese Version speichert Daten direkt in Airtable.
"""
from http.server import BaseHTTPRequestHandler
import json
import os
import sys
import hmac
from datetime import date, datetime, timedelta

# Projekt-Root zum Path hinzufügen
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        # 🔐 Authentication Check
        if not self._verify_auth():
            return
        
        try:
            result = self._run_daily_ingestion()
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())
            
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            
            error_response = {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
            self.wfile.write(json.dumps(error_response).encode())
    
    def do_GET(self):
        """GET für manuellen Test (auch authentifiziert)"""
        self.do_POST()
    
    def _verify_auth(self) -> bool:
        """Prüft CRON_SECRET Authentication"""
        cron_secret = os.getenv("CRON_SECRET", "")
        
        # Dev-Mode: Kein Secret = durchlassen mit Warnung
        if not cron_secret:
            if os.getenv("VERCEL_ENV") == "production":
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(b'{"error": "CRON_SECRET not configured in production"}')
                return False
            return True  # Dev-Mode
        
        # Authorization Header prüfen
        auth_header = self.headers.get("Authorization", "")
        
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            if hmac.compare_digest(token, cron_secret):
                return True
        
        # Vercel Cron Signature prüfen
        vercel_signature = self.headers.get("x-vercel-signature", "")
        if vercel_signature and hmac.compare_digest(vercel_signature, cron_secret):
            return True
        
        # Nicht autorisiert
        self.send_response(401)
        self.send_header('Content-type', 'application/json')
        self.send_header('WWW-Authenticate', 'Bearer realm="OEWA Cron API"')
        self.end_headers()
        self.wfile.write(b'{"error": "Unauthorized", "message": "Valid CRON_SECRET required"}')
        return False

    def _run_daily_ingestion(self):
        """Führt die tägliche Ingestion durch und speichert in Airtable"""
        import requests
        
        # Config laden
        api_key = os.getenv("INFONLINE_API_KEY", "")
        airtable_key = os.getenv("AIRTABLE_API_KEY", "")
        airtable_base = os.getenv("AIRTABLE_BASE_ID", "")  # Muss in Umgebungsvariablen gesetzt sein
        teams_webhook = os.getenv("TEAMS_WEBHOOK_URL", "")
        
        if not api_key:
            return {"status": "error", "error": "INFONLINE_API_KEY nicht gesetzt"}
        
        if not airtable_key:
            return {"status": "error", "error": "AIRTABLE_API_KEY nicht gesetzt"}
        
        target_date = date.today() - timedelta(days=1)
        
        result = {
            "status": "success",
            "date": target_date.isoformat(),
            "ingested": 0,
            "errors": [],
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Sites und Metriken
        sites = [
            {"name": "VOL Web Desktop", "site_id": "EA000004_desktop", "brand": "VOL", "surface": "Web Desktop"},
            {"name": "VOL Web Mobile", "site_id": "EA000004_mobile", "brand": "VOL", "surface": "Web Mobile"},
            {"name": "VOL App", "site_id": "SB000074", "brand": "VOL", "surface": "App"},
        ]
        metrics_map = {
            "pageimpressions": "Page Impressions",
            "visits": "Visits"
        }
        
        # API Session für INFOnline
        api_session = requests.Session()
        api_session.headers.update({
            "authorization": api_key,
            "Accept": "application/json"
        })
        
        # Airtable Session
        airtable_session = requests.Session()
        airtable_session.headers.update({
            "Authorization": f"Bearer {airtable_key}",
            "Content-Type": "application/json"
        })
        airtable_url = f"https://api.airtable.com/v0/{airtable_base}/Measurements"
        
        records_to_create = []
        
        for site in sites:
            for metric_key, metric_name in metrics_map.items():
                try:
                    # API Call zu INFOnline
                    url = f"https://reportingapi.infonline.de/api/v1/{metric_key}"
                    params = {
                        "site": site["site_id"],
                        "date": target_date.isoformat(),
                        "aggregation": "DAY"
                    }
                    
                    response = api_session.get(url, params=params, timeout=30)
                    
                    if response.status_code == 200:
                        data = response.json()
                        
                        # Wert extrahieren
                        iom_total = None
                        preliminary = True
                        
                        if isinstance(data, list) and len(data) > 0:
                            day_data = data[0]
                            if "iom" in day_data:
                                iom_total = day_data["iom"].get("total")
                                preliminary = day_data.get("preliminary", True)
                        
                        if iom_total is not None:
                            # Airtable Record vorbereiten
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
                            
                            result["ingested"] += 1
                    else:
                        result["errors"].append(f"{site['name']}/{metric_key}: HTTP {response.status_code}")
                        
                except Exception as e:
                    result["errors"].append(f"{site['name']}/{metric_key}: {str(e)}")
        
        # Batch-Insert in Airtable (max 10 pro Request)
        for i in range(0, len(records_to_create), 10):
            batch = records_to_create[i:i+10]
            try:
                airtable_response = airtable_session.post(
                    airtable_url,
                    json={"records": batch},
                    timeout=30
                )
                
                if airtable_response.status_code not in (200, 201):
                    result["errors"].append(f"Airtable Batch {i//10 + 1}: {airtable_response.text[:100]}")
                    
            except Exception as e:
                result["errors"].append(f"Airtable Batch {i//10 + 1}: {str(e)}")
        
        # Teams Notification
        if teams_webhook and result["ingested"] > 0:
            self._send_teams_notification(teams_webhook, result, target_date)
        
        if result["errors"]:
            result["status"] = "partial"
        
        return result
    
    def _send_teams_notification(self, webhook_url, result, target_date):
        """Sendet Zusammenfassung an Teams"""
        import requests
        
        card = {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "summary": f"ÖWA Daily Ingestion: {target_date}",
            "themeColor": "28A745" if result["status"] == "success" else "FFC107",
            "sections": [{
                "activityTitle": f"📥 ÖWA Tägliche Ingestion → Airtable",
                "activitySubtitle": target_date.strftime("%d.%m.%Y"),
                "facts": [
                    {"name": "Status", "value": "✅ Erfolgreich" if result["status"] == "success" else "⚠️ Teilweise"},
                    {"name": "Datensätze", "value": str(result["ingested"])},
                    {"name": "Ziel", "value": "Airtable"},
                ],
                "markdown": True
            }]
        }
        
        if result["errors"]:
            card["sections"][0]["text"] = "Fehler:\n" + "\n".join(f"• {e}" for e in result["errors"][:5])
        
        try:
            requests.post(webhook_url, json=card, timeout=10)
        except:
            pass
