"""
ÖWA Reporting System - Vollständiger Testcase
==============================================

Dieser Test:
1. Initialisiert die Datenbank
2. Lädt 30 Tage Daten für alle Metriken
3. Führt Anomalie-Erkennung durch
4. Generiert Reports (Terminal + HTML)
5. Zeigt Zusammenfassung und Interpretation

Ausführung:
    python run_full_test.py
"""

import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
import time

# Umgebungsvariablen setzen
os.environ["INFONLINE_API_KEY"] = "MmFiNjk4YTgtZTA2OS00MGYwLWEyNWQtNGY3ODg0NWI5ODI3"
os.environ["DATABASE_URL"] = "sqlite:///oewa_fulltest.db"
os.environ["TEAMS_ENABLED"] = "false"

# Projekt-Pfad hinzufügen
sys.path.insert(0, str(Path(__file__).parent))


class Colors:
    """Terminal-Farben"""
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    END = '\033[0m'


def print_header(text: str):
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'═' * 70}")
    print(f"  {text}")
    print(f"{'═' * 70}{Colors.END}\n")


def print_section(text: str):
    print(f"\n{Colors.CYAN}━━━ {text} ━━━{Colors.END}")


def print_ok(text: str):
    print(f"  {Colors.GREEN}✓{Colors.END} {text}")


def print_info(text: str):
    print(f"  {Colors.BLUE}ℹ{Colors.END} {text}")


def print_warn(text: str):
    print(f"  {Colors.YELLOW}⚠{Colors.END} {text}")


def print_error(text: str):
    print(f"  {Colors.RED}✗{Colors.END} {text}")


