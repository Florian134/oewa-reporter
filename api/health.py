"""
Health Check Endpoint
"""
from http.server import BaseHTTPRequestHandler
import json
from datetime import datetime


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        
        response = {
            "status": "healthy",
            "service": "oewa-reporter",
            "timestamp": datetime.utcnow().isoformat(),
            "version": "1.1.0",
            "security": "CRON_SECRET enabled",
            "deployment_test": "2024-12-03T11:30"
        }
        
        self.wfile.write(json.dumps(response).encode())

