"""
ÖWA Reporting - Visualisierung
==============================

Multi-Plattform Visualisierungslösung:
1. Streamlit Dashboard (interaktiv)
2. HTML Report Generator (statisch/offline)
3. Terminal Quick View (CLI)

Nutzung:
    # Streamlit Dashboard
    python -m oewa_reporting dashboard
    
    # HTML Report generieren
    python -m oewa_reporting report-html --date 2025-11-25
    
    # Terminal Quick View
    python -m oewa_reporting quick-view --date 2025-11-25
"""

import os
import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


# ============================================================================
# DATEN-LAYER
# ============================================================================

@dataclass
class DashboardData:
    """Container für Dashboard-Daten"""
    measurements: pd.DataFrame
    alerts: pd.DataFrame
    start_date: date
    end_date: date
    brands: List[str]
    surfaces: List[str]
    metrics: List[str]
    
    @property
    def has_data(self) -> bool:
        return not self.measurements.empty
    
    @property
    def latest_date(self) -> Optional[date]:
        if self.has_data:
            return self.measurements['date'].max().date()
        return None
    
    def get_metric_data(self, metric: str) -> pd.DataFrame:
        """Filtert nach Metrik"""
        return self.measurements[self.measurements['metric'] == metric].copy()
    
    def get_daily_totals(self, metric: str) -> pd.DataFrame:
        """Aggregiert zu Tagessummen"""
        metric_df = self.get_metric_data(metric)
        return metric_df.groupby('date')['value_total'].sum().reset_index()
    
    def get_surface_totals(self, metric: str) -> pd.DataFrame:
        """Aggregiert nach Surface"""
        metric_df = self.get_metric_data(metric)
        return metric_df.groupby('surface')['value_total'].sum().reset_index()


class DataLoader:
    """Lädt Daten aus verschiedenen Quellen"""
    
    def __init__(self, db_url: str = None):
        self.db_url = db_url or os.getenv(
            "DATABASE_URL",
            "sqlite:///oewa_test.db"
        )
        self._engine = None
    
    @property
    def engine(self):
        if self._engine is None:
            from sqlalchemy import create_engine
            self._engine = create_engine(self.db_url)
        return self._engine
    
    def load_data(
        self,
        start_date: date,
        end_date: date,
        brands: List[str] = None,
        surfaces: List[str] = None,
        metrics: List[str] = None
    ) -> DashboardData:
        """Lädt alle Dashboard-Daten"""
        
        # Measurements laden
        measurements = self._load_measurements(
            start_date, end_date, brands, surfaces, metrics
        )
        
        # Alerts laden
        alerts = self._load_alerts(start_date, end_date)
        
        # Verfügbare Dimensionen extrahieren
        available_brands = measurements['brand'].unique().tolist() if not measurements.empty else []
        available_surfaces = measurements['surface'].unique().tolist() if not measurements.empty else []
        available_metrics = measurements['metric'].unique().tolist() if not measurements.empty else []
        
        return DashboardData(
            measurements=measurements,
            alerts=alerts,
            start_date=start_date,
            end_date=end_date,
            brands=available_brands,
            surfaces=available_surfaces,
            metrics=available_metrics
        )
    
    def _load_measurements(
        self,
        start_date: date,
        end_date: date,
        brands: List[str] = None,
        surfaces: List[str] = None,
        metrics: List[str] = None
    ) -> pd.DataFrame:
        """Lädt Messdaten"""
        query = """
            SELECT 
                date, brand, surface, metric, site_id,
                value_total, value_national, value_international,
                value_iomp, value_iomb, preliminary,
                exported_at, ingested_at
            FROM measurements
            WHERE date >= :start_date AND date <= :end_date
        """
        
        params = {"start_date": start_date, "end_date": end_date}
        
        try:
            df = pd.read_sql(query, self.engine, params=params)
            
            if not df.empty:
                df['date'] = pd.to_datetime(df['date'])
                
                # Filter anwenden
                if brands:
                    df = df[df['brand'].isin(brands)]
                if surfaces:
                    df = df[df['surface'].isin(surfaces)]
                if metrics:
                    df = df[df['metric'].isin(metrics)]
            
            return df
            
        except Exception as e:
            logger.error(f"Fehler beim Laden der Measurements: {e}")
            return pd.DataFrame()
    
    def _load_alerts(
        self,
        start_date: date,
        end_date: date
    ) -> pd.DataFrame:
        """Lädt Alerts"""
        query = """
            SELECT * FROM alerts
            WHERE date >= :start_date AND date <= :end_date
            ORDER BY created_at DESC
        """
        
        try:
            df = pd.read_sql(
                query, 
                self.engine, 
                params={"start_date": start_date, "end_date": end_date}
            )
            
            if not df.empty and 'date' in df.columns:
                df['date'] = pd.to_datetime(df['date'])
            
            return df
            
        except Exception as e:
            logger.error(f"Fehler beim Laden der Alerts: {e}")
            return pd.DataFrame()


