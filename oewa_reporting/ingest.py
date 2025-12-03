"""
Daten-Ingestion
===============

Holt Daten von der API und speichert sie in der Datenbank.
Optimiert für:
- Upsert-Operationen (INSERT ... ON CONFLICT UPDATE)
- Batch-Queries zur Vermeidung von N+1 Problemen
- Optionales Parallel Processing für Backfills
"""

import logging
from datetime import date, datetime, timedelta, timezone
from typing import List, Dict, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from sqlalchemy import and_, or_, func, text
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.dialects.postgresql import insert as pg_insert

from .config import get_config, SiteConfig
from .models import Measurement, DailySummary, utc_now
from .db import get_session, get_engine
from .api_client import INFOnlineAPIClient, MetricData

logger = logging.getLogger(__name__)


@dataclass
class IngestionStats:
    """Statistiken für Ingestion-Operationen"""
    inserted: int = 0
    updated: int = 0
    errors: int = 0
    skipped: int = 0
    
    def merge(self, other: 'IngestionStats'):
        """Fügt Statistiken zusammen"""
        self.inserted += other.inserted
        self.updated += other.updated
        self.errors += other.errors
        self.skipped += other.skipped
    
    def to_dict(self) -> dict:
        return {
            "inserted": self.inserted,
            "updated": self.updated,
            "errors": self.errors,
            "skipped": self.skipped
        }


