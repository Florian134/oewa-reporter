"""
AI-Powered Report Interpretation
=================================

Verwendet OpenAI GPT-4 für:
- Intelligente Interpretation von Metriken
- Professionelle Management-Zusammenfassungen
- Trend-Analyse und Prognosen
- Anomalie-Erklärungen

Die generierten Texte werden an die Geschäftsleitung via Teams gesendet.
"""

import logging
import json
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

import requests

from .config import get_config
from .db import get_session
from .models import Measurement, Alert

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION
# =============================================================================

# Prompts für verschiedene Report-Typen
SYSTEM_PROMPT = """Du bist ein erfahrener Digital-Analyst für Russmedia. 
Deine Aufgabe ist es, Web-Traffic-Daten (Page Impressions, Visits) für VOL.at zu analysieren 
und prägnante, professionelle Zusammenfassungen für die Geschäftsleitung zu erstellen.

Wichtige Richtlinien:
- Schreibe auf Deutsch in einem professionellen, aber verständlichen Stil
- Fokussiere auf die wichtigsten Erkenntnisse und Trends
- Erkläre Anomalien und mögliche Ursachen
- Gib wenn möglich Handlungsempfehlungen
- Halte dich kurz und präzise (max. 300 Wörter)
- Verwende Zahlen mit Tausendertrennzeichen (Punkt) im deutschen Format
- Beziehe dich auf konkrete Daten aus dem Report
"""

WEEKLY_PROMPT_TEMPLATE = """Analysiere die folgenden Wochen-Daten für VOL.at und erstelle eine prägnante Zusammenfassung für die Geschäftsleitung:

## Wochenzeitraum
{week_period}

## Aktuelle Woche - Metriken
{current_week_data}

## Vergleich zur Vorwoche
{comparison_data}

## Erkannte Anomalien
{anomalies}

## Tagesverteilung
{daily_breakdown}

Erstelle eine professionelle Zusammenfassung mit:
1. Executive Summary (2-3 Sätze Kernaussage)
2. Wichtigste Trends und Entwicklungen
3. Auffälligkeiten und mögliche Erklärungen
4. Kurzer Ausblick / Empfehlung

Format: Verwende Bullet Points und klare Struktur. Max. 300 Wörter."""

MONTHLY_PROMPT_TEMPLATE = """Analysiere die folgenden Monats-Daten für VOL.at und erstelle einen umfassenden Report für die Geschäftsleitung:

## Monat
{month_period}

## Gesamtzahlen des Monats
{monthly_totals}

## Vergleich zum Vormonat
{month_comparison}

## Vergleich zum Vorjahresmonat (falls verfügbar)
{yoy_comparison}

## Wochentrend im Monat
{weekly_trend}

## Anomalien im Monat
{monthly_anomalies}

## Plattform-Verteilung
{platform_distribution}

Erstelle einen umfassenden Monatsbericht mit:
1. Executive Summary (3-4 Sätze)
2. Performance-Highlights
3. Herausforderungen und Auffälligkeiten
4. Plattform-Entwicklung (Web vs. App)
5. Strategische Empfehlungen

Format: Professioneller Bericht-Stil. Max. 500 Wörter."""

ANOMALY_PROMPT_TEMPLATE = """Eine signifikante Anomalie wurde in den ÖWA-Daten erkannt:

## Alert Details
- Brand: {brand}
- Plattform: {surface}
- Metrik: {metric}
- Datum: {date}
- Aktueller Wert: {actual_value}
- Erwarteter Bereich (Median): {median}
- Abweichung: {pct_delta}%
- Z-Score: {zscore}
- Schweregrad: {severity}

## Kontext (letzte 7 Tage)
{recent_context}

Analysiere diese Anomalie und erstelle eine kurze Erklärung:
1. Was ist passiert? (1-2 Sätze)
2. Mögliche Ursachen (2-3 Optionen)
3. Empfohlene Aktion

Halte dich sehr kurz (max. 100 Wörter)."""


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class AIInterpretation:
    """Ergebnis einer KI-Interpretation"""
    success: bool
    interpretation: str
    model_used: str
    tokens_used: int
    error: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "interpretation": self.interpretation,
            "model_used": self.model_used,
            "tokens_used": self.tokens_used,
            "error": self.error
        }


