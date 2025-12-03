"""
Monthly Cron Job - Monatlicher KI-Report

Ausführung: 1. des Monats um 10:00 UTC via Vercel Cron
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
            
            # Monatlichen Report generieren
            result = ScheduledTasks.monthly_report(
                send_teams=True,
                use_ai=True
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

