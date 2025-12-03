"""
Scheduler für Vercel Deployment
================================

Definiert Cron-Jobs und Trigger-Endpoints für:
- Tägliche Daten-Ingestion
- Wöchentliche Reports mit KI-Interpretation
- Monatliche Reports mit KI-Interpretation
- Airtable-Synchronisation
- Alert-Checks

Diese Endpoints können von Vercel Cron-Jobs oder externen
Triggern aufgerufen werden.
"""

import logging
import os
from datetime import date, datetime, timedelta
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# SCHEDULED TASKS
# =============================================================================

class ScheduledTasks:
    """
    Container für alle geplanten Aufgaben.
    
    Jede Methode kann als Vercel Serverless Function aufgerufen werden.
    """
    
    @staticmethod
    def daily_ingestion(
        target_date: date = None,
        send_alerts: bool = True,
        sync_airtable: bool = True
    ) -> Dict[str, Any]:
        """
        Tägliche Daten-Ingestion.
        
        Ausführung: Täglich um 08:00 Uhr
        
        1. Holt Daten von INFOnline API
        2. Speichert in Datenbank
        3. Führt Anomalie-Erkennung durch
        4. Prüft Schwellenwerte
        5. Sendet Alerts (falls nötig)
        6. Synchronisiert mit Airtable
        
        Args:
            target_date: Datum für Ingestion (Default: gestern)
            send_alerts: Alerts bei Anomalien senden
            sync_airtable: Daten mit Airtable synchronisieren
            
        Returns:
            Ergebnis-Dictionary
        """
        target_date = target_date or (date.today() - timedelta(days=1))
        
        logger.info(f"=== DAILY INGESTION: {target_date} ===")
        
        result = {
            "date": target_date.isoformat(),
            "status": "success",
            "ingestion": None,
            "alerts": None,
            "airtable": None,
            "errors": []
        }
        
        try:
            # 1. Daten-Ingestion
            from .ingest import DataIngester
            
            ingester = DataIngester()
            ingestion_stats = ingester.ingest_day(target_date)
            result["ingestion"] = ingestion_stats
            
            logger.info(f"Ingestion: {ingestion_stats}")
            
        except Exception as e:
            logger.error(f"Ingestion Fehler: {e}")
            result["errors"].append(f"Ingestion: {str(e)}")
            result["status"] = "partial"
        
        # 2. Alert-Check
        if send_alerts:
            try:
                from .alerting import run_daily_alert_check
                
                alert_result = run_daily_alert_check(target_date)
                result["alerts"] = alert_result
                
                logger.info(f"Alerts: {alert_result.get('status', 'unknown')}")
                
            except Exception as e:
                logger.error(f"Alert-Check Fehler: {e}")
                result["errors"].append(f"Alerts: {str(e)}")
        
        # 3. Airtable Sync
        if sync_airtable:
            try:
                from .airtable_sync import sync_daily_data
                
                airtable_result = sync_daily_data(target_date)
                result["airtable"] = airtable_result
                
                logger.info(f"Airtable Sync: {airtable_result}")
                
            except Exception as e:
                logger.error(f"Airtable Sync Fehler: {e}")
                result["errors"].append(f"Airtable: {str(e)}")
        
        if result["errors"]:
            result["status"] = "partial" if result["ingestion"] else "failed"
        
        logger.info(f"=== DAILY INGESTION COMPLETE: {result['status']} ===")
        
        return result
    
    @staticmethod
    def weekly_report(
        week_end: date = None,
        send_teams: bool = True,
        use_ai: bool = True
    ) -> Dict[str, Any]:
        """
        Wöchentlicher Report mit KI-Interpretation.
        
        Ausführung: Montag um 09:00 Uhr
        
        1. Aggregiert Wochendaten
        2. Generiert KI-Interpretation (GPT-4)
        3. Sendet Report an Teams
        
        Args:
            week_end: Letzter Tag der Woche (Default: letzter Sonntag)
            send_teams: Report an Teams senden
            use_ai: KI-Interpretation verwenden
            
        Returns:
            Ergebnis-Dictionary
        """
        if week_end is None:
            today = date.today()
            # Finde letzten Sonntag
            week_end = today - timedelta(days=today.weekday() + 1)
        
        week_start = week_end - timedelta(days=6)
        
        logger.info(f"=== WEEKLY REPORT: {week_start} - {week_end} ===")
        
        result = {
            "week_start": week_start.isoformat(),
            "week_end": week_end.isoformat(),
            "status": "success",
            "ai_interpretation": None,
            "teams_sent": False,
            "errors": []
        }
        
        interpretation_text = ""
        
        # 1. KI-Interpretation generieren
        if use_ai:
            try:
                from .ai_interpreter import AIInterpreter
                
                interpreter = AIInterpreter()
                ai_result = interpreter.generate_weekly_summary(week_end)
                
                if ai_result.success:
                    interpretation_text = ai_result.interpretation
                    result["ai_interpretation"] = {
                        "success": True,
                        "tokens_used": ai_result.tokens_used
                    }
                    logger.info(f"KI-Interpretation generiert ({ai_result.tokens_used} Tokens)")
                else:
                    result["ai_interpretation"] = {
                        "success": False,
                        "error": ai_result.error
                    }
                    result["errors"].append(f"AI: {ai_result.error}")
                    
            except Exception as e:
                logger.error(f"KI-Interpretation Fehler: {e}")
                result["errors"].append(f"AI: {str(e)}")
        
        # 2. Teams-Benachrichtigung
        if send_teams:
            try:
                from .teams import TeamsNotifier
                from .ingest import DataIngester
                from .alerting import AlertingEngine
                
                # Daten aggregieren
                ingester = DataIngester()
                alerting = AlertingEngine()
                
                # Hole Wochendaten
                from .db import get_session
                from .models import Measurement, Alert
                from sqlalchemy import func, and_
                
                with get_session() as session:
                    # Aggregierte Metriken
                    metrics = {}
                    for brand in ["vol"]:
                        summary = ingester.get_date_range_summary(
                            week_start, week_end, brand
                        )
                        
                        web_pi = (
                            summary.get("pageimpressions", {}).get("web_desktop", 0) +
                            summary.get("pageimpressions", {}).get("web_mobile", 0)
                        )
                        app_pi = summary.get("pageimpressions", {}).get("app", 0)
                        
                        metrics[brand] = {
                            "web_pi": web_pi,
                            "app_pi": app_pi,
                            "avg_web_pi": web_pi // 7,
                            "avg_app_pi": app_pi // 7
                        }
                    
                    # Alerts der Woche
                    alerts = session.query(Alert).filter(
                        and_(
                            Alert.date >= week_start,
                            Alert.date <= week_end
                        )
                    ).all()
                
                # Card erstellen
                notifier = TeamsNotifier()
                
                # Executive Briefing Card
                card = {
                    "@type": "MessageCard",
                    "@context": "http://schema.org/extensions",
                    "summary": f"ÖWA Wochenbericht KW{week_start.isocalendar()[1]}",
                    "themeColor": "0078D7",
                    "sections": [
                        {
                            "activityTitle": f"📊 ÖWA Wochenbericht KW{week_start.isocalendar()[1]}",
                            "activitySubtitle": f"{week_start.strftime('%d.%m.')} - {week_end.strftime('%d.%m.%Y')}",
                            "facts": [
                                {"name": "VOL Web PI (Gesamt)", "value": f"{metrics['vol']['web_pi']:,.0f}".replace(",", ".")},
                                {"name": "VOL App PI (Gesamt)", "value": f"{metrics['vol']['app_pi']:,.0f}".replace(",", ".")},
                                {"name": "Alerts", "value": f"{len(alerts)} ({sum(1 for a in alerts if a.severity == 'critical')} kritisch)"},
                            ],
                            "markdown": True
                        }
                    ]
                }
                
                # KI-Interpretation hinzufügen
                if interpretation_text:
                    card["sections"].append({
                        "activityTitle": "🤖 KI-Analyse",
                        "text": interpretation_text,
                        "markdown": True
                    })
                
                if notifier._send_card(card):
                    result["teams_sent"] = True
                    logger.info("Teams-Report gesendet")
                else:
                    result["errors"].append("Teams: Senden fehlgeschlagen")
                    
            except Exception as e:
                logger.error(f"Teams-Report Fehler: {e}")
                result["errors"].append(f"Teams: {str(e)}")
        
        if result["errors"]:
            result["status"] = "partial"
        
        logger.info(f"=== WEEKLY REPORT COMPLETE: {result['status']} ===")
        
        return result
    
    @staticmethod
    def monthly_report(
        year: int = None,
        month: int = None,
        send_teams: bool = True,
        use_ai: bool = True
    ) -> Dict[str, Any]:
        """
        Monatlicher Report mit KI-Interpretation.
        
        Ausführung: 1. des Monats um 10:00 Uhr
        
        Args:
            year: Jahr (Default: voriger Monat)
            month: Monat (Default: voriger Monat)
            send_teams: Report an Teams senden
            use_ai: KI-Interpretation verwenden
            
        Returns:
            Ergebnis-Dictionary
        """
        import calendar
        
        if year is None or month is None:
            today = date.today()
            if today.month == 1:
                year = today.year - 1
                month = 12
            else:
                year = today.year
                month = today.month - 1
        
        month_name = calendar.month_name[month]
        _, last_day = calendar.monthrange(year, month)
        month_start = date(year, month, 1)
        month_end = date(year, month, last_day)
        
        logger.info(f"=== MONTHLY REPORT: {month_name} {year} ===")
        
        result = {
            "year": year,
            "month": month,
            "month_name": month_name,
            "status": "success",
            "ai_interpretation": None,
            "teams_sent": False,
            "errors": []
        }
        
        interpretation_text = ""
        
        # 1. KI-Interpretation
        if use_ai:
            try:
                from .ai_interpreter import AIInterpreter
                
                interpreter = AIInterpreter()
                ai_result = interpreter.generate_monthly_summary(year, month)
                
                if ai_result.success:
                    interpretation_text = ai_result.interpretation
                    result["ai_interpretation"] = {
                        "success": True,
                        "tokens_used": ai_result.tokens_used
                    }
                else:
                    result["ai_interpretation"] = {
                        "success": False,
                        "error": ai_result.error
                    }
                    result["errors"].append(f"AI: {ai_result.error}")
                    
            except Exception as e:
                logger.error(f"KI-Interpretation Fehler: {e}")
                result["errors"].append(f"AI: {str(e)}")
        
        # 2. Teams-Benachrichtigung
        if send_teams:
            try:
                from .teams import TeamsNotifier
                from .db import get_session
                from .models import Measurement, Alert
                from sqlalchemy import func, and_
                
                with get_session() as session:
                    # Monats-Aggregate
                    totals = session.query(
                        Measurement.metric,
                        Measurement.surface,
                        func.sum(Measurement.value_total).label("total")
                    ).filter(
                        and_(
                            Measurement.date >= month_start,
                            Measurement.date <= month_end
                        )
                    ).group_by(
                        Measurement.metric,
                        Measurement.surface
                    ).all()
                    
                    # Alerts
                    alerts = session.query(Alert).filter(
                        and_(
                            Alert.date >= month_start,
                            Alert.date <= month_end
                        )
                    ).all()
                
                # Aggregieren
                metrics = {"pageimpressions": {}, "visits": {}}
                for row in totals:
                    if row.metric in metrics:
                        metrics[row.metric][row.surface] = row.total
                
                web_pi = (
                    metrics["pageimpressions"].get("web_desktop", 0) +
                    metrics["pageimpressions"].get("web_mobile", 0)
                )
                app_pi = metrics["pageimpressions"].get("app", 0)
                
                notifier = TeamsNotifier()
                
                card = {
                    "@type": "MessageCard",
                    "@context": "http://schema.org/extensions",
                    "summary": f"ÖWA Monatsbericht {month_name} {year}",
                    "themeColor": "17A2B8",
                    "sections": [
                        {
                            "activityTitle": f"📊 ÖWA Monatsbericht",
                            "activitySubtitle": f"{month_name} {year}",
                            "facts": [
                                {"name": "Web PI (Gesamt)", "value": f"{web_pi:,.0f}".replace(",", ".")},
                                {"name": "App PI (Gesamt)", "value": f"{app_pi:,.0f}".replace(",", ".")},
                                {"name": "Ø PI/Tag (Web)", "value": f"{web_pi // last_day:,.0f}".replace(",", ".")},
                                {"name": "Alerts im Monat", "value": f"{len(alerts)}"},
                            ],
                            "markdown": True
                        }
                    ]
                }
                
                if interpretation_text:
                    card["sections"].append({
                        "activityTitle": "🤖 KI-Analyse",
                        "text": interpretation_text,
                        "markdown": True
                    })
                
                if notifier._send_card(card):
                    result["teams_sent"] = True
                else:
                    result["errors"].append("Teams: Senden fehlgeschlagen")
                    
            except Exception as e:
                logger.error(f"Teams-Report Fehler: {e}")
                result["errors"].append(f"Teams: {str(e)}")
        
        if result["errors"]:
            result["status"] = "partial"
        
        logger.info(f"=== MONTHLY REPORT COMPLETE: {result['status']} ===")
        
        return result


