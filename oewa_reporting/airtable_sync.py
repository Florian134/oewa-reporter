"""
Airtable Synchronisation
=========================

Synchronisiert ÖWA-Daten mit Airtable für:
- Backup und Archivierung
- Einfache Datenanalyse für Non-Tech-User
- Integration mit anderen Airtable-Automations

Features:
- Inkrementelle Synchronisation (nur neue/geänderte Daten)
- Batch-Uploads für Performance
- Automatisches Spalten-Mapping
- Fehlerbehandlung und Retry-Logik
"""

import logging
import time
import os
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass

import requests

from .config import get_config
from .db import get_session
from .models import Measurement, Alert, utc_now

logger = logging.getLogger(__name__)


# =============================================================================
# AIRTABLE CONFIGURATION
# =============================================================================

@dataclass
class AirtableConfig:
    """Airtable-Konfiguration"""
    api_key: str = ""
    base_id: str = ""
    measurements_table: str = "Measurements"
    alerts_table: str = "Alerts"
    summaries_table: str = "Summaries"
    
    @classmethod
    def from_env(cls) -> "AirtableConfig":
        """Lädt Konfiguration aus Environment"""
        return cls(
            api_key=os.getenv("AIRTABLE_API_KEY", ""),
            base_id=os.getenv("AIRTABLE_BASE_ID", "appj6S8TQHMlKyahg"),  # Default VOL.at Base
            measurements_table=os.getenv("AIRTABLE_MEASUREMENTS_TABLE", "Measurements"),
            alerts_table=os.getenv("AIRTABLE_ALERTS_TABLE", "Alerts"),
            summaries_table=os.getenv("AIRTABLE_SUMMARIES_TABLE", "Summaries"),
        )
    
    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and self.base_id)


# =============================================================================
# FIELD MAPPINGS
# =============================================================================

# Mapping: DB-Feld -> Airtable-Feld
MEASUREMENT_FIELD_MAP = {
    "brand": "Brand",
    "surface": "Plattform",
    "metric": "Metrik",
    "date": "Datum",
    "site_id": "Site ID",
    "value_total": "Wert Gesamt",
    "value_national": "Wert National",
    "value_international": "Wert International",
    "value_iomp": "Wert Consent",
    "value_iomb": "Wert Consentless",
    "preliminary": "Vorläufig",
    "ingested_at": "Erfasst am",
}

ALERT_FIELD_MAP = {
    "brand": "Brand",
    "surface": "Plattform",
    "metric": "Metrik",
    "date": "Datum",
    "severity": "Schweregrad",
    "zscore": "Z-Score",
    "pct_delta": "Abweichung %",
    "baseline_median": "Median (Baseline)",
    "actual_value": "Aktueller Wert",
    "message": "Meldung",
    "acknowledged": "Bestätigt",
}

# Surface-Übersetzungen für Airtable
SURFACE_LABELS = {
    "web_desktop": "Web Desktop",
    "web_mobile": "Web Mobile",
    "app": "App"
}

# Metrik-Übersetzungen für Airtable
METRIC_LABELS = {
    "pageimpressions": "Page Impressions",
    "visits": "Visits",
    "clients": "Clients"
}


# =============================================================================
# AIRTABLE CLIENT
# =============================================================================

