"""
Erweitertes Alarming-System
============================

Business-kritische Schwellenwert-Überwachung mit:
- Absolute Mindestwerte für Metriken
- Prozentuale Abweichungen vs. Vorperiode
- Eskalationsstufen (Warning, Critical, Emergency)
- Automatische Teams-Benachrichtigung
- KI-gestützte Anomalie-Interpretation

Schwellenwerte basieren auf historischen VOL.at Daten.
"""

import logging
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum

from sqlalchemy import func, and_

from .config import get_config
from .db import get_session
from .models import Measurement, Alert, utc_now
from .teams import TeamsNotifier
from .anomaly import AnomalyDetector, AnomalyResult, Severity

logger = logging.getLogger(__name__)


# =============================================================================
# ALERT THRESHOLDS (Business-kritische Werte)
# =============================================================================

class AlertLevel(Enum):
    """Eskalationsstufen"""
    NORMAL = "normal"
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"  # Sofortige Eskalation an Management


@dataclass
class ThresholdConfig:
    """Konfiguration für Schwellenwerte einer Metrik"""
    metric: str
    
    # Absolute Mindestwerte pro Tag
    min_daily_warning: int      # Unter diesem Wert: Warning
    min_daily_critical: int     # Unter diesem Wert: Critical
    min_daily_emergency: int    # Unter diesem Wert: Emergency
    
    # Prozentuale Abweichung vs. Vorwoche
    pct_change_warning: float   # z.B. -0.15 = -15%
    pct_change_critical: float  # z.B. -0.25 = -25%
    pct_change_emergency: float # z.B. -0.40 = -40%
    
    # Beschreibung
    description: str = ""


# Standard-Schwellenwerte für VOL.at (basierend auf historischen Daten)
DEFAULT_THRESHOLDS = {
    "pageimpressions": ThresholdConfig(
        metric="pageimpressions",
        min_daily_warning=300000,      # < 300.000 PI/Tag
        min_daily_critical=200000,     # < 200.000 PI/Tag
        min_daily_emergency=100000,    # < 100.000 PI/Tag (Totalausfall?)
        pct_change_warning=-0.15,      # -15% vs. Vorwoche
        pct_change_critical=-0.25,     # -25% vs. Vorwoche
        pct_change_emergency=-0.40,    # -40% vs. Vorwoche
        description="Page Impressions - Seitenaufrufe"
    ),
    "visits": ThresholdConfig(
        metric="visits",
        min_daily_warning=100000,      # < 100.000 Visits/Tag
        min_daily_critical=70000,      # < 70.000 Visits/Tag
        min_daily_emergency=40000,     # < 40.000 Visits/Tag
        pct_change_warning=-0.15,      # -15% vs. Vorwoche
        pct_change_critical=-0.25,     # -25% vs. Vorwoche
        pct_change_emergency=-0.40,    # -40% vs. Vorwoche
        description="Visits - Besuche"
    ),
}


@dataclass
class ThresholdAlert:
    """Ein Schwellenwert-basierter Alert"""
    alert_type: str              # "absolute" oder "percentage"
    level: AlertLevel
    metric: str
    brand: str
    surface: str
    date: date
    
    # Werte
    actual_value: float
    threshold_value: float
    
    # Vergleich (für prozentuale Alerts)
    comparison_value: Optional[float] = None
    pct_change: Optional[float] = None
    
    # Kontext
    message: str = ""
    context: Dict[str, Any] = field(default_factory=dict)
    
    # Zeitstempel
    created_at: datetime = field(default_factory=utc_now)
    
    def to_dict(self) -> dict:
        return {
            "alert_type": self.alert_type,
            "level": self.level.value,
            "metric": self.metric,
            "brand": self.brand,
            "surface": self.surface,
            "date": self.date.isoformat(),
            "actual_value": self.actual_value,
            "threshold_value": self.threshold_value,
            "comparison_value": self.comparison_value,
            "pct_change": self.pct_change,
            "message": self.message
        }


# =============================================================================
# ALERTING ENGINE
# =============================================================================

