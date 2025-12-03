"""
Anomalie-Erkennung
==================

Robuste Ausreißer-Erkennung basierend auf Median/MAD (Median Absolute Deviation).
Unterstützt Day-of-Week Vergleiche für bessere Genauigkeit.

Features:
- Division-by-Zero Protection
- Edge Case Handling
- Konfigurierbare Schwellwerte
- Thread-safe
"""

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import List, Optional, Tuple, Dict, Union
from enum import Enum

import pandas as pd
import numpy as np

from .config import get_config, AnomalyConfig
from .models import Alert, utc_now
from .db import get_session

logger = logging.getLogger(__name__)


# =============================================================================
# CONSTANTS
# =============================================================================

# MAD Konsistenzfaktor für Normalverteilung
# Macht MAD vergleichbar mit Standardabweichung
MAD_CONSISTENCY_FACTOR = 1.4826

# Minimaler MAD-Wert um Division durch Null zu vermeiden
# Bei sehr stabilen Daten (z.B. konstante Werte) kann MAD sehr klein sein
MIN_MAD_VALUE = 0.001

# Maximaler Z-Score (verhindert extreme Werte bei sehr kleiner MAD)
MAX_ZSCORE = 10.0


class Severity(Enum):
    """Schweregrad einer Anomalie"""
    NONE = "none"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class AnomalyResult:
    """Ergebnis der Anomalie-Analyse"""
    is_outlier: bool
    severity: Severity
    zscore: float
    pct_delta: float
    median: float
    mad: float
    actual_value: float
    
    # Zusätzliche Infos
    data_points: int = 0
    message: Optional[str] = None
    weekday_adjusted: bool = False
    
    def to_dict(self) -> dict:
        return {
            "is_outlier": self.is_outlier,
            "severity": self.severity.value,
            "zscore": round(self.zscore, 2),
            "pct_delta": round(self.pct_delta * 100, 1),  # Als Prozent
            "median": round(self.median, 2),
            "mad": round(self.mad, 2),
            "actual_value": self.actual_value,
            "data_points": self.data_points,
            "message": self.message,
            "weekday_adjusted": self.weekday_adjusted,
        }
    
    @property
    def pct_delta_formatted(self) -> str:
        """Formatierte prozentuale Abweichung"""
        return f"{self.pct_delta * 100:+.1f}%"


# =============================================================================
# CALCULATION FUNCTIONS
# =============================================================================

def calculate_mad(series: pd.Series) -> float:
    """
    Berechnet die Median Absolute Deviation (MAD).
    
    MAD = median(|Xi - median(X)|)
    
    Args:
        series: Pandas Series mit Werten
        
    Returns:
        MAD-Wert (mindestens MIN_MAD_VALUE)
    """
    if series.empty or len(series) == 0:
        return 0.0
    
    median = series.median()
    
    if pd.isna(median):
        return 0.0
    
    mad = (series - median).abs().median()
    
    # Schutz vor Division durch Null
    if pd.isna(mad) or mad < MIN_MAD_VALUE:
        return MIN_MAD_VALUE
    
    return float(mad)


def calculate_robust_zscore(
    value: float, 
    median: float, 
    mad: float
) -> float:
    """
    Berechnet den robusten Z-Score basierend auf Median/MAD.
    
    z = (x - median) / (1.4826 * MAD)
    
    Der Faktor 1.4826 macht MAD vergleichbar mit der Standardabweichung
    bei normalverteilten Daten.
    
    Args:
        value: Zu prüfender Wert
        median: Median der Verteilung
        mad: Median Absolute Deviation
        
    Returns:
        Z-Score (begrenzt auf ±MAX_ZSCORE)
    """
    # Schutz vor ungültigen Werten
    if pd.isna(value) or pd.isna(median):
        return 0.0
    
    # Differenz zum Median
    diff = value - median
    
    # Schutz vor Division durch Null
    if mad < MIN_MAD_VALUE:
        # Wenn MAD sehr klein ist, gibt es keine Varianz
        # Ein Wert der vom Median abweicht ist dann ein extremer Ausreißer
        if abs(diff) < MIN_MAD_VALUE:
            return 0.0
        # Bei signifikanter Abweichung: Maximaler Z-Score
        return MAX_ZSCORE if diff > 0 else -MAX_ZSCORE
    
    # Z-Score berechnen
    zscore = diff / (MAD_CONSISTENCY_FACTOR * mad)
    
    # Begrenze auf Maximum (verhindert extreme Werte)
    return max(-MAX_ZSCORE, min(MAX_ZSCORE, zscore))


