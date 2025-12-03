# 📊 ÖWA Reporting System

Automatisiertes Reporting-System für INFOnline/ÖWA-Metriken mit KI-Interpretation und Teams-Integration.

## ✨ Features

- **📥 Automatische Daten-Ingestion** von der INFOnline Reporting API
- **🤖 KI-gestützte Reports** mit GPT-4 für Management-taugliche Zusammenfassungen
- **⚠️ Intelligentes Alerting** mit konfigurierbaren Schwellenwerten
- **📊 Interaktives Dashboard** mit Streamlit
- **📨 Teams-Integration** via Webhook für automatische Benachrichtigungen
- **🔄 Airtable-Sync** für Backup und einfache Datenanalyse
- **⏰ Scheduled Tasks** für tägliche, wöchentliche und monatliche Reports

## 🏗️ Architektur

```
┌─────────────────────────────────────────────────────────────────────┐
│                         OEWA REPORTING SYSTEM                        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐         │
│  │ INFOnline│──▶│ Database │──▶│  OpenAI  │──▶│  Teams   │         │
│  │   API    │   │(Postgres)│   │  GPT-4   │   │ Webhook  │         │
│  └──────────┘   └────┬─────┘   └──────────┘   └──────────┘         │
│                      │                                               │
│                      ▼                                               │
│  ┌──────────┐   ┌──────────┐                                        │
│  │ Airtable │◀──│Streamlit │                                        │
│  │   Sync   │   │Dashboard │                                        │
│  └──────────┘   └──────────┘                                        │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

## 📦 Module

| Modul | Beschreibung |
|-------|--------------|
| `config.py` | Zentrale Konfiguration aus Environment-Variablen |
| `api_client.py` | INFOnline API Client mit Retry-Logik |
| `models.py` | SQLAlchemy Datenbank-Modelle |
| `db.py` | Datenbank-Verbindung und Session-Management |
| `ingest.py` | Daten-Ingestion von API zu DB |
| `anomaly.py` | Anomalie-Erkennung (Median/MAD) |
| `alerting.py` | Erweitertes Schwellenwert-Alerting |
| `teams.py` | Microsoft Teams Integration |
| `ai_interpreter.py` | GPT-4 KI-Interpretation für Reports |
| `airtable_sync.py` | Airtable Datensynchronisation |
| `scheduler.py` | Scheduled Tasks für Cron-Jobs |
| `dashboard.py` | Streamlit Web-Dashboard |
| `cli.py` | Command-Line Interface |

## 🚀 Quick Start

### 1. Installation

```bash
# Repository klonen
git clone https://gitlab.com/Florian1143/oewa-reporter.git
cd oewa-reporter

# Virtual Environment erstellen
python -m venv venv
source venv/bin/activate  # Linux/Mac
# oder: venv\Scripts\activate  # Windows

# Dependencies installieren
pip install -r requirements.txt
```

### 2. Konfiguration

```bash
# Beispiel-Konfiguration kopieren
cp env.example .env

# .env bearbeiten und Werte eintragen
```

**Wichtige Variablen:**

| Variable | Beschreibung |
|----------|--------------|
| `INFONLINE_API_KEY` | INFOnline API Key |
| `DATABASE_URL` | PostgreSQL oder SQLite Connection String |
| `TEAMS_WEBHOOK_URL` | Teams Incoming Webhook URL |
| `OPENAI_API_KEY` | OpenAI API Key für KI-Reports |

### 3. Datenbank initialisieren

```bash
python -m oewa_reporting init-db
```

### 4. Erste Daten laden

```bash
# Daten für gestern laden
python -m oewa_reporting ingest-daily

# Oder: Backfill für die letzten 30 Tage
python -m oewa_reporting backfill --days 30
```

### 5. Dashboard starten

```bash
python -m oewa_reporting dashboard
```

## 💻 CLI Commands

```bash
# Konfiguration prüfen
python -m oewa_reporting check

# Datenbank initialisieren
python -m oewa_reporting init-db

# Tägliche Ingestion
python -m oewa_reporting ingest-daily

# Backfill historischer Daten
python -m oewa_reporting backfill --days 30

# Wochenbericht (mit KI)
python -m oewa_reporting report-weekly

# Monatsbericht (mit KI)
python -m oewa_reporting report-monthly

# Dashboard starten
python -m oewa_reporting dashboard

# Teams-Test senden
python -m oewa_reporting test-teams
```

## ⚠️ Alerting-System

### Schwellenwerte (Standard für VOL.at)

| Metrik | Warning | Critical | Emergency |
|--------|---------|----------|-----------|
| Page Impressions/Tag | < 300.000 | < 200.000 | < 100.000 |
| Visits/Tag | < 100.000 | < 70.000 | < 40.000 |
| % vs. Vorwoche | -15% | -25% | -40% |

### Eskalationsstufen

- **🟡 WARNING**: Tägliche Zusammenfassung
- **🔴 CRITICAL**: Sofortige Benachrichtigung
- **🚨 EMERGENCY**: Sofortige Eskalation an Management

## 🤖 KI-Reports

Die KI-Interpretation verwendet GPT-4 für:

1. **Wöchentliche Zusammenfassung** (Montag 09:00)
   - Trends und Entwicklungen
   - Anomalie-Erklärungen
   - Handlungsempfehlungen

2. **Monatlicher Report** (1. des Monats 10:00)
   - Performance-Analyse
   - Plattform-Vergleich
   - Strategische Insights

## 📅 Scheduled Tasks

| Task | Zeitplan | Beschreibung |
|------|----------|--------------|
| daily_ingestion | 08:00 täglich | Daten laden, Alerts prüfen, Airtable sync |
| weekly_report | 09:00 Montag | KI-Wochenbericht an Teams |
| monthly_report | 10:00 am 1. | KI-Monatsbericht an Teams |

## 🐳 Docker

```bash
# Build
docker build -t oewa-reporter .

# Run mit .env
docker run --env-file .env oewa-reporter ingest-daily

# Docker Compose
docker-compose up -d
```

## 🌐 Vercel Deployment

Siehe [DEPLOYMENT.md](DEPLOYMENT.md) für detaillierte Anweisungen.

## 📁 Projektstruktur

```
oewa-reporter/
├── oewa_reporting/
│   ├── __init__.py
│   ├── __main__.py
│   ├── config.py          # Konfiguration
│   ├── models.py          # DB-Modelle
│   ├── db.py              # DB-Verbindung
│   ├── api_client.py      # INFOnline API
│   ├── ingest.py          # Daten-Ingestion
│   ├── anomaly.py         # Anomalie-Erkennung
│   ├── alerting.py        # Schwellenwert-Alerts
│   ├── teams.py           # Teams Integration
│   ├── ai_interpreter.py  # GPT-4 KI-Reports
│   ├── airtable_sync.py   # Airtable Sync
│   ├── scheduler.py       # Scheduled Tasks
│   ├── dashboard.py       # Streamlit UI
│   ├── visualization.py   # Charts & Reports
│   └── cli.py             # CLI Commands
├── tests/
│   ├── test_anomaly.py
│   └── test_ingest.py
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── env.example
├── .gitignore
└── README.md
```

## 🔒 Sicherheit

- **API Keys**: Niemals in Git committen! Immer als Environment-Variable
- **Datenbank**: Verschlüsselte Verbindung (SSL) in Produktion
- **Teams Webhook**: Nur an autorisierte Channels

## 📝 Lizenz

Intern - Russmedia

## 👥 Team

- **Entwicklung**: Florian Ramsebner
- **Projekt**: ÖWA Reporting PoC
- **Status**: Pilot-Phase