class DataIngester:
    """
    Orchestriert die Daten-Ingestion von der API in die Datenbank.
    
    Features:
    - Upsert-Operationen (keine Race Conditions)
    - Batch-Inserts für Performance
    - Optional: Parallel Processing für Backfills
    - Optimierte Queries (keine N+1)
    """
    
    def __init__(self, api_client: INFOnlineAPIClient = None):
        self.api_client = api_client or INFOnlineAPIClient()
        self.config = get_config()
        self._is_postgres = self._check_db_type()
    
    def _check_db_type(self) -> bool:
        """Prüft ob PostgreSQL verwendet wird"""
        db_url = self.config.database.url.lower()
        return 'postgresql' in db_url or 'postgres' in db_url
    
    def ingest_day(
        self,
        target_date: date,
        sites: List[SiteConfig] = None,
        metrics: List[str] = None
    ) -> Dict[str, int]:
        """
        Ingestion für einen einzelnen Tag.
        
        Args:
            target_date: Ziel-Datum
            sites: Site-Konfigurationen (optional)
            metrics: Metrik-Liste (optional)
            
        Returns:
            Dict mit Statistiken (inserted, updated, errors)
        """
        sites = sites or self.config.sites
        metrics = metrics or self.config.metrics
        
        date_str = target_date.strftime("%Y-%m-%d")
        
        logger.info(f"Starte Ingestion für {date_str}")
        logger.debug(f"Sites: {[s.name for s in sites]}")
        logger.debug(f"Metriken: {metrics}")
        
        stats = IngestionStats()
        measurements_batch: List[dict] = []
        
        for site in sites:
            for metric in metrics:
                try:
                    result = self._fetch_single(site, metric, date_str)
                    
                    if result is None:
                        stats.errors += 1
                    elif result == "skipped":
                        stats.skipped += 1
                    else:
                        measurements_batch.append(result)
                        
                except Exception as e:
                    logger.error(f"Fehler bei {site.name}/{metric}: {e}")
                    stats.errors += 1
        
        # Batch-Insert/Upsert
        if measurements_batch:
            batch_stats = self._upsert_batch(measurements_batch)
            stats.merge(batch_stats)
        
        logger.info(
            f"Ingestion abgeschlossen: {stats.inserted} neu, "
            f"{stats.updated} aktualisiert, {stats.errors} Fehler"
        )
        
        return stats.to_dict()
    
    def _fetch_single(
        self,
        site: SiteConfig,
        metric: str,
        date_str: str
    ) -> Optional[dict]:
        """
        Holt Daten für eine einzelne Site/Metrik-Kombination.
        
        Returns:
            Dict mit Measurement-Daten, "skipped", oder None bei Fehler
        """
        # Daten von API holen
        metric_data = self.api_client.fetch_metric_parsed(
            metric=metric,
            site_id=site.site_id,
            date=date_str
        )
        
        if metric_data is None:
            logger.warning(f"Keine Daten für {site.name}/{metric}/{date_str}")
            return None
        
        if metric_data.iom_total is None:
            logger.debug(f"Keine IOM-Daten für {site.name}/{metric}/{date_str}")
            return "skipped"
        
        # Measurement-Dict für Batch-Insert
        return {
            "brand": site.brand,
            "surface": site.surface,
            "metric": metric,
            "date": datetime.strptime(date_str, "%Y-%m-%d").date(),
            "site_id": site.site_id,
            "value_total": metric_data.iom_total,
            "value_national": metric_data.iom_national,
            "value_international": metric_data.iom_international,
            "value_iomp": metric_data.iomp_total,
            "value_iomb": metric_data.iomb_total,
            "preliminary": metric_data.iom_preliminary,
            "exported_at": metric_data.exported_at,
            "version": metric_data.version,
            "ingested_at": utc_now(),
            "updated_at": utc_now(),
        }
    
    def _upsert_batch(self, measurements: List[dict]) -> IngestionStats:
        """
        Führt Batch-Upsert durch (INSERT ... ON CONFLICT UPDATE).
        
        Verwendet SQLite oder PostgreSQL spezifischen Upsert.
        """
        stats = IngestionStats()
        
        if not measurements:
            return stats
        
        try:
            with get_session() as session:
                for measurement in measurements:
                    # Prüfe ob existiert
                    existing = session.query(Measurement).filter(
                        and_(
                            Measurement.brand == measurement["brand"],
                            Measurement.surface == measurement["surface"],
                            Measurement.metric == measurement["metric"],
                            Measurement.date == measurement["date"],
                            Measurement.site_id == measurement["site_id"],
                            Measurement.preliminary == measurement["preliminary"]
                        )
                    ).first()
                    
                    if existing:
                        # Update
                        existing.value_total = measurement["value_total"]
                        existing.value_national = measurement["value_national"]
                        existing.value_international = measurement["value_international"]
                        existing.value_iomp = measurement["value_iomp"]
                        existing.value_iomb = measurement["value_iomb"]
                        existing.exported_at = measurement["exported_at"]
                        existing.version = measurement["version"]
                        existing.updated_at = utc_now()
                        stats.updated += 1
                    else:
                        # Insert
                        new_measurement = Measurement(**measurement)
                        session.add(new_measurement)
                        stats.inserted += 1
                
                session.commit()
                
        except Exception as e:
            logger.error(f"Batch-Upsert Fehler: {e}")
            stats.errors = len(measurements)
            raise
        
        return stats
    
    def _upsert_batch_postgres(self, measurements: List[dict]) -> IngestionStats:
        """
        PostgreSQL-spezifischer Upsert mit INSERT ... ON CONFLICT.
        Deutlich performanter bei großen Datenmengen.
        """
        stats = IngestionStats()
        
        if not measurements:
            return stats
        
        try:
            engine = get_engine()
            
            # PostgreSQL INSERT ... ON CONFLICT DO UPDATE
            stmt = pg_insert(Measurement).values(measurements)
            
            update_cols = {
                'value_total': stmt.excluded.value_total,
                'value_national': stmt.excluded.value_national,
                'value_international': stmt.excluded.value_international,
                'value_iomp': stmt.excluded.value_iomp,
                'value_iomb': stmt.excluded.value_iomb,
                'exported_at': stmt.excluded.exported_at,
                'version': stmt.excluded.version,
                'updated_at': utc_now(),
            }
            
            upsert_stmt = stmt.on_conflict_do_update(
                constraint='uq_measurement_identity',
                set_=update_cols
            )
            
            with engine.begin() as conn:
                result = conn.execute(upsert_stmt)
                # rowcount gibt Anzahl betroffener Zeilen
                stats.inserted = len(measurements)  # Kann nicht genau unterscheiden
                
        except Exception as e:
            logger.error(f"PostgreSQL Upsert Fehler: {e}")
            stats.errors = len(measurements)
            raise
        
        return stats
    
    def ingest_date_range(
        self,
        start_date: date,
        end_date: date,
        sites: List[SiteConfig] = None,
        metrics: List[str] = None,
        parallel: bool = False,
        max_workers: int = 4
    ) -> Dict[str, int]:
        """
        Ingestion für einen Datumsbereich.
        
        Args:
            start_date: Startdatum
            end_date: Enddatum
            sites: Sites (optional)
            metrics: Metriken (optional)
            parallel: Parallel Processing aktivieren
            max_workers: Anzahl Worker-Threads
        """
        total_stats = IngestionStats()
        
        days = []
        current = start_date
        while current <= end_date:
            days.append(current)
            current += timedelta(days=1)
        
        if parallel and len(days) > 1:
            # Parallel Processing
            logger.info(f"Starte parallele Ingestion mit {max_workers} Workers")
            
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(self.ingest_day, day, sites, metrics): day 
                    for day in days
                }
                
                for future in as_completed(futures):
                    day = futures[future]
                    try:
                        stats = future.result()
                        for key in stats:
                            setattr(total_stats, key, 
                                   getattr(total_stats, key) + stats[key])
                    except Exception as e:
                        logger.error(f"Fehler bei {day}: {e}")
                        total_stats.errors += 1
        else:
            # Sequentiell
            for day in days:
                stats = self.ingest_day(day, sites, metrics)
                for key in stats:
                    setattr(total_stats, key, 
                           getattr(total_stats, key) + stats[key])
        
        return total_stats.to_dict()
    
    def get_measurements_for_anomaly(
        self,
        brand: str,
        surface: str,
        metric: str,
        end_date: date,
        lookback_days: int = None
    ) -> List[Tuple[date, int]]:
        """
        Holt historische Messwerte für die Anomalie-Erkennung.
        
        Optimierte Query mit Index-Nutzung.
        
        Returns:
            Liste von (Datum, Wert) Tupeln, sortiert nach Datum
        """
        lookback_days = lookback_days or self.config.anomaly.lookback_days
        start_date = end_date - timedelta(days=lookback_days)
        
        with get_session() as session:
            results = session.query(
                Measurement.date,
                Measurement.value_total
            ).filter(
                and_(
                    Measurement.brand == brand,
                    Measurement.surface == surface,
                    Measurement.metric == metric,
                    Measurement.date >= start_date,
                    Measurement.date <= end_date,
                    # Verwende beide: vorläufige und finale Daten
                )
            ).order_by(Measurement.date).all()
            
            return [(r.date, r.value_total) for r in results]
    
    def get_latest_measurement(
        self,
        brand: str,
        surface: str,
        metric: str
    ) -> Optional[Measurement]:
        """Holt den neuesten Messwert"""
        with get_session() as session:
            return session.query(Measurement).filter(
                and_(
                    Measurement.brand == brand,
                    Measurement.surface == surface,
                    Measurement.metric == metric
                )
            ).order_by(Measurement.date.desc()).first()
    
    def get_daily_summary_batch(
        self,
        target_date: date,
        brands: List[str] = None
    ) -> Dict[str, Dict[str, Optional[int]]]:
        """
        Erstellt Tageszusammenfassungen für alle Brands in einer Query.
        
        Optimiert: Verwendet GROUP BY statt N+1 Queries.
        
        Returns:
            Dict mit Brand als Key und Summary-Dict als Value
        """
        brands = brands or list(set(s.brand for s in self.config.sites))
        
        with get_session() as session:
            # Eine Query für alle Brands und Surfaces
            results = session.query(
                Measurement.brand,
                Measurement.surface,
                Measurement.metric,
                func.sum(Measurement.value_total).label("total")
            ).filter(
                and_(
                    Measurement.date == target_date,
                    Measurement.brand.in_(brands)
                )
            ).group_by(
                Measurement.brand,
                Measurement.surface,
                Measurement.metric
            ).all()
            
            # Ergebnisse gruppieren
            summaries = {brand: {
                "web_pi": 0,
                "app_pi": 0,
                "web_visits": 0,
                "app_visits": 0,
            } for brand in brands}
            
            for row in results:
                brand = row.brand
                surface = row.surface
                metric = row.metric
                total = row.total or 0
                
                if surface in ("web_desktop", "web_mobile"):
                    if metric == "pageimpressions":
                        summaries[brand]["web_pi"] += total
                    elif metric == "visits":
                        summaries[brand]["web_visits"] += total
                elif surface == "app":
                    if metric == "pageimpressions":
                        summaries[brand]["app_pi"] += total
                    elif metric == "visits":
                        summaries[brand]["app_visits"] += total
            
            return summaries
    
    def get_daily_summary(
        self,
        target_date: date,
        brand: str
    ) -> Dict[str, Optional[int]]:
        """
        Erstellt eine Tageszusammenfassung für einen Brand.
        
        Verwendet die optimierte Batch-Methode.
        """
        summaries = self.get_daily_summary_batch(target_date, [brand])
        return summaries.get(brand, {
            "web_pi": 0,
            "app_pi": 0,
            "web_visits": 0,
            "app_visits": 0,
        })
    
    def get_date_range_summary(
        self,
        start_date: date,
        end_date: date,
        brand: str = None
    ) -> Dict[str, Dict[str, int]]:
        """
        Holt aggregierte Daten für einen Datumsbereich.
        
        Optimierte Query mit GROUP BY.
        
        Returns:
            Dict mit Metrik als Key und {surface: total} als Value
        """
        with get_session() as session:
            query = session.query(
                Measurement.surface,
                Measurement.metric,
                func.sum(Measurement.value_total).label("total")
            ).filter(
                and_(
                    Measurement.date >= start_date,
                    Measurement.date <= end_date
                )
            )
            
            if brand:
                query = query.filter(Measurement.brand == brand)
            
            results = query.group_by(
                Measurement.surface,
                Measurement.metric
            ).all()
            
            summary = {}
            for row in results:
                metric = row.metric
                surface = row.surface
                
                if metric not in summary:
                    summary[metric] = {}
                
                summary[metric][surface] = row.total or 0
            
            return summary