def calculate_pct_delta(value: float, median: float) -> float:
    """
    Berechnet die prozentuale Abweichung vom Median.
    
    Args:
        value: Zu prüfender Wert
        median: Median der Verteilung
        
    Returns:
        Prozentuale Abweichung (-1 bis +∞)
    """
    # Schutz vor ungültigen Werten
    if pd.isna(value) or pd.isna(median):
        return 0.0
    
    # Schutz vor Division durch Null
    if abs(median) < MIN_MAD_VALUE:
        if abs(value) < MIN_MAD_VALUE:
            return 0.0
        # Bei Median nahe 0: Maximale Abweichung
        return 10.0 if value > 0 else -10.0
    
    return (value - median) / median


def detect_outliers(
    series: pd.Series,
    config: AnomalyConfig = None
) -> AnomalyResult:
    """
    Erkennt Ausreißer in einer Zeitreihe.
    
    Args:
        series: Zeitreihe mit historischen Werten (letzter Wert = aktuell)
        config: Anomalie-Konfiguration (optional)
        
    Returns:
        AnomalyResult mit Analyse-Ergebnis
    """
    config = config or get_config().anomaly
    
    # Edge Case: Leere Serie
    if series.empty or len(series) == 0:
        return AnomalyResult(
            is_outlier=False,
            severity=Severity.NONE,
            zscore=0.0,
            pct_delta=0.0,
            median=0.0,
            mad=0.0,
            actual_value=0,
            data_points=0,
            message="Keine Daten"
        )
    
    # Edge Case: Zu wenige Datenpunkte
    if len(series) < config.min_data_points:
        logger.warning(
            f"Zu wenige Datenpunkte ({len(series)}) für Anomalie-Erkennung "
            f"(min: {config.min_data_points})"
        )
        return AnomalyResult(
            is_outlier=False,
            severity=Severity.NONE,
            zscore=0.0,
            pct_delta=0.0,
            median=float(series.median()) if len(series) > 0 else 0,
            mad=0.0,
            actual_value=float(series.iloc[-1]) if len(series) > 0 else 0,
            data_points=len(series),
            message="Zu wenige Datenpunkte"
        )
    
    # Konvertiere zu numerischen Werten und entferne NaN
    series = pd.to_numeric(series, errors='coerce').dropna()
    
    if len(series) < 2:
        return AnomalyResult(
            is_outlier=False,
            severity=Severity.NONE,
            zscore=0.0,
            pct_delta=0.0,
            median=float(series.iloc[0]) if len(series) > 0 else 0,
            mad=0.0,
            actual_value=float(series.iloc[-1]) if len(series) > 0 else 0,
            data_points=len(series),
            message="Nicht genug valide Datenpunkte"
        )
    
    # Aktueller Wert (letztes Element)
    actual = float(series.iloc[-1])
    
    # Historische Werte (ohne aktuellen Wert)
    historical = series.iloc[:-1]
    
    # Statistiken berechnen
    median = float(historical.median())
    mad = calculate_mad(historical)
    
    # Z-Score und prozentuale Abweichung
    zscore = calculate_robust_zscore(actual, median, mad)
    pct_delta = calculate_pct_delta(actual, median)
    
    # Schweregrad bestimmen
    severity = Severity.NONE
    is_outlier = False
    
    abs_zscore = abs(zscore)
    abs_pct_delta = abs(pct_delta)
    
    # Critical: |z| >= 2.5 UND |%Δ| >= 20%
    if abs_zscore >= config.critical_zscore and abs_pct_delta >= config.critical_pct_delta:
        severity = Severity.CRITICAL
        is_outlier = True
    # Warning: |z| >= 2.0 UND |%Δ| >= 15%
    elif abs_zscore >= config.warning_zscore and abs_pct_delta >= config.warning_pct_delta:
        severity = Severity.WARNING
        is_outlier = True
    
    # Nachricht generieren
    message = None
    if is_outlier:
        direction = "über" if pct_delta > 0 else "unter"
        message = (
            f"{severity.value.upper()}: {abs(pct_delta)*100:.1f}% {direction} Median "
            f"(z = {zscore:+.2f})"
        )
    
    return AnomalyResult(
        is_outlier=is_outlier,
        severity=severity,
        zscore=zscore,
        pct_delta=pct_delta,
        median=median,
        mad=mad,
        actual_value=actual,
        data_points=len(series),
        message=message
    )