class AirtableClient:
    """
    Client für die Airtable API.
    
    Features:
    - Batch-Operationen (max 10 Records pro Request)
    - Rate Limiting (5 Requests/Sekunde)
    - Automatisches Retry bei Fehlern
    """
    
    API_BASE = "https://api.airtable.com/v0"
    BATCH_SIZE = 10  # Airtable erlaubt max 10 Records pro Request
    RATE_LIMIT_DELAY = 0.2  # 5 Requests/Sekunde
    
    def __init__(self, config: AirtableConfig = None):
        """
        Initialisiert den Airtable Client.
        
        Args:
            config: Airtable-Konfiguration
        """
        self.config = config or AirtableConfig.from_env()
        
        if not self.config.is_configured:
            logger.warning("Airtable nicht konfiguriert - Sync deaktiviert")
        
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json"
        })
        
        self._last_request_time = 0.0
    
    def _rate_limit(self):
        """Implementiert Rate Limiting"""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.RATE_LIMIT_DELAY:
            time.sleep(self.RATE_LIMIT_DELAY - elapsed)
        self._last_request_time = time.time()
    
    def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Dict = None,
        params: Dict = None
    ) -> Tuple[bool, Any]:
        """
        Führt einen API-Request durch.
        
        Returns:
            Tuple (success, response_data_or_error)
        """
        if not self.config.is_configured:
            return False, "Airtable nicht konfiguriert"
        
        self._rate_limit()
        
        url = f"{self.API_BASE}/{self.config.base_id}/{endpoint}"
        
        try:
            if method == "GET":
                response = self.session.get(url, params=params, timeout=30)
            elif method == "POST":
                response = self.session.post(url, json=data, timeout=30)
            elif method == "PATCH":
                response = self.session.patch(url, json=data, timeout=30)
            elif method == "DELETE":
                response = self.session.delete(url, timeout=30)
            else:
                return False, f"Unbekannte Methode: {method}"
            
            if response.status_code in (200, 201):
                return True, response.json()
            elif response.status_code == 429:
                # Rate Limit - warte und retry
                logger.warning("Airtable Rate Limit erreicht, warte 30s...")
                time.sleep(30)
                return self._make_request(method, endpoint, data, params)
            else:
                error = response.json().get("error", {}).get("message", response.text)
                logger.error(f"Airtable API Fehler: {response.status_code} - {error}")
                return False, error
                
        except requests.exceptions.Timeout:
            logger.error("Airtable API Timeout")
            return False, "Timeout"
        except Exception as e:
            logger.error(f"Airtable API Fehler: {e}")
            return False, str(e)
    
    def list_records(
        self,
        table: str,
        filter_formula: str = None,
        max_records: int = None
    ) -> List[Dict]:
        """
        Listet Records aus einer Tabelle.
        
        Args:
            table: Tabellenname
            filter_formula: Airtable-Formel zum Filtern
            max_records: Maximale Anzahl Records
            
        Returns:
            Liste der Records
        """
        records = []
        offset = None
        
        while True:
            params = {}
            if filter_formula:
                params["filterByFormula"] = filter_formula
            if max_records:
                params["maxRecords"] = max_records
            if offset:
                params["offset"] = offset
            
            success, result = self._make_request("GET", table, params=params)
            
            if not success:
                logger.error(f"Fehler beim Laden von {table}: {result}")
                break
            
            records.extend(result.get("records", []))
            
            offset = result.get("offset")
            if not offset:
                break
            
            if max_records and len(records) >= max_records:
                break
        
        return records
    
    def create_records(
        self,
        table: str,
        records: List[Dict]
    ) -> Tuple[int, int]:
        """
        Erstellt Records in Batches.
        
        Args:
            table: Tabellenname
            records: Liste der Records (als Dicts)
            
        Returns:
            Tuple (erfolgreich, fehlgeschlagen)
        """
        success_count = 0
        error_count = 0
        
        # In Batches aufteilen
        for i in range(0, len(records), self.BATCH_SIZE):
            batch = records[i:i + self.BATCH_SIZE]
            
            payload = {
                "records": [{"fields": r} for r in batch]
            }
            
            success, result = self._make_request("POST", table, data=payload)
            
            if success:
                success_count += len(result.get("records", []))
                logger.debug(f"Batch {i//self.BATCH_SIZE + 1}: {len(batch)} Records erstellt")
            else:
                error_count += len(batch)
                logger.error(f"Batch {i//self.BATCH_SIZE + 1} fehlgeschlagen: {result}")
        
        return success_count, error_count
    
    def update_records(
        self,
        table: str,
        updates: List[Tuple[str, Dict]]  # (record_id, fields)
    ) -> Tuple[int, int]:
        """
        Aktualisiert Records in Batches.
        
        Args:
            table: Tabellenname
            updates: Liste von (Record-ID, Felder) Tupeln
            
        Returns:
            Tuple (erfolgreich, fehlgeschlagen)
        """
        success_count = 0
        error_count = 0
        
        for i in range(0, len(updates), self.BATCH_SIZE):
            batch = updates[i:i + self.BATCH_SIZE]
            
            payload = {
                "records": [
                    {"id": record_id, "fields": fields}
                    for record_id, fields in batch
                ]
            }
            
            success, result = self._make_request("PATCH", table, data=payload)
            
            if success:
                success_count += len(result.get("records", []))
            else:
                error_count += len(batch)
        
        return success_count, error_count


