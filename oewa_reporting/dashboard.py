"""
ÖWA Reporting Dashboard - Streamlit Interface
==============================================

Professionelles Dashboard für die Datenanalyse mit:
- Interaktive Datentabellen
- Präzise Datenvisualisierung
- Hochwertige UX
- Datenvalidierung

Start: streamlit run oewa_reporting/dashboard.py
"""

import streamlit as st
import pandas as pd
import numpy as np
from datetime import date, datetime, timedelta
from pathlib import Path
import sys
import os

# Projekt-Pfad hinzufügen
sys.path.insert(0, str(Path(__file__).parent.parent))

# Environment Variables setzen falls nicht vorhanden
if "DATABASE_URL" not in os.environ:
    os.environ["DATABASE_URL"] = "sqlite:///oewa_fulltest.db"

from oewa_reporting.db import get_session
from oewa_reporting.models import Measurement, Alert
from oewa_reporting.config import get_config
from sqlalchemy import func, and_, desc

# =============================================================================
# PAGE CONFIG
# =============================================================================
st.set_page_config(
    page_title="ÖWA Reporting Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =============================================================================
# CUSTOM CSS für professionelle UX
# =============================================================================
st.markdown("""
<style>
    /* Hauptfarben */
    :root {
        --primary: #1E3A5F;
        --secondary: #3498DB;
        --success: #27AE60;
        --warning: #F39C12;
        --danger: #E74C3C;
        --light: #F8F9FA;
        --dark: #2C3E50;
    }
    
    /* Header Styling */
    .main-header {
        background: linear-gradient(135deg, #1E3A5F 0%, #2C5282 100%);
        padding: 1.5rem 2rem;
        border-radius: 12px;
        margin-bottom: 2rem;
        color: white;
    }
    
    .main-header h1 {
        margin: 0;
        font-size: 2rem;
        font-weight: 700;
    }
    
    .main-header p {
        margin: 0.5rem 0 0 0;
        opacity: 0.85;
        font-size: 1rem;
    }
    
    /* KPI Cards */
    .kpi-card {
        background: white;
        border-radius: 12px;
        padding: 1.5rem;
        box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        border-left: 4px solid #3498DB;
        height: 100%;
    }
    
    .kpi-card.success { border-left-color: #27AE60; }
    .kpi-card.warning { border-left-color: #F39C12; }
    .kpi-card.danger { border-left-color: #E74C3C; }
    
    .kpi-label {
        font-size: 0.85rem;
        color: #666;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-bottom: 0.5rem;
    }
    
    .kpi-value {
        font-size: 2rem;
        font-weight: 700;
        color: #1E3A5F;
        line-height: 1.2;
    }
    
    .kpi-delta {
        font-size: 0.9rem;
        margin-top: 0.5rem;
    }
    
    .kpi-delta.positive { color: #27AE60; }
    .kpi-delta.negative { color: #E74C3C; }
    
    /* Data Table Styling */
    .dataframe {
        font-size: 0.9rem !important;
    }
    
    .dataframe th {
        background-color: #1E3A5F !important;
        color: white !important;
        font-weight: 600 !important;
        text-transform: uppercase;
        font-size: 0.8rem;
        letter-spacing: 0.5px;
    }
    
    /* Section Headers */
    .section-header {
        border-bottom: 2px solid #1E3A5F;
        padding-bottom: 0.5rem;
        margin: 2rem 0 1rem 0;
        color: #1E3A5F;
        font-weight: 600;
    }
    
    /* Info Box */
    .info-box {
        background: #E8F4FD;
        border-radius: 8px;
        padding: 1rem;
        margin: 1rem 0;
        border-left: 4px solid #3498DB;
    }
    
    /* Sidebar Styling */
    .css-1d391kg {
        background: #F8F9FA;
    }
    
    /* Footer */
    .footer {
        text-align: center;
        padding: 2rem;
        color: #666;
        font-size: 0.85rem;
        border-top: 1px solid #eee;
        margin-top: 3rem;
    }
    
    /* Hide Streamlit branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)


# =============================================================================
# DATA LOADING FUNCTIONS (Optimiert für Performance)
# =============================================================================

# Maximale Anzahl Datensätze für schnelles Laden
MAX_RECORDS_DEFAULT = 10000
PAGE_SIZE = 100


@st.cache_data(ttl=60, show_spinner=False)
def load_measurements(
    start_date: date, 
    end_date: date,
    max_records: int = MAX_RECORDS_DEFAULT
) -> pd.DataFrame:
    """
    Lädt Messdaten aus der Datenbank mit Validierung.
    
    Optimiert für:
    - Memory: Begrenzte Datensätze
    - Performance: Nur benötigte Spalten
    """
    try:
        with get_session() as session:
            # Zähle zuerst die Gesamtanzahl
            total_count = session.query(func.count(Measurement.id)).filter(
                and_(
                    Measurement.date >= start_date,
                    Measurement.date <= end_date
                )
            ).scalar()
            
            # Query mit Limit für Performance
            query = session.query(Measurement).filter(
                and_(
                    Measurement.date >= start_date,
                    Measurement.date <= end_date
                )
            ).order_by(
                Measurement.date.desc(), 
                Measurement.brand, 
                Measurement.surface, 
                Measurement.metric
            )
            
            # Limit anwenden wenn nötig
            if total_count > max_records:
                st.info(f"📊 {total_count:,} Datensätze gefunden. Zeige die neuesten {max_records:,}.")
                query = query.limit(max_records)
            
            # Effizientes Laden - verwende yield_per für Memory-Optimierung
            data = []
            for m in query.yield_per(500):
                # Sichere Formatierung von ingested_at
                try:
                    erfasst = m.ingested_at.strftime("%Y-%m-%d %H:%M") if m.ingested_at else "-"
                except (AttributeError, ValueError):
                    erfasst = "-"
                
                data.append({
                    "id": m.id,
                    "Datum": m.date,
                    "Brand": m.brand.upper() if m.brand else "",
                    "Plattform": format_surface(m.surface),
                    "Metrik": format_metric(m.metric),
                    "Wert": m.value_total or 0,
                    "Site ID": m.site_id or "",
                    "Vorläufig": "Ja" if m.preliminary else "Nein",
                    "Erfasst": erfasst,
                    "_surface": m.surface,
                    "_metric": m.metric,
                    "_brand": m.brand,
                })
            
            df = pd.DataFrame(data)
            
            # Datenvalidierung (nur wenn Daten vorhanden)
            if not df.empty and len(df) < 5000:  # Nur bei kleinen Mengen
                duplicates = df.duplicated(subset=["Datum", "Brand", "_surface", "_metric"], keep=False)
                if duplicates.any():
                    st.warning(f"⚠️ {duplicates.sum()} potenzielle Duplikate gefunden")
            
            return df
            
    except Exception as e:
        st.error(f"Fehler beim Laden der Daten: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=60, show_spinner=False)
def load_alerts(start_date: date, end_date: date) -> pd.DataFrame:
    """Lädt Anomalie-Alerts aus der Datenbank"""
    try:
        with get_session() as session:
            query = session.query(Alert).filter(
                and_(
                    Alert.date >= start_date,
                    Alert.date <= end_date
                )
            ).order_by(Alert.date.desc())
            
            data = []
            for a in query.all():
                # Sichere Wert-Extraktion
                zscore = round(a.zscore, 2) if a.zscore is not None else None
                pct_delta = a.pct_delta if a.pct_delta is not None else 0
                baseline_median = a.baseline_median if a.baseline_median is not None else 0
                actual_value = a.actual_value if a.actual_value is not None else 0  # FIXED: war a.actual
                
                data.append({
                    "id": a.id,
                    "Datum": a.date,
                    "Brand": a.brand.upper() if a.brand else "",
                    "Plattform": format_surface(a.surface),
                    "Metrik": format_metric(a.metric),
                    "Schwere": "🔴 Kritisch" if a.severity == "critical" else "🟡 Warnung",
                    "Z-Score": zscore,
                    "Abweichung %": f"{pct_delta*100:+.1f}%",
                    "Median": f"{baseline_median:,.0f}".replace(",", "."),
                    "Aktuell": f"{actual_value:,.0f}".replace(",", "."),
                    "Meldung": a.message or "",
                    "_severity": a.severity,
                })
            
            return pd.DataFrame(data)
            
    except Exception as e:
        st.error(f"Fehler beim Laden der Alerts: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=60, show_spinner=False)
def load_aggregated_data(start_date: date, end_date: date) -> pd.DataFrame:
    """
    Lädt aggregierte Daten für Übersicht.
    
    Optimiert: Verwendet SQL-Aggregation statt Python.
    """
    try:
        with get_session() as session:
            # Aggregation per Tag und Metrik
            query = session.query(
                Measurement.date,
                Measurement.metric,
                Measurement.surface,
                func.sum(Measurement.value_total).label("total")
            ).filter(
                and_(
                    Measurement.date >= start_date,
                    Measurement.date <= end_date
                )
            ).group_by(
                Measurement.date,
                Measurement.metric,
                Measurement.surface
            ).order_by(Measurement.date)
            
            data = []
            for row in query.all():
                data.append({
                    "Datum": row.date,
                    "Metrik": row.metric,
                    "Plattform": row.surface,
                    "Wert": row.total or 0
                })
            
            return pd.DataFrame(data)
            
    except Exception as e:
        st.error(f"Fehler beim Laden aggregierter Daten: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=300, show_spinner=False)
def get_date_range_info() -> dict:
    """
    Holt Info über verfügbaren Datumsbereich.
    Cache für 5 Minuten.
    """
    try:
        with get_session() as session:
            min_date = session.query(func.min(Measurement.date)).scalar()
            max_date = session.query(func.max(Measurement.date)).scalar()
            total_count = session.query(func.count(Measurement.id)).scalar()
            
            return {
                "min_date": min_date,
                "max_date": max_date,
                "total_count": total_count or 0
            }
    except Exception:
        return {"min_date": None, "max_date": None, "total_count": 0}


def get_summary_stats(df: pd.DataFrame, metric: str) -> dict:
    """Berechnet Zusammenfassungsstatistiken für eine Metrik"""
    if df.empty:
        return {"total": 0, "avg": 0, "min": 0, "max": 0, "count": 0}
    
    metric_df = df[df["_metric"] == metric]
    
    if metric_df.empty:
        return {"total": 0, "avg": 0, "min": 0, "max": 0, "count": 0}
    
    return {
        "total": int(metric_df["Wert"].sum()),
        "avg": int(metric_df["Wert"].mean()),
        "min": int(metric_df["Wert"].min()),
        "max": int(metric_df["Wert"].max()),
        "count": len(metric_df)
    }


def calculate_trend(df: pd.DataFrame, metric: str, days: int = 7) -> float:
    """Berechnet Trend (Änderung in %) gegenüber Vorperiode"""
    if df.empty:
        return 0.0
    
    metric_df = df[df["_metric"] == metric].copy()
    if metric_df.empty:
        return 0.0
    
    # Sortiere nach Datum
    metric_df = metric_df.sort_values("Datum")
    dates = metric_df["Datum"].unique()
    
    if len(dates) < days * 2:
        return 0.0
    
    # Letzte X Tage vs. vorherige X Tage
    recent_dates = dates[-days:]
    previous_dates = dates[-days*2:-days]
    
    recent_sum = metric_df[metric_df["Datum"].isin(recent_dates)]["Wert"].sum()
    previous_sum = metric_df[metric_df["Datum"].isin(previous_dates)]["Wert"].sum()
    
    if previous_sum == 0:
        return 0.0
    
    return ((recent_sum - previous_sum) / previous_sum) * 100


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def format_surface(surface: str) -> str:
    """Formatiert Surface-Namen für Anzeige"""
    mapping = {
        "web_desktop": "🖥️ Web Desktop",
        "web_mobile": "📱 Web Mobile",
        "app": "📲 App"
    }
    return mapping.get(surface, surface)


def format_metric(metric: str) -> str:
    """Formatiert Metrik-Namen für Anzeige"""
    mapping = {
        "pageimpressions": "Page Impressions",
        "visits": "Visits",
        "clients": "Clients",
        "qualifiedclients": "Qualified Clients"
    }
    return mapping.get(metric, metric)


def format_number(value: int) -> str:
    """Formatiert Zahlen mit Tausendertrennzeichen (deutsch)"""
    return f"{value:,.0f}".replace(",", ".")


def render_kpi_card(label: str, value: str, delta: str = None, delta_positive: bool = True, card_type: str = ""):
    """Rendert eine KPI-Karte"""
    delta_html = ""
    if delta:
        delta_class = "positive" if delta_positive else "negative"
        delta_icon = "↑" if delta_positive else "↓"
        delta_html = f'<div class="kpi-delta {delta_class}">{delta_icon} {delta}</div>'
    
    st.markdown(f"""
        <div class="kpi-card {card_type}">
            <div class="kpi-label">{label}</div>
            <div class="kpi-value">{value}</div>
            {delta_html}
        </div>
    """, unsafe_allow_html=True)


# =============================================================================
# MAIN DASHBOARD
# =============================================================================

def main():
    """Hauptfunktion des Dashboards mit robustem Session State Management"""
    
    # =========================================================================
    # SESSION STATE INITIALISIERUNG (VOR ALLEM ANDEREN!)
    # =========================================================================
    # Wichtig: Session State muss VOR dem Rendern von Widgets initialisiert werden
    
    # Standardwerte für Datumsbereich
    default_start = date.today() - timedelta(days=30)
    default_end = date.today() - timedelta(days=1)
    
    # Initialisiere Session State nur wenn nicht vorhanden
    if "date_start" not in st.session_state:
        st.session_state.date_start = default_start
    if "date_end" not in st.session_state:
        st.session_state.date_end = default_end
    
    # Flag für Button-Klicks (vermeidet Rerun-Konflikte)
    if "needs_date_update" not in st.session_state:
        st.session_state.needs_date_update = False
    
    # =========================================================================
    # HEADER
    # =========================================================================
    st.markdown("""
        <div class="main-header">
            <h1>📊 ÖWA Reporting Dashboard</h1>
            <p>Datenanalyse für INFOnline/ÖWA Metriken • VOL.at</p>
        </div>
    """, unsafe_allow_html=True)
    
    # =========================================================================
    # SIDEBAR - Filter & Einstellungen
    # =========================================================================
    with st.sidebar:
        st.markdown("### ⚙️ Filter & Einstellungen")
        
        # Datumsbereich
        st.markdown("#### 📅 Zeitraum")
        
        # Quick Select Buttons
        st.markdown("##### ⚡ Schnellauswahl")
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("Letzte 7 Tage", use_container_width=True, key="btn_7d"):
                st.session_state.date_start = date.today() - timedelta(days=7)
                st.session_state.date_end = date.today() - timedelta(days=1)
                st.rerun()
        
        with col2:
            if st.button("Letzte 30 Tage", use_container_width=True, key="btn_30d"):
                st.session_state.date_start = date.today() - timedelta(days=30)
                st.session_state.date_end = date.today() - timedelta(days=1)
                st.rerun()
        
        st.markdown("")
        
        # Date Inputs - Verwende Callback-Pattern für Updates
        col1, col2 = st.columns(2)
        
        with col1:
            start_date = st.date_input(
                "Von",
                value=st.session_state.date_start,
                max_value=date.today() - timedelta(days=1),
                key="input_start_date"
            )
        
        with col2:
            end_date = st.date_input(
                "Bis",
                value=st.session_state.date_end,
                max_value=date.today() - timedelta(days=1),
                key="input_end_date"
            )
        
        # Aktualisiere Session State basierend auf Widget-Werten
        # (Dies ist sicher, da wir unterschiedliche Keys verwenden)
        st.session_state.date_start = start_date
        st.session_state.date_end = end_date
        
        # Validierung
        if start_date > end_date:
            st.error("⚠️ Startdatum muss vor Enddatum liegen!")
            return
        
        days_selected = (end_date - start_date).days + 1
        st.info(f"📆 {days_selected} Tage ausgewählt")
        
        st.markdown("---")
        
        # Metrik-Filter
        st.markdown("#### 📊 Metriken")
        show_pi = st.checkbox("Page Impressions", value=True)
        show_visits = st.checkbox("Visits", value=True)
        
        st.markdown("---")
        
        # Plattform-Filter
        st.markdown("#### 📱 Plattformen")
        show_desktop = st.checkbox("Web Desktop", value=True)
        show_mobile = st.checkbox("Web Mobile", value=True)
        show_app = st.checkbox("App", value=True)
        
        st.markdown("---")
        
        # Daten aktualisieren
        if st.button("🔄 Daten aktualisieren", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
        
        # Info
        st.markdown("---")
        st.markdown("""
            <div style="font-size: 0.8rem; color: #666;">
                <strong>Datenquelle:</strong><br>
                INFOnline Reporting API<br><br>
                <strong>Letzte Aktualisierung:</strong><br>
                {timestamp}
            </div>
        """.format(timestamp=datetime.now().strftime("%d.%m.%Y %H:%M")), unsafe_allow_html=True)
    
    # ==========================================================================
    # DATEN LADEN
    # ==========================================================================
    
    with st.spinner("Lade Daten..."):
        df = load_measurements(start_date, end_date)
        df_alerts = load_alerts(start_date, end_date)
        df_agg = load_aggregated_data(start_date, end_date)
    
    # Filter anwenden
    metrics_filter = []
    if show_pi:
        metrics_filter.append("pageimpressions")
    if show_visits:
        metrics_filter.append("visits")
    
    surfaces_filter = []
    if show_desktop:
        surfaces_filter.append("web_desktop")
    if show_mobile:
        surfaces_filter.append("web_mobile")
    if show_app:
        surfaces_filter.append("app")
    
    if not df.empty:
        df_filtered = df[
            (df["_metric"].isin(metrics_filter)) & 
            (df["_surface"].isin(surfaces_filter))
        ]
    else:
        df_filtered = df
    
    # Prüfen ob Daten vorhanden
    if df.empty:
        st.warning("⚠️ Keine Daten für den ausgewählten Zeitraum gefunden.")
        st.info("💡 Führe zuerst den Daten-Import aus: `python run_full_test.py`")
        return
    
    # ==========================================================================
    # TAB NAVIGATION
    # ==========================================================================
    
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📊 Übersicht",
        "📋 Datentabelle",
        "📈 Zeitreihen",
        "⚠️ Anomalien",
        "📥 Export"
    ])
    
    # ==========================================================================
    # TAB 1: ÜBERSICHT
    # ==========================================================================
    with tab1:
        st.markdown('<h3 class="section-header">📊 Kennzahlen-Übersicht</h3>', unsafe_allow_html=True)
        
        # KPI Cards
        col1, col2, col3, col4 = st.columns(4)
        
        # Page Impressions
        pi_stats = get_summary_stats(df_filtered, "pageimpressions")
        pi_trend = calculate_trend(df_filtered, "pageimpressions", 7)
        
        with col1:
            render_kpi_card(
                "Page Impressions (Gesamt)",
                format_number(pi_stats["total"]),
                f"{pi_trend:+.1f}% vs. Vorwoche" if pi_trend != 0 else None,
                pi_trend >= 0
            )
        
        # Visits
        visits_stats = get_summary_stats(df_filtered, "visits")
        visits_trend = calculate_trend(df_filtered, "visits", 7)
        
        with col2:
            render_kpi_card(
                "Visits (Gesamt)",
                format_number(visits_stats["total"]),
                f"{visits_trend:+.1f}% vs. Vorwoche" if visits_trend != 0 else None,
                visits_trend >= 0,
                "success" if visits_trend >= 0 else "danger"
            )
        
        # Durchschnitt pro Tag
        with col3:
            render_kpi_card(
                "Ø PI / Tag",
                format_number(pi_stats["avg"]),
                card_type="success"
            )
        
        # Anomalien
        alert_count = len(df_alerts[df_alerts["_severity"] == "critical"]) if not df_alerts.empty else 0
        with col4:
            render_kpi_card(
                "Kritische Anomalien",
                str(alert_count),
                card_type="danger" if alert_count > 0 else "success"
            )
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        # Plattform-Verteilung
        st.markdown('<h3 class="section-header">📱 Verteilung nach Plattform</h3>', unsafe_allow_html=True)
        
        if not df_filtered.empty and "pageimpressions" in metrics_filter:
            pi_df = df_filtered[df_filtered["_metric"] == "pageimpressions"]
            
            if not pi_df.empty:
                platform_totals = pi_df.groupby("Plattform")["Wert"].sum().reset_index()
                platform_totals["Anteil %"] = (platform_totals["Wert"] / platform_totals["Wert"].sum() * 100).round(1)
                platform_totals["Wert formatiert"] = platform_totals["Wert"].apply(format_number)
                
                col1, col2 = st.columns([2, 1])
                
                with col1:
                    # Bar Chart
                    import plotly.express as px
                    fig = px.bar(
                        platform_totals,
                        x="Plattform",
                        y="Wert",
                        color="Plattform",
                        text="Wert formatiert",
                        title="Page Impressions nach Plattform"
                    )
                    fig.update_traces(textposition="outside")
                    fig.update_layout(
                        showlegend=False,
                        height=350,
                        font=dict(family="Arial", size=12),
                        title_font_size=14
                    )
                    st.plotly_chart(fig, use_container_width=True)
                
                with col2:
                    # Pie Chart
                    fig2 = px.pie(
                        platform_totals,
                        values="Wert",
                        names="Plattform",
                        title="Anteil nach Plattform"
                    )
                    fig2.update_layout(height=350, font=dict(family="Arial", size=12))
                    st.plotly_chart(fig2, use_container_width=True)
        
        # Wochentags-Analyse
        st.markdown('<h3 class="section-header">📅 Wochentags-Muster</h3>', unsafe_allow_html=True)
        
        if not df_filtered.empty:
            df_weekday = df_filtered.copy()
            df_weekday["Wochentag"] = pd.to_datetime(df_weekday["Datum"]).dt.dayofweek
            weekday_names = {0: "Mo", 1: "Di", 2: "Mi", 3: "Do", 4: "Fr", 5: "Sa", 6: "So"}
            df_weekday["Wochentag Name"] = df_weekday["Wochentag"].map(weekday_names)
            
            # Aggregieren nach Wochentag und Metrik
            weekday_agg = df_weekday.groupby(["Wochentag", "Wochentag Name", "_metric"])["Wert"].mean().reset_index()
            weekday_agg["Wert"] = weekday_agg["Wert"].round(0).astype(int)
            weekday_agg = weekday_agg.sort_values("Wochentag")
            
            if "pageimpressions" in metrics_filter:
                pi_weekday = weekday_agg[weekday_agg["_metric"] == "pageimpressions"]
                
                fig3 = px.bar(
                    pi_weekday,
                    x="Wochentag Name",
                    y="Wert",
                    title="Ø Page Impressions nach Wochentag",
                    color="Wert",
                    color_continuous_scale="Blues"
                )
                fig3.update_layout(
                    height=300,
                    xaxis_title="",
                    yaxis_title="Ø PI",
                    font=dict(family="Arial", size=12)
                )
                st.plotly_chart(fig3, use_container_width=True)
    
    # ==========================================================================
    # TAB 2: DATENTABELLE
    # ==========================================================================
    with tab2:
        st.markdown('<h3 class="section-header">📋 Detaillierte Datentabelle</h3>', unsafe_allow_html=True)
        
        st.markdown("""
            <div class="info-box">
                <strong>💡 Tipps zur Nutzung:</strong>
                <ul style="margin-bottom: 0;">
                    <li>Klicke auf Spaltenüberschriften zum Sortieren</li>
                    <li>Nutze das Suchfeld zum Filtern</li>
                    <li>Spaltenbreite durch Ziehen anpassen</li>
                </ul>
            </div>
        """, unsafe_allow_html=True)
        
        # Zusätzliche Filter für Tabelle
        col1, col2, col3 = st.columns(3)
        
        with col1:
            search_term = st.text_input("🔍 Suche", placeholder="z.B. Desktop, PI...")
        
        with col2:
            sort_by = st.selectbox(
                "Sortieren nach",
                ["Datum (neueste zuerst)", "Datum (älteste zuerst)", "Wert (höchste zuerst)", "Wert (niedrigste zuerst)"]
            )
        
        with col3:
            show_preliminary = st.selectbox("Vorläufige Daten", ["Alle anzeigen", "Nur finale", "Nur vorläufige"])
        
        # Filter anwenden
        display_df = df_filtered.copy()
        
        # Suchfilter
        if search_term:
            mask = display_df.apply(lambda row: search_term.lower() in str(row).lower(), axis=1)
            display_df = display_df[mask]
        
        # Sortierung
        if "neueste" in sort_by:
            display_df = display_df.sort_values("Datum", ascending=False)
        elif "älteste" in sort_by:
            display_df = display_df.sort_values("Datum", ascending=True)
        elif "höchste" in sort_by:
            display_df = display_df.sort_values("Wert", ascending=False)
        elif "niedrigste" in sort_by:
            display_df = display_df.sort_values("Wert", ascending=True)
        
        # Vorläufige Daten Filter
        if show_preliminary == "Nur finale":
            display_df = display_df[display_df["Vorläufig"] == "Nein"]
        elif show_preliminary == "Nur vorläufige":
            display_df = display_df[display_df["Vorläufig"] == "Ja"]
        
        # Spalten für Anzeige auswählen
        display_columns = ["Datum", "Brand", "Plattform", "Metrik", "Wert", "Vorläufig", "Erfasst"]
        
        # Wert formatieren für Anzeige
        display_df_formatted = display_df[display_columns].copy()
        display_df_formatted["Wert"] = display_df_formatted["Wert"].apply(format_number)
        
        # Statistik
        st.markdown(f"**{len(display_df_formatted)} Datensätze** gefunden")
        
        # Interaktive Tabelle
        st.dataframe(
            display_df_formatted,
            use_container_width=True,
            height=500,
            hide_index=True,
            column_config={
                "Datum": st.column_config.DateColumn("Datum", format="DD.MM.YYYY"),
                "Wert": st.column_config.TextColumn("Wert", help="Formatiert mit Tausendertrennzeichen"),
            }
        )
        
        # Aggregierte Statistik
        st.markdown("---")
        st.markdown("**📊 Aggregierte Statistik für Auswahl:**")
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Summe", format_number(df_filtered["Wert"].sum()))
        with col2:
            st.metric("Durchschnitt", format_number(int(df_filtered["Wert"].mean())))
        with col3:
            st.metric("Minimum", format_number(df_filtered["Wert"].min()))
        with col4:
            st.metric("Maximum", format_number(df_filtered["Wert"].max()))
    
    # ==========================================================================
    # TAB 3: ZEITREIHEN
    # ==========================================================================
    with tab3:
        st.markdown('<h3 class="section-header">📈 Zeitreihen-Analyse</h3>', unsafe_allow_html=True)
        
        if not df_filtered.empty:
            import plotly.express as px
            import plotly.graph_objects as go
            
            # Gruppierung nach Datum und Metrik
            time_series = df_filtered.groupby(["Datum", "_metric"])["Wert"].sum().reset_index()
            time_series["Datum"] = pd.to_datetime(time_series["Datum"])
            time_series["Metrik"] = time_series["_metric"].apply(format_metric)
            
            # Hauptchart
            fig = px.line(
                time_series,
                x="Datum",
                y="Wert",
                color="Metrik",
                title="Tägliche Entwicklung",
                markers=True
            )
            
            fig.update_layout(
                height=400,
                xaxis_title="",
                yaxis_title="Wert",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                font=dict(family="Arial", size=12)
            )
            
            st.plotly_chart(fig, use_container_width=True)
            
            # 7-Tage Durchschnitt
            st.markdown("#### 📉 Gleitender 7-Tage-Durchschnitt")
            
            for metric in metrics_filter:
                metric_ts = time_series[time_series["_metric"] == metric].copy()
                if not metric_ts.empty:
                    metric_ts = metric_ts.sort_values("Datum")
                    metric_ts["MA7"] = metric_ts["Wert"].rolling(window=7, min_periods=1).mean()
                    
                    fig2 = go.Figure()
                    
                    fig2.add_trace(go.Scatter(
                        x=metric_ts["Datum"],
                        y=metric_ts["Wert"],
                        mode="lines+markers",
                        name="Tageswert",
                        line=dict(color="#3498DB", width=1),
                        marker=dict(size=4)
                    ))
                    
                    fig2.add_trace(go.Scatter(
                        x=metric_ts["Datum"],
                        y=metric_ts["MA7"],
                        mode="lines",
                        name="7-Tage Ø",
                        line=dict(color="#E74C3C", width=2)
                    ))
                    
                    fig2.update_layout(
                        title=f"{format_metric(metric)} - Trend",
                        height=300,
                        xaxis_title="",
                        yaxis_title="Wert",
                        legend=dict(orientation="h", yanchor="bottom", y=1.02),
                        font=dict(family="Arial", size=12)
                    )
                    
                    st.plotly_chart(fig2, use_container_width=True)
    
    # ==========================================================================
    # TAB 4: ANOMALIEN
    # ==========================================================================
    with tab4:
        st.markdown('<h3 class="section-header">⚠️ Anomalie-Übersicht</h3>', unsafe_allow_html=True)
        
        if df_alerts.empty:
            st.success("✅ Keine Anomalien im ausgewählten Zeitraum erkannt!")
            st.info("Die Anomalie-Erkennung basiert auf dem robusten Z-Score (Median/MAD) und prüft auf signifikante Abweichungen vom historischen Durchschnitt.")
        else:
            # Zusammenfassung
            critical_count = len(df_alerts[df_alerts["_severity"] == "critical"])
            warning_count = len(df_alerts[df_alerts["_severity"] == "warning"])
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("🔴 Kritisch", critical_count)
            with col2:
                st.metric("🟡 Warnung", warning_count)
            with col3:
                st.metric("Gesamt", len(df_alerts))
            
            st.markdown("---")
            
            # Anomalie-Tabelle
            display_alerts = df_alerts[["Datum", "Brand", "Plattform", "Metrik", "Schwere", "Abweichung %", "Z-Score", "Median", "Aktuell", "Meldung"]].copy()
            
            st.dataframe(
                display_alerts,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Datum": st.column_config.DateColumn("Datum", format="DD.MM.YYYY"),
                }
            )
            
            # Erklärung
            with st.expander("ℹ️ Wie funktioniert die Anomalie-Erkennung?"):
                st.markdown("""
                    **Methodik: Robuster Z-Score (Median/MAD)**
                    
                    Der robuste Z-Score verwendet Median und MAD (Median Absolute Deviation) anstelle von Mittelwert und Standardabweichung.
                    Dies macht die Erkennung weniger anfällig für Ausreißer in den historischen Daten.
                    
                    **Formel:**
                    ```
                    z = (x - Median) / (1.4826 × MAD)
                    ```
                    
                    **Schwellwerte:**
                    - 🟡 **Warnung**: |z| ≥ 2.0 UND |Abweichung| ≥ 15%
                    - 🔴 **Kritisch**: |z| ≥ 2.5 UND |Abweichung| ≥ 20%
                    
                    **Zeitraum:** Die letzten 56 Tage (8 Wochen) mit Wochentags-Berücksichtigung.
                """)
    
    # ==========================================================================
    # TAB 5: EXPORT
    # ==========================================================================
    with tab5:
        st.markdown('<h3 class="section-header">📥 Daten exportieren</h3>', unsafe_allow_html=True)
        
        st.markdown("""
            Exportiere die Daten in verschiedenen Formaten für weitere Analysen.
        """)
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("#### 📋 Messdaten")
            
            # CSV Export
            csv_data = df_filtered[["Datum", "Brand", "Plattform", "Metrik", "Wert", "Site ID", "Vorläufig", "Erfasst"]].copy()
            csv = csv_data.to_csv(index=False, sep=";", decimal=",")
            
            st.download_button(
                label="⬇️ CSV herunterladen",
                data=csv,
                file_name=f"oewa_daten_{start_date}_{end_date}.csv",
                mime="text/csv",
                use_container_width=True
            )
            
            st.caption(f"{len(csv_data)} Datensätze")
        
        with col2:
            st.markdown("#### ⚠️ Anomalien")
            
            if not df_alerts.empty:
                alerts_export = df_alerts[["Datum", "Brand", "Plattform", "Metrik", "Schwere", "Abweichung %", "Z-Score", "Meldung"]].copy()
                csv_alerts = alerts_export.to_csv(index=False, sep=";", decimal=",")
                
                st.download_button(
                    label="⬇️ CSV herunterladen",
                    data=csv_alerts,
                    file_name=f"oewa_anomalien_{start_date}_{end_date}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
                
                st.caption(f"{len(alerts_export)} Anomalien")
            else:
                st.info("Keine Anomalien zum Exportieren")
        
        st.markdown("---")
        
        # Excel Export
        st.markdown("#### 📊 Excel-Export (alle Daten)")
        
        try:
            import io
            
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df_filtered[["Datum", "Brand", "Plattform", "Metrik", "Wert", "Site ID", "Vorläufig", "Erfasst"]].to_excel(
                    writer, sheet_name="Messdaten", index=False
                )
                if not df_alerts.empty:
                    df_alerts[["Datum", "Brand", "Plattform", "Metrik", "Schwere", "Abweichung %", "Z-Score", "Meldung"]].to_excel(
                        writer, sheet_name="Anomalien", index=False
                    )
            
            st.download_button(
                label="⬇️ Excel herunterladen",
                data=buffer.getvalue(),
                file_name=f"oewa_report_{start_date}_{end_date}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
        except ImportError:
            st.warning("⚠️ Für Excel-Export wird `openpyxl` benötigt: `pip install openpyxl`")
    
    # ==========================================================================
    # FOOTER
    # ==========================================================================
    st.markdown("""
        <div class="footer">
            ÖWA Reporting Dashboard • Datenquelle: INFOnline Reporting API<br>
            <small>© 2025 • Entwickelt als Proof-of-Concept</small>
        </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()