# =============================================================================
# VERCEL HANDLER
# =============================================================================

def handle_cron_request(
    task_type: str,
    **kwargs
) -> Dict[str, Any]:
    """
    Handler für Vercel Cron-Requests.
    
    Kann als Serverless Function verwendet werden.
    
    Args:
        task_type: Art der Aufgabe (daily, weekly, monthly)
        **kwargs: Zusätzliche Parameter
        
    Returns:
        Ergebnis-Dictionary
    """
    tasks = ScheduledTasks()
    
    if task_type == "daily":
        return tasks.daily_ingestion(**kwargs)
    elif task_type == "weekly":
        return tasks.weekly_report(**kwargs)
    elif task_type == "monthly":
        return tasks.monthly_report(**kwargs)
    else:
        return {
            "error": f"Unbekannter Task-Typ: {task_type}",
            "available": ["daily", "weekly", "monthly"]
        }


# =============================================================================
# CRON SCHEDULE DEFINITIONS (für vercel.json)
# =============================================================================

CRON_SCHEDULES = {
    "daily_ingestion": {
        "schedule": "0 8 * * *",  # Täglich um 08:00 UTC
        "description": "Tägliche Daten-Ingestion",
        "endpoint": "/api/cron/daily"
    },
    "weekly_report": {
        "schedule": "0 9 * * 1",  # Montag um 09:00 UTC
        "description": "Wöchentlicher KI-Report",
        "endpoint": "/api/cron/weekly"
    },
    "monthly_report": {
        "schedule": "0 10 1 * *",  # 1. des Monats um 10:00 UTC
        "description": "Monatlicher KI-Report",
        "endpoint": "/api/cron/monthly"
    }
}


if __name__ == "__main__":
    # Test-Ausführung
    import sys
    
    if len(sys.argv) > 1:
        task = sys.argv[1]
        result = handle_cron_request(task)
        print(result)
    else:
        print("Usage: python scheduler.py [daily|weekly|monthly]")