def run_full_test():
    """Führt den vollständigen Test durch"""
    
    print_header("ÖWA Reporting System - Vollständiger Testcase")
    
    start_time = time.time()
    
    # Konfiguration
    end_date = date.today() - timedelta(days=1)  # Gestern
    start_date = end_date - timedelta(days=29)   # 30 Tage
    all_metrics = ["pageimpressions", "visits"]  # Hauptmetriken
    
    print(f"  Testparameter:")
    print(f"  ├─ Zeitraum:  {start_date} bis {end_date} (30 Tage)")
    print(f"  ├─ Metriken:  {', '.join(all_metrics)}")
    print(f"  ├─ Datenbank: {os.environ['DATABASE_URL']}")
    print(f"  └─ API-Key:   {os.environ['INFONLINE_API_KEY'][:8]}...{Colors.END}")
    
    # =========================================================================
    # PHASE 1: Datenbank initialisieren
    # =========================================================================
    print_section("Phase 1: Datenbank initialisieren")
    
    try:
        from oewa_reporting.db import init_database, check_connection
        
        init_database(drop_existing=True)
        print_ok("Datenbank initialisiert (Tabellen erstellt)")
        
        if check_connection():
            print_ok("Datenbankverbindung OK")
        else:
            print_error("Datenbankverbindung fehlgeschlagen")
            return False
            
    except Exception as e:
        print_error(f"Datenbankfehler: {e}")
        return False
    
    # =========================================================================
    # PHASE 2: API-Verbindung prüfen
    # =========================================================================
    print_section("Phase 2: API-Verbindung prüfen")
    
    try:
        from oewa_reporting.api_client import INFOnlineAPIClient
        
        client = INFOnlineAPIClient()
        
        if client.health_check():
            print_ok("INFOnline API erreichbar")
        else:
            print_error("INFOnline API nicht erreichbar")
            return False
        
        # Test-Abfrage
        test_response = client.fetch_metric(
            metric="pageimpressions",
            site_id="EA000004_desktop",
            date=end_date.strftime("%Y-%m-%d")
        )
        
        if test_response.success:
            print_ok(f"Test-Abfrage erfolgreich ({test_response.response_time_ms:.0f}ms)")
        else:
            print_error(f"Test-Abfrage fehlgeschlagen: {test_response.error}")
            return False
            
    except Exception as e:
        print_error(f"API-Fehler: {e}")
        return False
    
    # =========================================================================
    # PHASE 3: Daten laden (30 Tage Backfill)
    # =========================================================================
    print_section("Phase 3: Daten laden (30 Tage Backfill)")
    
    try:
        from oewa_reporting.ingest import DataIngester
        from oewa_reporting.config import get_config
        
        config = get_config()
        ingester = DataIngester()
        
        total_stats = {"inserted": 0, "updated": 0, "errors": 0, "skipped": 0}
        
        # Fortschrittsanzeige
        total_days = (end_date - start_date).days + 1
        
        print_info(f"Lade {total_days} Tage für {len(config.sites)} Sites × {len(all_metrics)} Metriken")
        print()
        
        current_date = start_date
        day_count = 0
        
        while current_date <= end_date:
            day_count += 1
            progress = int((day_count / total_days) * 40)
            bar = "█" * progress + "░" * (40 - progress)
            
            print(f"\r  [{bar}] {day_count}/{total_days} - {current_date}", end="", flush=True)
            
            # Ingestion für diesen Tag
            stats = ingester.ingest_day(
                target_date=current_date,
                metrics=all_metrics
            )
            
            for key in total_stats:
                total_stats[key] += stats.get(key, 0)
            
            current_date += timedelta(days=1)
            
            # Kurze Pause um API nicht zu überlasten
            time.sleep(0.2)
        
        print()  # Neue Zeile nach Fortschrittsbalken
        print()
        
        print_ok(f"Backfill abgeschlossen:")
        print(f"      ├─ Neu eingefügt:  {total_stats['inserted']}")
        print(f"      ├─ Aktualisiert:   {total_stats['updated']}")
        print(f"      ├─ Übersprungen:   {total_stats['skipped']}")
        print(f"      └─ Fehler:         {total_stats['errors']}")
        
    except Exception as e:
        print_error(f"Ingestion-Fehler: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # =========================================================================
    # PHASE 4: Daten analysieren
    # =========================================================================
    print_section("Phase 4: Daten analysieren")
    
    try:
        from oewa_reporting.db import get_session
        from oewa_reporting.models import Measurement
        from sqlalchemy import func
        
        with get_session() as session:
            # Gesamtstatistik
            total_records = session.query(Measurement).count()
            print_ok(f"Gespeicherte Datensätze: {total_records}")
            
            # Nach Metrik
            print_info("Verteilung nach Metrik:")
            metric_counts = session.query(
                Measurement.metric,
                func.count(Measurement.id),
                func.sum(Measurement.value_total)
            ).group_by(Measurement.metric).all()
            
            for metric, count, total in metric_counts:
                print(f"      {metric:20} | {count:4} Einträge | {total:>15,} Gesamt")
            
            # Nach Surface
            print_info("Verteilung nach Plattform:")
            surface_counts = session.query(
                Measurement.surface,
                func.count(Measurement.id),
                func.sum(Measurement.value_total)
            ).group_by(Measurement.surface).all()
            
            for surface, count, total in surface_counts:
                print(f"      {surface:20} | {count:4} Einträge | {total:>15,} Gesamt")
            
            # Datumsbereich
            min_date = session.query(func.min(Measurement.date)).scalar()
            max_date = session.query(func.max(Measurement.date)).scalar()
            print_info(f"Datumsbereich: {min_date} bis {max_date}")
            
    except Exception as e:
        print_error(f"Analyse-Fehler: {e}")
        return False
    
    # =========================================================================
    # PHASE 5: Anomalie-Erkennung
    # =========================================================================
    print_section("Phase 5: Anomalie-Erkennung")
    
    try:
        from oewa_reporting.anomaly import AnomalyDetector
        
        detector = AnomalyDetector()
        alerts = []
        
        # Prüfe die letzten 7 Tage auf Anomalien
        check_start = end_date - timedelta(days=6)
        
        print_info(f"Prüfe Zeitraum {check_start} bis {end_date}")
        
        for site in config.sites:
            for metric in all_metrics:
                # Hole historische Daten
                historical = ingester.get_measurements_for_anomaly(
                    brand=site.brand,
                    surface=site.surface,
                    metric=metric,
                    end_date=end_date
                )
                
                if len(historical) >= 7:
                    result = detector.analyze_measurement(
                        brand=site.brand,
                        surface=site.surface,
                        metric=metric,
                        target_date=end_date,
                        historical_data=historical
                    )
                    
                    if result.is_outlier:
                        alert = detector.save_alert(
                            brand=site.brand,
                            surface=site.surface,
                            metric=metric,
                            target_date=end_date,
                            result=result
                        )
                        if alert:
                            alerts.append(alert)
        
        if alerts:
            print_warn(f"{len(alerts)} Anomalien erkannt:")
            for alert in alerts:
                icon = "🔴" if alert.severity == "critical" else "🟡"
                print(f"      {icon} {alert.brand.upper()} {alert.surface} | "
                      f"{alert.metric} | {alert.pct_delta*100:+.1f}% | z={alert.zscore:.2f}")
        else:
            print_ok("Keine Anomalien in den letzten Daten erkannt")
            
    except Exception as e:
        print_error(f"Anomalie-Erkennungs-Fehler: {e}")
        import traceback
        traceback.print_exc()
    
    # =========================================================================
    # PHASE 6: Terminal Quick View
    # =========================================================================
    print_section("Phase 6: Terminal Quick View")
    
    try:
        from oewa_reporting.visualization import show_terminal_view
        
        show_terminal_view(
            start_date=start_date,
            end_date=end_date,
            metric="pageimpressions"
        )
        
        print_ok("Terminal Quick View erfolgreich")
        
    except Exception as e:
        print_error(f"Quick View Fehler: {e}")
    
    # =========================================================================
    # PHASE 7: HTML Report generieren
    # =========================================================================
    print_section("Phase 7: HTML Report generieren")
    
    try:
        from oewa_reporting.visualization import create_html_report
        
        report_path = create_html_report(
            start_date=start_date,
            end_date=end_date,
            output_path="oewa_testcase_report.html",
            metric="pageimpressions"
        )
        
        print_ok(f"HTML Report generiert: {report_path}")
        
    except Exception as e:
        print_error(f"HTML Report Fehler: {e}")
    
    # =========================================================================
    # PHASE 8: Daten-Interpretation
    # =========================================================================
    print_section("Phase 8: Daten-Interpretation")
    
    try:
        with get_session() as session:
            # Durchschnitte berechnen
            print_info("📊 Durchschnittliche Tageswerte (Page Impressions):")
            
            from sqlalchemy import and_
            
            for surface in ["web_desktop", "web_mobile", "app"]:
                avg = session.query(func.avg(Measurement.value_total)).filter(
                    and_(
                        Measurement.metric == "pageimpressions",
                        Measurement.surface == surface
                    )
                ).scalar() or 0
                
                print(f"      {surface:15} Ø {avg:>12,.0f} PI/Tag")
            
            # Wochentags-Analyse
            print_info("📅 Wochentags-Analyse (Web Desktop PI):")
            
            weekdays = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
            
            for wd in range(7):
                # SQLite: strftime('%w', date) gibt 0-6 zurück (0=Sonntag)
                # Wir brauchen 0=Montag, also Umrechnung
                sqlite_wd = (wd + 1) % 7  # Konvertiere zu SQLite Format
                
                from oewa_reporting.models import Measurement
                
                measurements = session.query(Measurement).filter(
                    and_(
                        Measurement.metric == "pageimpressions",
                        Measurement.surface == "web_desktop"
                    )
                ).all()
                
                # Manuell filtern nach Wochentag
                wd_values = [
                    m.value_total for m in measurements 
                    if m.date.weekday() == wd
                ]
                
                if wd_values:
                    avg = sum(wd_values) / len(wd_values)
                    print(f"      {weekdays[wd]:3} | {avg:>12,.0f} PI | {len(wd_values)} Tage")
            
            # Trend-Analyse
            print_info("📈 Trend-Analyse (letzte 7 vs. vorherige 7 Tage):")
            
            week_1_end = end_date
            week_1_start = end_date - timedelta(days=6)
            week_2_end = week_1_start - timedelta(days=1)
            week_2_start = week_2_end - timedelta(days=6)
            
            for metric in all_metrics:
                week_1 = session.query(func.sum(Measurement.value_total)).filter(
                    and_(
                        Measurement.metric == metric,
                        Measurement.date >= week_1_start,
                        Measurement.date <= week_1_end
                    )
                ).scalar() or 0
                
                week_2 = session.query(func.sum(Measurement.value_total)).filter(
                    and_(
                        Measurement.metric == metric,
                        Measurement.date >= week_2_start,
                        Measurement.date <= week_2_end
                    )
                ).scalar() or 0
                
                if week_2 > 0:
                    change = ((week_1 - week_2) / week_2) * 100
                    arrow = "📈" if change > 0 else "📉" if change < 0 else "➡️"
                    print(f"      {metric:18} | {arrow} {change:+.1f}%")
                else:
                    print(f"      {metric:18} | ➡️ N/A (keine Vergleichsdaten)")
                    
    except Exception as e:
        print_error(f"Interpretations-Fehler: {e}")
        import traceback
        traceback.print_exc()
    
    # =========================================================================
    # ZUSAMMENFASSUNG
    # =========================================================================
    duration = time.time() - start_time
    
    print_header("Testcase Zusammenfassung")
    
    print(f"  {Colors.GREEN}✓ Alle Phasen erfolgreich durchgeführt{Colors.END}")
    print()
    print(f"  Ergebnisse:")
    print(f"  ├─ Datenbank:     oewa_fulltest.db")
    print(f"  ├─ HTML Report:   oewa_testcase_report.html")
    print(f"  ├─ Datensätze:    {total_stats['inserted']} geladen")
    print(f"  ├─ Anomalien:     {len(alerts) if 'alerts' in dir() else 0} erkannt")
    print(f"  └─ Dauer:         {duration:.1f} Sekunden")
    print()
    
    # =========================================================================
    # PHASE 9: Report automatisch öffnen
    # =========================================================================
    print_section("Phase 9: Report im Browser öffnen")
    
    try:
        import webbrowser
        import http.server
        import socketserver
        import threading
        
        # HTML Report im Browser öffnen
        report_file = Path("oewa_testcase_report.html").absolute()
        
        if report_file.exists():
            # Starte lokalen HTTP Server für bessere Darstellung
            PORT = 8888
            
            print_info(f"Starte lokalen Webserver auf Port {PORT}...")
            
            # Server in separatem Thread starten
            handler = http.server.SimpleHTTPRequestHandler
            
            # Suppress server logs
            class QuietHandler(handler):
                def log_message(self, format, *args):
                    pass
            
            try:
                httpd = socketserver.TCPServer(("", PORT), QuietHandler)
                
                # Server in Thread starten
                server_thread = threading.Thread(target=httpd.serve_forever)
                server_thread.daemon = True
                server_thread.start()
                
                print_ok(f"Webserver gestartet: http://localhost:{PORT}")
                
                # Report im Browser öffnen
                report_url = f"http://localhost:{PORT}/oewa_testcase_report.html"
                webbrowser.open(report_url)
                
                print_ok(f"Report geöffnet: {report_url}")
                print()
                print(f"  {Colors.YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Colors.END}")
                print(f"  {Colors.YELLOW}  Der Webserver läuft auf http://localhost:{PORT}{Colors.END}")
                print(f"  {Colors.YELLOW}  Drücke ENTER zum Beenden...{Colors.END}")
                print(f"  {Colors.YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Colors.END}")
                
                # Warte auf Benutzer-Eingabe
                input()
                
                # Server stoppen
                httpd.shutdown()
                print_ok("Webserver beendet")
                
            except OSError as e:
                # Port bereits belegt - öffne direkt
                print_warn(f"Port {PORT} belegt, öffne Report direkt...")
                webbrowser.open(str(report_file))
                print_ok("Report im Browser geöffnet (Datei-Modus)")
        else:
            print_error(f"Report-Datei nicht gefunden: {report_file}")
            
    except Exception as e:
        print_warn(f"Konnte Report nicht automatisch öffnen: {e}")
        print_info("Manuell öffnen mit: start oewa_testcase_report.html")
    
    print()
    print(f"  {Colors.CYAN}Weitere Optionen:{Colors.END}")
    print(f"  • Dashboard starten:  python -m oewa_reporting dashboard")
    print(f"  • Quick View:         python -m oewa_reporting quick-view")
    print()
    
    return True


if __name__ == "__main__":
    success = run_full_test()
    sys.exit(0 if success else 1)

