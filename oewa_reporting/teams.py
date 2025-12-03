"""
Microsoft Teams Integration
============================

Sendet Benachrichtigungen an Teams via Incoming Webhook.
Verwendet O365 Connector Cards für strukturierte Nachrichten.

Features:
- Retry-Logik mit exponentiellem Backoff
- Strukturierte Nachrichtenformate
- Thread-safe
"""

import logging
import time
import json
from datetime import date, datetime, timezone
from typing import List, Dict, Optional, Any
from functools import wraps

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import get_config
from .models import Alert
from .anomaly import AnomalyResult, Severity

logger = logging.getLogger(__name__)


# =============================================================================
# RETRY DECORATOR
# =============================================================================

def retry_on_failure(max_retries: int = 3, delay: float = 1.0, backoff: float = 2.0):
    """
    Decorator für Retry-Logik bei HTTP-Fehlern.
    
    Args:
        max_retries: Maximale Anzahl Versuche
        delay: Initiale Wartezeit
        backoff: Multiplikator für Wartezeit
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            current_delay = delay
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except requests.exceptions.RequestException as e:
                    last_exception = e
                    
                    if attempt < max_retries:
                        logger.warning(
                            f"Teams Webhook fehlgeschlagen (Versuch {attempt + 1}/{max_retries + 1}): {e}. "
                            f"Retry in {current_delay:.1f}s..."
                        )
                        time.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        logger.error(f"Teams Webhook fehlgeschlagen nach {max_retries + 1} Versuchen")
                        raise
            
            raise last_exception
        
        return wrapper
    return decorator


# =============================================================================
# TEAMS NOTIFIER CLASS
# =============================================================================

class TeamsNotifier:
    """
    Sendet Benachrichtigungen an Microsoft Teams.
    
    Verwendet das O365 Connector Card Format:
    https://docs.microsoft.com/en-us/outlook/actionable-messages/message-card-reference
    """
    
    # Farben für verschiedene Schweregrade
    COLORS = {
        "default": "0078D7",    # Microsoft Blue
        "success": "28A745",    # Grün
        "warning": "FFC107",    # Gelb/Orange
        "critical": "DC3545",   # Rot
        "info": "17A2B8",       # Cyan
    }
    
    def __init__(self, webhook_url: str = None):
        config = get_config()
        self.webhook_url = webhook_url or config.teams.webhook_url
        self.enabled = config.teams.enabled
        self.retry_attempts = config.teams.retry_attempts
        self.retry_delay = config.teams.retry_delay
        
        if not self.webhook_url and self.enabled:
            logger.warning("Teams Webhook URL nicht konfiguriert")
            self.enabled = False
        
        # Session mit Retry-Strategie
        self._session = self._create_session()
    
    def _create_session(self) -> requests.Session:
        """Erstellt eine HTTP-Session mit Retry-Strategie"""
        session = requests.Session()
        
        retry_strategy = Retry(
            total=self.retry_attempts,
            backoff_factor=self.retry_delay,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["POST"],
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        
        return session
    
    @retry_on_failure(max_retries=3, delay=1.0)
    def _send_card(self, card: Dict[str, Any]) -> bool:
        """
        Sendet eine Connector Card an Teams.
        
        Returns:
            True bei Erfolg, False bei Fehler
        """
        if not self.enabled:
            logger.debug("Teams Benachrichtigungen deaktiviert")
            return False
        
        try:
            response = self._session.post(
                self.webhook_url,
                json=card,
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            
            if response.status_code == 200:
                logger.info("Teams Nachricht erfolgreich gesendet")
                return True
            else:
                logger.error(
                    f"Teams Webhook Fehler: {response.status_code} - {response.text}"
                )
                return False
                
        except requests.exceptions.Timeout:
            logger.error("Teams Webhook Timeout")
            raise
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Teams Webhook Verbindungsfehler: {e}")
            raise
        except Exception as e:
            logger.error(f"Teams Webhook unerwarteter Fehler: {type(e).__name__}: {e}")
            raise
    
    def send_daily_report(
        self,
        report_date: date,
        metrics: Dict[str, Dict[str, int]],
        alerts: List[Alert] = None
    ) -> bool:
        """
        Sendet den täglichen Report.
        
        Args:
            report_date: Berichtsdatum
            metrics: Dict mit Metrik-Werten {brand: {metric_surface: value}}
            alerts: Liste der Alerts (optional)
            
        Returns:
            True bei Erfolg
        """
        alerts = alerts or []
        
        # Schweregrad für Farbe bestimmen
        has_critical = any(
            (a.severity == "critical" if isinstance(a.severity, str) else a.severity == Severity.CRITICAL)
            for a in alerts
        )
        has_warning = any(
            (a.severity == "warning" if isinstance(a.severity, str) else a.severity == Severity.WARNING)
            for a in alerts
        )
        
        if has_critical:
            color = self.COLORS["critical"]
        elif has_warning:
            color = self.COLORS["warning"]
        else:
            color = self.COLORS["success"]
        
        # Facts erstellen
        facts = []
        
        for brand, brand_metrics in metrics.items():
            brand_upper = brand.upper()
            
            # Page Impressions
            web_pi = brand_metrics.get("web_pi", 0)
            app_pi = brand_metrics.get("app_pi", 0)
            
            if web_pi:
                facts.append({
                    "name": f"{brand_upper} Web – PI",
                    "value": f"{web_pi:,}".replace(",", ".")
                })
            
            if app_pi:
                facts.append({
                    "name": f"{brand_upper} App – PI",
                    "value": f"{app_pi:,}".replace(",", ".")
                })
            
            # Visits
            web_visits = brand_metrics.get("web_visits", 0)
            app_visits = brand_metrics.get("app_visits", 0)
            
            if web_visits:
                facts.append({
                    "name": f"{brand_upper} Web – Visits",
                    "value": f"{web_visits:,}".replace(",", ".")
                })
            
            if app_visits:
                facts.append({
                    "name": f"{brand_upper} App – Visits",
                    "value": f"{app_visits:,}".replace(",", ".")
                })
        
        # Alert-Text erstellen
        alert_text = ""
        if alerts:
            alert_lines = []
            for alert in alerts:
                severity_str = alert.severity if isinstance(alert.severity, str) else alert.severity.value
                icon = "🔴" if severity_str == "critical" else "🟡"
                surface_name = alert.surface.replace("_", " ").title()
                pct_delta = alert.pct_delta if isinstance(alert.pct_delta, float) else 0.0
                direction = "+" if pct_delta > 0 else ""
                
                alert_lines.append(
                    f"{icon} **{alert.brand.upper()} {surface_name} – {alert.metric}**: "
                    f"{direction}{pct_delta*100:.1f}% vs. Median (z = {alert.zscore:+.2f})"
                )
            
            alert_text = "\n\n".join(alert_lines)
        else:
            alert_text = "✅ Keine Ausreißer erkannt"
        
        # Card erstellen
        card = {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "summary": f"ÖWA Daily Report – {report_date}",
            "themeColor": color,
            "sections": [
                {
                    "activityTitle": f"📊 ÖWA Daily Report – {report_date.strftime('%d.%m.%Y')}",
                    "activitySubtitle": f"Automatischer Tagesbericht",
                    "facts": facts,
                    "text": alert_text,
                    "markdown": True
                }
            ]
        }
        
        return self._send_card(card)
    
    def send_alert(
        self,
        alert: Alert,
        additional_context: str = None
    ) -> bool:
        """
        Sendet einen einzelnen Alert.
        """
        severity_str = alert.severity if isinstance(alert.severity, str) else alert.severity.value
        color = self.COLORS["critical"] if severity_str == "critical" else self.COLORS["warning"]
        icon = "🔴" if severity_str == "critical" else "🟡"
        
        surface_name = alert.surface.replace("_", " ").title()
        pct_delta = alert.pct_delta if isinstance(alert.pct_delta, float) else 0.0
        direction = "über" if pct_delta > 0 else "unter"
        
        facts = [
            {"name": "Brand", "value": alert.brand.upper()},
            {"name": "Surface", "value": surface_name},
            {"name": "Metrik", "value": alert.metric},
            {"name": "Datum", "value": alert.date.strftime("%d.%m.%Y")},
            {"name": "Aktueller Wert", "value": f"{alert.actual_value:,.0f}".replace(",", ".")},
            {"name": "Median (Baseline)", "value": f"{alert.baseline_median:,.0f}".replace(",", ".")},
            {"name": "Abweichung", "value": f"{pct_delta*100:+.1f}%"},
            {"name": "Z-Score", "value": f"{alert.zscore:+.2f}"},
        ]
        
        text = (
            f"Der Wert liegt **{abs(pct_delta)*100:.1f}% {direction}** dem "
            f"historischen Median. Dies entspricht einem Z-Score von **{alert.zscore:.2f}**."
        )
        
        if additional_context:
            text += f"\n\n{additional_context}"
        
        card = {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "summary": f"ÖWA Alert: {severity_str.upper()}",
            "themeColor": color,
            "sections": [
                {
                    "activityTitle": f"{icon} ÖWA Alert: {severity_str.upper()}",
                    "activitySubtitle": f"{alert.brand.upper()} {surface_name} – {alert.metric}",
                    "facts": facts,
                    "text": text,
                    "markdown": True
                }
            ]
        }
        
        return self._send_card(card)
    
    def send_weekly_summary(
        self,
        week_start: date,
        week_end: date,
        metrics_summary: Dict[str, Any],
        alerts: List[Alert]
    ) -> bool:
        """
        Sendet die wöchentliche Zusammenfassung.
        """
        warning_count = sum(
            1 for a in alerts 
            if (a.severity == "warning" if isinstance(a.severity, str) else a.severity == Severity.WARNING)
        )
        critical_count = sum(
            1 for a in alerts 
            if (a.severity == "critical" if isinstance(a.severity, str) else a.severity == Severity.CRITICAL)
        )
        
        if critical_count > 0:
            color = self.COLORS["critical"]
        elif warning_count > 0:
            color = self.COLORS["warning"]
        else:
            color = self.COLORS["success"]
        
        facts = []
        
        for brand, data in metrics_summary.items():
            brand_upper = brand.upper()
            
            facts.append({
                "name": f"{brand_upper} Web – PI (Ø/Tag)",
                "value": f"{data.get('avg_web_pi', 0):,.0f}".replace(",", ".")
            })
            
            facts.append({
                "name": f"{brand_upper} App – PI (Ø/Tag)",
                "value": f"{data.get('avg_app_pi', 0):,.0f}".replace(",", ".")
            })
        
        alert_text = f"📈 **Alerts diese Woche:**\n"
        alert_text += f"- 🔴 Critical: {critical_count}\n"
        alert_text += f"- 🟡 Warning: {warning_count}"
        
        if not alerts:
            alert_text = "✅ Keine Ausreißer in dieser Woche"
        
        card = {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "summary": f"ÖWA Wochenbericht KW{week_start.isocalendar()[1]}",
            "themeColor": color,
            "sections": [
                {
                    "activityTitle": f"📊 ÖWA Wochenbericht",
                    "activitySubtitle": f"KW{week_start.isocalendar()[1]} ({week_start.strftime('%d.%m.')} - {week_end.strftime('%d.%m.%Y')})",
                    "facts": facts,
                    "text": alert_text,
                    "markdown": True
                }
            ]
        }
        
        return self._send_card(card)
    
    def send_monthly_summary(
        self,
        year: int,
        month: int,
        metrics_summary: Dict[str, Any],
        alerts: List[Alert],
        comparison: Dict[str, float] = None
    ) -> bool:
        """
        Sendet die monatliche Zusammenfassung.
        """
        import calendar
        month_name = calendar.month_name[month]
        
        warning_count = sum(
            1 for a in alerts 
            if (a.severity == "warning" if isinstance(a.severity, str) else a.severity == Severity.WARNING)
        )
        critical_count = sum(
            1 for a in alerts 
            if (a.severity == "critical" if isinstance(a.severity, str) else a.severity == Severity.CRITICAL)
        )
        
        color = self.COLORS["info"]
        
        facts = []
        
        for brand, data in metrics_summary.items():
            brand_upper = brand.upper()
            
            # Gesamtwerte
            facts.append({
                "name": f"{brand_upper} Web – PI (Gesamt)",
                "value": f"{data.get('total_web_pi', 0):,.0f}".replace(",", ".")
            })
            
            facts.append({
                "name": f"{brand_upper} App – PI (Gesamt)",
                "value": f"{data.get('total_app_pi', 0):,.0f}".replace(",", ".")
            })
            
            # Vergleich zum Vormonat
            if comparison and brand in comparison:
                change = comparison[brand].get("web_pi_change", 0)
                arrow = "📈" if change > 0 else "📉" if change < 0 else "➡️"
                facts.append({
                    "name": f"{brand_upper} Web PI vs. Vormonat",
                    "value": f"{arrow} {change:+.1f}%"
                })
        
        text = f"**Alerts im {month_name}:**\n"
        text += f"- 🔴 Critical: {critical_count}\n"
        text += f"- 🟡 Warning: {warning_count}"
        
        card = {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "summary": f"ÖWA Monatsbericht {month_name} {year}",
            "themeColor": color,
            "sections": [
                {
                    "activityTitle": f"📊 ÖWA Monatsbericht",
                    "activitySubtitle": f"{month_name} {year}",
                    "facts": facts,
                    "text": text,
                    "markdown": True
                }
            ]
        }
        
        return self._send_card(card)
    
    def send_test_message(self) -> bool:
        """Sendet eine Testnachricht"""
        card = {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "summary": "ÖWA Reporting – Testverbindung",
            "themeColor": self.COLORS["info"],
            "sections": [
                {
                    "activityTitle": "🔔 ÖWA Reporting – Testverbindung",
                    "text": "Die Verbindung zum Teams-Webhook wurde erfolgreich hergestellt!",
                    "markdown": True
                }
            ]
        }
        
        return self._send_card(card)
    
    def close(self):
        """Schließt die HTTP-Session"""
        if self._session:
            self._session.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
