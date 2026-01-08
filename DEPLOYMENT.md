# 🚀 Deployment Guide

## Übersicht

Das ÖWA Reporting System ist für ein hybrides Deployment konzipiert:

```
┌─────────────────────────────────────────────────────────────────────┐
│                     PRODUCTION ARCHITECTURE                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   ┌──────────────┐                  ┌──────────────┐               │
│   │    VERCEL    │                  │   GitLab     │               │
│   │  Cron Jobs   │◀────Trigger─────▶│  Repository  │               │
│   │ (Serverless) │                  │   (Source)   │               │
│   └──────┬───────┘                  └──────────────┘               │
│          │                                                          │
│          │ HTTP Call                                                │
│          ▼                                                          │
│   ┌──────────────┐     ┌──────────────┐     ┌──────────────┐       │
│   │    VERCEL    │     │  PostgreSQL  │     │   Airtable   │       │
│   │  Streamlit   │◀───▶│  (Supabase)  │────▶│   (Backup)   │       │
│   │  Dashboard   │     │              │     │              │       │
│   └──────────────┘     └──────────────┘     └──────────────┘       │
│                               │                                     │
│                               ▼                                     │
│   ┌──────────────┐     ┌──────────────┐                            │
│   │   OpenAI     │     │   MS Teams   │                            │
│   │   GPT-4      │────▶│   Webhook    │                            │
│   └──────────────┘     └──────────────┘                            │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

## Komponenten

### 1. GitLab Repository
- **URL**: https://gitlab.com/Florian1143/oewa-reporter
- **Zweck**: Source Code, CI/CD Pipeline
- **Branch**: `main` (Production), `develop` (Development)

### 2. Vercel - Serverless Functions
- **Zweck**: Cron-Jobs für tägliche/wöchentliche/monatliche Tasks
- **Endpoints**:
  - `/api/cron/daily` - Tägliche Ingestion (08:00 UTC)
  - `/api/cron/weekly` - Wochenbericht (Mo 09:00 UTC)
  - `/api/cron/monthly` - Monatsbericht (1. des Monats 10:00 UTC)

### 3. Vercel - Streamlit Dashboard
- **Zweck**: Interaktives Web-Dashboard
- **Framework**: Streamlit Community Cloud oder Vercel Python Runtime

### 4. PostgreSQL (Supabase empfohlen)
- **Zweck**: Zentrale Datenspeicherung
- **Features**: Automatische Backups, SSL, Connection Pooling

### 5. Airtable
- **Zweck**: Backup, Non-Tech-Zugang, Automations
- **Sync**: Nach jeder Ingestion

---

## Schritt-für-Schritt Deployment

### Phase 1: GitLab Setup

#### 1.1 Repository vorbereiten

```bash
# Lokales Repo initialisieren
cd oewa-reporter
git init
git remote add origin https://gitlab.com/Florian1143/oewa-reporter.git

# .gitignore prüfen (keine Secrets!)
cat .gitignore

# Ersten Commit
git add .
git commit -m "Initial commit: ÖWA Reporting System v1.0"
git push -u origin main
```

#### 1.2 GitLab CI/CD (optional)

```yaml
# .gitlab-ci.yml
stages:
  - test
  - deploy

test:
  stage: test
  image: python:3.11
  script:
    - pip install -r requirements.txt
    - pytest tests/

deploy:
  stage: deploy
  only:
    - main
  script:
    - echo "Deploy to Vercel via Webhook"
    # Vercel Deploy Hook hier einfügen
```

### Phase 2: Datenbank Setup (Supabase)

#### 2.1 Supabase Projekt erstellen

1. https://supabase.com → Neues Projekt
2. PostgreSQL Connection String kopieren
3. In `.env` eintragen: `DATABASE_URL=postgresql://...`

#### 2.2 Tabellen erstellen

```bash
# Lokal mit Supabase DB verbinden
export DATABASE_URL="postgresql://..."
python -m oewa_reporting init-db
```

### Phase 3: Vercel Deployment

#### 3.1 Vercel Projekt erstellen

1. https://vercel.com → Import from GitLab
2. Repository: `Florian1143/oewa-reporter`
3. Framework: Python (oder Other)

#### 3.2 Environment Variables in Vercel