def detect_outliers_by_weekday(
    data: List[Tuple[date, Union[int, float]]],
    target_date: date,
    config: AnomalyConfig = None
) -> AnomalyResult:
    """
    Erkennt Ausreißer mit Day-of-Week Berücksichtigung.
    
    Vergleicht nur mit demselben Wochentag (z.B. alle Montage).
    
    Args:
        data: Liste von (Datum, Wert) Tupeln
        target_date: Zu prüfendes Datum
        config: Anomalie-Konfiguration
        
    Returns:
        AnomalyResult
    """
    # Edge Case: Keine Daten
    if not data:
        return AnomalyResult(
            is_outlier=False,
            severity=Severity.NONE,
            zscore=0.0,
            pct_delta=0.0,
            median=0.0,
            mad=0.0,
            actual_value=0,
            message="Keine Daten"
        )
    
    # DataFrame erstellen
    df = pd.DataFrame(data, columns=["date", "value"])
    df["value"] = pd.to_numeric(df["value"], errors='coerce')
    df = df.dropna(subset=["value"])
    
    if df.empty:
        return AnomalyResult(
            is_outlier=False,
            severity=Severity.NONE,
            zscore=0.0,
            pct_delta=0.0,
            median=0.0,
            mad=0.0,
            actual_value=0,
            message="Keine validen Daten"
        )
    
    df["weekday"] = df["date"].apply(lambda d: d.weekday())
    
    target_weekday = target_date.weekday()
    target_value = None
    
    # Finde den Wert für das Zieldatum
    target_row = df[df["date"] == target_date]
    if not target_row.empty:
        target_value = float(target_row["value"].iloc[0])
    else:
        logger.warning(f"Kein Wert für Zieldatum {target_date}")
        return AnomalyResult(
            is_outlier=False,
            severity=Severity.NONE,
            zscore=0.0,
            pct_delta=0.0,
            median=float(df["value"].median()),
            mad=calculate_mad(df["value"]),
            actual_value=0,
            message="Kein Wert für Zieldatum"
        )
    
    # Filtere nach gleichem Wochentag
    same_weekday = df[df["weekday"] == target_weekday]["value"]
    
    if len(same_weekday) < 2:
        # Fallback auf alle Daten
        logger.debug(f"Nur {len(same_weekday)} Datenpunkte für Wochentag, nutze alle Daten")
        result = detect_outliers(df["value"], config)
        result.weekday_adjusted = False
        return result
    
    result = detect_outliers(same_weekday, config)
    result.weekday_adjusted = True
    return result


# =============================================================================
# ANOMALY DETECTOR CLASS
# =============================================================================

