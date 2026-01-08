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
# 🔐 AUTHENTICATION - Passwort-Schutz
# =============================================================================
def check_password():
    """Prüft ob der Benutzer das korrekte Passwort eingegeben hat."""
    
    def password_entered():
        """Callback wenn Passwort eingegeben wurde."""
        entered_password = st.session_state.get("password", "")
        correct_password = st.secrets.get("app_password", "")
        
        if entered_password == correct_password:
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # Passwort nicht speichern
        else:
            st.session_state["password_correct"] = False

    # Prüfen ob Passwort in Secrets konfiguriert ist
    # SECURITY: Fail-Closed - Blockiere Zugriff wenn kein Passwort konfiguriert
    if not st.secrets.get("app_password"):
        st.error("❌ SICHERHEITSFEHLER: Kein Passwort konfiguriert!")
        st.error("Bitte 'app_password' in Streamlit Cloud → Settings → Secrets setzen.")
        st.stop()
        return False  # Blockieren statt durchlassen
    
    if "password_correct" not in st.session_state:
        # Erster Aufruf - Passwort-Eingabe anzeigen
        st.markdown("""
        <div style="display: flex; justify-content: center; align-items: center; height: 60vh;">
            <div style="text-align: center; padding: 2rem; background: #f8f9fa; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.1);">
                <h1>🔐 ÖWA Reporting Dashboard</h1>
                <p style="color: #666;">Bitte Passwort eingeben um fortzufahren</p>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.text_input(
                "Passwort", 
                type="password", 
                on_change=password_entered, 
                key="password",
                placeholder="Passwort eingeben..."
            )
            st.caption("🔒 Zugang nur für autorisierte Benutzer")
        return False
    
    elif not st.session_state["password_correct"]:
        # Falsches Passwort eingegeben
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.text_input(
                "Passwort", 
                type="password", 
                on_change=password_entered, 
                key="password",
                placeholder="Passwort eingeben..."
            )
            st.error("❌ Falsches Passwort. Bitte erneut versuchen.")
        return False
    
    else:
        # Passwort korrekt
        return True

# Passwort-Check ausführen - stoppt hier wenn nicht authentifiziert
if not check_password():
    st.stop()

# =============================================================================
# AIRTABLE CONFIG (from Streamlit Secrets)
# =============================================================================
AIRTABLE_API_KEY = st.secrets.get("AIRTABLE_API_KEY", os.getenv("AIRTABLE_API_KEY", ""))
AIRTABLE_BASE_ID = st.secrets.get("AIRTABLE_BASE_ID", os.getenv("AIRTABLE_BASE_ID", ""))  # Muss in Secrets gesetzt sein

# =============================================================================
# DATA LOADING FROM AIRTABLE
# =============================================================================
@st.cache_data(ttl=300)  # Cache for 5 minutes
def load_data_from_airtable():
    """
    Lädt Daten direkt aus Airtable.
    
    WICHTIG: Unterscheidet zwischen täglichen und monatlichen Daten anhand des Unique Key.
    - Tägliche Daten: Unique Key ohne "_MONTH_"
    - Monatliche Daten: Unique Key enthält "_MONTH_"
    
    Returns:
        DataFrame mit zusätzlicher Spalte 'is_monthly' zur Unterscheidung
    """
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
                    unique_key = fields.get("Unique Key", "")
                    # Unterscheide monatliche von täglichen Daten
                    is_monthly = "_MONTH_" in unique_key if unique_key else False
                    
                    all_records.append({
                        "datum": fields.get("Datum"),
                        "brand": fields.get("Brand"),
                        "plattform": fields.get("Plattform"),
                        "metrik": fields.get("Metrik"),
                        "wert": fields.get("Wert"),
                        "site_id": fields.get("Site ID"),
                        "vorlaeufig": fields.get("Vorläufig", False),
                        "unique_key": unique_key,
                        "is_monthly": is_monthly,  # NEU: Markierung für Monatsdaten
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
df_all = load_data_from_airtable()

# Trenne tägliche von monatlichen Daten
# WICHTIG: Verhindert Vermischung von Monatsaggregaten mit Tagesdaten!
if not df_all.empty:
    df = df_all[df_all["is_monthly"] == False].copy()  # Nur Tagesdaten für normale Ansicht
    df_monthly_raw = df_all[df_all["is_monthly"] == True].copy()  # Monatsdaten separat
else:
    df = pd.DataFrame()
    df_monthly_raw = pd.DataFrame()

# Determine available data range (nur aus Tagesdaten)
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

# Show available data range info (inkl. Monatsdaten)
DAILY_DATA_CUTOFF = date.today() - timedelta(days=180)

# Monatsdaten-Range ermitteln
monthly_min_date = None
monthly_max_date = None
if not df_monthly_raw.empty:
    monthly_min_date = df_monthly_raw["datum"].min().date()
    monthly_max_date = df_monthly_raw["datum"].max().date()

# Gesamte Datenspanne (Tages- + Monatsdaten)
overall_min_date = min(data_min_date, monthly_min_date) if monthly_min_date else data_min_date
overall_max_date = max(data_max_date, monthly_max_date) if monthly_max_date else data_max_date

st.sidebar.info(f"📅 **Verfügbare Daten:**\n{overall_min_date.strftime('%d.%m.%Y')} - {overall_max_date.strftime('%d.%m.%Y')}")

# Zusätzliche Info zu Datenquellen
with st.sidebar.expander("ℹ️ Datenverfügbarkeit"):
    st.markdown(f"""
    **Tagesdaten:** {data_min_date.strftime('%d.%m.%Y')} - {data_max_date.strftime('%d.%m.%Y')}
    
    **Monatsdaten:** {'Nicht verfügbar' if monthly_min_date is None else f"{monthly_min_date.strftime('%d.%m.%Y')} - {monthly_max_date.strftime('%d.%m.%Y')}"}
    
    ---
    *Tagesdaten nur für die letzten ~180 Tage verfügbar (API-Limit). Für ältere Zeiträume: Monatsansicht verwenden.*
    """)

# Date range - Messzeitraum
st.sidebar.subheader("📊 Messzeitraum")

# Initialize session state for date range (using widget keys)
# WICHTIG: Verwende overall_min_date um auch Monatsdaten zu berücksichtigen!
if "start_input" not in st.session_state:
    st.session_state.start_input = max(min(date.today(), overall_max_date) - timedelta(days=30), overall_min_date)
if "end_input" not in st.session_state:
    st.session_state.end_input = min(date.today(), overall_max_date)

# Quick select buttons - directly modify widget keys
col_btn1, col_btn2 = st.sidebar.columns(2)
if col_btn1.button("Letzte 7 Tage"):
    st.session_state.start_input = max(date.today() - timedelta(days=7), data_min_date)  # Tagesdaten
    st.session_state.end_input = min(date.today(), data_max_date)
    st.rerun()

if col_btn2.button("Letzte 30 Tage"):
    st.session_state.start_input = max(date.today() - timedelta(days=30), data_min_date)  # Tagesdaten
    st.session_state.end_input = min(date.today(), data_max_date)
    st.rerun()

# Date inputs with widget keys
# WICHTIG: Erlaube Zugriff auf ALLE Daten (Tages- UND Monatsdaten)
col1, col2 = st.sidebar.columns(2)
start_date = col1.date_input("Von", min_value=overall_min_date, max_value=overall_max_date, key="start_input")
end_date = col2.date_input("Bis", min_value=overall_min_date, max_value=overall_max_date, key="end_input")

# Prüfen ob gewählter Zeitraum nur Monatsdaten enthält (vor 180-Tage-Grenze)
uses_monthly_data_only = start_date < DAILY_DATA_CUTOFF and end_date < DAILY_DATA_CUTOFF
uses_mixed_data = start_date < DAILY_DATA_CUTOFF and end_date >= DAILY_DATA_CUTOFF

if uses_monthly_data_only:
    st.sidebar.warning("📆 **Nur Monatsdaten verfügbar** für diesen Zeitraum. Bitte verwende die Monatsansicht im Zeitreihen-Tab.")
elif uses_mixed_data:
    st.sidebar.info(f"📆 **Gemischter Zeitraum:** Tagesdaten ab {DAILY_DATA_CUTOFF.strftime('%d.%m.%Y')}, davor nur Monatsdaten.")

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

# WICHTIG: Verwende overall_min_date für Vergleichszeiträume (inkl. Monatsdaten)
comparison_uses_monthly_only = False

if comparison_mode == "Vorperiode (automatisch)":
    # Automatische Vorperiode = gleich langer Zeitraum direkt davor
    prev_end = start_date - timedelta(days=1)
    prev_start = prev_end - timedelta(days=selected_days - 1)
    
    # Check if comparison period is within available data (inkl. Monatsdaten!)
    if prev_start >= overall_min_date:
        comparison_fully_available = True
        # Prüfen ob Vergleichszeitraum nur Monatsdaten enthält
        if prev_end < DAILY_DATA_CUTOFF:
            comparison_uses_monthly_only = True
            st.sidebar.info(f"📆 Vergleich (Monatsdaten): {prev_start.strftime('%d.%m.')} - {prev_end.strftime('%d.%m.%Y')}")
        elif prev_start < DAILY_DATA_CUTOFF:
            st.sidebar.warning(f"⚠️ Gemischter Vergleich: {prev_start.strftime('%d.%m.')} - {prev_end.strftime('%d.%m.%Y')}\n(Teilweise nur Monatsdaten)")
        else:
            st.sidebar.success(f"✅ Vergleich: {prev_start.strftime('%d.%m.')} - {prev_end.strftime('%d.%m.%Y')}")
    elif prev_end >= overall_min_date:
        comparison_fully_available = False
        actual_prev_start = max(prev_start, overall_min_date)
        actual_days = (prev_end - actual_prev_start).days + 1
        st.sidebar.warning(f"⚠️ Nur {actual_days}/{selected_days} Tage verfügbar:\n{actual_prev_start.strftime('%d.%m.')} - {prev_end.strftime('%d.%m.%Y')}")
        prev_start = actual_prev_start
    else:
        comparison_fully_available = False
        prev_start = None
        prev_end = None
        st.sidebar.error("❌ Keine Vergleichsdaten verfügbar")

elif comparison_mode == "Benutzerdefiniert":
    # Vereinfachte Auswahl: NUR Startdatum, Enddatum wird automatisch berechnet
    # basierend auf der Länge des Messzeitraums
    
    # Spätestes mögliches Startdatum für Vergleich (damit Vergleichszeitraum nicht in Messzeitraum ragt)
    latest_comparison_start = start_date - timedelta(days=selected_days)
    
    if latest_comparison_start >= overall_min_date:
        # Info über den Mechanismus anzeigen
        st.sidebar.info(f"ℹ️ Wähle das Startdatum. Enddatum wird automatisch berechnet (+{selected_days} Tage)")
        
        # Default: gleicher Zeitraum wie "Vorperiode automatisch"
        default_cmp_start = max(start_date - timedelta(days=selected_days), overall_min_date)
        
        # NUR ein Datumsfeld für den Start - erlaube Zugriff auf Monatsdaten
        prev_start = st.sidebar.date_input(
            "Vergleichszeitraum ab", 
            value=default_cmp_start,
            min_value=overall_min_date, 
            max_value=latest_comparison_start,
            key="cmp_start",
            help=f"Das Enddatum wird automatisch auf {selected_days} Tage nach dem Startdatum gesetzt"
        )
        
        # Enddatum automatisch berechnen (gleiche Länge wie Messzeitraum)
        prev_end = prev_start + timedelta(days=selected_days - 1)
        
        # Prüfen ob genug Daten vorhanden sind
        if prev_end <= overall_max_date:
            comparison_fully_available = True
            # Prüfen ob Vergleichszeitraum nur Monatsdaten enthält
            if prev_end < DAILY_DATA_CUTOFF:
                comparison_uses_monthly_only = True
                st.sidebar.info(f"📆 Vergleich (Monatsdaten): {prev_start.strftime('%d.%m.')} - {prev_end.strftime('%d.%m.%Y')} ({selected_days} Tage)")
            elif prev_start < DAILY_DATA_CUTOFF:
                st.sidebar.warning(f"⚠️ Gemischter Vergleich: {prev_start.strftime('%d.%m.')} - {prev_end.strftime('%d.%m.%Y')}\n(Teilweise nur Monatsdaten)")
            else:
                st.sidebar.success(f"✅ Vergleich: {prev_start.strftime('%d.%m.')} - {prev_end.strftime('%d.%m.%Y')} ({selected_days} Tage)")
        else:
            # Falls Enddatum außerhalb der verfügbaren Daten liegt
            comparison_fully_available = False
            actual_end = min(prev_end, overall_max_date)
            actual_days = (actual_end - prev_start).days + 1
            st.sidebar.warning(f"⚠️ Nur {actual_days}/{selected_days} Tage verfügbar:\n{prev_start.strftime('%d.%m.')} - {actual_end.strftime('%d.%m.%Y')}")
            prev_end = actual_end
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

# =============================================================================
# DATENQUELLE BESTIMMEN (Tagesdaten vs. Monatsdaten)
# =============================================================================
# Wenn der Zeitraum vor der 180-Tage-Grenze liegt, müssen Monatsdaten verwendet werden
main_period_uses_monthly = uses_monthly_data_only

if df.empty and df_monthly_raw.empty:
    st.warning("Keine Daten verfügbar. Bitte prüfe die Airtable-Konfiguration.")
    st.stop()

# Filter by date - wähle passende Datenquelle
if main_period_uses_monthly:
    # Nur Monatsdaten verfügbar für diesen Zeitraum
    df_filtered = df_monthly_raw[
        (df_monthly_raw["datum"].dt.date >= start_date) & 
        (df_monthly_raw["datum"].dt.date <= end_date)
    ].copy()
    
    if df_filtered.empty:
        st.warning(f"""
        ⚠️ **Keine Daten für den gewählten Zeitraum ({start_date.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')})**
        
        Für Zeiträume vor dem {DAILY_DATA_CUTOFF.strftime('%d.%m.%Y')} sind nur **Monatsdaten** verfügbar.
        Die Monatsdaten haben das Datum am letzten Tag des jeweiligen Monats (z.B. 31.01.2024 für Januar 2024).
        
        **Tipp:** Wähle einen kompletten Monat (z.B. 01.01.2024 - 31.01.2024) oder nutze die Schnellauswahl.
        """)
else:
    # Tagesdaten verwenden
    df_filtered = df[
        (df["datum"].dt.date >= start_date) & 
        (df["datum"].dt.date <= end_date)
    ].copy()

# Sidebar brand filter
# Ermittle verfügbare Brands aus der passenden Datenquelle
if df_filtered.empty and not main_period_uses_monthly:
    # Fallback: Zeige alle Brands aus den Tagesdaten
    brands = df["brand"].dropna().unique().tolist()
else:
    brands = df_filtered["brand"].dropna().unique().tolist()
selected_brands = st.sidebar.multiselect("Brands", brands, default=brands)
df_filtered = df_filtered[df_filtered["brand"].isin(selected_brands)]

# Sidebar platform filter (NEU: Web/iOS/Android mit App-Aggregation)
st.sidebar.subheader("📱 Plattform-Filter")

# Verfügbare Plattformen ermitteln
raw_platforms = df_filtered["plattform"].dropna().unique().tolist()

# Prüfen ob iOS/Android-Daten vorhanden sind
has_ios = "iOS" in raw_platforms
has_android = "Android" in raw_platforms
has_app_platforms = has_ios or has_android

# Default-Wert für aggregate_app (wird überschrieben wenn iOS/Android vorhanden)
aggregate_app = False

if has_app_platforms:
    # App-Aggregationsoption anbieten
    aggregate_app = st.sidebar.checkbox(
        "📱 iOS + Android als 'App' zusammenfassen",
        value=False,
        help="Aggregiert iOS und Android Daten zu einer kombinierten 'App'-Ansicht"
    )
    
    if aggregate_app:
        # Temporär iOS/Android zu App aggregieren für Anzeige
        df_filtered = df_filtered.copy()
        df_filtered.loc[df_filtered["plattform"].isin(["iOS", "Android"]), "plattform"] = "App"
    
    # Aktualisierte Plattform-Liste nach evtl. Aggregation
    platforms = df_filtered["plattform"].dropna().unique().tolist()
else:
    platforms = raw_platforms

if len(platforms) > 1:
    selected_platforms = st.sidebar.multiselect("Plattform", platforms, default=platforms)
    df_filtered = df_filtered[df_filtered["plattform"].isin(selected_platforms)]
else:
    selected_platforms = platforms

# Sidebar metric filter
metrics = df_filtered["metrik"].dropna().unique().tolist()
selected_metrics = st.sidebar.multiselect("Metriken", metrics, default=metrics)
df_filtered = df_filtered[df_filtered["metrik"].isin(selected_metrics)]

st.sidebar.markdown(f"**{len(df_filtered)} Datensätze**")

# Logout-Button
st.sidebar.markdown("---")
if st.sidebar.button("🚪 Abmelden", use_container_width=True):
    st.session_state["password_correct"] = False
    st.rerun()

# =============================================================================
# VERGLEICHSDATEN VORBEREITEN (für alle Diagramme)
# =============================================================================
# df_prev wird für KPIs UND Diagramme verwendet
# WICHTIG: Nutze Monatsdaten wenn Vergleichszeitraum vor 180-Tage-Grenze liegt
if prev_start is not None and prev_end is not None:
    # Zuerst versuchen: Tagesdaten
    df_prev_daily = df[
        (df["datum"].dt.date >= prev_start) & 
        (df["datum"].dt.date <= prev_end) &
        (df["brand"].isin(selected_brands)) &
        (df["metrik"].isin(selected_metrics)) &
        (df["plattform"].isin(selected_platforms))
    ]
    
    # Falls keine Tagesdaten und Zeitraum vor 180-Tage-Grenze: Monatsdaten verwenden
    if df_prev_daily.empty and comparison_uses_monthly_only and not df_monthly_raw.empty:
        # Filtere Monatsdaten für Vergleichszeitraum
        # Monatsdaten haben das Datum am Ende des Monats (z.B. 31.01.2024 = Januar 2024)
        df_prev_monthly = df_monthly_raw[
            (df_monthly_raw["datum"].dt.date >= prev_start) & 
            (df_monthly_raw["datum"].dt.date <= prev_end) &
            (df_monthly_raw["brand"].isin(selected_brands)) &
            (df_monthly_raw["metrik"].isin(selected_metrics))
        ]
        # Plattform-Filter für Monatsdaten (App = iOS + Android)
        if has_app_platforms and aggregate_app:
            df_prev_monthly = df_prev_monthly.copy()
            df_prev_monthly.loc[df_prev_monthly["plattform"].isin(["iOS", "Android"]), "plattform"] = "App"
        df_prev_monthly = df_prev_monthly[df_prev_monthly["plattform"].isin(selected_platforms)]
        
        df_prev = df_prev_monthly
        comparison_is_monthly = True
    else:
        df_prev = df_prev_daily
        comparison_is_monthly = False
    
    has_comparison = len(df_prev) > 0
else:
    df_prev = pd.DataFrame()
    has_comparison = False
    comparison_is_monthly = False

# Farben für Vergleich
colors_current = {"VOL": "#3B82F6", "Vienna": "#8B5CF6"}
colors_comparison = {"VOL": "#93C5FD", "Vienna": "#C4B5FD"}

# =============================================================================
# KPI CARDS
# =============================================================================
st.subheader("📈 Kennzahlen")

# Calculate all KPIs (erweitert für UC und HP-PI)
pi_total = df_filtered[df_filtered["metrik"] == "Page Impressions"]["wert"].sum()
visits_total = df_filtered[df_filtered["metrik"] == "Visits"]["wert"].sum()
uc_total = df_filtered[df_filtered["metrik"] == "Unique Clients"]["wert"].sum()
hp_pi_total = df_filtered[df_filtered["metrik"] == "Homepage PI"]["wert"].sum()

days = (end_date - start_date).days or 1
pi_avg = pi_total / days
visits_avg = visits_total / days
uc_avg = uc_total / days
hp_pi_avg = hp_pi_total / days

# Erste Zeile: PI und Visits
col1, col2, col3, col4 = st.columns(4)

# Calculate period-over-period change using the comparison period from sidebar
# HINWEIS: df_prev wurde bereits oben vorbereitet (inkl. Monatsdaten-Fallback)
if prev_start is not None and prev_end is not None and has_comparison:
    # Berechne Vergleichsdaten (df_prev wurde bereits oben definiert!)
    prev_days_with_data = df_prev["datum"].dt.date.nunique()
    comparison_days = (prev_end - prev_start).days + 1
    
    pi_prev = df_prev[df_prev["metrik"] == "Page Impressions"]["wert"].sum()
    visits_prev = df_prev[df_prev["metrik"] == "Visits"]["wert"].sum()

    # Vergleichstext basierend auf Modus
    if comparison_mode == "Benutzerdefiniert":
        period_label = f"vs. {prev_start.strftime('%d.%m.')}-{prev_end.strftime('%d.%m.')}"
    else:
        period_label = "vs. Vorperiode"
    
    # Hinweis wenn Monatsdaten verwendet werden
    if comparison_is_monthly:
        period_label += " (Monatsdaten)"
    elif prev_days_with_data < comparison_days:
        # Zusätzlicher Hinweis bei unvollständigen Daten
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
    # Kein Vergleich ausgewählt oder keine Daten
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

# Zweite Zeile: UC und HP-PI (wenn Daten vorhanden)
if uc_total > 0 or hp_pi_total > 0:
    # Berechne Vergleichsdaten für UC und HP-PI
    if prev_start is not None and prev_end is not None:
        uc_prev = df_prev[df_prev["metrik"] == "Unique Clients"]["wert"].sum()
        hp_pi_prev = df_prev[df_prev["metrik"] == "Homepage PI"]["wert"].sum()
        
        if uc_prev > 0:
            uc_change = ((uc_total - uc_prev) / uc_prev * 100)
            uc_delta_text = f"{uc_change:+.1f}% {period_label}"
        else:
            uc_delta_text = "↑ Keine Vergleichsdaten"
        
        if hp_pi_prev > 0:
            hp_pi_change = ((hp_pi_total - hp_pi_prev) / hp_pi_prev * 100)
            hp_pi_delta_text = f"{hp_pi_change:+.1f}% {period_label}"
        else:
            hp_pi_delta_text = "↑ Keine Vergleichsdaten"
    else:
        uc_delta_text = None
        hp_pi_delta_text = None
    
    col5, col6, col7, col8 = st.columns(4)
    
    with col5:
        if uc_total > 0:
            st.metric(
                label="Unique Clients (Gesamt)",
                value=f"{uc_total:,.0f}".replace(",", "."),
                delta=uc_delta_text
            )
    
    with col6:
        if hp_pi_total > 0:
            st.metric(
                label="Homepage PI (Gesamt)",
                value=f"{hp_pi_total:,.0f}".replace(",", "."),
                delta=hp_pi_delta_text
            )
    
    with col7:
        if uc_total > 0:
            st.metric(
                label="Ø Unique Clients / Tag",
                value=f"{uc_avg:,.0f}".replace(",", ".")
            )
    
    with col8:
        if hp_pi_total > 0:
            st.metric(
                label="Ø Homepage PI / Tag",
                value=f"{hp_pi_avg:,.0f}".replace(",", ".")
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
    
    # Vergleichsinfo anzeigen
    if has_comparison:
        st.info(f"📅 Vergleich: **Aktuell** ({start_date.strftime('%d.%m.')}-{end_date.strftime('%d.%m.')}) vs. **Vorperiode** ({prev_start.strftime('%d.%m.')}-{prev_end.strftime('%d.%m.')})")
    
    # Brand comparison - Aktueller Zeitraum
    brand_summary = df_filtered.groupby(["brand", "metrik"])["wert"].sum().reset_index()
    brand_summary["periode"] = "Aktuell"
    
    # Vergleichszeitraum hinzufügen wenn verfügbar
    if has_comparison:
        brand_summary_prev = df_prev.groupby(["brand", "metrik"])["wert"].sum().reset_index()
        brand_summary_prev["periode"] = "Vergleich"
        brand_combined = pd.concat([brand_summary, brand_summary_prev], ignore_index=True)
    else:
        brand_combined = brand_summary
    
    # Dynamische Diagramme für alle ausgewählten Metriken
    # Farben pro Metrik
    metric_colors = {
        "Page Impressions": {"Aktuell": "#3B82F6", "Vergleich": "#93C5FD"},
        "Visits": {"Aktuell": "#8B5CF6", "Vergleich": "#C4B5FD"},
        "Unique Clients": {"Aktuell": "#10B981", "Vergleich": "#6EE7B7"},
        "Homepage PI": {"Aktuell": "#F59E0B", "Vergleich": "#FCD34D"}
    }
    
    # Metriken in der richtigen Reihenfolge anzeigen
    metric_order = ["Page Impressions", "Visits", "Unique Clients", "Homepage PI"]
    available_metrics = [m for m in metric_order if m in selected_metrics]
    
    # Anzahl der Spalten bestimmen (max 2 pro Zeile)
    if len(available_metrics) > 0:
        for i in range(0, len(available_metrics), 2):
            cols = st.columns(2)
            for j, metric in enumerate(available_metrics[i:i+2]):
                metric_data = brand_combined[brand_combined["metrik"] == metric]
                colors_for_metric = metric_colors.get(metric, {"Aktuell": "#666", "Vergleich": "#999"})
                
                with cols[j]:
                    if not metric_data.empty:
                        if has_comparison:
                            fig = px.bar(
                                metric_data,
                                x="brand",
                                y="wert",
                                color="periode",
                                barmode="group",
                                title=f"{metric} nach Brand",
                                color_discrete_map=colors_for_metric
                            )
                        else:
                            fig = px.bar(
                                metric_data,
                                x="brand",
                                y="wert",
                                color="brand",
                                title=f"{metric} nach Brand",
                                color_discrete_map=colors_current
                            )
                            fig.update_layout(showlegend=False)
                        fig.update_layout(yaxis=dict(tickformat=","))
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.info(f"Keine {metric} Daten für den ausgewählten Zeitraum.")
    else:
        st.info("Keine Metriken ausgewählt.")
    
    # Wochentags-Analyse nach Brand (VOL vs Vienna)
    st.subheader("📅 Wochentags-Analyse nach Property")
    
    # Deutsche Wochentags-Namen
    weekday_map = {
        "Monday": "Montag", "Tuesday": "Dienstag", "Wednesday": "Mittwoch",
        "Thursday": "Donnerstag", "Friday": "Freitag", "Saturday": "Samstag", "Sunday": "Sonntag"
    }
    
    # Aktueller Zeitraum vorbereiten
    df_weekday = df_filtered.copy()
    df_weekday["wochentag"] = df_weekday["datum"].dt.dayofweek
    df_weekday["wochentag_name"] = df_weekday["datum"].dt.day_name()
    df_weekday["wochentag_de"] = df_weekday["wochentag_name"].map(weekday_map)
    df_weekday["periode"] = "Aktuell"
    
    # Vergleichszeitraum hinzufügen wenn verfügbar
    if has_comparison:
        df_weekday_prev = df_prev.copy()
        df_weekday_prev["wochentag"] = df_weekday_prev["datum"].dt.dayofweek
        df_weekday_prev["wochentag_name"] = df_weekday_prev["datum"].dt.day_name()
        df_weekday_prev["wochentag_de"] = df_weekday_prev["wochentag_name"].map(weekday_map)
        df_weekday_prev["periode"] = "Vergleich"
        df_weekday_combined = pd.concat([df_weekday, df_weekday_prev], ignore_index=True)
    else:
        df_weekday_combined = df_weekday
    
    # Durchschnitt pro Wochentag, Brand UND Periode berechnen
    weekday_avg = df_weekday_combined.groupby(["wochentag", "wochentag_de", "brand", "metrik", "periode"])["wert"].mean().reset_index()
    weekday_avg = weekday_avg.sort_values("wochentag")
    
    # Farben für Kombination aus Brand und Periode
    if has_comparison:
        # Separate Farben für jede Brand-Periode-Kombination
        weekday_avg["brand_periode"] = weekday_avg["brand"] + " " + weekday_avg["periode"]
        brand_periode_colors = {
            "VOL Aktuell": "#3B82F6", "VOL Vergleich": "#93C5FD",
            "Vienna Aktuell": "#8B5CF6", "Vienna Vergleich": "#C4B5FD"
        }
    
    if not weekday_avg.empty:
        # Dynamische Wochentags-Diagramme für alle ausgewählten Metriken
        for i in range(0, len(available_metrics), 2):
            cols = st.columns(2)
            for j, metric in enumerate(available_metrics[i:i+2]):
                metric_weekday = weekday_avg[weekday_avg["metrik"] == metric]
                
                with cols[j]:
                    if not metric_weekday.empty:
                        if has_comparison:
                            fig_week = px.bar(
                                metric_weekday,
                                x="wochentag_de",
                                y="wert",
                                color="brand_periode",
                                barmode="group",
                                title=f"Ø {metric} pro Wochentag",
                                color_discrete_map=brand_periode_colors,
                                category_orders={"brand_periode": ["VOL Aktuell", "VOL Vergleich", "Vienna Aktuell", "Vienna Vergleich"]}
                            )
                        else:
                            fig_week = px.bar(
                                metric_weekday,
                                x="wochentag_de",
                                y="wert",
                                color="brand",
                                barmode="group",
                                title=f"Ø {metric} pro Wochentag",
                                color_discrete_map=colors_current
                            )
                        fig_week.update_layout(
                            yaxis=dict(tickformat=","),
                            xaxis_title="",
                            legend_title="Property",
                            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                        )
                        st.plotly_chart(fig_week, use_container_width=True)
        
        # Insights: Bester und schlechtester Tag PRO BRAND (nur für aktuellen Zeitraum)
        # Verwende die erste verfügbare Metrik für Insights
        primary_metric = available_metrics[0] if available_metrics else "Page Impressions"
        st.markdown(f"**📈 Erkenntnisse ({primary_metric} - Aktueller Zeitraum):**")
        
        # Nur aktuelle Periode für Insights
        insight_data = weekday_avg[(weekday_avg["metrik"] == primary_metric) & (weekday_avg["periode"] == "Aktuell")]
        if not insight_data.empty:
            unique_brands = insight_data["brand"].unique()
            insights_cols = st.columns(len(unique_brands)) if len(unique_brands) > 0 else [st]
            
            for idx, brand in enumerate(sorted(unique_brands)):
                brand_data = insight_data[insight_data["brand"] == brand]
                if not brand_data.empty:
                    best_day = brand_data.loc[brand_data["wert"].idxmax()]
                    worst_day = brand_data.loc[brand_data["wert"].idxmin()]
                    avg_brand = brand_data["wert"].mean()
                    
                    best_pct = ((best_day["wert"] - avg_brand) / avg_brand * 100) if avg_brand > 0 else 0
                    worst_pct = ((worst_day["wert"] - avg_brand) / avg_brand * 100) if avg_brand > 0 else 0
                    
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
    # =========================================================================
    # 180-TAGE CUTOFF LOGIK
    # =========================================================================
    # INFOnline API liefert Tagesdaten nur für die letzten ~180 Tage
    DAILY_DATA_DAYS_LIMIT = 180
    daily_data_cutoff = date.today() - timedelta(days=DAILY_DATA_DAYS_LIMIT)
    
    # Prüfen ob ausgewählter Zeitraum außerhalb der Tagesdaten-Verfügbarkeit liegt
    daily_data_available = start_date >= daily_data_cutoff
    daily_data_partially_available = start_date < daily_data_cutoff <= end_date
    daily_data_unavailable = end_date < daily_data_cutoff
    
    # Gruppierungsauswahl: Brand oder Plattform
    col_group, col_agg = st.columns([1, 1])
    
    with col_group:
        grouping_mode = st.radio(
            "📊 Gruppierung",
            ["🏢 Nach Brand (VOL/Vienna)", "📱 Nach Plattform (iOS/Android/Web)"],
            index=0,
            horizontal=True,
            help="Wähle ob die Daten nach Brand oder nach Plattform gruppiert werden sollen"
        )
    
    is_platform_view = "Plattform" in grouping_mode
    
    # Dynamischer Titel basierend auf Gruppierung
    if is_platform_view:
        st.subheader("📈 Zeitreihen-Analyse nach Plattform")
    else:
        st.subheader("📈 Zeitreihen-Analyse nach Property")
    
    # Aggregationsauswahl: Tag oder Monat
    with col_agg:
        if daily_data_unavailable:
            # Tagesansicht komplett deaktiviert - nur Monatsdaten verfügbar
            st.warning(f"⚠️ Für Zeiträume vor dem {daily_data_cutoff.strftime('%d.%m.%Y')} sind nur **Monatsdaten** verfügbar.")
            aggregation_mode = "📆 Monatsansicht"
            st.radio(
                "⏱️ Aggregation",
                ["📆 Monatsansicht"],
                index=0,
                horizontal=True,
                disabled=True,
                help="Tagesdaten nur für die letzten 180 Tage verfügbar"
            )
        elif daily_data_partially_available:
            # Gemischter Zeitraum - Hinweis anzeigen
            st.info(f"ℹ️ Tagesdaten ab {daily_data_cutoff.strftime('%d.%m.%Y')} verfügbar. Für ältere Daten: Monatsansicht nutzen.")
            aggregation_mode = st.radio(
                "⏱️ Aggregation",
                ["📅 Tagesansicht", "📆 Monatsansicht"],
                index=0,
                horizontal=True,
                help=f"Tagesdaten nur ab {daily_data_cutoff.strftime('%d.%m.%Y')} verfügbar"
            )
        else:
            # Volle Tagesdaten-Verfügbarkeit
            aggregation_mode = st.radio(
                "⏱️ Aggregation",
                ["📅 Tagesansicht", "📆 Monatsansicht"],
                index=0,
                horizontal=True
            )
    
    is_monthly = aggregation_mode == "📆 Monatsansicht"
    
    # Farben für Properties (Brands)
    property_colors = {
        "VOL": {"current": "#3B82F6", "comparison": "#93C5FD"},      # Blau
        "Vienna": {"current": "#8B5CF6", "comparison": "#C4B5FD"}    # Lila
    }
    
    # NEU: Farben für Plattformen
    platform_colors = {
        "iOS": {"current": "#10B981", "comparison": "#6EE7B7"},       # Grün
        "Android": {"current": "#F59E0B", "comparison": "#FCD34D"},   # Orange
        "Web": {"current": "#3B82F6", "comparison": "#93C5FD"},       # Blau
        "App": {"current": "#8B5CF6", "comparison": "#C4B5FD"}        # Lila (für aggregierte App)
    }
    
    if is_monthly:
        # =====================================================================
        # MONATSANSICHT
        # =====================================================================
        st.info("📆 **Monatsansicht:** Daten werden pro Monat aggregiert. Die Balken zeigen die **Veränderung zum Vormonat** (MoM).")
        
        # Hinweis zu YoY
        st.caption("ℹ️ *Year-over-Year (YoY) Vergleiche werden verfügbar sein, sobald Daten für mindestens 12 Monate vorliegen (voraussichtlich ab Juni 2026).*")
        
        # Hinweis zur Datenquelle
        if not df_monthly_raw.empty:
            monthly_count = len(df_monthly_raw)
            st.caption(f"📊 *{monthly_count} echte Monatsdaten aus ÖWA API verfügbar (ab Jan 2024)*")
        
        # Gruppierungsspalte bestimmen
        group_col = "plattform" if is_platform_view else "brand"
        colors_map = platform_colors if is_platform_view else property_colors
        group_label = "Plattform" if is_platform_view else "Brand"
        
        # Verfügbare Gruppen ermitteln
        if is_platform_view:
            # Prüfe beide Datenquellen für verfügbare Plattformen
            daily_platforms = df_filtered[group_col].unique().tolist() if not df_filtered.empty else []
            monthly_platforms = df_monthly_raw[group_col].unique().tolist() if not df_monthly_raw.empty else []
            all_platforms = list(set(daily_platforms + monthly_platforms))
            available_groups = [p for p in ["iOS", "Android", "Web", "App"] if p in all_platforms]
        else:
            available_groups = ["VOL", "Vienna"]
        
        # =====================================================================
        # HYBRID DATENQUELLEN: Echte Monatsdaten + aggregierte Tagesdaten
        # =====================================================================
        # Priorität: Echte Monatsdaten (df_monthly_raw) für ältere Perioden,
        # aggregierte Tagesdaten (df) für aktuelle Perioden
        
        # 1. Echte Monatsdaten aus Airtable (mit _MONTH_ im Key)
        monthly_from_api = df_monthly_raw[
            (df_monthly_raw["brand"].isin(selected_brands)) &
            (df_monthly_raw["metrik"].isin(selected_metrics)) &
            (df_monthly_raw["plattform"].isin(selected_platforms))
        ].copy() if not df_monthly_raw.empty else pd.DataFrame()
        
        # 2. Tagesdaten zu Monatsdaten aggregieren (für Überlappungsperioden)
        daily_for_monthly = df[
            (df["brand"].isin(selected_brands)) &
            (df["metrik"].isin(selected_metrics)) &
            (df["plattform"].isin(selected_platforms))
        ].copy()
        
        # Kombiniere beide Datenquellen
        has_api_monthly = not monthly_from_api.empty
        has_daily_data = not daily_for_monthly.empty
        
        if not has_api_monthly and not has_daily_data:
            st.warning("Keine Daten für die ausgewählten Filter verfügbar.")
        else:
            monthly_parts = []
            
            # Echte Monatsdaten verarbeiten
            if has_api_monthly:
                monthly_from_api["monat"] = monthly_from_api["datum"].dt.to_period("M")
                monthly_from_api["monat_start"] = monthly_from_api["monat"].dt.to_timestamp()
                monthly_from_api["monat_label"] = monthly_from_api["datum"].dt.strftime("%b %Y")
                monthly_from_api["datenquelle"] = "API Monatsdaten"
                # Echte Monatsdaten sind bereits Summen pro Monat
                monthly_api_agg = monthly_from_api.groupby(
                    ["monat_start", "monat_label", "metrik", group_col, "datenquelle"]
                )["wert"].sum().reset_index()
                monthly_parts.append(monthly_api_agg)
            
            # Tagesdaten zu Monatssummen aggregieren
            if has_daily_data:
                daily_for_monthly["monat"] = daily_for_monthly["datum"].dt.to_period("M")
                daily_for_monthly["monat_start"] = daily_for_monthly["monat"].dt.to_timestamp()
                daily_for_monthly["monat_label"] = daily_for_monthly["datum"].dt.strftime("%b %Y")
                daily_for_monthly["datenquelle"] = "Tagesdaten aggregiert"
                daily_agg = daily_for_monthly.groupby(
                    ["monat_start", "monat_label", "metrik", group_col, "datenquelle"]
                )["wert"].sum().reset_index()
                monthly_parts.append(daily_agg)
            
            # Kombinieren und Duplikate entfernen (API Monatsdaten haben Priorität)
            monthly_combined = pd.concat(monthly_parts, ignore_index=True)
            
            # Bei Duplikaten: Echte API-Monatsdaten bevorzugen
            monthly_combined = monthly_combined.sort_values(
                ["monat_start", group_col, "metrik", "datenquelle"],
                ascending=[True, True, True, True]  # "API Monatsdaten" < "Tagesdaten aggregiert"
            )
            monthly_agg = monthly_combined.drop_duplicates(
                subset=["monat_start", group_col, "metrik"],
                keep="first"  # Behalte API-Daten wenn verfügbar
            )
            monthly_agg = monthly_agg.sort_values("monat_start")
            
            # Für jede Metrik ein Diagramm
            for metrik in selected_metrics:
                metric_data = monthly_agg[monthly_agg["metrik"] == metrik]
                
                if metric_data.empty:
                    st.info(f"Keine {metrik} Monatsdaten verfügbar.")
                    continue
                
                fig = go.Figure()
                
                for group in available_groups:
                    group_data = metric_data[metric_data[group_col] == group].copy()
                    colors = colors_map.get(group, {"current": "#666", "comparison": "#999"})
                    
                    if not group_data.empty:
                        group_data = group_data.sort_values("monat_start")
                        
                        # Berechne MoM-Änderung
                        group_data["mom_change"] = group_data["wert"].pct_change() * 100
                        
                        # Hole den Vormonatsnamen für den Tooltip
                        group_data["vormonat"] = group_data["monat_label"].shift(1)
                        
                        # Marker-Symbol basierend auf Datenquelle
                        # API Monatsdaten: Kreis (circle), Tagesdaten aggregiert: Raute (diamond)
                        if "datenquelle" in group_data.columns:
                            marker_symbols = [
                                "circle" if src == "API Monatsdaten" else "diamond" 
                                for src in group_data["datenquelle"]
                            ]
                            # Hover-Text mit Datenquelle
                            hover_texts = [
                                f"<b>{group}</b><br>{row['monat_label']}<br>Wert: {row['wert']:,.0f}<br><i>({row['datenquelle']})</i>".replace(",", ".")
                                for _, row in group_data.iterrows()
                            ]
                        else:
                            marker_symbols = "circle"
                            hover_texts = group_data["wert"].apply(lambda x: f"{x:,.0f}".replace(",", "."))
                        
                        fig.add_trace(go.Scatter(
                            x=group_data["monat_start"],
                            y=group_data["wert"],
                            mode="lines+markers",
                            name=f"{group}",
                            line=dict(color=colors["current"], width=3),
                            marker=dict(size=10, symbol=marker_symbols),
                            text=hover_texts,
                            hovertemplate="%{text}<extra></extra>"
                        ))
                        
                        # MoM-Balken mit klarer Beschriftung (Veränderung zum Vormonat)
                        if len(group_data) > 1:
                            mom_data = group_data[group_data["mom_change"].notna()].copy()
                            if not mom_data.empty:
                                bar_colors = ["#10B981" if x >= 0 else "#EF4444" for x in mom_data["mom_change"]]
                                fig.add_trace(go.Bar(
                                    x=mom_data["monat_start"],
                                    y=mom_data["mom_change"],
                                    name=f"{group} Δ Vormonat",
                                    marker_color=bar_colors,
                                    opacity=0.3,
                                    yaxis="y2",
                                    showlegend=True,
                                    text=mom_data["mom_change"].apply(lambda x: f"{x:+.1f}%"),
                                    hovertemplate=f"<b>{group}</b><br>" +
                                                  "%{x|%B %Y}<br>" +
                                                  "Veränderung vs. Vormonat: %{text}<br>" +
                                                  "<extra></extra>"
                                ))
                
                fig.update_layout(
                    title=f"{metrik} - Monatstrend nach {group_label}",
                    yaxis=dict(
                        title="Wert",
                        tickformat=",",
                        side="left"
                    ),
                    yaxis2=dict(
                        title="Δ Vormonat (%)",
                        overlaying="y",
                        side="right",
                        showgrid=False,
                        zeroline=True,
                        zerolinecolor="#999",
                        zerolinewidth=2,
                        range=[-50, 50]
                    ),
                    xaxis=dict(
                        tickformat="%b %Y",
                        dtick="M1",
                        tickangle=-45
                    ),
                    xaxis_title="Monat",
                    legend=dict(
                        orientation="h",
                        yanchor="bottom",
                        y=1.02,
                        xanchor="right",
                        x=1
                    ),
                    hovermode="x unified",
                    barmode="group"
                )
                st.plotly_chart(fig, use_container_width=True)
            
            # MoM-Tabelle (formatiert!)
            st.markdown("### 📊 Monatsvergleich")
            st.caption(f"Werte = Monatssumme | Δ = Veränderung zum Vormonat in % | Gruppiert nach: {group_label}")
            
            # Bessere Tabelle: Für jede Metrik/Gruppe eine MoM-Berechnung
            table_data = []
            
            for _, row in monthly_agg.iterrows():
                monat = row["monat_start"]
                label = row["monat_label"]
                group = row[group_col]
                metrik = row["metrik"]
                wert = row["wert"]
                
                # Vormonat suchen
                vormonat = monat - pd.DateOffset(months=1)
                prev_row = monthly_agg[
                    (monthly_agg["monat_start"] == vormonat) &
                    (monthly_agg[group_col] == group) &
                    (monthly_agg["metrik"] == metrik)
                ]
                
                if not prev_row.empty:
                    prev_wert = prev_row["wert"].values[0]
                    if prev_wert > 0:
                        mom_pct = ((wert - prev_wert) / prev_wert) * 100
                    else:
                        mom_pct = None
                else:
                    mom_pct = None
                
                table_data.append({
                    "Monat": label,
                    group_label: group,
                    "Metrik": metrik,
                    "Wert": f"{wert:,.0f}".replace(",", "."),
                    "Δ Vormonat": f"{mom_pct:+.1f}%" if mom_pct is not None else "—"
                })
            
            df_table = pd.DataFrame(table_data)
            
            # Pivot für bessere Lesbarkeit
            if not df_table.empty:
                # Sortiere absteigend nach Datum
                df_table["_sort"] = pd.to_datetime(df_table["Monat"], format="%b %Y")
                df_table = df_table.sort_values(["_sort", group_label, "Metrik"], ascending=[False, True, True])
                df_table = df_table.drop("_sort", axis=1)
                
                st.dataframe(df_table.head(48), use_container_width=True, hide_index=True)
    
    else:
        # =====================================================================
        # TAGESANSICHT
        # =====================================================================
        # Vergleichsinfo anzeigen
        if has_comparison:
            st.info(f"📅 Vergleich: **Durchgezogen** = Aktuell ({start_date.strftime('%d.%m.')}-{end_date.strftime('%d.%m.')}) | **Gestrichelt** = Vorperiode ({prev_start.strftime('%d.%m.')}-{prev_end.strftime('%d.%m.')})")
        
        # Gruppierungsspalte bestimmen
        group_col = "plattform" if is_platform_view else "brand"
        colors_map = platform_colors if is_platform_view else property_colors
        group_label = "Plattform" if is_platform_view else "Property"
        
        # Verfügbare Gruppen ermitteln
        if is_platform_view:
            available_groups = [p for p in ["iOS", "Android", "Web", "App"] if p in df_filtered[group_col].unique()]
        else:
            available_groups = ["VOL", "Vienna"]
        
        # Daten pro Tag aggregieren - Aktueller Zeitraum
        daily = df_filtered.copy()
        daily["datum_tag"] = daily["datum"].dt.date
        daily = daily.groupby(["datum_tag", "metrik", group_col])["wert"].sum().reset_index()
        daily["datum_tag"] = pd.to_datetime(daily["datum_tag"])
        daily["periode"] = "Aktuell"
        
        # Vergleichszeitraum vorbereiten (Daten auf X-Achse des aktuellen Zeitraums verschieben)
        if has_comparison:
            daily_prev = df_prev.copy()
            daily_prev["datum_tag"] = daily_prev["datum"].dt.date
            daily_prev = daily_prev.groupby(["datum_tag", "metrik", group_col])["wert"].sum().reset_index()
            daily_prev["datum_tag"] = pd.to_datetime(daily_prev["datum_tag"])
            daily_prev["periode"] = "Vergleich"
            
            # Verschiebung berechnen: Vergleichsdaten auf X-Achse des aktuellen Zeitraums mappen
            day_offset = (pd.Timestamp(start_date) - pd.Timestamp(prev_start)).days
            daily_prev["datum_tag_shifted"] = daily_prev["datum_tag"] + pd.Timedelta(days=day_offset)
    
        if daily.empty:
            st.info("Keine Daten für den ausgewählten Zeitraum.")
        else:
            # Dynamische Zeitreihen für alle ausgewählten Metriken
            for metrik in selected_metrics:
                metric_data = daily[daily["metrik"] == metrik].sort_values("datum_tag")
                
                if metric_data.empty:
                    st.info(f"Keine {metrik} Daten verfügbar.")
                    continue
                
                fig = go.Figure()
                
                # Für jede Gruppe (Brand oder Plattform) eine eigene Linie
                for group in available_groups:
                    group_data = metric_data[metric_data[group_col] == group].copy()
                    colors = colors_map.get(group, {"current": "#666", "comparison": "#999"})
                    
                    if not group_data.empty:
                        group_data = group_data.sort_values("datum_tag")
                        
                        # Aktueller Zeitraum - Kräftige durchgezogene Linie
                        fig.add_trace(go.Scatter(
                            x=group_data["datum_tag"],
                            y=group_data["wert"],
                            mode="lines+markers",
                            name=f"{group} Aktuell",
                            line=dict(color=colors["current"], width=2),
                            marker=dict(size=6),
                            legendgroup=f"{group}_current"
                        ))
                    
                    # Vergleichszeitraum hinzufügen wenn verfügbar
                    if has_comparison:
                        metric_data_prev = daily_prev[daily_prev["metrik"] == metrik]
                        group_data_prev = metric_data_prev[metric_data_prev[group_col] == group].copy()
                        
                        if not group_data_prev.empty:
                            group_data_prev = group_data_prev.sort_values("datum_tag_shifted")
                            
                            # Vergleichszeitraum - Gestrichelte hellere Linie
                            fig.add_trace(go.Scatter(
                                x=group_data_prev["datum_tag_shifted"],
                                y=group_data_prev["wert"],
                                mode="lines+markers",
                                name=f"{group} Vergleich",
                                line=dict(color=colors["comparison"], width=2, dash="dash"),
                                marker=dict(size=4, symbol="diamond"),
                                legendgroup=f"{group}_comparison",
                                opacity=0.8
                            ))
                
                fig.update_layout(
                    title=f"{metrik} - Trend nach {group_label}" + (" (mit Vergleichszeitraum)" if has_comparison else ""),
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
    
    # Datenquellen-Legende für Monatsansicht
    if is_monthly:
        st.markdown("**Datenquellen-Kennzeichnung:**")
        col_src1, col_src2 = st.columns(2)
        with col_src1:
            st.markdown("⚫ **Kreis-Marker** — Echte ÖWA Monatsdaten (API)")
        with col_src2:
            st.markdown("◆ **Rauten-Marker** — Aus Tagesdaten aggregiert")
        st.caption("*Für Zeiträume vor 180 Tagen sind nur echte Monatsdaten aus der ÖWA API verfügbar.*")
        st.markdown("---")
    
    if is_platform_view:
        # Plattform-Legende
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown("🟢 **iOS** - Apple App Store")
        with col2:
            st.markdown("🟠 **Android** - Google Play Store")
        with col3:
            st.markdown("🔵 **Web** - Browser-Zugriffe")
    else:
        # Brand-Legende
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