Füge folgende Variablen in Vercel Dashboard hinzu:

```
INFONLINE_API_KEY=...
DATABASE_URL=postgresql://...
TEAMS_WEBHOOK_URL=https://...
OPENAI_API_KEY=sk-proj-...
AIRTABLE_API_KEY=pat_your_token_here
AIRTABLE_BASE_ID=app_your_base_id
```

#### 3.3 Serverless Functions erstellen

Erstelle `api/` Ordner für Vercel Functions:

```
api/
├── cron/
│   ├── daily.py
│   ├── weekly.py
│   └── monthly.py
└── health.py
```

**api/cron/daily.py:**
```python
from oewa_reporting.scheduler import ScheduledTasks
import json

def handler(request):
    result = ScheduledTasks.daily_ingestion()
    return {
        "statusCode": 200,
        "body": json.dumps(result)
    }
```

#### 3.4 Cron-Jobs konfigurieren

**vercel.json:**
```json
{
  "crons": [
    {
      "path": "/api/cron/daily",
      "schedule": "0 8 * * *"
    },
    {
      "path": "/api/cron/weekly",
      "schedule": "0 9 * * 1"
    },
    {
      "path": "/api/cron/monthly",
      "schedule": "0 10 1 * *"
    }
  ]
}
```

### Phase 4: Streamlit Dashboard

#### Option A: Streamlit Community Cloud (empfohlen)

1. https://share.streamlit.io
2. GitHub/GitLab verbinden
3. Repository auswählen
4. Main file: `oewa_reporting/dashboard.py`
5. Secrets konfigurieren

#### Option B: Vercel mit Streamlit

Nutze einen Wrapper:

```python
# api/dashboard.py
import streamlit.web.bootstrap as bootstrap

def handler(request):
    bootstrap.run(
        "oewa_reporting/dashboard.py",
        "",
        [],
        {}
    )
```

### Phase 5: Airtable Setup

#### 5.1 Base strukturieren

Erstelle folgende Tabellen in Airtable:

**Measurements:**
| Feld | Typ |
|------|-----|
| Brand | Single line text |
| Plattform | Single select |
| Metrik | Single select |
| Datum | Date |
| Wert Gesamt | Number |
| Vorläufig | Checkbox |
| Unique Key | Single line text |

**Alerts:**
| Feld | Typ |
|------|-----|
| Brand | Single line text |
| Plattform | Single select |
| Metrik | Single select |
| Datum | Date |
| Schweregrad | Single select |
| Abweichung % | Number |
| Meldung | Long text |

#### 5.2 API Key erstellen

1. https://airtable.com/create/tokens
2. Personal Access Token erstellen
3. Scopes: `data.records:read`, `data.records:write`
4. In `.env` eintragen

---

## Monitoring & Wartung

### Logs prüfen

```bash
# Vercel Logs
vercel logs

# Lokale Logs
tail -f logs/oewa_reporting.log
```

### Alerts testen

```bash
python -m oewa_reporting test-teams
```

### Manueller Cron-Trigger

```bash
curl -X POST https://your-vercel-app.vercel.app/api/cron/daily \
  -H "Authorization: Bearer $CRON_SECRET"
```

---

## Troubleshooting

### Problem: Datenbank-Verbindung fehlschlägt

```bash
# SSL erzwingen (Supabase)
DATABASE_URL="postgresql://...?sslmode=require"
```

### Problem: Teams-Nachricht kommt nicht an

1. Webhook-URL prüfen
2. Firewall-Regeln checken
3. Payload-Format validieren

### Problem: Airtable-Sync langsam

- Rate Limit: max 5 Requests/Sekunde
- Batch-Size auf 10 begrenzen
- Inkrementellen Sync nutzen

---

## Checkliste vor Go-Live

- [ ] Alle Environment-Variablen in Vercel gesetzt
- [ ] Datenbank-Tabellen erstellt
- [ ] Teams-Webhook getestet
- [ ] Airtable-Base strukturiert
- [ ] Cron-Jobs konfiguriert
- [ ] Erster Daten-Import erfolgreich
- [ ] Dashboard erreichbar
- [ ] Alerting getestet
- [ ] Backup-Strategie dokumentiert

