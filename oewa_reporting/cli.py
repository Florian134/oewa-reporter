"""
Command Line Interface
======================

CLI-Befehle für das ÖWA Reporting System.
"""

import logging
import sys
from datetime import date, datetime, timedelta
from typing import Optional

import click

from .config import get_config, reload_config
from .db import init_database, check_connection
from .api_client import INFOnlineAPIClient
from .ingest import DataIngester
from .anomaly import AnomalyDetector
from .teams import TeamsNotifier

# Logging Setup
def setup_logging(level: str = "INFO"):
    """Konfiguriert das Logging"""
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # Weniger verbose für externe Libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)


logger = logging.getLogger(__name__)


@click.group()
@click.option("--debug", is_flag=True, help="Debug-Modus aktivieren")
@click.pass_context
def cli(ctx, debug):
    """
    ÖWA/INFOnline Reporting System
    
    Automatisiertes Reporting mit Anomalie-Erkennung und Teams-Benachrichtigungen.
    """
    ctx.ensure_object(dict)
    
    config = get_config()
    level = "DEBUG" if debug else config.log_level
    setup_logging(level)
    
    ctx.obj["config"] = config


@cli.command()
@click.pass_context
def check(ctx):
    """Prüft die Konfiguration und Verbindungen"""
    config = ctx.obj["config"]
    
    click.echo("=" * 50)
    click.echo("ÖWA Reporting – Systemprüfung")
    click.echo("=" * 50)
    
    # Konfiguration validieren
    click.echo("\n📋 Konfiguration:")
    errors = config.validate()
    
    if errors:
        for error in errors:
            click.echo(f"  ❌ {error}")
        sys.exit(1)
    else:
        click.echo("  ✓ Konfiguration OK")
    
    # API prüfen
    click.echo("\n🌐 INFOnline API:")
    client = INFOnlineAPIClient()
    if client.health_check():
        click.echo("  ✓ API erreichbar")
    else:
        click.echo("  ❌ API nicht erreichbar")
    
    # Datenbank prüfen
    click.echo("\n🗄️ Datenbank:")
    if check_connection():
        click.echo("  ✓ Verbindung OK")
    else:
        click.echo("  ❌ Verbindung fehlgeschlagen")
    
    # Teams prüfen
    click.echo("\n💬 Microsoft Teams:")
    if config.teams.enabled:
        if config.teams.webhook_url:
            click.echo("  ✓ Webhook konfiguriert")
        else:
            click.echo("  ❌ Webhook URL fehlt")
    else:
        click.echo("  ⚠ Deaktiviert")
    
    click.echo("\n" + "=" * 50)
    click.echo("Prüfung abgeschlossen")


@cli.command()
@click.option("--drop", is_flag=True, help="Existierende Tabellen löschen")
@click.pass_context
def init_db(ctx, drop):
    """Initialisiert die Datenbank"""
    if drop:
        if not click.confirm("⚠️ Wirklich alle Tabellen löschen?"):
            click.echo("Abgebrochen.")
            return
    
    click.echo("Initialisiere Datenbank...")
    init_database(drop_existing=drop)
    click.echo("✓ Datenbank initialisiert")


