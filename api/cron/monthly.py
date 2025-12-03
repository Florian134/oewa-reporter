"""
Monthly Cron Job - Monatlicher KI-Report (Lite Version)

Ausführung: 1. des Monats um 10:00 UTC via Vercel Cron
"""
from http.server import BaseHTTPRequestHandler
import json
import os
import sys
from datetime import date, datetime, timedelta
import calendar

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            result = self._run_monthly_report()
            
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
    
    def _run_monthly_report(self):
        """Generiert monatlichen KI-Report"""
        import requests
        from sqlalchemy import create_engine, text
        from sqlalchemy.orm import sessionmaker
        
        db_url = os.getenv("DATABASE_URL", "")
        teams_webhook = os.getenv("TEAMS_WEBHOOK_URL", "")
        openai_key = os.getenv("OPENAI_API_KEY", "")
        
        if not db_url:
            return {"status": "error", "error": "DATABASE_URL nicht gesetzt"}
        
        # Vormonat berechnen
        today = date.today()
        if today.month == 1:
            year, month = today.year - 1, 12
        else:
            year, month = today.year, today.month - 1
        
        _, last_day = calendar.monthrange(year, month)
        month_start = date(year, month, 1)
        month_end = date(year, month, last_day)
        month_name = ["", "Januar", "Februar", "März", "April", "Mai", "Juni", 
                      "Juli", "August", "September", "Oktober", "November", "Dezember"][month]
        
        result = {
            "status": "success",
            "month": f"{month_name} {year}",
            "month_start": month_start.isoformat(),
            "month_end": month_end.isoformat(),
            "ai_generated": False,
            "teams_sent": False,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Daten aus DB laden
        engine = create_engine(db_url)
        Session = sessionmaker(bind=engine)
        db_session = Session()
        
        try:
            sql = text("""
                SELECT metric, surface, SUM(value_total) as total
                FROM measurements
                WHERE date >= :start AND date <= :end
                GROUP BY metric, surface
            """)
            
            rows = db_session.execute(sql, {"start": month_start, "end": month_end}).fetchall()
            
            metrics_data = {}
            for row in rows:
                key = f"{row[0]}_{row[1]}"
                metrics_data[key] = row[2]
            
            # Vormonat
            if month == 1:
                prev_year, prev_month = year - 1, 12
            else:
                prev_year, prev_month = year, month - 1
            _, prev_last = calendar.monthrange(prev_year, prev_month)
            prev_start = date(prev_year, prev_month, 1)
            prev_end = date(prev_year, prev_month, prev_last)
            
            prev_rows = db_session.execute(sql, {"start": prev_start, "end": prev_end}).fetchall()
            
            prev_data = {}
            for row in prev_rows:
                key = f"{row[0]}_{row[1]}"
                prev_data[key] = row[2]
            
        finally:
            db_session.close()
        
        # Metriken berechnen
        web_pi = (metrics_data.get("pageimpressions_web_desktop", 0) + 
                  metrics_data.get("pageimpressions_web_mobile", 0))
        app_pi = metrics_data.get("pageimpressions_app", 0)
        total_pi = web_pi + app_pi
        
        prev_web_pi = (prev_data.get("pageimpressions_web_desktop", 0) + 
                       prev_data.get("pageimpressions_web_mobile", 0))
        prev_app_pi = prev_data.get("pageimpressions_app", 0)
        prev_total = prev_web_pi + prev_app_pi
        
        total_change = ((total_pi - prev_total) / prev_total * 100) if prev_total > 0 else 0
        
        result["metrics"] = {
            "total_pi": total_pi,
            "web_pi": web_pi,
            "app_pi": app_pi,
            "avg_daily_pi": total_pi // last_day,
            "total_change_pct": round(total_change, 1),
            "web_share_pct": round(web_pi / total_pi * 100, 1) if total_pi > 0 else 0,
            "app_share_pct": round(app_pi / total_pi * 100, 1) if total_pi > 0 else 0
        }
        
        # KI-Interpretation
        ai_text = ""
        if openai_key:
            ai_text = self._generate_ai_summary(openai_key, result["metrics"], month_name, year)
            if ai_text:
                result["ai_generated"] = True
                result["ai_summary"] = ai_text
        
        # Teams Notification
        if teams_webhook:
            if self._send_teams_report(teams_webhook, result, month_name, year, ai_text):
                result["teams_sent"] = True
        
        return result
    
    def _generate_ai_summary(self, api_key, metrics, month_name, year):
        """Generiert KI-Zusammenfassung"""
        import requests
        
        prompt = f"""Analysiere diese Monats-Daten für VOL.at und erstelle einen Management-Report (max. 200 Wörter, auf Deutsch):

Monat: {month_name} {year}

Metriken:
- Gesamt Page Impressions: {metrics['total_pi']:,.0f} ({metrics['total_change_pct']:+.1f}% vs. Vormonat)
- Ø PI pro Tag: {metrics['avg_daily_pi']:,.0f}
- Web-Anteil: {metrics['web_share_pct']:.1f}%
- App-Anteil: {metrics['app_share_pct']:.1f}%

Erstelle einen professionellen Monatsbericht mit:
1. Executive Summary (2-3 Sätze)
2. Performance-Highlight
3. Plattform-Entwicklung
4. Strategische Empfehlung"""

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
                        {"role": "system", "content": "Du bist ein erfahrener Digital-Analyst für Russmedia. Erstelle professionelle Monatsberichte auf Deutsch."},
                        {"role": "user", "content": prompt}
                    ],
                    "max_tokens": 500,
                    "temperature": 0.7
                },
                timeout=30
            )
            
            if response.status_code == 200:
                return response.json()["choices"][0]["message"]["content"]
        except:
            pass
        
        return ""
    
    def _send_teams_report(self, webhook_url, result, month_name, year, ai_text):
        """Sendet Monatsbericht an Teams"""
        import requests
        
        metrics = result["metrics"]
        
        card = {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "summary": f"ÖWA Monatsbericht {month_name} {year}",
            "themeColor": "17A2B8",
            "sections": [{
                "activityTitle": f"📊 ÖWA Monatsbericht",
                "activitySubtitle": f"{month_name} {year}",
                "facts": [
                    {"name": "Gesamt PI", "value": f"{metrics['total_pi']:,.0f}".replace(",", ".")},
                    {"name": "Ø PI/Tag", "value": f"{metrics['avg_daily_pi']:,.0f}".replace(",", ".")},
                    {"name": "vs. Vormonat", "value": f"{metrics['total_change_pct']:+.1f}%"},
                    {"name": "Web / App", "value": f"{metrics['web_share_pct']:.0f}% / {metrics['app_share_pct']:.0f}%"},
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
