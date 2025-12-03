"""
Daily Cron Job - Tägliche Daten-Ingestion (Lite Version)

Ausführung: Täglich um 08:00 UTC via Vercel Cron

Diese Version verwendet KEINE schweren Pakete (pandas, numpy).
Datenverarbeitung erfolgt mit reinem Python + SQLAlchemy.
"""
from http.server import BaseHTTPRequestHandler
import json
import os
import sys
from datetime import date, datetime, timedelta

# Projekt-Root zum Path hinzufügen
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
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
        """GET für manuellen Test"""
        self.do_POST()
    
    def _run_daily_ingestion(self):
        """Führt die tägliche Ingestion durch (ohne pandas)"""
        import requests
        from sqlalchemy import create_engine, text
        from sqlalchemy.orm import sessionmaker
        
        # Config laden
        api_key = os.getenv("INFONLINE_API_KEY", "")
        db_url = os.getenv("DATABASE_URL", "")
        teams_webhook = os.getenv("TEAMS_WEBHOOK_URL", "")
        
        if not api_key:
            return {"status": "error", "error": "INFONLINE_API_KEY nicht gesetzt"}
        
        if not db_url:
            return {"status": "error", "error": "DATABASE_URL nicht gesetzt"}
        
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
            {"name": "VOL Web Desktop", "site_id": "EA000004_desktop", "brand": "vol", "surface": "web_desktop"},
            {"name": "VOL Web Mobile", "site_id": "EA000004_mobile", "brand": "vol", "surface": "web_mobile"},
            {"name": "VOL App", "site_id": "SB000074", "brand": "vol", "surface": "app"},
        ]
        metrics = ["pageimpressions", "visits"]
        
        # API Session
        session = requests.Session()
        session.headers.update({
            "authorization": api_key,
            "Accept": "application/json"
        })
        
        # DB Connection
        engine = create_engine(db_url)
        Session = sessionmaker(bind=engine)
        db_session = Session()
        
        try:
            for site in sites:
                for metric in metrics:
                    try:
                        # API Call
                        url = f"https://reportingapi.infonline.de/api/v1/{metric}"
                        params = {
                            "site": site["site_id"],
                            "date": target_date.isoformat(),
                            "aggregation": "DAY"
                        }
                        
                        response = session.get(url, params=params, timeout=30)
                        
                        if response.status_code == 200:
                            data = response.json()
                            
                            # Wert extrahieren
                            iom_total = None
                            if isinstance(data, list) and len(data) > 0:
                                day_data = data[0]
                                if "iom" in day_data:
                                    iom_total = day_data["iom"].get("total")
                            
                            if iom_total is not None:
                                # In DB speichern (UPSERT)
                                sql = text("""
                                    INSERT INTO measurements 
                                    (brand, surface, metric, date, site_id, value_total, preliminary, ingested_at)
                                    VALUES (:brand, :surface, :metric, :date, :site_id, :value_total, :preliminary, :ingested_at)
                                    ON CONFLICT (brand, surface, metric, date, site_id, preliminary) 
                                    DO UPDATE SET value_total = :value_total, updated_at = :ingested_at
                                """)
                                
                                db_session.execute(sql, {
                                    "brand": site["brand"],
                                    "surface": site["surface"],
                                    "metric": metric,
                                    "date": target_date,
                                    "site_id": site["site_id"],
                                    "value_total": iom_total,
                                    "preliminary": True,
                                    "ingested_at": datetime.utcnow()
                                })
                                
                                result["ingested"] += 1
                        else:
                            result["errors"].append(f"{site['name']}/{metric}: HTTP {response.status_code}")
                            
                    except Exception as e:
                        result["errors"].append(f"{site['name']}/{metric}: {str(e)}")
            
            db_session.commit()
            
        finally:
            db_session.close()
        
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
                "activityTitle": f"📥 ÖWA Tägliche Ingestion",
                "activitySubtitle": target_date.strftime("%d.%m.%Y"),
                "facts": [
                    {"name": "Status", "value": "✅ Erfolgreich" if result["status"] == "success" else "⚠️ Teilweise"},
                    {"name": "Datensätze", "value": str(result["ingested"])},
                    {"name": "Fehler", "value": str(len(result["errors"]))},
                ],
                "markdown": True
            }]
        }
        
        if result["errors"]:
            card["sections"][0]["text"] = "Fehler:\n" + "\n".join(f"• {e}" for e in result["errors"][:5])
        
        try:
            requests.post(webhook_url, json=card, timeout=10)
        except:
            pass  # Ignore notification errors