@cli.command()
@click.option(
    "--date", "-d", "target_date",
    type=click.DateTime(formats=["%Y-%m-%d"]),
    default=None,
    help="Datum (Standard: gestern)"
)
@click.option("--no-alert", is_flag=True, help="Keine Anomalie-Erkennung")
@click.option("--no-teams", is_flag=True, help="Keine Teams-Benachrichtigung")
@click.pass_context
def ingest_daily(ctx, target_date, no_alert, no_teams):
    """
    Tägliche Daten-Ingestion.
    
    Holt Daten für das angegebene Datum (Standard: gestern),
    führt Anomalie-Erkennung durch und sendet Teams-Report.
    """
    config = ctx.obj["config"]
    
    # Datum bestimmen
    if target_date:
        target = target_date.date()
    else:
        target = date.today() - timedelta(days=1)
    
    click.echo(f"\n📅 Starte Ingestion für {target}")
    click.echo("=" * 50)
    
    # 1. Daten von API holen und speichern
    click.echo("\n1️⃣ Hole Daten von API...")
    ingester = DataIngester()
    stats = ingester.ingest_day(target)
    
    click.echo(f"   → {stats['inserted']} neu, {stats['updated']} aktualisiert, "
               f"{stats['errors']} Fehler")
    
    # 2. Anomalie-Erkennung
    alerts = []
    if not no_alert:
        click.echo("\n2️⃣ Prüfe auf Anomalien...")
        detector = AnomalyDetector()
        
        for site in config.sites:
            for metric in config.metrics:
                # Historische Daten holen
                historical = ingester.get_measurements_for_anomaly(
                    brand=site.brand,
                    surface=site.surface,
                    metric=metric,
                    end_date=target
                )
                
                if len(historical) >= config.anomaly.min_data_points:
                    result = detector.analyze_measurement(
                        brand=site.brand,
                        surface=site.surface,
                        metric=metric,
                        target_date=target,
                        historical_data=historical
                    )
                    
                    if result.is_outlier:
                        alert = detector.save_alert(
                            brand=site.brand,
                            surface=site.surface,
                            metric=metric,
                            target_date=target,
                            result=result
                        )
                        if alert:
                            alerts.append(alert)
                            click.echo(f"   ⚠️ {alert.severity.upper()}: "
                                      f"{site.name} / {metric}")
        
        if not alerts:
            click.echo("   ✓ Keine Anomalien erkannt")
    
    # 3. Teams-Benachrichtigung
    if not no_teams and config.teams.enabled:
        click.echo("\n3️⃣ Sende Teams-Report...")
        
        # Zusammenfassung erstellen
        metrics_summary = {}
        for brand in set(s.brand for s in config.sites):
            summary = ingester.get_daily_summary(target, brand)
            metrics_summary[brand] = summary
        
        notifier = TeamsNotifier()
        if notifier.send_daily_report(target, metrics_summary, alerts):
            click.echo("   ✓ Teams-Report gesendet")
        else:
            click.echo("   ❌ Teams-Report fehlgeschlagen")
    
    click.echo("\n" + "=" * 50)
    click.echo("✓ Ingestion abgeschlossen")


@cli.command()
@click.option(
    "--start", "-s", "start_date",
    type=click.DateTime(formats=["%Y-%m-%d"]),
    required=True,
    help="Startdatum"
)
@click.option(
    "--end", "-e", "end_date",
    type=click.DateTime(formats=["%Y-%m-%d"]),
    required=True,
    help="Enddatum"
)
@click.pass_context
def backfill(ctx, start_date, end_date):
    """
    Holt historische Daten für einen Datumsbereich.
    """
    start = start_date.date()
    end = end_date.date()
    
    if start > end:
        click.echo("❌ Startdatum muss vor Enddatum liegen")
        sys.exit(1)
    
    days = (end - start).days + 1
    click.echo(f"\n📅 Backfill für {days} Tage ({start} bis {end})")
    
    if not click.confirm("Fortfahren?"):
        click.echo("Abgebrochen.")
        return
    
    ingester = DataIngester()
    stats = ingester.ingest_date_range(start, end)
    
    click.echo(f"\n✓ Backfill abgeschlossen:")
    click.echo(f"  → {stats['inserted']} neu")
    click.echo(f"  → {stats['updated']} aktualisiert")
    click.echo(f"  → {stats['errors']} Fehler")


