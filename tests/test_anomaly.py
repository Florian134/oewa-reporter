"""
Tests für die Anomalie-Erkennung
================================
"""

import pytest
import pandas as pd
import numpy as np
from datetime import date, timedelta

from oewa_reporting.anomaly import (
    detect_outliers,
    detect_outliers_by_weekday,
    calculate_mad,
    calculate_robust_zscore,
    calculate_pct_delta,
    AnomalyResult,
    Severity,
    AnomalyConfig
)


class TestCalculations:
    """Tests für die Grundberechnungen"""
    
    def test_calculate_mad_normal(self):
        """MAD für normale Verteilung"""
        series = pd.Series([1, 2, 3, 4, 5, 6, 7, 8, 9])
        mad = calculate_mad(series)
        
        # Median = 5, Abweichungen: 4,3,2,1,0,1,2,3,4 -> Median = 2
        assert mad == 2.0
    
    def test_calculate_mad_constant(self):
        """MAD für konstante Werte"""
        series = pd.Series([5, 5, 5, 5, 5])
        mad = calculate_mad(series)
        
        assert mad == 0.0
    
    def test_calculate_robust_zscore(self):
        """Robuster Z-Score Berechnung"""
        # Wert = 10, Median = 5, MAD = 2
        zscore = calculate_robust_zscore(10, 5, 2)
        
        # z = (10 - 5) / (1.4826 * 2) = 5 / 2.9652 ≈ 1.686
        assert abs(zscore - 1.686) < 0.01
    
    def test_calculate_robust_zscore_zero_mad(self):
        """Z-Score bei MAD = 0"""
        zscore = calculate_robust_zscore(10, 5, 0)
        assert zscore == 0.0
    
    def test_calculate_pct_delta(self):
        """Prozentuale Abweichung"""
        # 120 ist 20% über 100
        delta = calculate_pct_delta(120, 100)
        assert delta == 0.2
        
        # 80 ist 20% unter 100
        delta = calculate_pct_delta(80, 100)
        assert delta == -0.2
    
    def test_calculate_pct_delta_zero_median(self):
        """Prozentuale Abweichung bei Median = 0"""
        delta = calculate_pct_delta(100, 0)
        assert delta == 0.0


class TestDetectOutliers:
    """Tests für die Haupt-Erkennungsfunktion"""
    
    @pytest.fixture
    def config(self):
        """Standard Anomalie-Konfiguration"""
        return AnomalyConfig(
            lookback_days=56,
            min_data_points=7,
            warning_zscore=2.0,
            warning_pct_delta=0.15,
            critical_zscore=2.5,
            critical_pct_delta=0.20
        )
    
    def test_no_outlier_normal_data(self, config):
        """Keine Anomalie bei normalen Daten"""
        # Normale Daten mit kleiner Variation
        values = [100, 102, 98, 101, 99, 100, 103, 97, 100, 101]
        series = pd.Series(values)
        
        result = detect_outliers(series, config)
        
        assert not result.is_outlier
        assert result.severity == Severity.NONE
    
    def test_warning_outlier(self, config):
        """Warning bei mäßiger Abweichung"""
        # Normale Daten, letzter Wert deutlich höher
        values = [100, 102, 98, 101, 99, 100, 103, 97, 100, 120]
        series = pd.Series(values)
        
        result = detect_outliers(series, config)
        
        # 120 ist ~20% über Median (100), sollte Warning sein
        assert result.is_outlier
        assert result.severity in [Severity.WARNING, Severity.CRITICAL]
    
    def test_critical_outlier(self, config):
        """Critical bei starker Abweichung"""
        # Normale Daten, letzter Wert extrem hoch
        values = [100, 102, 98, 101, 99, 100, 103, 97, 100, 150]
        series = pd.Series(values)
        
        result = detect_outliers(series, config)
        
        # 150 ist 50% über Median, sollte Critical sein
        assert result.is_outlier
        assert result.severity == Severity.CRITICAL
    
    def test_negative_outlier(self, config):
        """Erkennung von negativen Ausreißern"""
        # Normale Daten, letzter Wert deutlich niedriger
        values = [100, 102, 98, 101, 99, 100, 103, 97, 100, 70]
        series = pd.Series(values)
        
        result = detect_outliers(series, config)
        
        # 70 ist 30% unter Median (100), sollte Critical sein
        assert result.is_outlier
        assert result.pct_delta < 0
    
    def test_insufficient_data(self, config):
        """Zu wenige Datenpunkte"""
        values = [100, 102, 98]  # Nur 3 Punkte
        series = pd.Series(values)
        
        result = detect_outliers(series, config)
        
        assert not result.is_outlier
        assert "wenige Datenpunkte" in result.message
    
    def test_empty_series(self, config):
        """Leere Serie"""
        series = pd.Series([], dtype=float)
        
        result = detect_outliers(series, config)
        
        assert not result.is_outlier
    
    def test_result_contains_statistics(self, config):
        """Ergebnis enthält alle Statistiken"""
        values = [100, 102, 98, 101, 99, 100, 103, 97, 100, 105]
        series = pd.Series(values)
        
        result = detect_outliers(series, config)
        
        assert result.median > 0
        assert result.mad >= 0
        assert result.actual_value == 105
        assert result.data_points == 10