# =============================================================================
# AIRTABLE SYNC
# =============================================================================

class AirtableSync:
    """
    Synchronisiert ÖWA-Daten mit Airtable.
    
    Unterstützt:
    - Inkrementelle Synchronisation
    - Vollständiger Backfill
    - Automatisches Mapping
    """
    
    def __init__(self, client: AirtableClient = None):
        """
        Initialisiert den Sync.
        
        Args:
            client: Airtable-Client
        """
        self.client = client or AirtableClient()
        self.config = self.client.config
    
    def _measurement_to_airtable(self, m: Measurement) -> Dict:
        """Konvertiert Measurement zu Airtable-Format"""
        return {
            "Brand": m.brand.upper(),
            "Plattform": SURFACE_LABELS.get(m.surface, m.surface),
            "Metrik": METRIC_LABELS.get(m.metric, m.metric),
            "Datum": m.date.isoformat(),
            "Site ID": m.site_id,
            "Wert Gesamt": m.value_total,
            "Wert National": m.value_national or 0,
            "Wert International": m.value_international or 0,
            "Wert Consent": m.value_iomp or 0,
            "Wert Consentless": m.value_iomb or 0,
            "Vorläufig": "Ja" if m.preliminary else "Nein",
            "Erfasst am": m.ingested_at.isoformat() if m.ingested_at else "",
            # Unique Key für Deduplizierung
            "Unique Key": f"{m.brand}_{m.surface}_{m.metric}_{m.date.isoformat()}"
        }
    
    def _alert_to_airtable(self, a: Alert) -> Dict:
        """Konvertiert Alert zu Airtable-Format"""
        return {
            "Brand": a.brand.upper(),
            "Plattform": SURFACE_LABELS.get(a.surface, a.surface),
            "Metrik": METRIC_LABELS.get(a.metric, a.metric),
            "Datum": a.date.isoformat(),
            "Schweregrad": "Kritisch" if a.severity == "critical" else "Warnung",
            "Z-Score": round(a.zscore, 2) if a.zscore else 0,
            "Abweichung %": round(a.pct_delta * 100, 1) if a.pct_delta else 0,
            "Median (Baseline)": round(a.baseline_median, 0) if a.baseline_median else 0,
            "Aktueller Wert": round(a.actual_value, 0) if a.actual_value else 0,
            "Meldung": a.message or "",
            "Bestätigt": "Ja" if a.acknowledged else "Nein",
            "Unique Key": f"alert_{a.brand}_{a.surface}_{a.metric}_{a.date.isoformat()}"
        }
    
    def sync_measurements(
        self,
        start_date: date = None,
        end_date: date = None,
        incremental: bool = True
    ) -> Dict[str, int]:
        """
        Synchronisiert Messdaten mit Airtable.
        
        Args:
            start_date: Startdatum (Default: gestern)
            end_date: Enddatum (Default: gestern)
            incremental: Inkrementelle Sync (prüft auf Duplikate)
            
        Returns:
            Statistiken (created, updated, errors)
        """
        if not self.config.is_configured:
            logger.warning("Airtable nicht konfiguriert")
            return {"created": 0, "updated": 0, "errors": 0, "skipped": 0}
        
        end_date = end_date or (date.today() - timedelta(days=1))
        start_date = start_date or end_date
        
        logger.info(f"Sync Measurements: {start_date} - {end_date}")
        
        # Lade Daten aus DB
        from sqlalchemy import and_
        
        with get_session() as session:
            measurements = session.query(Measurement).filter(
                and_(
                    Measurement.date >= start_date,
                    Measurement.date <= end_date
                )
            ).all()
        
        if not measurements:
            logger.info("Keine Messdaten zum Synchronisieren")
            return {"created": 0, "updated": 0, "errors": 0, "skipped": 0}
        
        # Konvertiere zu Airtable-Format
        records = [self._measurement_to_airtable(m) for m in measurements]
        
        # Prüfe auf existierende Records (wenn inkrementell)
        existing_keys = set()
        if incremental:
            filter_formula = f"AND({{Datum}} >= '{start_date.isoformat()}', {{Datum}} <= '{end_date.isoformat()}')"
            existing = self.client.list_records(
                self.config.measurements_table,
                filter_formula=filter_formula
            )
            existing_keys = {
                r.get("fields", {}).get("Unique Key")
                for r in existing
            }
        
        # Filtere neue Records
        new_records = [
            r for r in records
            if r.get("Unique Key") not in existing_keys
        ]
        
        stats = {"created": 0, "updated": 0, "errors": 0, "skipped": len(records) - len(new_records)}
        
        if new_records:
            created, errors = self.client.create_records(
                self.config.measurements_table,
                new_records
            )
            stats["created"] = created
            stats["errors"] = errors
        
        logger.info(f"Measurements Sync: {stats}")
        
        return stats
    
    def sync_alerts(
        self,
        start_date: date = None,
        end_date: date = None
    ) -> Dict[str, int]:
        """
        Synchronisiert Alerts mit Airtable.
        """
        if not self.config.is_configured:
            return {"created": 0, "errors": 0}
        
        end_date = end_date or date.today()
        start_date = start_date or (end_date - timedelta(days=7))
        
        logger.info(f"Sync Alerts: {start_date} - {end_date}")
        
        from sqlalchemy import and_
        
        with get_session() as session:
            alerts = session.query(Alert).filter(
                and_(
                    Alert.date >= start_date,
                    Alert.date <= end_date
                )
            ).all()
        
        if not alerts:
            return {"created": 0, "errors": 0}
        
        records = [self._alert_to_airtable(a) for a in alerts]
        
        created, errors = self.client.create_records(
            self.config.alerts_table,
            records
        )
        
        return {"created": created, "errors": errors}
    
    def full_backfill(
        self,
        start_date: date,
        end_date: date = None
    ) -> Dict[str, int]:
        """
        Führt vollständigen Backfill durch.
        
        ACHTUNG: Kann bei großen Datenmengen lange dauern!
        """
        end_date = end_date or date.today()
        
        logger.info(f"Full Backfill: {start_date} - {end_date}")
        
        total_stats = {"created": 0, "errors": 0}
        
        # In Wochen-Chunks aufteilen
        current = start_date
        while current <= end_date:
            chunk_end = min(current + timedelta(days=6), end_date)
            
            stats = self.sync_measurements(current, chunk_end, incremental=False)
            
            total_stats["created"] += stats["created"]
            total_stats["errors"] += stats["errors"]
            
            current = chunk_end + timedelta(days=1)
            
            # Progress log
            logger.info(f"Backfill Progress: {current} / {end_date}")
        
        # Alerts synchronisieren
        alert_stats = self.sync_alerts(start_date, end_date)
        total_stats["alerts_created"] = alert_stats["created"]
        
        logger.info(f"Backfill abgeschlossen: {total_stats}")
        
        return total_stats


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def sync_daily_data(target_date: date = None) -> Dict[str, int]:
    """
    Convenience-Funktion für tägliche Synchronisation.
    
    Sollte nach dem täglichen Daten-Import aufgerufen werden.
    """
    sync = AirtableSync()
    
    target_date = target_date or (date.today() - timedelta(days=1))
    
    measurement_stats = sync.sync_measurements(target_date, target_date)
    alert_stats = sync.sync_alerts(target_date, target_date)
    
    return {
        "measurements": measurement_stats,
        "alerts": alert_stats
    }


def check_airtable_connection() -> bool:
    """
    Prüft die Airtable-Verbindung.
    """
    client = AirtableClient()
    
    if not client.config.is_configured:
        logger.warning("Airtable nicht konfiguriert")
        return False
    
    # Versuche einen Record zu laden
    success, result = client._make_request(
        "GET",
        client.config.measurements_table,
        params={"maxRecords": 1}
    )
    
    if success:
        logger.info("Airtable-Verbindung OK")
        return True
    else:
        logger.error(f"Airtable-Verbindung fehlgeschlagen: {result}")
        return False