@cli.command()
@click.option(
    "--year", "-y",
    type=int,
    default=None,
    help="Jahr (Standard: voriger Monat)"
)
@click.option(
    "--month", "-m",
    type=int,
    default=None,
    help="Monat (Standard: voriger Monat)"
)
@click.pass_context
def report_monthly(ctx, year, month):
    """
    Erstellt und sendet den Monatsbericht.
    """
    config = ctx.obj["config"]
    
    # Standard: voriger Monat
    if year is None or month is None:
        today = date.today()
        if today.month == 1:
            year = today.year - 1
            month = 12
        else:
            year = today.year
            month = today.month - 1
    
    import calendar
    month_name = calendar.month_name[month]
    
    click.echo(f"\n📊 Erstelle Monatsbericht für {month_name} {year}")
    click.echo("=" * 50)
    
    # Datumsbereich
    _, last_day = calendar.monthrange(year, month)
    start_date = date(year, month, 1)
    end_date = date(year, month, last_day)
    
    # Daten aggregieren
    from .db import get_session
    from .models import Measurement, Alert
    from sqlalchemy import func, and_
    
    metrics_summary = {}
    
    with get_session() as session:
        for brand in set(s.brand for s in config.sites):
            # Web PI Summe
            web_pi = session.query(func.sum(Measurement.value_total)).filter(
                and_(
                    Measurement.brand == brand,
                    Measurement.surface.in_(["web_desktop", "web_mobile"]),
                    Measurement.metric == "pageimpressions",
                    Measurement.date >= start_date,
                    Measurement.date <= end_date
                )
            ).scalar() or 0
            
            # App PI Summe
            app_pi = session.query(func.sum(Measurement.value_total)).filter(
                and_(
                    Measurement.brand == brand,
                    Measurement.surface == "app",
                    Measurement.metric == "pageimpressions",
                    Measurement.date >= start_date,
                    Measurement.date <= end_date
                )
            ).scalar() or 0
            
            metrics_summary[brand] = {
                "total_web_pi": web_pi,
                "total_app_pi": app_pi,
            }
            
            click.echo(f"\n{brand.upper()}:")
            click.echo(f"  Web PI:  {web_pi:,}".replace(",", "."))
            click.echo(f"  App PI:  {app_pi:,}".replace(",", "."))
        
        # Alerts im Monat
        alerts = session.query(Alert).filter(
            and_(
                Alert.date >= start_date,
                Alert.date <= end_date
            )
        ).all()
        
        warning_count = sum(1 for a in alerts if a.severity == "warning")
        critical_count = sum(1 for a in alerts if a.severity == "critical")
        
        click.echo(f"\nAlerts: {warning_count} Warnings, {critical_count} Criticals")
    
    # Teams senden
    if config.teams.enabled:
        click.echo("\nSende Teams-Report...")
        notifier = TeamsNotifier()
        if notifier.send_monthly_summary(year, month, metrics_summary, alerts):
            click.echo("✓ Teams-Report gesendet")
        else:
            click.echo("❌ Teams-Report fehlgeschlagen")


@cli.command()
@click.pass_context
def test_teams(ctx):
    """Sendet eine Test-Nachricht an Teams"""
    config = ctx.obj["config"]
    
    if not config.teams.webhook_url:
        click.echo("❌ Teams Webhook URL nicht konfiguriert")
        sys.exit(1)
    
    click.echo("Sende Testnachricht an Teams...")
    notifier = TeamsNotifier()
    
    if notifier.send_test_message():
        click.echo("✓ Testnachricht gesendet")
    else:
        click.echo("❌ Testnachricht fehlgeschlagen")


@cli.command()
@click.option("--port", "-p", default=8501, help="Port für das Dashboard")
@click.option("--host", "-h", default="localhost", help="Host-Adresse")
@click.pass_context
def dashboard(ctx, port, host):
    """Startet das Streamlit Dashboard"""
    import subprocess
    import sys
    from pathlib import Path
    
    click.echo(f"\n📊 Starte ÖWA Reporting Dashboard")
    click.echo(f"   URL: http://{host}:{port}")
    click.echo("   Beenden mit Ctrl+C\n")
    
    dashboard_path = Path(__file__).parent / "dashboard.py"
    
    try:
        subprocess.run([
            sys.executable, "-m", "streamlit", "run",
            str(dashboard_path),
            "--server.port", str(port),
            "--server.address", host,
            "--browser.gatherUsageStats", "false"
        ])
    except KeyboardInterrupt:
        click.echo("\n✓ Dashboard beendet")
    except FileNotFoundError:
        click.echo("❌ Streamlit nicht installiert. Installieren mit:")
        click.echo("   pip install streamlit plotly")