# ============================================================================
# HTML REPORT GENERATOR
# ============================================================================

class HTMLReportGenerator:
    """
    Generiert statische HTML-Reports mit Plotly.
    
    Vorteile:
    - Kein Server erforderlich
    - Kann per Email/Teams geteilt werden
    - Offline nutzbar
    - Interaktive Charts bleiben erhalten
    """
    
    # Farbschema
    COLORS = {
        'primary': '#0078D7',
        'success': '#28A745',
        'warning': '#FFC107',
        'danger': '#DC3545',
        'vol': '#E63946',
        'vienna': '#457B9D',
        'web_desktop': '#2A9D8F',
        'web_mobile': '#E9C46A',
        'app': '#F4A261',
    }
    
    def __init__(self, data: DashboardData):
        self.data = data
        self._ensure_plotly()
    
    def _ensure_plotly(self):
        """Stellt sicher dass Plotly verfügbar ist"""
        try:
            import plotly.graph_objects as go
            import plotly.express as px
            from plotly.subplots import make_subplots
            self.go = go
            self.px = px
            self.make_subplots = make_subplots
        except ImportError:
            raise ImportError(
                "Plotly ist erforderlich. Installieren mit: pip install plotly"
            )
    
    def generate_report(
        self,
        output_path: str = None,
        metric: str = "pageimpressions",
        title: str = None
    ) -> str:
        """
        Generiert einen vollständigen HTML-Report.
        
        Returns:
            Pfad zur generierten HTML-Datei
        """
        if not self.data.has_data:
            raise ValueError("Keine Daten für Report verfügbar")
        
        if output_path is None:
            output_path = f"oewa_report_{self.data.start_date}_{self.data.end_date}.html"
        
        if title is None:
            title = f"ÖWA Report: {self.data.start_date} - {self.data.end_date}"
        
        # Charts erstellen
        time_series_fig = self._create_time_series(metric)
        comparison_fig = self._create_comparison_chart(metric)
        trend_fig = self._create_trend_chart(metric)
        
        # KPIs berechnen
        kpis = self._calculate_kpis(metric)
        
        # HTML zusammenbauen
        html_content = self._build_html(
            title=title,
            kpis=kpis,
            time_series_fig=time_series_fig,
            comparison_fig=comparison_fig,
            trend_fig=trend_fig,
            metric=metric
        )
        
        # Speichern
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        logger.info(f"Report generiert: {output_path}")
        return output_path
    
    def _create_time_series(self, metric: str):
        """Erstellt Zeitreihen-Chart"""
        metric_df = self.data.get_metric_data(metric)
        
        if metric_df.empty:
            return self.go.Figure()
        
        agg_df = metric_df.groupby(['date', 'surface'])['value_total'].sum().reset_index()
        
        fig = self.px.line(
            agg_df,
            x='date',
            y='value_total',
            color='surface',
            color_discrete_map={
                'web_desktop': self.COLORS['web_desktop'],
                'web_mobile': self.COLORS['web_mobile'],
                'app': self.COLORS['app']
            },
            title=f'{metric.title()} nach Plattform'
        )
        
        fig.update_layout(
            hovermode='x unified',
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
            xaxis_title="",
            yaxis_title=metric.title()
        )
        
        return fig
    
    def _create_comparison_chart(self, metric: str):
        """Erstellt Vergleichs-Balkendiagramm"""
        surface_totals = self.data.get_surface_totals(metric)
        
        if surface_totals.empty:
            return self.go.Figure()
        
        fig = self.px.bar(
            surface_totals,
            x='surface',
            y='value_total',
            color='surface',
            color_discrete_map={
                'web_desktop': self.COLORS['web_desktop'],
                'web_mobile': self.COLORS['web_mobile'],
                'app': self.COLORS['app']
            },
            title=f'{metric.title()} Gesamt nach Plattform'
        )
        
        fig.update_layout(showlegend=False)
        
        return fig
    
    def _create_trend_chart(self, metric: str):
        """Erstellt Trend-Chart mit gleitendem Durchschnitt"""
        daily_totals = self.data.get_daily_totals(metric)
        
        if daily_totals.empty:
            return self.go.Figure()
        
        daily_totals['ma_7'] = daily_totals['value_total'].rolling(
            window=7, min_periods=1
        ).mean()
        
        fig = self.go.Figure()
        
        fig.add_trace(self.go.Scatter(
            x=daily_totals['date'],
            y=daily_totals['value_total'],
            mode='markers',
            name='Tageswerte',
            marker=dict(size=6, opacity=0.5)
        ))
        
        fig.add_trace(self.go.Scatter(
            x=daily_totals['date'],
            y=daily_totals['ma_7'],
            mode='lines',
            name='7-Tage Durchschnitt',
            line=dict(width=2, color=self.COLORS['primary'])
        ))
        
        fig.update_layout(
            title='Trend-Analyse',
            hovermode='x unified',
            xaxis_title="",
            yaxis_title=metric.title()
        )
        
        return fig
    
    def _calculate_kpis(self, metric: str) -> Dict[str, Any]:
        """Berechnet KPIs für den Report"""
        metric_df = self.data.get_metric_data(metric)
        
        if metric_df.empty:
            return {}
        
        latest_date = metric_df['date'].max()
        prev_date = latest_date - timedelta(days=1)
        
        latest = metric_df[metric_df['date'] == latest_date]
        previous = metric_df[metric_df['date'] == prev_date]
        
        def calc_change(current, prev):
            if prev == 0:
                return 0
            return ((current - prev) / prev) * 100
        
        # Web Gesamt
        web_current = latest[latest['surface'].isin(['web_desktop', 'web_mobile'])]['value_total'].sum()
        web_prev = previous[previous['surface'].isin(['web_desktop', 'web_mobile'])]['value_total'].sum()
        
        # App
        app_current = latest[latest['surface'] == 'app']['value_total'].sum()
        app_prev = previous[previous['surface'] == 'app']['value_total'].sum()
        
        return {
            'total': web_current + app_current,
            'total_change': calc_change(web_current + app_current, web_prev + app_prev),
            'web': web_current,
            'web_change': calc_change(web_current, web_prev),
            'app': app_current,
            'app_change': calc_change(app_current, app_prev),
            'latest_date': latest_date.strftime('%d.%m.%Y'),
            'period_days': (self.data.end_date - self.data.start_date).days + 1
        }
    
    def _build_html(
        self,
        title: str,
        kpis: Dict,
        time_series_fig,
        comparison_fig,
        trend_fig,
        metric: str
    ) -> str:
        """Baut das vollständige HTML-Dokument"""
        
        # Plotly Charts zu HTML konvertieren
        time_series_html = time_series_fig.to_html(
            full_html=False, include_plotlyjs=False
        )
        comparison_html = comparison_fig.to_html(
            full_html=False, include_plotlyjs=False
        )
        trend_html = trend_fig.to_html(
            full_html=False, include_plotlyjs=False
        )
        
        # Alerts verarbeiten
        alerts_html = self._generate_alerts_html()
        
        # Daten-Tabelle
        data_table_html = self._generate_data_table_html(metric)
        
        return f"""
<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 2rem;
        }}
        
        .container {{
            max-width: 1400px;
            margin: 0 auto;
        }}
        
        .header {{
            background: white;
            border-radius: 1rem;
            padding: 2rem;
            margin-bottom: 2rem;
            box-shadow: 0 10px 40px rgba(0,0,0,0.1);
        }}
        
        .header h1 {{
            color: #1a1a2e;
            font-size: 2rem;
            margin-bottom: 0.5rem;
        }}
        
        .header .subtitle {{
            color: #666;
            font-size: 1rem;
        }}
        
        .header .meta {{
            margin-top: 1rem;
            color: #888;
            font-size: 0.875rem;
        }}
        
        .kpi-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1.5rem;
            margin-bottom: 2rem;
        }}
        
        .kpi-card {{
            background: white;
            border-radius: 1rem;
            padding: 1.5rem;
            box-shadow: 0 10px 40px rgba(0,0,0,0.1);
        }}
        
        .kpi-card .label {{
            color: #666;
            font-size: 0.875rem;
            margin-bottom: 0.5rem;
        }}
        
        .kpi-card .value {{
            font-size: 2rem;
            font-weight: 700;
            color: #1a1a2e;
        }}
        
        .kpi-card .change {{
            font-size: 0.875rem;
            margin-top: 0.25rem;
        }}
        
        .kpi-card .change.positive {{
            color: #28A745;
        }}
        
        .kpi-card .change.negative {{
            color: #DC3545;
        }}
        
        .chart-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(500px, 1fr));
            gap: 2rem;
            margin-bottom: 2rem;
        }}
        
        .chart-card {{
            background: white;
            border-radius: 1rem;
            padding: 1.5rem;
            box-shadow: 0 10px 40px rgba(0,0,0,0.1);
        }}
        
        .chart-card h3 {{
            color: #1a1a2e;
            margin-bottom: 1rem;
            font-size: 1.125rem;
        }}
        
        .alerts-section {{
            background: white;
            border-radius: 1rem;
            padding: 1.5rem;
            margin-bottom: 2rem;
            box-shadow: 0 10px 40px rgba(0,0,0,0.1);
        }}
        
        .alerts-section h3 {{
            color: #1a1a2e;
            margin-bottom: 1rem;
        }}
        
        .alert {{
            padding: 1rem;
            border-radius: 0.5rem;
            margin-bottom: 0.75rem;
        }}
        
        .alert.critical {{
            background: #fee2e2;
            border-left: 4px solid #DC3545;
        }}
        
        .alert.warning {{
            background: #fef3c7;
            border-left: 4px solid #FFC107;
        }}
        
        .alert.success {{
            background: #d1fae5;
            border-left: 4px solid #28A745;
        }}
        
        .data-table {{
            background: white;
            border-radius: 1rem;
            padding: 1.5rem;
            box-shadow: 0 10px 40px rgba(0,0,0,0.1);
            overflow-x: auto;
        }}
        
        .data-table h3 {{
            color: #1a1a2e;
            margin-bottom: 1rem;
        }}
        
        table {{
            width: 100%;
            border-collapse: collapse;
        }}
        
        th, td {{
            padding: 0.75rem;
            text-align: left;
            border-bottom: 1px solid #eee;
        }}
        
        th {{
            background: #f8f9fa;
            font-weight: 600;
            color: #1a1a2e;
        }}
        
        tr:hover {{
            background: #f8f9fa;
        }}
        
        .footer {{
            text-align: center;
            color: rgba(255,255,255,0.7);
            margin-top: 2rem;
            font-size: 0.875rem;
        }}
        
        @media (max-width: 768px) {{
            .chart-grid {{
                grid-template-columns: 1fr;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <div class="header">
            <h1>📊 {title}</h1>
            <p class="subtitle">ÖWA/INFOnline Reporting Dashboard</p>
            <p class="meta">
                Zeitraum: {self.data.start_date.strftime('%d.%m.%Y')} - {self.data.end_date.strftime('%d.%m.%Y')} 
                ({kpis.get('period_days', 0)} Tage) | 
                Metrik: {metric.title()} |
                Generiert: {datetime.now().strftime('%d.%m.%Y %H:%M')}
            </p>
        </div>
        
        <!-- KPIs -->
        <div class="kpi-grid">
            <div class="kpi-card">
                <div class="label">📊 Total {metric.title()}</div>
                <div class="value">{self._format_number(kpis.get('total', 0))}</div>
                <div class="change {'positive' if kpis.get('total_change', 0) >= 0 else 'negative'}">
                    {'+' if kpis.get('total_change', 0) >= 0 else ''}{kpis.get('total_change', 0):.1f}% vs. Vortag
                </div>
            </div>
            <div class="kpi-card">
                <div class="label">🌐 Web Gesamt</div>
                <div class="value">{self._format_number(kpis.get('web', 0))}</div>
                <div class="change {'positive' if kpis.get('web_change', 0) >= 0 else 'negative'}">
                    {'+' if kpis.get('web_change', 0) >= 0 else ''}{kpis.get('web_change', 0):.1f}% vs. Vortag
                </div>
            </div>
            <div class="kpi-card">
                <div class="label">📱 App</div>
                <div class="value">{self._format_number(kpis.get('app', 0))}</div>
                <div class="change {'positive' if kpis.get('app_change', 0) >= 0 else 'negative'}">
                    {'+' if kpis.get('app_change', 0) >= 0 else ''}{kpis.get('app_change', 0):.1f}% vs. Vortag
                </div>
            </div>
            <div class="kpi-card">
                <div class="label">📅 Letzter Datenpunkt</div>
                <div class="value" style="font-size: 1.5rem;">{kpis.get('latest_date', 'N/A')}</div>
            </div>
        </div>
        
        <!-- Charts -->
        <div class="chart-grid">
            <div class="chart-card">
                <h3>📈 Zeitverlauf</h3>
                {time_series_html}
            </div>
            <div class="chart-card">
                <h3>📊 Vergleich nach Plattform</h3>
                {comparison_html}
            </div>
        </div>
        
        <div class="chart-card" style="margin-bottom: 2rem;">
            <h3>📉 Trend-Analyse</h3>
            {trend_html}
        </div>
        
        <!-- Alerts -->
        <div class="alerts-section">
            <h3>⚠️ Anomalien & Alerts</h3>
            {alerts_html}
        </div>
        
        <!-- Data Table -->
        <div class="data-table">
            <h3>📋 Datenübersicht (letzte 7 Tage)</h3>
            {data_table_html}
        </div>
        
        <!-- Footer -->
        <div class="footer">
            <p>ÖWA Reporting System v1.0 | Generiert am {datetime.now().strftime('%d.%m.%Y um %H:%M Uhr')}</p>
        </div>
    </div>
</body>
</html>
"""
    
    def _format_number(self, value: float) -> str:
        """Formatiert Zahlen für Anzeige"""
        if value >= 1_000_000:
            return f"{value/1_000_000:.2f}M"
        elif value >= 1_000:
            return f"{value/1_000:.1f}K"
        else:
            return f"{value:.0f}"
    
    def _generate_alerts_html(self) -> str:
        """Generiert HTML für Alerts"""
        if self.data.alerts.empty:
            return '<div class="alert success">✅ Keine Anomalien im Berichtszeitraum erkannt.</div>'
        
        html_parts = []
        
        for _, alert in self.data.alerts.iterrows():
            severity_class = "critical" if alert['severity'] == 'critical' else "warning"
            icon = "🔴" if alert['severity'] == 'critical' else "🟡"
            
            html_parts.append(f"""
            <div class="alert {severity_class}">
                <strong>{icon} {alert['brand'].upper()} - {alert['surface']} - {alert['metric']}</strong><br>
                <small>
                    Datum: {alert['date'].strftime('%d.%m.%Y') if hasattr(alert['date'], 'strftime') else alert['date']} | 
                    Z-Score: {alert['zscore']:.2f} | 
                    Abweichung: {alert['pct_delta']*100:.1f}%<br>
                    Aktuell: {alert['actual_value']:,.0f} | Median: {alert['baseline_median']:,.0f}
                </small>
            </div>
            """)
        
        return '\n'.join(html_parts)
    
    def _generate_data_table_html(self, metric: str) -> str:
        """Generiert HTML für Datentabelle"""
        metric_df = self.data.get_metric_data(metric)
        
        if metric_df.empty:
            return '<p>Keine Daten verfügbar.</p>'
        
        # Letzte 7 Tage
        latest_date = metric_df['date'].max()
        week_ago = latest_date - timedelta(days=7)
        recent = metric_df[metric_df['date'] >= week_ago].copy()
        
        # Aggregiere nach Datum und Surface
        pivot = recent.pivot_table(
            index='date',
            columns='surface',
            values='value_total',
            aggfunc='sum'
        ).reset_index()
        
        pivot = pivot.sort_values('date', ascending=False)
        
        # HTML Tabelle
        html = '<table><thead><tr><th>Datum</th>'
        
        for col in pivot.columns[1:]:
            html += f'<th>{col.replace("_", " ").title()}</th>'
        
        html += '</tr></thead><tbody>'
        
        for _, row in pivot.iterrows():
            html += f'<tr><td>{row["date"].strftime("%d.%m.%Y")}</td>'
            for col in pivot.columns[1:]:
                val = row[col]
                html += f'<td>{val:,.0f}</td>' if pd.notna(val) else '<td>-</td>'
            html += '</tr>'
        
        html += '</tbody></table>'
        
        return html


