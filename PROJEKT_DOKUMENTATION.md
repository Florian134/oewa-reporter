# ÖWA Reporter - Projekt Dokumentation
## Vollständiger Entwicklungsverlauf

**Erstellt:** 03.12.2025  
**Projekt:** ÖWA/INFOnline Web-Analytics Reporting System  
**Entwickelt für:** Russmedia (VOL.AT & VIENNA.AT)

---

## 📋 Inhaltsverzeichnis

1. [Projektübersicht](#1-projektübersicht)
2. [Architektur](#2-architektur)
3. [Implementierte Features](#3-implementierte-features)
4. [Technischer Stack](#4-technischer-stack)
5. [Deployment](#5-deployment)
6. [Konfiguration](#6-konfiguration)
7. [Fehlerbehebungen](#7-fehlerbehebungen)
8. [Wichtige Dateien](#8-wichtige-dateien)
9. [Nächste Schritte](#9-nächste-schritte)

---

## 1. Projektübersicht

### Ziel
Entwicklung eines Proof-of-Concept (PoC) für ein ÖWA/INFOnline-Reporting-System, das:
- Tägliche Web-Analytics Daten von VOL.AT und VIENNA.AT abruft
- Daten in Airtable speichert
- Anomalie-Erkennung durchführt
- Wöchentliche/monatliche Reports mit GPT-Zusammenfassungen erstellt
- Benachrichtigungen via MS Teams Webhook sendet
- Ein interaktives Streamlit Dashboard bereitstellt

### Stakeholder
- **Pilot-Nutzer:** Florian Ramsebner, Dominic Depaoli
- **Zielgruppe:** Geschäftsleitung Russmedia

---

## 2. Architektur

### Hybrid-Architektur (Final)

```
┌─────────────────────────────────────────────────────────────────┐
│                        AIRTABLE                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐   │
│  │ Measurements │  │    Alerts    │  │   Weekly Reports     │   │
│  │   (Daten)    │  │  (Anomalien) │  │  (Zusammenfassungen) │   │
│  └──────────────┘  └──────────────┘  └──────────────────────┘   │
│                            │                                     │
│         Airtable Automations (Trigger)                          │
└─────────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                     GITLAB CI/CD                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐   │
│  │ Daily Ingest │  │Weekly Report │  │   Monthly Report     │   │
│  │   (Python)   │  │   (Python)   │  │     (Python)         │   │
│  └──────────────┘  └──────────────┘  └──────────────────────┘   │
│                             │                                    │
│         Pipeline Trigger via API                                 │
└─────────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    EXTERNE SERVICES                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐   │
│  │INFOnline API │  │  OpenAI GPT  │  │  MS Teams Webhook    │   │
│  │   (Daten)    │  │ (Summaries)  │  │  (Notifications)     │   │
│  └──────────────┘  └──────────────┘  └──────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                   STREAMLIT CLOUD                                │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              Interaktives Dashboard                       │   │
│  │   - KPI Cards (PI, Visits, Durchschnitte)                │   │
│  │   - Brand-Vergleich Charts                                │   │
│  │   - Zeitreihen-Analyse mit 7-Tage-Durchschnitt           │   │
│  │   - Datentabelle mit Suche & Export                      │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Implementierte Features

### ✅ Abgeschlossen

| Feature | Beschreibung | Status |
|---------|-------------|--------|
| API Testing | INFOnline Reporting API Tester mit pytest | ✅ |
| Daily Ingestion | Täglicher Datenabruf für VOL.AT & VIENNA.AT | ✅ |
| Airtable Integration | Speicherung aller Messdaten in Airtable | ✅ |
| 30-Tage Backfill | Historische Daten der letzten 30 Tage | ✅ |
| Anomalie-Erkennung | Z-Score basierte Erkennung (MAD/Median) | ✅ |
| GPT Summaries | KI-generierte Wochenberichte | ✅ |
| Teams Notifications | Webhook-basierte Benachrichtigungen | ✅ |
| Streamlit Dashboard | Interaktives Web-Dashboard | ✅ |
| Airtable Automations | Automatische Trigger für Daily/Weekly | ✅ |
| GitLab CI/CD | Pipeline für Python-Code Ausführung | ✅ |
| Streamlit Cloud Deploy | Dashboard online verfügbar | ✅ |

### 📊 Metriken

- **Page Impressions** (PI)
- **Visits**

### 🌐 Sites

- **VOL.AT Web** (Site ID: `at_w_atvol`)
- **VIENNA.AT Web** (Site ID: `at_w_atvienna`)

---

## 4. Technischer Stack

### Backend (GitLab CI/CD)
- **Python 3.11**
- **requests** - HTTP Client für API Calls
- **python-dotenv** - Environment Variables
- **openai** - GPT API Integration

### Datenbank
- **Airtable** - Primäre Datenspeicherung
  - Base ID: `appTIeod85xnBy7Vn`
  - Tabellen: Measurements, Alerts, Weekly Reports

### Frontend
- **Streamlit 1.51.0** - Dashboard Framework
- **Plotly 6.5.0** - Interaktive Charts
- **Pandas** - Datenverarbeitung

### Externe APIs
- **INFOnline Reporting API** - Web-Analytics Daten
- **OpenAI GPT-4** - KI Zusammenfassungen
- **MS Teams Webhook** - Benachrichtigungen
- **Airtable API** - Datenspeicherung

### CI/CD & Hosting
- **GitLab** - Repository & CI/CD Pipelines
- **Streamlit Cloud** - Dashboard Hosting
- **Airtable Automations** - Trigger Scheduling

---

## 5. Deployment

### Repository URLs

| Plattform | URL |
|-----------|-----|
| GitLab | https://gitlab.com/Florian1143/oewa-reporter |
| GitHub | https://github.com/Florian134/oewa-reporter |
| Streamlit Cloud | https://oewa-reporter-ucgucmpvryylvvkhefxyeq.streamlit.app |

### GitLab CI/CD Variables

| Variable | Beschreibung | Protected |
|----------|-------------|-----------|
| `INFONLINE_API_KEY` | INFOnline API Key | Nein |
| `AIRTABLE_API_KEY` | Airtable Personal Access Token | Nein |
| `AIRTABLE_BASE_ID` | `appTIeod85xnBy7Vn` | Nein |
| `TEAMS_WEBHOOK_URL` | MS Teams Incoming Webhook | Nein |
| `OPENAI_API_KEY` | OpenAI API Key | Nein |

### Streamlit Cloud Secrets

```toml
AIRTABLE_API_KEY = "pat..."
AIRTABLE_BASE_ID = "appTIeod85xnBy7Vn"
```

### Airtable Automations

1. **Daily ÖWA Ingestion**
   - Trigger: Täglich um 08:00 UTC
   - Aktion: GitLab Pipeline via API triggern

2. **Weekly ÖWA Report**
   - Trigger: Montags um 09:00 UTC
   - Aktion: GitLab Pipeline via API triggern

---

## 6. Konfiguration

### INFOnline API

```python
# API Endpoints
BASE_URL = "https://reportingapi.infonline.de/api/v1"

# Metriken
METRICS = ["pageimpressions", "visits"]

# Sites
SITES = [
    {"name": "VOL.AT Web", "site_id": "at_w_atvol", "brand": "VOL"},
    {"name": "VIENNA.AT Web", "site_id": "at_w_atvienna", "brand": "Vienna"},
]

# API Response Format (Page Impressions)
{
    "data": {
        "pageimpressions": [
            {
                "pis": 874938,
                "preliminary": false,
                "date": "2025-12-02"
            }
        ]
    }
}

# API Response Format (Visits)
{
    "data": {
        "visits": [
            {
                "visits": 123456,
                "preliminary": false,
                "date": "2025-12-02"
            }
        ]
    }
}
```

### Airtable Schema

**Tabelle: Measurements**
| Feld | Typ | Beschreibung |
|------|-----|--------------|
| Datum | Date | Messdatum |
| Brand | Single Select | VOL, Vienna |
| Plattform | Single Select | Web |
| Metrik | Single Select | Page Impressions, Visits |
| Wert | Number | Messwert |
| Site ID | Text | at_w_atvol, at_w_atvienna |
| Vorläufig | Checkbox | Ob Daten vorläufig sind |
| Erfasst am | DateTime | Importzeitpunkt |
| Unique Key | Formula | Deduplizierung |

---

## 7. Fehlerbehebungen

### Behobene Probleme

| Problem | Lösung | Datum |
|---------|--------|-------|
| Vercel 250MB Limit | Wechsel zu GitLab CI + Airtable | 03.12.2025 |
| GitLab Pipeline Variables | `rules` statt `TRIGGER_TYPE` | 03.12.2025 |
| YAML Script Format | Array statt String | 03.12.2025 |
| Falsche Site IDs | `at_w_atvol` statt `EA000004` | 03.12.2025 |
| API Response Parsing | `data["data"]["pageimpressions"][0]["pis"]` | 03.12.2025 |
| Airtable Auth | Neuer Personal Access Token | 03.12.2025 |
| Airtable Base ID Typo | `appTIeod85xnBy7Vn` (mit I) | 03.12.2025 |
| Single Select Options | Manuell in Airtable hinzugefügt | 03.12.2025 |
| Korrupte requirements.txt | Neu erstellt mit UTF-8 | 03.12.2025 |
| Plotly 6.x Kompatibilität | `update_layout(yaxis=dict(...))` | 03.12.2025 |

---

## 8. Wichtige Dateien

### Projekt-Struktur

```
oewa-reporter/
├── .gitlab-ci.yml              # GitLab CI/CD Pipeline
├── .streamlit/
│   └── secrets.toml.example    # Streamlit Secrets Template
├── api/                        # Vercel API (nicht mehr verwendet)
├── ci_scripts/
│   ├── daily_ingest.py         # Tägliche Datenabfrage
│   ├── weekly_report.py        # Wochenbericht mit GPT
│   ├── monthly_report.py       # Monatsbericht
│   └── backfill.py             # Historische Daten laden
├── oewa_reporting/
│   ├── __init__.py
│   ├── config.py               # Konfiguration
│   ├── models.py               # SQLAlchemy Models
│   ├── db.py                   # Database Connection
│   ├── api_client.py           # INFOnline API Client
│   ├── ingest.py               # Daten-Ingestion
│   ├── anomaly.py              # Anomalie-Erkennung
│   ├── teams.py                # Teams Webhook
│   ├── visualization.py        # Lokale Visualisierung
│   ├── dashboard.py            # Lokales Streamlit Dashboard
│   ├── ai_interpreter.py       # GPT Integration
│   ├── alerting.py             # Alarming System
│   └── airtable_sync.py        # Airtable Sync
├── tests/
│   ├── test_anomaly.py
│   └── test_ingest.py
├── streamlit_app.py            # Streamlit Cloud Entry Point
├── requirements.txt            # Python Dependencies
├── requirements-streamlit.txt  # Streamlit Cloud Dependencies
├── README.md                   # Projekt README
├── DEPLOYMENT.md               # Deployment Guide
├── AIRTABLE_SETUP_PROMPT.md    # Airtable AI Prompt
└── API-testing.py              # INFOnline API Tester
```

### Kritische Code-Snippets

**GitLab CI/CD Trigger (Airtable Automation):**
```javascript
let response = await fetch(
    'https://gitlab.com/api/v4/projects/76833234/trigger/pipeline',
    {
        method: 'POST',
        headers: {'Content-Type': 'application/x-www-form-urlencoded'},
        body: 'token=glptt-XXXXXX&ref=main'
    }
);
```

**INFOnline API Call:**
```python
url = f"https://reportingapi.infonline.de/api/v1/{metric}"
params = {"site": site_id, "date": target_date.isoformat(), "aggregation": "DAY"}
headers = {"authorization": API_KEY, "Accept": "application/json"}
response = requests.get(url, params=params, headers=headers)
```

**Plotly 6.x Kompatibilität:**
```python
# Korrekt für Plotly 6.x
fig.update_layout(yaxis=dict(tickformat=","))

# NICHT: fig.update_yaxis(tickformat=",")  # Existiert nicht mehr
```

---

## 9. Nächste Schritte

### Optional / Zukünftig

| Task | Priorität | Aufwand |
|------|-----------|---------|
| Monthly Reports aktivieren | Mittel | 30 Min |
| Mehr Metriken (Clients, Qualified Clients) | Niedrig | 1-2 Std |
| App-Daten integrieren | Niedrig | 2-3 Std |
| Airtable Dashboard optimieren | Niedrig | 1 Std |
| Alerting-Schwellenwerte verfeinern | Mittel | 1 Std |

---

## 📞 Support & Kontakt

**Entwickelt von:** Claude (Anthropic AI)  
**Projekt-Owner:** Florian Ramsebner  
**Organisation:** Russmedia

---

## 📝 Changelog

| Version | Datum | Änderungen |
|---------|-------|------------|
| 1.0.0 | 03.12.2025 | Initial Release - Alle Features implementiert |

---

*Dokumentation generiert am 03.12.2025*

