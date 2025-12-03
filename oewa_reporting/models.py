"""
SQLAlchemy Datenmodelle
=======================

Definiert die Datenbankstruktur für Measurements und Alerts.
Verwendet UTC-Timestamps für konsistente Zeitverwaltung.
"""

from datetime import datetime, date, timezone
from typing import Optional
from sqlalchemy import (
    Column, Integer, BigInteger, String, Date, DateTime, 
    Boolean, Float, Text, UniqueConstraint, Index, create_engine,
    event
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()


def utc_now() -> datetime:
    """Gibt aktuelle UTC-Zeit zurück (timezone-aware)"""
    return datetime.now(timezone.utc)


class Measurement(Base):
    """
    Speichert ÖWA-Messwerte (Page Impressions, Visits, etc.)
    
    Unique Constraint auf (brand, surface, metric, date, site_id, preliminary)
    verhindert Duplikate.
    """
    __tablename__ = "measurements"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Identifikation
    brand = Column(String(50), nullable=False, index=True)  # z.B. "vol", "vienna"
    surface = Column(String(50), nullable=False, index=True)  # z.B. "web_desktop", "app"
    metric = Column(String(50), nullable=False, index=True)  # z.B. "pageimpressions", "visits"
    date = Column(Date, nullable=False, index=True)
    site_id = Column(String(100), nullable=False)  # z.B. "EA000004_desktop"
    
    # Messwerte
    value_total = Column(BigInteger, nullable=False)  # Gesamtwert (IOM)
    value_national = Column(BigInteger, nullable=True)  # National
    value_international = Column(BigInteger, nullable=True)  # International
    
    # Consent-spezifische Werte
    value_iomp = Column(BigInteger, nullable=True)  # Pseudonym/Consent
    value_iomb = Column(BigInteger, nullable=True)  # Zensus/Consentless
    
    # Metadaten
    preliminary = Column(Boolean, default=True, nullable=False)  # Vorläufige Daten?
    exported_at = Column(DateTime(timezone=True), nullable=True)  # Zeitpunkt des API-Exports
    version = Column(String(20), nullable=True)  # API-Version
    
    # Tracking (UTC-aware)
    ingested_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
    
    # Unique Constraint
    __table_args__ = (
        UniqueConstraint(
            'brand', 'surface', 'metric', 'date', 'site_id', 'preliminary',
            name='uq_measurement_identity'
        ),
        Index('ix_measurement_lookup', 'brand', 'surface', 'metric', 'date'),
        Index('ix_measurement_brand_date', 'brand', 'date'),  # Für Daily Summaries
    )
    
    def __repr__(self):
        return (
            f"<Measurement(brand={self.brand}, surface={self.surface}, "
            f"metric={self.metric}, date={self.date}, value={self.value_total})>"
        )
    
    def to_dict(self) -> dict:
        """Konvertiert zu Dictionary"""
        return {
            "id": self.id,
            "brand": self.brand,
            "surface": self.surface,
            "metric": self.metric,
            "date": self.date.isoformat() if self.date else None,
            "site_id": self.site_id,
            "value_total": self.value_total,
            "value_national": self.value_national,
            "value_international": self.value_international,
            "value_iomp": self.value_iomp,
            "value_iomb": self.value_iomb,
            "preliminary": self.preliminary,
            "exported_at": self.exported_at.isoformat() if self.exported_at else None,
            "ingested_at": self.ingested_at.isoformat() if self.ingested_at else None,
        }
    
    @classmethod
    def upsert_data(cls) -> dict:
        """
        Gibt die Spalten für einen Upsert zurück (ohne id und ingested_at).
        Verwendet für INSERT ... ON CONFLICT UPDATE.
        """
        return {
            'value_total': cls.value_total,
            'value_national': cls.value_national,
            'value_international': cls.value_international,
            'value_iomp': cls.value_iomp,
            'value_iomb': cls.value_iomb,
            'exported_at': cls.exported_at,
            'version': cls.version,
            'updated_at': utc_now(),
        }


class Alert(Base):
    """
    Speichert erkannte Anomalien/Ausreißer
    """
    __tablename__ = "alerts"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    
    # Identifikation
    brand = Column(String(50), nullable=False, index=True)
    surface = Column(String(50), nullable=False, index=True)
    metric = Column(String(50), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    
    # Schweregrad
    severity = Column(String(20), nullable=False)  # "warning" oder "critical"
    
    # Statistik-Werte
    zscore = Column(Float, nullable=False)
    pct_delta = Column(Float, nullable=False)  # Prozentuale Abweichung
    baseline_median = Column(Float, nullable=False)
    baseline_mad = Column(Float, nullable=True)  # Median Absolute Deviation
    actual_value = Column(Float, nullable=False)
    
    # Nachricht
    message = Column(Text, nullable=True)
    
    # Status
    acknowledged = Column(Boolean, default=False)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    acknowledged_by = Column(String(100), nullable=True)
    
    # Tracking
    notified_at = Column(DateTime(timezone=True), nullable=True)  # Wann wurde Teams benachrichtigt?
    
    __table_args__ = (
        Index('ix_alert_lookup', 'brand', 'surface', 'metric', 'date'),
        Index('ix_alert_severity', 'severity', 'created_at'),
        Index('ix_alert_date_severity', 'date', 'severity'),  # Für schnelle Alert-Übersichten
    )
    
    def __repr__(self):
        return (
            f"<Alert(severity={self.severity}, brand={self.brand}, "
            f"metric={self.metric}, date={self.date}, zscore={self.zscore:.2f})>"
        )
    
    def to_dict(self) -> dict:
        """Konvertiert zu Dictionary"""
        return {
            "id": self.id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "brand": self.brand,
            "surface": self.surface,
            "metric": self.metric,
            "date": self.date.isoformat() if self.date else None,
            "severity": self.severity,
            "zscore": self.zscore,
            "pct_delta": self.pct_delta,
            "baseline_median": self.baseline_median,
            "baseline_mad": self.baseline_mad,
            "actual_value": self.actual_value,
            "message": self.message,
            "acknowledged": self.acknowledged,
        }
    
    @property
    def is_critical(self) -> bool:
        """Prüft ob Alert kritisch ist"""
        return self.severity == "critical"
    
    @property
    def is_warning(self) -> bool:
        """Prüft ob Alert eine Warnung ist"""
        return self.severity == "warning"


class DailySummary(Base):
    """
    Tägliche Zusammenfassung pro Brand
    """
    __tablename__ = "daily_summaries"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False, index=True)
    brand = Column(String(50), nullable=False, index=True)
    
    # Aggregierte Werte
    web_total_pi = Column(BigInteger, nullable=True)  # Desktop + Mobile Web
    app_total_pi = Column(BigInteger, nullable=True)
    web_total_visits = Column(BigInteger, nullable=True)
    app_total_visits = Column(BigInteger, nullable=True)
    
    # Alerts
    warning_count = Column(Integer, default=0)
    critical_count = Column(Integer, default=0)
    
    # Tracking (UTC-aware)
    created_at = Column(DateTime(timezone=True), default=utc_now)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
    
    __table_args__ = (
        UniqueConstraint('date', 'brand', name='uq_daily_summary'),
        Index('ix_daily_summary_brand_date', 'brand', 'date'),
    )


class MonthlySummary(Base):
    """
    Monatliche Zusammenfassung pro Brand
    """
    __tablename__ = "monthly_summaries"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)
    brand = Column(String(50), nullable=False, index=True)
    
    # Aggregierte Werte
    web_total_pi = Column(BigInteger, nullable=True)
    app_total_pi = Column(BigInteger, nullable=True)
    web_total_visits = Column(BigInteger, nullable=True)
    app_total_visits = Column(BigInteger, nullable=True)
    
    # Durchschnittswerte
    web_avg_daily_pi = Column(Float, nullable=True)
    app_avg_daily_pi = Column(Float, nullable=True)
    
    # Vergleich zum Vormonat
    web_pi_change_pct = Column(Float, nullable=True)
    app_pi_change_pct = Column(Float, nullable=True)
    
    # Alerts im Monat
    total_warnings = Column(Integer, default=0)
    total_criticals = Column(Integer, default=0)
    
    # Tracking (UTC-aware)
    created_at = Column(DateTime(timezone=True), default=utc_now)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
    
    __table_args__ = (
        UniqueConstraint('year', 'month', 'brand', name='uq_monthly_summary'),
        Index('ix_monthly_summary_brand', 'brand', 'year', 'month'),
    )