@cli.command()
@click.option(
    "--date", "-d", "target_date",
    type=click.DateTime(formats=["%Y-%m-%d"]),
    default=None,
    help="Datum (Standard: gestern)"
)
@click.pass_context
def show_data(ctx, target_date):
    """Zeigt die gespeicherten Daten für ein Datum"""
    from .db import get_session
    from .models import Measurement
    
    if target_date:
        target = target_date.date()
    else:
        target = date.today() - timedelta(days=1)
    
    click.echo(f"\n📊 Daten für {target}")
    click.echo("=" * 60)
    
    with get_session() as session:
        measurements = session.query(Measurement).filter(
            Measurement.date == target
        ).order_by(
            Measurement.brand, Measurement.surface, Measurement.metric
        ).all()
        
        if not measurements:
            click.echo("Keine Daten gefunden.")
            return
        
        current_brand = None
        
        for m in measurements:
            if m.brand != current_brand:
                current_brand = m.brand
                click.echo(f"\n{m.brand.upper()}:")
            
            preliminary = " (vorläufig)" if m.preliminary else ""
            click.echo(
                f"  {m.surface:15} | {m.metric:18} | "
                f"{m.value_total:>12,}{preliminary}".replace(",", ".")
            )


@cli.command()
@click.option(
    "--start", "-s", "start_date",
    type=click.DateTime(formats=["%Y-%m-%d"]),
    default=None,
    help="Startdatum (Standard: vor 30 Tagen)"
)
@click.option(
    "--end", "-e", "end_date",
    type=click.DateTime(formats=["%Y-%m-%d"]),
    default=None,
    help="Enddatum (Standard: heute)"
)
@click.option(
    "--output", "-o",
    type=str,
    default=None,
    help="Ausgabe-Datei (Standard: oewa_report_<datum>.html)"
)
@click.option(
    "--metric", "-m",
    type=click.Choice(["pageimpressions", "visits", "clients"]),
    default="pageimpressions",
    help="Metrik für den Report"
)
@click.pass_context
def report_html(ctx, start_date, end_date, output, metric):
    """
    Generiert einen statischen HTML-Report.
    
    Der Report enthält interaktive Plotly-Charts und kann
    per Email/Teams geteilt werden.
    """
    from datetime import timedelta
    from .visualization import create_html_report
    
    # Datumsbereich
    if end_date:
        end = end_date.date()
    else:
        end = date.today()
    
    if start_date:
        start = start_date.date()
    else:
        start = end - timedelta(days=30)
    
    click.echo(f"\n📊 Generiere HTML-Report")
    click.echo(f"   Zeitraum: {start} - {end}")
    click.echo(f"   Metrik: {metric}")
    
    try:
        output_path = create_html_report(
            start_date=start,
            end_date=end,
            output_path=output,
            metric=metric
        )
        
        click.echo(f"\n✓ Report generiert: {output_path}")
        click.echo(f"  Öffnen mit: start {output_path}")
        
    except Exception as e:
        click.echo(f"\n❌ Fehler: {e}")
        sys.exit(1)


@cli.command()
@click.option(
    "--date", "-d", "target_date",
    type=click.DateTime(formats=["%Y-%m-%d"]),
    default=None,
    help="Datum (Standard: gestern)"
)
@click.option(
    "--days", "-n",
    type=int,
    default=7,
    help="Anzahl Tage zurück (Standard: 7)"
)
@click.option(
    "--metric", "-m",
    type=click.Choice(["pageimpressions", "visits", "clients"]),
    default="pageimpressions",
    help="Metrik für die Ansicht"
)
@click.pass_context
def quick_view(ctx, target_date, days, metric):
    """
    Zeigt eine schnelle Übersicht im Terminal.
    
    ASCII-basierte Visualisierung ohne GUI.
    """
    from datetime import timedelta
    from .visualization import show_terminal_view
    
    # Datumsbereich
    if target_date:
        end = target_date.date()
    else:
        end = date.today() - timedelta(days=1)
    
    start = end - timedelta(days=days)
    
    try:
        show_terminal_view(
            start_date=start,
            end_date=end,
            metric=metric
        )
    except Exception as e:
        click.echo(f"\n❌ Fehler: {e}")
        sys.exit(1)


def main():
    """Entry Point"""
    cli(obj={})


if __name__ == "__main__":
    main()