# =============================================================================
# AI INTERPRETER CLASS
# =============================================================================

class AIInterpreter:
    """
    KI-gestützte Interpretation von ÖWA-Daten.
    
    Verwendet OpenAI GPT-4 für professionelle Zusammenfassungen.
    """
    
    API_URL = "https://api.openai.com/v1/chat/completions"
    DEFAULT_MODEL = "gpt-4o-mini"  # Kosteneffizient für Reports
    
    def __init__(self, api_key: str = None):
        """
        Initialisiert den AI Interpreter.
        
        Args:
            api_key: OpenAI API Key (oder aus OPENAI_API_KEY Environment)
        """
        import os
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        
        if not self.api_key:
            logger.warning("OPENAI_API_KEY nicht gesetzt - KI-Interpretation deaktiviert")
        
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        })
    
    def _call_gpt(
        self, 
        prompt: str, 
        system_prompt: str = SYSTEM_PROMPT,
        model: str = None,
        max_tokens: int = 1000
    ) -> AIInterpretation:
        """
        Ruft die OpenAI API auf.
        
        Args:
            prompt: User-Prompt
            system_prompt: System-Prompt
            model: GPT-Modell
            max_tokens: Maximale Antwort-Tokens
            
        Returns:
            AIInterpretation Objekt
        """
        if not self.api_key:
            return AIInterpretation(
                success=False,
                interpretation="",
                model_used="",
                tokens_used=0,
                error="API Key nicht konfiguriert"
            )
        
        model = model or self.DEFAULT_MODEL
        
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": max_tokens,
            "temperature": 0.7
        }
        
        try:
            response = self.session.post(
                self.API_URL,
                json=payload,
                timeout=60
            )
            
            if response.status_code == 200:
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                tokens = data.get("usage", {}).get("total_tokens", 0)
                
                logger.info(f"GPT Response: {len(content)} chars, {tokens} tokens")
                
                return AIInterpretation(
                    success=True,
                    interpretation=content,
                    model_used=model,
                    tokens_used=tokens
                )
            else:
                error_msg = f"API Fehler: {response.status_code} - {response.text[:200]}"
                logger.error(error_msg)
                return AIInterpretation(
                    success=False,
                    interpretation="",
                    model_used=model,
                    tokens_used=0,
                    error=error_msg
                )
                
        except requests.exceptions.Timeout:
            logger.error("OpenAI API Timeout")
            return AIInterpretation(
                success=False,
                interpretation="",
                model_used=model,
                tokens_used=0,
                error="Timeout"
            )
        except Exception as e:
            logger.error(f"OpenAI API Fehler: {e}")
            return AIInterpretation(
                success=False,
                interpretation="",
                model_used=model,
                tokens_used=0,
                error=str(e)
            )
    
    def generate_weekly_summary(
        self,
        week_end: date = None
    ) -> AIInterpretation:
        """
        Generiert einen KI-interpretierten Wochenbericht.
        
        Args:
            week_end: Letzter Tag der Woche (Default: letzter Sonntag)
            
        Returns:
            AIInterpretation mit Wochenbericht
        """
        if week_end is None:
            # Finde letzten Sonntag
            today = date.today()
            week_end = today - timedelta(days=today.weekday() + 1)
        
        week_start = week_end - timedelta(days=6)
        prev_week_end = week_start - timedelta(days=1)
        prev_week_start = prev_week_end - timedelta(days=6)
        
        # Daten laden
        current_data = self._get_week_data(week_start, week_end)
        previous_data = self._get_week_data(prev_week_start, prev_week_end)
        anomalies = self._get_alerts_for_period(week_start, week_end)
        daily = self._get_daily_breakdown(week_start, week_end)
        
        # Vergleich berechnen
        comparison = self._calculate_comparison(current_data, previous_data)
        
        # Prompt erstellen
        prompt = WEEKLY_PROMPT_TEMPLATE.format(
            week_period=f"{week_start.strftime('%d.%m.%Y')} - {week_end.strftime('%d.%m.%Y')}",
            current_week_data=self._format_metrics(current_data),
            comparison_data=self._format_comparison(comparison),
            anomalies=self._format_anomalies(anomalies),
            daily_breakdown=self._format_daily(daily)
        )
        
        return self._call_gpt(prompt, max_tokens=800)
    
    def generate_monthly_summary(
        self,
        year: int = None,
        month: int = None
    ) -> AIInterpretation:
        """
        Generiert einen KI-interpretierten Monatsbericht.
        
        Args:
            year: Jahr (Default: letzter Monat)
            month: Monat (Default: letzter Monat)
            
        Returns:
            AIInterpretation mit Monatsbericht
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
        
        _, last_day = calendar.monthrange(year, month)
        month_start = date(year, month, 1)
        month_end = date(year, month, last_day)
        month_name = calendar.month_name[month]
        
        # Vormonat
        if month == 1:
            prev_year, prev_month = year - 1, 12
        else:
            prev_year, prev_month = year, month - 1
        _, prev_last = calendar.monthrange(prev_year, prev_month)
        prev_start = date(prev_year, prev_month, 1)
        prev_end = date(prev_year, prev_month, prev_last)
        
        # Daten laden
        current_data = self._get_period_totals(month_start, month_end)
        previous_data = self._get_period_totals(prev_start, prev_end)
        anomalies = self._get_alerts_for_period(month_start, month_end)
        weekly = self._get_weekly_trend(month_start, month_end)
        platforms = self._get_platform_distribution(month_start, month_end)
        
        # Vergleiche
        mom_comparison = self._calculate_comparison(current_data, previous_data)
        
        # YoY (falls Daten vorhanden)
        yoy_start = date(year - 1, month, 1)
        yoy_end = date(year - 1, month, last_day)
        yoy_data = self._get_period_totals(yoy_start, yoy_end)
        yoy_comparison = self._calculate_comparison(current_data, yoy_data) if yoy_data else "Keine Vorjahresdaten verfügbar"
        
        prompt = MONTHLY_PROMPT_TEMPLATE.format(
            month_period=f"{month_name} {year}",
            monthly_totals=self._format_metrics(current_data),
            month_comparison=self._format_comparison(mom_comparison),
            yoy_comparison=self._format_comparison(yoy_comparison) if isinstance(yoy_comparison, dict) else yoy_comparison,
            weekly_trend=self._format_weekly_trend(weekly),
            monthly_anomalies=self._format_anomalies(anomalies),
            platform_distribution=self._format_platforms(platforms)
        )
        
        return self._call_gpt(prompt, max_tokens=1200)
    
    def interpret_anomaly(self, alert: Alert) -> AIInterpretation:
        """
        Generiert eine KI-Erklärung für eine einzelne Anomalie.
        
        Args:
            alert: Alert-Objekt
            
        Returns:
            AIInterpretation mit Anomalie-Erklärung
        """
        # Kontext: Letzte 7 Tage
        context_start = alert.date - timedelta(days=7)
        context = self._get_daily_values(
            alert.brand, alert.surface, alert.metric,
            context_start, alert.date
        )
        
        prompt = ANOMALY_PROMPT_TEMPLATE.format(
            brand=alert.brand.upper(),
            surface=self._format_surface(alert.surface),
            metric=self._format_metric(alert.metric),
            date=alert.date.strftime("%d.%m.%Y"),
            actual_value=f"{alert.actual_value:,.0f}".replace(",", "."),
            median=f"{alert.baseline_median:,.0f}".replace(",", "."),
            pct_delta=f"{alert.pct_delta * 100:+.1f}",
            zscore=f"{alert.zscore:.2f}",
            severity="KRITISCH" if alert.severity == "critical" else "WARNUNG",
            recent_context=self._format_context(context)
        )
        
        return self._call_gpt(prompt, max_tokens=300)
    
    def create_executive_briefing(
        self,
        period_type: str = "weekly",
        **kwargs
    ) -> str:
        """
        Erstellt ein komplettes Executive Briefing für Teams.
        
        Args:
            period_type: "weekly" oder "monthly"
            **kwargs: Zusätzliche Parameter für den Report
            
        Returns:
            Formatierter Text für Teams-Nachricht
        """
        if period_type == "weekly":
            result = self.generate_weekly_summary(**kwargs)
        else:
            result = self.generate_monthly_summary(**kwargs)
        
        if result.success:
            return result.interpretation
        else:
            logger.error(f"Briefing-Generierung fehlgeschlagen: {result.error}")
            return f"⚠️ KI-Interpretation nicht verfügbar: {result.error}"
    
    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    
    def _get_week_data(self, start: date, end: date) -> Dict[str, int]:
        """Holt aggregierte Wochendaten"""
        from sqlalchemy import func, and_
        
        with get_session() as session:
            results = session.query(
                Measurement.metric,
                func.sum(Measurement.value_total).label("total")
            ).filter(
                and_(
                    Measurement.date >= start,
                    Measurement.date <= end
                )
            ).group_by(Measurement.metric).all()
            
            return {r.metric: r.total or 0 for r in results}
    
    def _get_period_totals(self, start: date, end: date) -> Dict[str, int]:
        """Holt aggregierte Periodendaten"""
        return self._get_week_data(start, end)
    
    def _get_alerts_for_period(self, start: date, end: date) -> List[Alert]:
        """Holt Alerts für Zeitraum"""
        from sqlalchemy import and_
        
        with get_session() as session:
            return session.query(Alert).filter(
                and_(
                    Alert.date >= start,
                    Alert.date <= end
                )
            ).order_by(Alert.date.desc()).all()
    
    def _get_daily_breakdown(self, start: date, end: date) -> List[Dict]:
        """Holt tägliche Aufschlüsselung"""
        from sqlalchemy import func, and_
        
        with get_session() as session:
            results = session.query(
                Measurement.date,
                Measurement.metric,
                func.sum(Measurement.value_total).label("total")
            ).filter(
                and_(
                    Measurement.date >= start,
                    Measurement.date <= end
                )
            ).group_by(
                Measurement.date,
                Measurement.metric
            ).order_by(Measurement.date).all()
            
            return [{"date": r.date, "metric": r.metric, "total": r.total} for r in results]
    
    def _get_weekly_trend(self, start: date, end: date) -> List[Dict]:
        """Holt wöchentlichen Trend"""
        # Gruppiere nach Kalenderwochen
        weeks = []
        current = start
        while current <= end:
            week_end = min(current + timedelta(days=6), end)
            data = self._get_week_data(current, week_end)
            weeks.append({
                "week_start": current,
                "week_end": week_end,
                "data": data
            })
            current = week_end + timedelta(days=1)
        return weeks
    
    def _get_platform_distribution(self, start: date, end: date) -> Dict[str, int]:
        """Holt Plattform-Verteilung"""
        from sqlalchemy import func, and_
        
        with get_session() as session:
            results = session.query(
                Measurement.surface,
                func.sum(Measurement.value_total).label("total")
            ).filter(
                and_(
                    Measurement.date >= start,
                    Measurement.date <= end,
                    Measurement.metric == "pageimpressions"
                )
            ).group_by(Measurement.surface).all()
            
            return {r.surface: r.total or 0 for r in results}
    
    def _get_daily_values(
        self, brand: str, surface: str, metric: str,
        start: date, end: date
    ) -> List[Dict]:
        """Holt tägliche Werte für eine spezifische Kombination"""
        from sqlalchemy import and_
        
        with get_session() as session:
            results = session.query(Measurement).filter(
                and_(
                    Measurement.brand == brand,
                    Measurement.surface == surface,
                    Measurement.metric == metric,
                    Measurement.date >= start,
                    Measurement.date <= end
                )
            ).order_by(Measurement.date).all()
            
            return [{"date": m.date, "value": m.value_total} for m in results]
    
    def _calculate_comparison(
        self, current: Dict[str, int], previous: Dict[str, int]
    ) -> Dict[str, Dict]:
        """Berechnet Vergleich zwischen zwei Perioden"""
        comparison = {}
        for metric in set(list(current.keys()) + list(previous.keys())):
            curr_val = current.get(metric, 0)
            prev_val = previous.get(metric, 0)
            
            if prev_val > 0:
                change_pct = ((curr_val - prev_val) / prev_val) * 100
            else:
                change_pct = 0
            
            comparison[metric] = {
                "current": curr_val,
                "previous": prev_val,
                "change": curr_val - prev_val,
                "change_pct": change_pct
            }
        
        return comparison
    
    # =========================================================================
    # FORMATTING HELPERS
    # =========================================================================
    
    def _format_metrics(self, data: Dict[str, int]) -> str:
        """Formatiert Metriken für Prompt"""
        lines = []
        for metric, value in data.items():
            name = self._format_metric(metric)
            formatted = f"{value:,.0f}".replace(",", ".")
            lines.append(f"- {name}: {formatted}")
        return "\n".join(lines) if lines else "Keine Daten verfügbar"
    
    def _format_comparison(self, comp: Dict[str, Dict]) -> str:
        """Formatiert Vergleich für Prompt"""
        lines = []
        for metric, data in comp.items():
            name = self._format_metric(metric)
            curr = f"{data['current']:,.0f}".replace(",", ".")
            prev = f"{data['previous']:,.0f}".replace(",", ".")
            change = data['change_pct']
            arrow = "↑" if change > 0 else "↓" if change < 0 else "→"
            lines.append(f"- {name}: {curr} ({arrow} {change:+.1f}% vs. Vorperiode)")
        return "\n".join(lines) if lines else "Kein Vergleich verfügbar"
    
    def _format_anomalies(self, alerts: List[Alert]) -> str:
        """Formatiert Anomalien für Prompt"""
        if not alerts:
            return "Keine Anomalien erkannt"
        
        lines = []
        for a in alerts[:5]:  # Max 5
            icon = "🔴" if a.severity == "critical" else "🟡"
            lines.append(
                f"{icon} {a.date.strftime('%d.%m.')}: {self._format_surface(a.surface)} "
                f"{self._format_metric(a.metric)} ({a.pct_delta*100:+.1f}%)"
            )
        
        if len(alerts) > 5:
            lines.append(f"... und {len(alerts) - 5} weitere")
        
        return "\n".join(lines)
    
    def _format_daily(self, daily: List[Dict]) -> str:
        """Formatiert Tagesaufschlüsselung"""
        lines = []
        weekdays = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
        
        for d in daily:
            if d["metric"] == "pageimpressions":
                wd = weekdays[d["date"].weekday()]
                val = f"{d['total']:,.0f}".replace(",", ".")
                lines.append(f"- {wd} ({d['date'].strftime('%d.%m.')}): {val} PI")
        
        return "\n".join(lines) if lines else "Keine Tagesaufschlüsselung"
    
    def _format_weekly_trend(self, weekly: List[Dict]) -> str:
        """Formatiert Wochentrend"""
        lines = []
        for w in weekly:
            pi = w["data"].get("pageimpressions", 0)
            lines.append(
                f"- KW{w['week_start'].isocalendar()[1]}: "
                f"{pi:,.0f} PI".replace(",", ".")
            )
        return "\n".join(lines) if lines else "Kein Trend verfügbar"
    
    def _format_platforms(self, platforms: Dict[str, int]) -> str:
        """Formatiert Plattform-Verteilung"""
        total = sum(platforms.values())
        lines = []
        for surface, value in platforms.items():
            pct = (value / total * 100) if total > 0 else 0
            lines.append(
                f"- {self._format_surface(surface)}: "
                f"{value:,.0f} ({pct:.1f}%)".replace(",", ".")
            )
        return "\n".join(lines) if lines else "Keine Verteilung"
    
    def _format_context(self, context: List[Dict]) -> str:
        """Formatiert Kontext für Anomalie"""
        lines = []
        for c in context:
            val = f"{c['value']:,.0f}".replace(",", ".")
            lines.append(f"- {c['date'].strftime('%d.%m.')}: {val}")
        return "\n".join(lines) if lines else "Kein Kontext"
    
    def _format_surface(self, surface: str) -> str:
        """Formatiert Surface-Namen"""
        mapping = {
            "web_desktop": "Web Desktop",
            "web_mobile": "Web Mobile",
            "app": "App"
        }
        return mapping.get(surface, surface)
    
    def _format_metric(self, metric: str) -> str:
        """Formatiert Metrik-Namen"""
        mapping = {
            "pageimpressions": "Page Impressions",
            "visits": "Visits",
            "clients": "Clients"
        }
        return mapping.get(metric, metric)
    
    def close(self):
        """Schließt die Session"""
        self.session.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