class TestDetectOutliersByWeekday:
    """Tests für wochentagbasierte Erkennung"""
    
    @pytest.fixture
    def weekday_data(self):
        """Testdaten mit Wochentags-Muster"""
        # Simuliere 8 Wochen Daten mit Wochentags-Variation
        data = []
        base_date = date(2024, 1, 1)  # Montag
        
        for week in range(8):
            for day in range(7):
                current_date = base_date + timedelta(days=week*7 + day)
                
                # Wochenende hat weniger Traffic
                if day >= 5:  # Samstag, Sonntag
                    value = 50 + np.random.randint(-5, 5)
                else:  # Wochentag
                    value = 100 + np.random.randint(-5, 5)
                
                data.append((current_date, value))
        
        return data
    
    def test_weekday_comparison(self, weekday_data):
        """Vergleich nur mit gleichem Wochentag"""
        # Füge einen Ausreißer am letzten Tag hinzu
        target_date = weekday_data[-1][0]
        weekday_data[-1] = (target_date, 200)  # Stark erhöht
        
        result = detect_outliers_by_weekday(
            weekday_data,
            target_date
        )
        
        # Sollte Ausreißer erkannt werden
        assert result.is_outlier or result.data_points < 7


class TestAnomalyResult:
    """Tests für das Ergebnis-Objekt"""
    
    def test_to_dict(self):
        """Konvertierung zu Dictionary"""
        result = AnomalyResult(
            is_outlier=True,
            severity=Severity.WARNING,
            zscore=2.5,
            pct_delta=0.20,
            median=100.0,
            mad=5.0,
            actual_value=120,
            data_points=30,
            message="Test"
        )
        
        d = result.to_dict()
        
        assert d["is_outlier"] == True
        assert d["severity"] == "warning"
        assert d["zscore"] == 2.5
        assert d["pct_delta"] == 20.0  # Als Prozent
        assert d["median"] == 100.0
        assert d["actual_value"] == 120


# Zusätzliche Integrations-Tests
class TestIntegration:
    """Integrationstests mit realistischen Szenarien"""
    
    def test_typical_traffic_pattern(self):
        """Typisches Traffic-Muster mit Wochenend-Dip"""
        # Simuliere 4 Wochen typischen Web-Traffic
        np.random.seed(42)
        
        base_weekday = 100000
        base_weekend = 60000
        
        values = []
        for week in range(4):
            for day in range(5):  # Mo-Fr
                values.append(base_weekday + np.random.randint(-5000, 5000))
            for day in range(2):  # Sa-So
                values.append(base_weekend + np.random.randint(-3000, 3000))
        
        # Normaler Wert am Ende
        values.append(base_weekday + 2000)
        
        series = pd.Series(values)
        result = detect_outliers(series)
        
        # Sollte kein Ausreißer sein
        assert not result.is_outlier
    
    def test_sudden_traffic_drop(self):
        """Plötzlicher Traffic-Einbruch"""
        np.random.seed(42)
        
        # Normale Werte
        values = [100000 + np.random.randint(-5000, 5000) for _ in range(28)]
        
        # Plötzlicher Einbruch auf 50%
        values.append(50000)
        
        series = pd.Series(values)
        result = detect_outliers(series)
        
        # Sollte Critical sein (50% unter Median)
        assert result.is_outlier
        assert result.severity == Severity.CRITICAL
        assert result.pct_delta < -0.4  # Mehr als 40% unter Median