# ============================================================================
# TERMINAL QUICK VIEW
# ============================================================================

class TerminalQuickView:
    """
    Einfache Terminal-basierte Visualisierung.
    Nutzt ASCII-Zeichen für schnelle Übersicht ohne GUI.
    """
    
    def __init__(self, data: DashboardData):
        self.data = data
    
    def show(self, metric: str = "pageimpressions"):
        """Zeigt Quick View im Terminal"""
        if not self.data.has_data:
            print("❌ Keine Daten verfügbar")
            return
        
        self._print_header()
        self._print_kpis(metric)
        self._print_bar_chart(metric)
        self._print_alerts()
    
    def _print_header(self):
        """Druckt Header"""
        print("\n" + "=" * 60)
        print("  📊 ÖWA Quick View")
        print(f"  Zeitraum: {self.data.start_date} - {self.data.end_date}")
        print("=" * 60)
    
    def _print_kpis(self, metric: str):
        """Druckt KPIs"""
        metric_df = self.data.get_metric_data(metric)
        
        if metric_df.empty:
            return
        
        latest = metric_df[metric_df['date'] == metric_df['date'].max()]
        
        web_total = latest[latest['surface'].isin(['web_desktop', 'web_mobile'])]['value_total'].sum()
        app_total = latest[latest['surface'] == 'app']['value_total'].sum()
        
        print(f"\n  📊 {metric.title()} ({self.data.latest_date})")
        print(f"  ├─ 🌐 Web:  {web_total:>12,.0f}")
        print(f"  ├─ 📱 App:  {app_total:>12,.0f}")
        print(f"  └─ 📈 Total: {web_total + app_total:>11,.0f}")
    
    def _print_bar_chart(self, metric: str):
        """Druckt einfaches ASCII-Balkendiagramm"""
        surface_totals = self.data.get_surface_totals(metric)
        
        if surface_totals.empty:
            return
        
        max_val = surface_totals['value_total'].max()
        
        print(f"\n  📊 Verteilung nach Plattform:")
        print("  " + "-" * 50)
        
        for _, row in surface_totals.iterrows():
            bar_length = int((row['value_total'] / max_val) * 30)
            bar = "█" * bar_length
            pct = (row['value_total'] / surface_totals['value_total'].sum()) * 100
            
            print(f"  {row['surface']:15} {bar:30} {pct:5.1f}%")
    
    def _print_alerts(self):
        """Druckt Alerts"""
        print(f"\n  ⚠️ Anomalien:")
        print("  " + "-" * 50)
        
        if self.data.alerts.empty:
            print("  ✅ Keine Anomalien erkannt")
            return
        
        for _, alert in self.data.alerts.head(5).iterrows():
            icon = "🔴" if alert['severity'] == 'critical' else "🟡"
            print(f"  {icon} {alert['brand'].upper()} {alert['surface']} "
                  f"| {alert['pct_delta']*100:+.1f}% | z={alert['zscore']:.2f}")


# ============================================================================
# FACTORY FUNKTIONEN
# ============================================================================

def create_html_report(
    start_date: date,
    end_date: date,
    output_path: str = None,
    metric: str = "pageimpressions",
    db_url: str = None
) -> str:
    """
    Erstellt einen HTML-Report.
    
    Beispiel:
        create_html_report(
            start_date=date(2025, 11, 1),
            end_date=date(2025, 11, 30),
            output_path="november_report.html"
        )
    """
    loader = DataLoader(db_url)
    data = loader.load_data(start_date, end_date)
    
    generator = HTMLReportGenerator(data)
    return generator.generate_report(output_path, metric)


def show_terminal_view(
    start_date: date,
    end_date: date,
    metric: str = "pageimpressions",
    db_url: str = None
):
    """
    Zeigt Quick View im Terminal.
    
    Beispiel:
        show_terminal_view(
            start_date=date(2025, 11, 1),
            end_date=date(2025, 11, 30)
        )
    """
    loader = DataLoader(db_url)
    data = loader.load_data(start_date, end_date)
    
    view = TerminalQuickView(data)
    view.show(metric)

