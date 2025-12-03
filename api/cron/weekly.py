"""
Weekly Cron Job - Wöchentlicher KI-Report (Lite Version)

Ausführung: Montag um 09:00 UTC via Vercel Cron

Diese Version verwendet OpenAI für KI-Interpretation
und sendet den Report an Teams.
"""
from http.server import BaseHTTPRequestHandler
import json
import os
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            result = self._run_weekly_report()
            
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
        self.do_POST()
    
    def _run_weekly_report(self):
        """Generiert wöchentlichen KI-Report"""
        import requests
        from sqlalchemy import create_engine, text
        from sqlalchemy.orm import sessionmaker
        
        # Config
        db_url = os.getenv("DATABASE_URL", "")
        teams_webhook = os.getenv("TEAMS_WEBHOOK_URL", "")
        openai_key = os.getenv("OPENAI_API_KEY", "")
        
        if not db_url:
            return {"status": "error", "error": "DATABASE_URL nicht gesetzt"}
        
        # Woche berechnen (letzter Sonntag)
        today = date.today()
        week_end = today - timedelta(days=today.weekday() + 1)
        week_start = week_end - timedelta(days=6)
        
        result = {
            "status": "success",
            "week_start": week_start.isoformat(),
            "week_end": week_end.isoformat(),
            "ai_generated": False,
            "teams_sent": False,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Daten aus DB laden
        engine = create_engine(db_url)
        Session = sessionmaker(bind=engine)
        db_session = Session()
        
        try:
            # Wochendaten aggregieren
            sql = text("""
                SELECT metric, surface, SUM(value_total) as total
                FROM measurements
                WHERE date >= :start AND date <= :end
                GROUP BY metric, surface
            """)
            
            rows = db_session.execute(sql, {"start": week_start, "end": week_end}).fetchall()
            
            metrics_data = {}
            for row in rows:
                key = f"{row[0]}_{row[1]}"
                metrics_data[key] = row[2]
            
            # Vorwoche laden
            prev_end = week_start - timedelta(days=1)
            prev_start = prev_end - timedelta(days=6)
            
            prev_rows = db_session.execute(sql, {"start": prev_start, "end": prev_end}).fetchall()
            
            prev_data = {}
            for row in prev_rows:
                key = f"{row[0]}_{row[1]}"
                prev_data[key] = row[2]
            
        finally:
            db_session.close()
        
        # Zusammenfassung erstellen
        web_pi = (metrics_data.get("pageimpressions_web_desktop", 0) + 
                  metrics_data.get("pageimpressions_web_mobile", 0))
        app_pi = metrics_data.get("pageimpressions_app", 0)
        
        prev_web_pi = (prev_data.get("pageimpressions_web_desktop", 0) + 
                       prev_data.get("pageimpressions_web_mobile", 0))
        prev_app_pi = prev_data.get("pageimpressions_app", 0)
        
        # Änderungen berechnen
        web_change = ((web_pi - prev_web_pi) / prev_web_pi * 100) if prev_web_pi > 0 else 0
        app_change = ((app_pi - prev_app_pi) / prev_app_pi * 100) if prev_app_pi > 0 else 0
        
        result["metrics"] = {
            "web_pi": web_pi,
            "app_pi": app_pi,
            "web_change_pct": round(web_change, 1),
            "app_change_pct": round(app_change, 1)
        }
        
        # KI-Interpretation (optional)
        ai_text = ""
        if openai_key:
            ai_text = self._generate_ai_summary(openai_key, result["metrics"], week_start, week_end)
            if ai_text:
                result["ai_generated"] = True
                result["ai_summary"] = ai_text
        
        # Teams Notification
        if teams_webhook:
            if self._send_teams_report(teams_webhook, result, week_start, week_end, ai_text):
                result["teams_sent"] = True
        
        return result
    
    def _generate_ai_summary(self, api_key, metrics, week_start, week_end):
        """Generiert KI-Zusammenfassung mit OpenAI"""
        import requests
        
        prompt = f"""Analysiere diese Wochen-Daten für VOL.at und erstelle eine kurze Management-Zusammenfassung (max. 150 Wörter, auf Deutsch):

Zeitraum: {week_start.strftime('%d.%m.')} - {week_end.strftime('%d.%m.%Y')}

Metriken:
- Web Page Impressions: {metrics['web_pi']:,.0f} ({metrics['web_change_pct']:+.1f}% vs. Vorwoche)
- App Page Impressions: {metrics['app_pi']:,.0f} ({metrics['app_change_pct']:+.1f}% vs. Vorwoche)

Erstelle eine prägnante Zusammenfassung mit:
1. Kernaussage (1 Satz)
2. Trend-Bewertung
3. Handlungsempfehlung (falls nötig)"""

        try:
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "gpt-4o-mini",
                    "messages": [
                        {"role": "system", "content": "Du bist ein Digital-Analyst für Russmedia. Schreibe prägnante, professionelle Zusammenfassungen auf Deutsch."},
                        {"role": "user", "content": prompt}
                    ],
                    "max_tokens": 400,
                    "temperature": 0.7
                },
                timeout=30
            )
            
            if response.status_code == 200:
                return response.json()["choices"][0]["message"]["content"]
        except:
            pass
        
        return ""
    
    def _send_teams_report(self, webhook_url, result, week_start, week_end, ai_text):
        """Sendet Wochenbericht an Teams"""
        import requests
        
        metrics = result["metrics"]
        
        card = {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "summary": f"ÖWA Wochenbericht KW{week_start.isocalendar()[1]}",
            "themeColor": "0078D7",
            "sections": [{
                "activityTitle": f"📊 ÖWA Wochenbericht KW{week_start.isocalendar()[1]}",
                "activitySubtitle": f"{week_start.strftime('%d.%m.')} - {week_end.strftime('%d.%m.%Y')}",
                "facts": [
                    {"name": "Web PI (Gesamt)", "value": f"{metrics['web_pi']:,.0f} ({metrics['web_change_pct']:+.1f}%)".replace(",", ".")},
                    {"name": "App PI (Gesamt)", "value": f"{metrics['app_pi']:,.0f} ({metrics['app_change_pct']:+.1f}%)".replace(",", ".")},
                ],
                "markdown": True
            }]
        }
        
        if ai_text:
            card["sections"].append({
                "activityTitle": "🤖 KI-Analyse",
                "text": ai_text,
                "markdown": True
            })
        
        try:
            response = requests.post(webhook_url, json=card, timeout=10)
            return response.status_code == 200
        except:
            return False
