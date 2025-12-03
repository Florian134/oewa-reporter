"""
API Authentication Module
==========================

Schützt API-Endpoints mit CRON_SECRET Token.

Verwendung:
- Vercel Cron-Jobs senden automatisch den Authorization-Header
- Manuelle Aufrufe benötigen: Authorization: Bearer <CRON_SECRET>
"""

import os
import hmac
import hashlib
from functools import wraps


def get_cron_secret() -> str:
    """Holt das CRON_SECRET aus den Environment-Variablen"""
    return os.getenv("CRON_SECRET", "")


def verify_cron_request(handler_method):
    """
    Decorator zur Authentifizierung von Cron-Requests.
    
    Prüft:
    1. Authorization Header (Bearer Token)
    2. Vercel Cron Header (x-vercel-cron-signature)
    
    Usage:
        @verify_cron_request
        def do_POST(self):
            ...
    """
    @wraps(handler_method)
    def wrapper(self, *args, **kwargs):
        # CRON_SECRET aus Environment
        cron_secret = get_cron_secret()
        
        # Wenn kein Secret konfiguriert → Warnung, aber durchlassen (Dev-Mode)
        if not cron_secret:
            # In Production sollte das IMMER gesetzt sein
            if os.getenv("VERCEL_ENV") == "production":
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(b'{"error": "CRON_SECRET not configured"}')
                return
            # Dev-Mode: Warnung loggen, aber durchlassen
            return handler_method(self, *args, **kwargs)
        
        # Header prüfen
        auth_header = self.headers.get("Authorization", "")
        vercel_signature = self.headers.get("x-vercel-signature", "")
        
        # Option 1: Bearer Token
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            if hmac.compare_digest(token, cron_secret):
                return handler_method(self, *args, **kwargs)
        
        # Option 2: Vercel Cron Signature (automatisch bei Vercel Cron-Jobs)
        if vercel_signature:
            # Vercel signiert mit dem CRON_SECRET
            if hmac.compare_digest(vercel_signature, cron_secret):
                return handler_method(self, *args, **kwargs)
        
        # Option 3: Query Parameter (für einfaches Testing)
        # NICHT für Production empfohlen!
        if os.getenv("VERCEL_ENV") != "production":
            from urllib.parse import urlparse, parse_qs
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            if params.get("secret", [None])[0] == cron_secret:
                return handler_method(self, *args, **kwargs)
        
        # Nicht autorisiert
        self.send_response(401)
        self.send_header('Content-type', 'application/json')
        self.send_header('WWW-Authenticate', 'Bearer realm="OEWA API"')
        self.end_headers()
        self.wfile.write(b'{"error": "Unauthorized", "message": "Valid CRON_SECRET required"}')
        return
    
    return wrapper


def generate_cron_secret(length: int = 32) -> str:
    """
    Generiert ein sicheres CRON_SECRET.
    
    Führe aus: python -c "from api.auth import generate_cron_secret; print(generate_cron_secret())"
    """
    import secrets
    return secrets.token_urlsafe(length)