class AnomalyDetector:
    """
    Orchestriert die Anomalie-Erkennung für alle konfigurierten Metriken.
    
    Thread-safe und konfigurierbar.
    """
    
    def __init__(self, config: AnomalyConfig = None):
        self.config = config or get_config().anomaly
    
    def analyze_measurement(
        self,
        brand: str,
        surface: str,
        metric: str,
        target_date: date,
        historical_data: List[Tuple[date, Union[int, float]]],
        use_weekday: bool = True
    ) -> AnomalyResult:
        """
        Analysiert einen einzelnen Messwert.
        
        Args:
            brand: Brand (z.B. "vol")
            surface: Surface (z.B. "web_desktop")
            metric: Metrik (z.B. "pageimpressions")
            target_date: Zu prüfendes Datum
            historical_data: Historische Daten
            use_weekday: Wochentag-basierte Analyse?
            
        Returns:
            AnomalyResult
        """
        logger.debug(
            f"Analysiere {brand}/{surface}/{metric} für {target_date} "
            f"({len(historical_data)} Datenpunkte)"
        )
        
        if use_weekday:
            return detect_outliers_by_weekday(
                historical_data,
                target_date,
                self.config
            )
        else:
            if not historical_data:
                return AnomalyResult(
                    is_outlier=False,
                    severity=Severity.NONE,
                    zscore=0.0,
                    pct_delta=0.0,
                    median=0.0,
                    mad=0.0,
                    actual_value=0,
                    message="Keine Daten"
                )
            
            values = pd.Series([v for _, v in historical_data])
            return detect_outliers(values, self.config)
    
    def save_alert(
        self,
        brand: str,
        surface: str,
        metric: str,
        target_date: date,
        result: AnomalyResult
    ) -> Optional[Alert]:
        """
        Speichert einen Alert in der Datenbank.
        
        Returns:
            Alert-Objekt oder None wenn kein Ausreißer
        """
        if not result.is_outlier:
            return None
        
        try:
            with get_session() as session:
                # Prüfe ob Alert bereits existiert
                existing = session.query(Alert).filter(
                    Alert.brand == brand,
                    Alert.surface == surface,
                    Alert.metric == metric,
                    Alert.date == target_date,
                    Alert.severity == result.severity.value
                ).first()
                
                if existing:
                    logger.debug(f"Alert existiert bereits: {existing}")
                    return existing
                
                alert = Alert(
                    brand=brand,
                    surface=surface,
                    metric=metric,
                    date=target_date,
                    severity=result.severity.value,
                    zscore=result.zscore,
                    pct_delta=result.pct_delta,
                    baseline_median=result.median,
                    baseline_mad=result.mad,
                    actual_value=result.actual_value,
                    message=result.message,
                    created_at=utc_now()
                )
                
                session.add(alert)
                logger.info(f"Alert gespeichert: {alert}")
                
                return alert
                
        except Exception as e:
            logger.error(f"Fehler beim Speichern des Alerts: {e}")
            raise
    
    def get_alerts_for_date(self, target_date: date) -> List[Alert]:
        """Holt alle Alerts für ein Datum"""
        with get_session() as session:
            return session.query(Alert).filter(
                Alert.date == target_date
            ).order_by(Alert.severity.desc()).all()
    
    def get_recent_alerts(self, days: int = 7) -> List[Alert]:
        """Holt Alerts der letzten N Tage"""
        cutoff = date.today() - timedelta(days=days)
        
        with get_session() as session:
            return session.query(Alert).filter(
                Alert.date >= cutoff
            ).order_by(Alert.date.desc(), Alert.severity.desc()).all()
    
    def acknowledge_alert(
        self,
        alert_id: int,
        acknowledged_by: str
    ) -> Optional[Alert]:
        """
        Markiert einen Alert als bestätigt.
        
        Args:
            alert_id: Alert-ID
            acknowledged_by: Benutzername
            
        Returns:
            Aktualisierter Alert oder None
        """
        with get_session() as session:
            alert = session.query(Alert).filter(Alert.id == alert_id).first()
            
            if not alert:
                logger.warning(f"Alert {alert_id} nicht gefunden")
                return None
            
            alert.acknowledged = True
            alert.acknowledged_at = utc_now()
            alert.acknowledged_by = acknowledged_by
            
            logger.info(f"Alert {alert_id} bestätigt von {acknowledged_by}")
            
            return alert
