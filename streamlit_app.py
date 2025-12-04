"""
ÖWA Reporting Dashboard - Streamlit Cloud Entry Point
======================================================
Dieses Script lädt Daten aus Airtable und zeigt ein professionelles Dashboard.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import date, datetime, timedelta
import requests
import os

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
# AIRTABLE CONFIG (from Streamlit Secrets)
# =============================================================================
AIRTABLE_API_KEY = st.secrets.get("AIRTABLE_API_KEY", os.getenv("AIRTABLE_API_KEY", ""))
AIRTABLE_BASE_ID = st.secrets.get("AIRTABLE_BASE_ID", os.getenv("AIRTABLE_BASE_ID", "appTIeod85xnBy7Vn"))

# =============================================================================
# DATA LOADING FROM AIRTABLE
# =============================================================================
@st.cache_data(ttl=300)  # Cache for 5 minutes
def load_data_from_airtable():
    """Lädt Daten direkt aus Airtable"""
    if not AIRTABLE_API_KEY:
        st.error("⚠️ AIRTABLE_API_KEY nicht konfiguriert! Bitte in Streamlit Secrets eintragen.")
        return pd.DataFrame()
    
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/Measurements"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    
    all_records = []
    offset = None
    
    with st.spinner("📥 Lade Daten aus Airtable..."):
        while True:
            params = {"pageSize": 100}
            if offset:
                params["offset"] = offset
            
            try:
                response = requests.get(url, headers=headers, params=params, timeout=30)
                if response.status_code != 200:
                    st.error(f"Airtable API Fehler: {response.status_code}")
                    break
                
                data = response.json()
                records = data.get("records", [])
                
                for record in records:
                    fields = record.get("fields", {})
                    all_records.append({
                        "datum": fields.get("Datum"),
                        "brand": fields.get("Brand"),
                        "plattform": fields.get("Plattform"),
                        "metrik": fields.get("Metrik"),
                        "wert": fields.get("Wert"),
                        "site_id": fields.get("Site ID"),
                        "vorlaeufig": fields.get("Vorläufig", False),
                    })
                
                offset = data.get("offset")
                if not offset:
                    break
                    
            except Exception as e:
                st.error(f"Fehler beim Laden: {e}")
                break
    
    if not all_records:
        return pd.DataFrame()
    
    df = pd.DataFrame(all_records)
    df["datum"] = pd.to_datetime(df["datum"])
    df["wert"] = pd.to_numeric(df["wert"], errors="coerce")
    
    return df

# =============================================================================
# CUSTOM CSS
# =============================================================================
st.markdown("""
<style>
    .main-header {
        background: linear-gradient(135deg, #1E3A5F 0%, #2C5282 100%);
        padding: 1.5rem 2rem;
        border-radius: 12px;
        margin-bottom: 2rem;
        color: white;
    }
    .kpi-card {
        background: white;
        border-radius: 12px;
        padding: 1.5rem;
        box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        border-left: 4px solid #3498DB;
        text-align: center;
    }
    .kpi-value {
        font-size: 2rem;
        font-weight: 700;
        color: #1E3A5F;
    }
    .kpi-label {
        font-size: 0.9rem;
        color: #666;
        margin-bottom: 0.5rem;
    }
    .kpi-delta-positive { color: #27AE60; }
    .kpi-delta-negative { color: #E74C3C; }
</style>
""", unsafe_allow_html=True)

# =============================================================================
# HEADER
# =============================================================================
st.markdown("""
<div class="main-header">
    <h1>📊 ÖWA Reporting Dashboard</h1>
    <p>VOL.AT & VIENNA.AT Web-Analytics • Daten aus Airtable</p>
</div>
""", unsafe_allow_html=True)

# =============================================================================
# LOAD DATA FIRST (to determine available date range)
# =============================================================================
df = load_data_from_airtable()

# Determine available data range
if not df.empty:
    data_min_date = df["datum"].min().date()
    data_max_date = df["datum"].max().date()
    data_days_available = (data_max_date - data_min_date).days + 1
else:
    data_min_date = date.today() - timedelta(days=30)
    data_max_date = date.today()
    data_days_available = 0

# =============================================================================
# SIDEBAR FILTERS
# =============================================================================
st.sidebar.header("⚙️ Filter")

# Show available data range info
st.sidebar.info(f"📅 **Verfügbare Daten:**\n{data_min_date.strftime('%d.%m.%Y')} - {data_max_date.strftime('%d.%m.%Y')}\n({data_days_available} Tage)")

# Date range - Messzeitraum
st.sidebar.subheader("📊 Messzeitraum")

# Initialize session state for date range (using widget keys)
if "start_input" not in st.session_state:
    st.session_state.start_input = max(min(date.today(), data_max_date) - timedelta(days=30), data_min_date)
if "end_input" not in st.session_state:
    st.session_state.end_input = min(date.today(), data_max_date)

# Quick select buttons - directly modify widget keys
col_btn1, col_btn2 = st.sidebar.columns(2)
if col_btn1.button("Letzte 7 Tage"):
    st.session_state.start_input = max(date.today() - timedelta(days=7), data_min_date)
    st.session_state.end_input = min(date.today(), data_max_date)
    st.rerun()

if col_btn2.button("Letzte 30 Tage"):
    st.session_state.start_input = max(date.today() - timedelta(days=30), data_min_date)
    st.session_state.end_input = min(date.today(), data_max_date)
    st.rerun()

# Date inputs with widget keys
col1, col2 = st.sidebar.columns(2)
start_date = col1.date_input("Von", min_value=data_min_date, max_value=data_max_date, key="start_input")
end_date = col2.date_input("Bis", min_value=data_min_date, max_value=data_max_date, key="end_input")

# =============================================================================
# COMPARISON PERIOD SELECTION (wie Google Analytics)
# =============================================================================
st.sidebar.subheader("🔄 Vergleichszeitraum")

selected_days = (end_date - start_date).days + 1

# Comparison mode selection
comparison_mode = st.sidebar.radio(
    "Vergleichsmodus",
    ["Vorperiode (automatisch)", "Benutzerdefiniert", "Kein Vergleich"],
    index=0,
    help="Vorperiode: Gleich langer Zeitraum direkt vor der Auswahl"
)

if comparison_mode == "Vorperiode (automatisch)":
    # Automatische Vorperiode = gleich langer Zeitraum direkt davor
    prev_end = start_date - timedelta(days=1)
    prev_start = prev_end - timedelta(days=selected_days - 1)
    
    # Check if comparison period is within available data
    if prev_start >= data_min_date:
        comparison_fully_available = True
        st.sidebar.success(f"✅ Vergleich: {prev_start.strftime('%d.%m.')} - {prev_end.strftime('%d.%m.%Y')}")
    elif prev_end >= data_min_date:
        comparison_fully_available = False
        actual_prev_start = max(prev_start, data_min_date)
        actual_days = (prev_end - actual_prev_start).days + 1
        st.sidebar.warning(f"⚠️ Nur {actual_days}/{selected_days} Tage verfügbar:\n{actual_prev_start.strftime('%d.%m.')} - {prev_end.strftime('%d.%m.%Y')}")
        prev_start = actual_prev_start
    else:
        comparison_fully_available = False
        prev_start = None
        prev_end = None
        st.sidebar.error("❌ Keine Vergleichsdaten verfügbar")

elif comparison_mode == "Benutzerdefiniert":
    # Manual comparison period selection
    # Prüfe ob überhaupt Vergleichsdaten VOR dem Messzeitraum existieren
    comparison_max_date = start_date - timedelta(days=1)  # Spätestes Vergleichsdatum = 1 Tag vor Messzeitraum
    
    if comparison_max_date >= data_min_date:
        # Es gibt mindestens 1 Tag für Vergleich
        col_cmp1, col_cmp2 = st.sidebar.columns(2)
        
        # Berechne sinnvolle Default-Werte (innerhalb des gültigen Bereichs)
        default_cmp_start = max(start_date - timedelta(days=selected_days), data_min_date)
        default_cmp_end = comparison_max_date
        
        # Stelle sicher, dass default_cmp_start nicht nach default_cmp_end liegt
        if default_cmp_start > default_cmp_end:
            default_cmp_start = data_min_date
        
        prev_start = col_cmp1.date_input("Vergleich Von", 
                                          value=default_cmp_start,
                                          min_value=data_min_date, 
                                          max_value=comparison_max_date,
                                          key="cmp_start")
        prev_end = col_cmp2.date_input("Vergleich Bis", 
                                        value=default_cmp_end,
                                        min_value=data_min_date, 
                                        max_value=comparison_max_date,
                                        key="cmp_end")
        
        # Validierung: prev_start sollte <= prev_end sein
        if prev_start > prev_end:
            st.sidebar.error("❌ 'Vergleich Von' muss vor 'Vergleich Bis' liegen!")
            prev_start = None
            prev_end = None
            comparison_fully_available = False
        else:
            comparison_fully_available = True
            cmp_days = (prev_end - prev_start).days + 1
            if cmp_days != selected_days:
                st.sidebar.warning(f"⚠️ Vergleichszeitraum ({cmp_days} Tage) ≠ Messzeitraum ({selected_days} Tage)")
            else:
                st.sidebar.success(f"✅ Vergleich: {prev_start.strftime('%d.%m.')} - {prev_end.strftime('%d.%m.%Y')}")
    else:
        # Kein gültiger Vergleichszeitraum möglich (Messzeitraum beginnt am ersten verfügbaren Tag)
        st.sidebar.error("❌ Keine Vergleichsdaten vor dem Messzeitraum verfügbar.\nWähle einen späteren Starttermin für den Messzeitraum.")
        prev_start = None
        prev_end = None
        comparison_fully_available = False
else:
    # No comparison
    prev_start = None
    prev_end = None
    comparison_fully_available = False

if df.empty:
    st.warning("Keine Daten verfügbar. Bitte prüfe die Airtable-Konfiguration.")
    st.stop()

# Filter by date
df_filtered = df[
    (df["datum"].dt.date >= start_date) & 
    (df["datum"].dt.date <= end_date)
]

# Sidebar brand filter
brands = df_filtered["brand"].dropna().unique().tolist()
selected_brands = st.sidebar.multiselect("Brands", brands, default=brands)
df_filtered = df_filtered[df_filtered["brand"].isin(selected_brands)]

# Sidebar metric filter
metrics = df_filtered["metrik"].dropna().unique().tolist()
selected_metrics = st.sidebar.multiselect("Metriken", metrics, default=metrics)
df_filtered = df_filtered[df_filtered["metrik"].isin(selected_metrics)]

st.sidebar.markdown(f"**{len(df_filtered)} Datensätze**")

# =============================================================================
# KPI CARDS
# =============================================================================
st.subheader("📈 Kennzahlen")

col1, col2, col3, col4 = st.columns(4)

# Calculate KPIs
pi_total = df_filtered[df_filtered["metrik"] == "Page Impressions"]["wert"].sum()
visits_total = df_filtered[df_filtered["metrik"] == "Visits"]["wert"].sum()
days = (end_date - start_date).days or 1
pi_avg = pi_total / days
visits_avg = visits_total / days

# Calculate period-over-period change using the comparison period from sidebar
if prev_start is not None and prev_end is not None:
    # Gleiche Filter wie Hauptauswahl (brands UND metrics)
    df_prev = df[
        (df["datum"].dt.date >= prev_start) & 
        (df["datum"].dt.date <= prev_end) &
        (df["brand"].isin(selected_brands)) &
        (df["metrik"].isin(selected_metrics))
    ]
    
    # Berechne Vergleichsdaten
    prev_days_with_data = df_prev["datum"].dt.date.nunique()
    comparison_days = (prev_end - prev_start).days + 1
    
    pi_prev = df_prev[df_prev["metrik"] == "Page Impressions"]["wert"].sum()
    visits_prev = df_prev[df_prev["metrik"] == "Visits"]["wert"].sum()
    
    # Vergleichstext basierend auf Modus
    if comparison_mode == "Benutzerdefiniert":
        period_label = f"vs. {prev_start.strftime('%d.%m.')}-{prev_end.strftime('%d.%m.')}"
    else:
        period_label = "vs. Vorperiode"
    
    # Zusätzlicher Hinweis bei unvollständigen Daten
    if prev_days_with_data < comparison_days:
        period_label += f" ({prev_days_with_data}d)"
    
    # Berechne Änderungen
    if pi_prev > 0:
        pi_change = ((pi_total - pi_prev) / pi_prev * 100)
        pi_delta_text = f"{pi_change:+.1f}% {period_label}"
    else:
        pi_change = None
        pi_delta_text = "Keine Vergleichsdaten"
    
    if visits_prev > 0:
        visits_change = ((visits_total - visits_prev) / visits_prev * 100)
        visits_delta_text = f"{visits_change:+.1f}% {period_label}"
    else:
        visits_change = None
        visits_delta_text = "Keine Vergleichsdaten"
else:
    # Kein Vergleich ausgewählt
    pi_change = None
    visits_change = None
    pi_delta_text = None
    visits_delta_text = None

with col1:
    st.metric(
        label="Page Impressions (Gesamt)",
        value=f"{pi_total:,.0f}".replace(",", "."),
        delta=pi_delta_text
    )

with col2:
    st.metric(
        label="Visits (Gesamt)",
        value=f"{visits_total:,.0f}".replace(",", "."),
        delta=visits_delta_text
    )

with col3:
    st.metric(
        label="Ø Page Impressions / Tag",
        value=f"{pi_avg:,.0f}".replace(",", ".")
    )

with col4:
    st.metric(
        label="Ø Visits / Tag",
        value=f"{visits_avg:,.0f}".replace(",", ".")
    )

# =============================================================================
# TABS
# =============================================================================
tab1, tab2, tab3 = st.tabs(["📊 Übersicht", "📋 Datentabelle", "📈 Zeitreihen"])

# -----------------------------------------------------------------------------
# TAB 1: ÜBERSICHT
# -----------------------------------------------------------------------------
with tab1:
    st.subheader("📊 Verteilung nach Brand")
    
    # Brand comparison
    brand_summary = df_filtered.groupby(["brand", "metrik"])["wert"].sum().reset_index()
    
    col1, col2 = st.columns(2)
    
    with col1:
        pi_data = brand_summary[brand_summary["metrik"] == "Page Impressions"]
        if not pi_data.empty:
            fig_pi = px.bar(
                pi_data,
                x="brand",
                y="wert",
                color="brand",
                title="Page Impressions nach Brand",
                color_discrete_map={"VOL": "#3B82F6", "Vienna": "#8B5CF6"}
            )
            fig_pi.update_layout(showlegend=False, yaxis=dict(tickformat=","))
            st.plotly_chart(fig_pi, use_container_width=True)
        else:
            st.info("Keine Page Impressions Daten für den ausgewählten Zeitraum.")
    
    with col2:
        visits_data = brand_summary[brand_summary["metrik"] == "Visits"]
        if not visits_data.empty:
            fig_visits = px.bar(
                visits_data,
                x="brand",
                y="wert",
                color="brand",
                title="Visits nach Brand",
                color_discrete_map={"VOL": "#3B82F6", "Vienna": "#8B5CF6"}
            )
            fig_visits.update_layout(showlegend=False, yaxis=dict(tickformat=","))
            st.plotly_chart(fig_visits, use_container_width=True)
        else:
            st.info("Keine Visits Daten für den ausgewählten Zeitraum.")
    
    # Wochentags-Analyse nach Brand (VOL vs Vienna)
    st.subheader("📅 Wochentags-Analyse nach Property")
    
    # Wochentag extrahieren (0=Montag, 6=Sonntag)
    df_weekday = df_filtered.copy()
    df_weekday["wochentag"] = df_weekday["datum"].dt.dayofweek
    df_weekday["wochentag_name"] = df_weekday["datum"].dt.day_name()
    
    # Deutsche Wochentags-Namen
    weekday_map = {
        "Monday": "Montag", "Tuesday": "Dienstag", "Wednesday": "Mittwoch",
        "Thursday": "Donnerstag", "Friday": "Freitag", "Saturday": "Samstag", "Sunday": "Sonntag"
    }
    df_weekday["wochentag_de"] = df_weekday["wochentag_name"].map(weekday_map)
    
    # Durchschnitt pro Wochentag UND Brand berechnen
    weekday_avg = df_weekday.groupby(["wochentag", "wochentag_de", "brand", "metrik"])["wert"].mean().reset_index()
    weekday_avg = weekday_avg.sort_values("wochentag")
    
    # Farben für Brands
    brand_colors = {"VOL": "#3B82F6", "Vienna": "#8B5CF6"}
    
    if not weekday_avg.empty:
        col1, col2 = st.columns(2)
        
        with col1:
            pi_weekday = weekday_avg[weekday_avg["metrik"] == "Page Impressions"]
            if not pi_weekday.empty:
                fig_pi_week = px.bar(
                    pi_weekday,
                    x="wochentag_de",
                    y="wert",
                    color="brand",
                    barmode="group",
                    title="Ø Page Impressions pro Wochentag",
                    color_discrete_map=brand_colors
                )
                fig_pi_week.update_layout(
                    yaxis=dict(tickformat=","),
                    xaxis_title="",
                    legend_title="Property",
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                )
                st.plotly_chart(fig_pi_week, use_container_width=True)
        
        with col2:
            visits_weekday = weekday_avg[weekday_avg["metrik"] == "Visits"]
            if not visits_weekday.empty:
                fig_visits_week = px.bar(
                    visits_weekday,
                    x="wochentag_de",
                    y="wert",
                    color="brand",
                    barmode="group",
                    title="Ø Visits pro Wochentag",
                    color_discrete_map=brand_colors
                )
                fig_visits_week.update_layout(
                    yaxis=dict(tickformat=","),
                    xaxis_title="",
                    legend_title="Property",
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                )
                st.plotly_chart(fig_visits_week, use_container_width=True)
        
        # Insights: Bester und schlechtester Tag PRO BRAND
        st.markdown("**📈 Erkenntnisse (Page Impressions):**")
        
        pi_data = weekday_avg[weekday_avg["metrik"] == "Page Impressions"]
        if not pi_data.empty:
            insights_cols = st.columns(len(pi_data["brand"].unique()))
            
            for idx, brand in enumerate(sorted(pi_data["brand"].unique())):
                brand_data = pi_data[pi_data["brand"] == brand]
                if not brand_data.empty:
                    best_day = brand_data.loc[brand_data["wert"].idxmax()]
                    worst_day = brand_data.loc[brand_data["wert"].idxmin()]
                    avg_brand = brand_data["wert"].mean()
                    
                    best_pct = ((best_day["wert"] - avg_brand) / avg_brand * 100)
                    worst_pct = ((worst_day["wert"] - avg_brand) / avg_brand * 100)
                    
                    brand_color = "#3B82F6" if brand == "VOL" else "#8B5CF6"
                    
                    with insights_cols[idx]:
                        st.markdown(f"""
                        <div style="padding: 10px; border-left: 4px solid {brand_color}; background: #f8f9fa; border-radius: 4px;">
                            <strong style="color: {brand_color};">{brand}</strong><br>
                            📈 Bester: <strong>{best_day['wochentag_de']}</strong> ({best_pct:+.1f}%)<br>
                            📉 Schwächster: <strong>{worst_day['wochentag_de']}</strong> ({worst_pct:+.1f}%)
                        </div>
                        """, unsafe_allow_html=True)
    else:
        st.info("Nicht genügend Daten für Wochentags-Analyse.")

# -----------------------------------------------------------------------------
# TAB 2: DATENTABELLE
# -----------------------------------------------------------------------------
with tab2:
    st.subheader("📋 Detaillierte Daten")
    
    # Search
    search = st.text_input("🔍 Suche", placeholder="z.B. VOL, Page Impressions...")
    
    df_display = df_filtered.copy()
    df_display["datum"] = df_display["datum"].dt.strftime("%d.%m.%Y")
    df_display["wert"] = df_display["wert"].apply(lambda x: f"{x:,.0f}".replace(",", "."))
    df_display = df_display.rename(columns={
        "datum": "Datum",
        "brand": "Brand",
        "plattform": "Plattform",
        "metrik": "Metrik",
        "wert": "Wert",
        "site_id": "Site ID",
        "vorlaeufig": "Vorläufig"
    })
    
    if search:
        df_display = df_display[
            df_display.apply(lambda row: search.lower() in str(row).lower(), axis=1)
        ]
    
    st.dataframe(df_display, use_container_width=True, height=500)
    
    # Download
    csv = df_filtered.to_csv(index=False)
    st.download_button(
        label="📥 Als CSV herunterladen",
        data=csv,
        file_name=f"oewa_daten_{start_date}_{end_date}.csv",
        mime="text/csv"
    )

# -----------------------------------------------------------------------------
# TAB 3: ZEITREIHEN
# -----------------------------------------------------------------------------
with tab3:
    st.subheader("📈 Zeitreihen-Analyse nach Property")
    
    # Farben für Properties
    property_colors = {
        "VOL": {"line": "#3B82F6", "fill": "#93C5FD"},      # Blau
        "Vienna": {"line": "#8B5CF6", "fill": "#C4B5FD"}    # Lila
    }
    
    # Daten pro Tag UND Brand aggregieren
    daily = df_filtered.copy()
    daily["datum_tag"] = daily["datum"].dt.date
    daily = daily.groupby(["datum_tag", "metrik", "brand"])["wert"].sum().reset_index()
    daily["datum_tag"] = pd.to_datetime(daily["datum_tag"])
    
    if daily.empty:
        st.info("Keine Daten für den ausgewählten Zeitraum.")
    else:
        for metrik in ["Page Impressions", "Visits"]:
            metric_data = daily[daily["metrik"] == metrik].sort_values("datum_tag")
            
            if metric_data.empty:
                st.info(f"Keine {metrik} Daten verfügbar.")
                continue
            
            fig = go.Figure()
            
            # Für jede Property (Brand) eine eigene Linie
            for brand in ["VOL", "Vienna"]:
                brand_data = metric_data[metric_data["brand"] == brand].copy()
                
                if brand_data.empty:
                    continue
                
                # 7-Tage-Durchschnitt pro Brand berechnen
                brand_data = brand_data.sort_values("datum_tag")
                brand_data["7d_avg"] = brand_data["wert"].rolling(window=7, min_periods=1).mean()
                
                colors = property_colors.get(brand, {"line": "#666", "fill": "#999"})
                
                # Tageswert (helle Linie mit Punkten)
                fig.add_trace(go.Scatter(
                    x=brand_data["datum_tag"],
                    y=brand_data["wert"],
                    mode="lines+markers",
                    name=f"{brand} Tageswert",
                    line=dict(color=colors["fill"], width=1),
                    marker=dict(size=5),
                    legendgroup=brand,
                    opacity=0.7
                ))
                
                # 7-Tage-Durchschnitt (kräftige Linie)
                fig.add_trace(go.Scatter(
                    x=brand_data["datum_tag"],
                    y=brand_data["7d_avg"],
                    mode="lines",
                    name=f"{brand} 7-Tage Ø",
                    line=dict(color=colors["line"], width=3),
                    legendgroup=brand
                ))
            
            fig.update_layout(
                title=f"{metrik} - Trend nach Property (mit 7-Tage-Durchschnitt)",
                yaxis_tickformat=",",
                xaxis=dict(
                    tickformat="%d.%m.",
                    dtick="D1",
                    tickangle=-45
                ),
                xaxis_title="Datum",
                yaxis_title="Wert",
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.02,
                    xanchor="right",
                    x=1
                ),
                hovermode="x unified"
            )
            st.plotly_chart(fig, use_container_width=True)
        
        # Erkenntnisse-Box
        st.markdown("---")
        st.markdown("### 📊 Legende")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("🔵 **VOL.AT** - Vorarlberg Online")
        with col2:
            st.markdown("🟣 **VIENNA.AT** - Wien Online")

# =============================================================================
# FOOTER
# =============================================================================
st.markdown("---")
st.markdown("""
<div style="text-align: center; color: #666; font-size: 0.9rem;">
    ÖWA Reporting Dashboard • Datenquelle: Airtable / INFOnline API<br>
    © 2025 Russmedia • Entwickelt als Proof-of-Concept
</div>
""", unsafe_allow_html=True)