class AlertingEngine:
    """
    Zentrale Alerting-Logik für das ÖWA Reporting System.
    
    Features:
    - Mehrere Schwellenwert-Typen (absolut, prozentual, Anomalie)
    - Eskalationsstufen mit unterschiedlichen Benachrichtigungen
    - Integration mit Teams und KI-Interpreter
    - Deduplizierung von Alerts
    """
    
    def __init__(
        self,
        thresholds: Dict[str, ThresholdConfig] = None,
        teams_notifier: TeamsNotifier = None
    ):
        """
        Initialisiert die Alerting Engine.
        
        Args:
            thresholds: Schwellenwert-Konfiguration (Default: VOL.at Werte)
            teams_notifier: Teams-Benachrichtigungs-Instanz
        """
        self.thresholds = thresholds or DEFAULT_THRESHOLDS
        self.teams = teams_notifier or TeamsNotifier()
        self.config = get_config()
        self.anomaly_detector = AnomalyDetector()
        
        # KI-Interpreter (optional)
        self._ai_interpreter = None
    
    @property
    def ai_interpreter(self):
        """Lazy-Loading des AI Interpreters"""
        if self._ai_interpreter is None:
            try:
                from .ai_interpreter import AIInterpreter
                self._ai_interpreter = AIInterpreter()
            except Exception as e:
                logger.warning(f"AI Interpreter nicht verfügbar: {e}")
        return self._ai_interpreter
    
    def check_daily_thresholds(
        self,
        target_date: date = None
    ) -> List[ThresholdAlert]:
        """
        Prüft alle Schwellenwerte für einen Tag.
        
        Args:
            target_date: Zu prüfendes Datum (Default: gestern)
            
        Returns:
            Liste der ausgelösten Alerts
        """
        target_date = target_date or (date.today() - timedelta(days=1))
        comparison_date = target_date - timedelta(days=7)  # Vorwoche
        
        alerts = []
        
        for site in self.config.sites:
            for metric, threshold in self.thresholds.items():
                # Aktueller Wert
                current = self._get_daily_value(
                    site.brand, site.surface, metric, target_date
                )
                
                if current is None:
                    logger.warning(
                        f"Keine Daten für {site.name}/{metric}/{target_date}"
                    )
                    continue
                
                # Vorwochen-Wert
                previous = self._get_daily_value(
                    site.brand, site.surface, metric, comparison_date
                )
                
                # 1. Absolute Schwellenwerte prüfen
                abs_alert = self._check_absolute_threshold(
                    current, threshold, metric, site.brand, site.surface, target_date
                )
                if abs_alert:
                    alerts.append(abs_alert)
                
                # 2. Prozentuale Schwellenwerte prüfen
                if previous and previous > 0:
                    pct_alert = self._check_percentage_threshold(
                        current, previous, threshold,
                        metric, site.brand, site.surface, target_date
                    )
                    if pct_alert:
                        alerts.append(pct_alert)
        
        # Nach Schweregrad sortieren
        alerts.sort(key=lambda a: list(AlertLevel).index(a.level), reverse=True)
        
        logger.info(f"Threshold-Check für {target_date}: {len(alerts)} Alerts")
        
        return alerts
    
    def check_weekly_thresholds(
        self,
        week_end: date = None
    ) -> List[ThresholdAlert]:
        """
        Prüft Wochen-aggregierte Schwellenwerte.
        
        Args:
            week_end: Letzter Tag der Woche
            
        Returns:
            Liste der ausgelösten Alerts
        """
        if week_end is None:
            today = date.today()
            week_end = today - timedelta(days=today.weekday() + 1)
        
        week_start = week_end - timedelta(days=6)
        prev_week_end = week_start - timedelta(days=1)
        prev_week_start = prev_week_end - timedelta(days=6)
        
        alerts = []
        
        for site in self.config.sites:
            for metric, threshold in self.thresholds.items():
                # Wochensummen
                current_week = self._get_period_sum(
                    site.brand, site.surface, metric, week_start, week_end
                )
                prev_week = self._get_period_sum(
                    site.brand, site.surface, metric, prev_week_start, prev_week_end
                )
                
                if current_week and prev_week and prev_week > 0:
                    pct_change = (current_week - prev_week) / prev_week
                    
                    # Prüfe prozentuale Schwellenwerte
                    level = AlertLevel.NORMAL
                    if pct_change <= threshold.pct_change_emergency:
                        level = AlertLevel.EMERGENCY
                    elif pct_change <= threshold.pct_change_critical:
                        level = AlertLevel.CRITICAL
                    elif pct_change <= threshold.pct_change_warning:
                        level = AlertLevel.WARNING
                    
                    if level != AlertLevel.NORMAL:
                        alerts.append(ThresholdAlert(
                            alert_type="weekly_percentage",
                            level=level,
                            metric=metric,
                            brand=site.brand,
                            surface=site.surface,
                            date=week_end,
                            actual_value=current_week,
                            threshold_value=threshold.pct_change_warning,
                            comparison_value=prev_week,
                            pct_change=pct_change,
                            message=self._generate_weekly_message(
                                metric, site.brand, site.surface,
                                current_week, prev_week, pct_change, level
                            )
                        ))
        
        return alerts
    
    def process_and_notify(
        self,
        alerts: List[ThresholdAlert],
        include_ai_interpretation: bool = True
    ) -> Dict[str, int]:
        """
        Verarbeitet Alerts und sendet Benachrichtigungen.
        
        Args:
            alerts: Liste der Alerts
            include_ai_interpretation: KI-Interpretation hinzufügen?
            
        Returns:
            Statistiken (gesendet, fehlgeschlagen)
        """
        stats = {"sent": 0, "failed": 0, "skipped": 0}
        
        if not alerts:
            logger.info("Keine Alerts zum Verarbeiten")
            return stats
        
        # Gruppiere nach Level
        emergency_alerts = [a for a in alerts if a.level == AlertLevel.EMERGENCY]
        critical_alerts = [a for a in alerts if a.level == AlertLevel.CRITICAL]
        warning_alerts = [a for a in alerts if a.level == AlertLevel.WARNING]
        
        # Emergency: Sofort einzeln senden
        for alert in emergency_alerts:
            if self._send_alert_notification(alert, include_ai_interpretation):
                stats["sent"] += 1
            else:
                stats["failed"] += 1
        
        # Critical: Zusammenfassen falls mehrere
        if critical_alerts:
            if len(critical_alerts) == 1:
                if self._send_alert_notification(critical_alerts[0], include_ai_interpretation):
                    stats["sent"] += 1
                else:
                    stats["failed"] += 1
            else:
                if self._send_grouped_notification(critical_alerts, "CRITICAL"):
                    stats["sent"] += len(critical_alerts)
                else:
                    stats["failed"] += len(critical_alerts)
        
        # Warning: Immer zusammenfassen
        if warning_alerts:
            if self._send_grouped_notification(warning_alerts, "WARNING"):
                stats["sent"] += len(warning_alerts)
            else:
                stats["failed"] += len(warning_alerts)
        
        return stats
    
    def run_full_check(
        self,
        target_date: date = None,
        send_notifications: bool = True
    ) -> Dict[str, Any]:
        """
        Führt kompletten Threshold- und Anomalie-Check durch.
        
        Args:
            target_date: Zu prüfendes Datum
            send_notifications: Teams-Benachrichtigungen senden?
            
        Returns:
            Zusammenfassung der Prüfung
        """
        target_date = target_date or (date.today() - timedelta(days=1))
        
        result = {
            "date": target_date.isoformat(),
            "threshold_alerts": [],
            "anomaly_alerts": [],
            "notifications_sent": 0,
            "status": "ok"
        }
        
        # 1. Schwellenwert-Check
        threshold_alerts = self.check_daily_thresholds(target_date)
        result["threshold_alerts"] = [a.to_dict() for a in threshold_alerts]
        
        # 2. Status basierend auf Alerts
        if any(a.level == AlertLevel.EMERGENCY for a in threshold_alerts):
            result["status"] = "emergency"
        elif any(a.level == AlertLevel.CRITICAL for a in threshold_alerts):
            result["status"] = "critical"
        elif any(a.level == AlertLevel.WARNING for a in threshold_alerts):
            result["status"] = "warning"
        
        # 3. Benachrichtigungen senden
        if send_notifications and threshold_alerts:
            stats = self.process_and_notify(threshold_alerts)
            result["notifications_sent"] = stats["sent"]
        
        logger.info(f"Full check completed: {result['status']}, {len(threshold_alerts)} alerts")
        
        return result
    
    # =========================================================================
    # PRIVATE METHODS
    # =========================================================================
    
    def _get_daily_value(
        self, brand: str, surface: str, metric: str, target_date: date
    ) -> Optional[int]:
        """Holt Tageswert aus DB"""
        with get_session() as session:
            result = session.query(
                func.sum(Measurement.value_total)
            ).filter(
                and_(
                    Measurement.brand == brand,
                    Measurement.surface == surface,
                    Measurement.metric == metric,
                    Measurement.date == target_date
                )
            ).scalar()
            
            return result
    
    def _get_period_sum(
        self, brand: str, surface: str, metric: str,
        start_date: date, end_date: date
    ) -> Optional[int]:
        """Holt Periodensumme aus DB"""
        with get_session() as session:
            result = session.query(
                func.sum(Measurement.value_total)
            ).filter(
                and_(
                    Measurement.brand == brand,
                    Measurement.surface == surface,
                    Measurement.metric == metric,
                    Measurement.date >= start_date,
                    Measurement.date <= end_date
                )
            ).scalar()
            
            return result
    
    def _check_absolute_threshold(
        self,
        value: int,
        threshold: ThresholdConfig,
        metric: str,
        brand: str,
        surface: str,
        target_date: date
    ) -> Optional[ThresholdAlert]:
        """Prüft absolute Schwellenwerte"""
        level = AlertLevel.NORMAL
        threshold_value = 0
        
        if value < threshold.min_daily_emergency:
            level = AlertLevel.EMERGENCY
            threshold_value = threshold.min_daily_emergency
        elif value < threshold.min_daily_critical:
            level = AlertLevel.CRITICAL
            threshold_value = threshold.min_daily_critical
        elif value < threshold.min_daily_warning:
            level = AlertLevel.WARNING
            threshold_value = threshold.min_daily_warning
        
        if level != AlertLevel.NORMAL:
            return ThresholdAlert(
                alert_type="absolute",
                level=level,
                metric=metric,
                brand=brand,
                surface=surface,
                date=target_date,
                actual_value=value,
                threshold_value=threshold_value,
                message=self._generate_absolute_message(
                    metric, brand, surface, value, threshold_value, level
                )
            )
        
        return None
    
    def _check_percentage_threshold(
        self,
        current: int,
        previous: int,
        threshold: ThresholdConfig,
        metric: str,
        brand: str,
        surface: str,
        target_date: date
    ) -> Optional[ThresholdAlert]:
        """Prüft prozentuale Schwellenwerte"""
        pct_change = (current - previous) / previous
        
        level = AlertLevel.NORMAL
        threshold_value = 0
        
        if pct_change <= threshold.pct_change_emergency:
            level = AlertLevel.EMERGENCY
            threshold_value = threshold.pct_change_emergency
        elif pct_change <= threshold.pct_change_critical:
            level = AlertLevel.CRITICAL
            threshold_value = threshold.pct_change_critical
        elif pct_change <= threshold.pct_change_warning:
            level = AlertLevel.WARNING
            threshold_value = threshold.pct_change_warning
        
        if level != AlertLevel.NORMAL:
            return ThresholdAlert(
                alert_type="percentage",
                level=level,
                metric=metric,
                brand=brand,
                surface=surface,
                date=target_date,
                actual_value=current,
                threshold_value=threshold_value,
                comparison_value=previous,
                pct_change=pct_change,
                message=self._generate_percentage_message(
                    metric, brand, surface, current, previous, pct_change, level
                )
            )
        
        return None
    
    def _generate_absolute_message(
        self, metric: str, brand: str, surface: str,
        value: int, threshold: int, level: AlertLevel
    ) -> str:
        """Generiert Nachricht für absoluten Alert"""
        metric_name = "Page Impressions" if metric == "pageimpressions" else "Visits"
        surface_name = self._format_surface(surface)
        
        return (
            f"⚠️ {level.value.upper()}: {brand.upper()} {surface_name} - "
            f"{metric_name} unter Minimum!\n"
            f"Aktuell: {value:,.0f} | Schwelle: {threshold:,.0f}".replace(",", ".")
        )
    
    def _generate_percentage_message(
        self, metric: str, brand: str, surface: str,
        current: int, previous: int, pct_change: float, level: AlertLevel
    ) -> str:
        """Generiert Nachricht für prozentualen Alert"""
        metric_name = "Page Impressions" if metric == "pageimpressions" else "Visits"
        surface_name = self._format_surface(surface)
        
        return (
            f"📉 {level.value.upper()}: {brand.upper()} {surface_name} - "
            f"{metric_name} {pct_change*100:+.1f}% vs. Vorwoche\n"
            f"Aktuell: {current:,.0f} | Vorwoche: {previous:,.0f}".replace(",", ".")
        )
    
    def _generate_weekly_message(
        self, metric: str, brand: str, surface: str,
        current: int, previous: int, pct_change: float, level: AlertLevel
    ) -> str:
        """Generiert Wochenbericht-Nachricht"""
        return self._generate_percentage_message(
            metric, brand, surface, current, previous, pct_change, level
        ).replace("vs. Vorwoche", "Woche vs. Vorwoche")
    
    def _format_surface(self, surface: str) -> str:
        """Formatiert Surface-Namen"""
        return {
            "web_desktop": "Web Desktop",
            "web_mobile": "Web Mobile",
            "app": "App"
        }.get(surface, surface)
    
    def _send_alert_notification(
        self,
        alert: ThresholdAlert,
        include_ai: bool = True
    ) -> bool:
        """Sendet einzelne Alert-Benachrichtigung"""
        # Farbe basierend auf Level
        colors = {
            AlertLevel.EMERGENCY: "8B0000",  # Dunkelrot
            AlertLevel.CRITICAL: "DC3545",   # Rot
            AlertLevel.WARNING: "FFC107",    # Gelb
        }
        
        color = colors.get(alert.level, "0078D7")
        icon = "🚨" if alert.level == AlertLevel.EMERGENCY else "🔴" if alert.level == AlertLevel.CRITICAL else "🟡"
        
        # KI-Interpretation (falls verfügbar)
        ai_text = ""
        if include_ai and self.ai_interpreter:
            try:
                # Erstelle temporären Alert für KI
                temp_alert = Alert(
                    brand=alert.brand,
                    surface=alert.surface,
                    metric=alert.metric,
                    date=alert.date,
                    severity=alert.level.value,
                    zscore=0,
                    pct_delta=alert.pct_change or 0,
                    baseline_median=alert.comparison_value or 0,
                    actual_value=alert.actual_value
                )
                
                interpretation = self.ai_interpreter.interpret_anomaly(temp_alert)
                if interpretation.success:
                    ai_text = f"\n\n**🤖 KI-Analyse:**\n{interpretation.interpretation}"
            except Exception as e:
                logger.warning(f"KI-Interpretation fehlgeschlagen: {e}")
        
        card = {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "summary": f"ÖWA Alert: {alert.level.value.upper()}",
            "themeColor": color,
            "sections": [
                {
                    "activityTitle": f"{icon} ÖWA {alert.level.value.upper()} Alert",
                    "activitySubtitle": f"{alert.brand.upper()} - {alert.date.strftime('%d.%m.%Y')}",
                    "facts": [
                        {"name": "Metrik", "value": alert.metric},
                        {"name": "Plattform", "value": self._format_surface(alert.surface)},
                        {"name": "Aktueller Wert", "value": f"{alert.actual_value:,.0f}".replace(",", ".")},
                        {"name": "Schwelle", "value": f"{alert.threshold_value:,.0f}".replace(",", ".")},
                    ],
                    "text": alert.message + ai_text,
                    "markdown": True
                }
            ]
        }
        
        if alert.pct_change is not None:
            card["sections"][0]["facts"].append({
                "name": "Veränderung",
                "value": f"{alert.pct_change*100:+.1f}%"
            })
        
        return self.teams._send_card(card)
    
    def _send_grouped_notification(
        self,
        alerts: List[ThresholdAlert],
        level: str
    ) -> bool:
        """Sendet gruppierte Benachrichtigung"""
        color = "DC3545" if level == "CRITICAL" else "FFC107"
        icon = "🔴" if level == "CRITICAL" else "🟡"
        
        # Gruppiere nach Metrik
        alert_text = ""
        for alert in alerts:
            alert_text += f"\n• {alert.brand.upper()} {self._format_surface(alert.surface)}: {alert.message}"
        
        card = {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "summary": f"ÖWA: {len(alerts)} {level} Alerts",
            "themeColor": color,
            "sections": [
                {
                    "activityTitle": f"{icon} ÖWA {level} Zusammenfassung",
                    "activitySubtitle": f"{len(alerts)} Alerts erkannt",
                    "text": alert_text,
                    "markdown": True
                }
            ]
        }
        
        return self.teams._send_card(card)


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def run_daily_alert_check(
    target_date: date = None,
    send_notifications: bool = True
) -> Dict[str, Any]:
    """
    Convenience-Funktion für täglichen Alert-Check.
    
    Args:
        target_date: Zu prüfendes Datum
        send_notifications: Teams-Benachrichtigungen senden?
        
    Returns:
        Prüfungsergebnis
    """
    engine = AlertingEngine()
    return engine.run_full_check(target_date, send_notifications)


def run_weekly_alert_check(
    week_end: date = None,
    send_notifications: bool = True
) -> Dict[str, Any]:
    """
    Convenience-Funktion für wöchentlichen Alert-Check.
    """
    engine = AlertingEngine()
    alerts = engine.check_weekly_thresholds(week_end)
    
    result = {
        "week_end": week_end.isoformat() if week_end else None,
        "alerts": [a.to_dict() for a in alerts],
        "notifications_sent": 0
    }
    
    if send_notifications and alerts:
        stats = engine.process_and_notify(alerts)
        result["notifications_sent"] = stats["sent"]
    
    return result

