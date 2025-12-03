"""
Daily Cron Job - Tägliche Daten-Ingestion

Ausführung: Täglich um 08:00 UTC via Vercel Cron
"""
from http.server import BaseHTTPRequestHandler
import json
import os
import sys

# Projekt-Root zum Path hinzufügen
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            from oewa_reporting.scheduler import ScheduledTasks
            
            # Tägliche Ingestion ausführen
            result = ScheduledTasks.daily_ingestion(
                send_alerts=True,
                sync_airtable=True
            )
            
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
                "error": str(e)
            }
            self.wfile.write(json.dumps(error_response).encode())
    
    def do_GET(self):
        """GET für manuellen Test"""
        self.do_POST()

