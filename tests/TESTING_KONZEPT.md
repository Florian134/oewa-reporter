# ÖWA Reporter - Testing Konzept
## Version 1.0 | Stand: 22. Dezember 2025

---

## 🎯 Ziel

Ein umfassendes Testing-Framework, das alle kritischen Komponenten des ÖWA Reporting Systems auf **Datenintegrität**, **Funktionalität** und **Sicherheit** prüft.

---

## 📊 Test-Kategorien

### 1. Datenintegritäts-Tests (DATA INTEGRITY)

| Test | Beschreibung | Priorität |
|------|--------------|-----------|
| `test_no_duplicates` | Prüft auf doppelte Unique Keys in Airtable | KRITISCH |
| `test_data_consistency` | Vergleicht Airtable-Summen mit INFOnline API | HOCH |
| `test_date_coverage` | Prüft ob alle erwarteten Tage vorhanden sind | MITTEL |
| `test_value_plausibility` | Prüft ob Werte im erwarteten Bereich liegen | MITTEL |
| `test_unique_key_format` | Validiert das Format aller Unique Keys | NIEDRIG |

### 2. API-Integrations-Tests (API INTEGRATION)

| Test | Beschreibung | Priorität |
|------|--------------|-----------|
| `test_infonline_api_auth` | Prüft INFOnline API-Authentifizierung | KRITISCH |
| `test_airtable_api_auth` | Prüft Airtable API-Authentifizierung | KRITISCH |
| `test_imgbb_api_auth` | Prüft imgBB API-Authentifizierung | HOCH |
| `test_openai_api_auth` | Prüft OpenAI API-Authentifizierung | MITTEL |
| `test_teams_webhook` | Prüft MS Teams Webhook Erreichbarkeit | HOCH |

### 3. Pipeline-Tests (CI/CD PIPELINE)

| Test | Beschreibung | Priorität |
|------|--------------|-----------|
| `test_daily_ingest_dry_run` | Simuliert Daily Ingest ohne Speicherung | HOCH |
| `test_weekly_report_generation` | Prüft Weekly Report Generierung | HOCH |
| `test_monthly_report_generation` | Prüft Monthly Report Generierung | HOCH |
| `test_alert_detection` | Prüft Anomalie-Erkennung | MITTEL |

### 4. Sicherheits-Tests (SECURITY)

| Test | Beschreibung | Priorität |
|------|--------------|-----------|
| `test_no_secrets_in_code` | Scannt Code nach API-Keys/Secrets | KRITISCH |
| `test_no_sensitive_files` | Prüft ob sensible Dateien ignoriert werden | HOCH |
| `test_env_vars_masked` | Validiert dass CI Variables maskiert sind | HOCH |

### 5. Streamlit-Tests (DASHBOARD)

| Test | Beschreibung | Priorität |
|------|--------------|-----------|
| `test_streamlit_auth` | Prüft Passwort-Schutz | KRITISCH |
| `test_data_loading` | Prüft Airtable-Datenladung | HOCH |
| `test_filter_logic` | Prüft Filterlogik (Datum, Brand, etc.) | MITTEL |

---

## 🔧 Implementierung

### Test-Struktur

```
tests/
├── __init__.py
├── conftest.py                 # Pytest Fixtures
├── TESTING_KONZEPT.md          # Dieses Dokument
│
├── test_data_integrity.py      # Datenintegritäts-Tests
├── test_api_integration.py     # API-Integrations-Tests
├── test_pipeline.py            # Pipeline-Tests
├── test_security.py            # Sicherheits-Tests
│
└── fixtures/                   # Test-Daten
    └── sample_data.json
```

### Ausführung

```bash
# Alle Tests
pytest tests/ -v

# Nur kritische Tests
pytest tests/ -v -m critical

# Nur Datenintegritäts-Tests
pytest tests/test_data_integrity.py -v

# Mit Coverage
pytest tests/ --cov=ci_scripts --cov-report=html
```

---

## 📅 Test-Schedule

| Test-Suite | Frequenz | Trigger |
|------------|----------|---------|
| Datenintegrität | Täglich | Nach Daily Ingest |
| API-Integration | Wöchentlich | Sonntag 06:00 |
| Security | Bei jedem Push | GitLab CI |
| Full Suite | Wöchentlich | Sonntag 08:00 |

---

## 🚨 Alerting bei Test-Fehlern

Bei fehlgeschlagenen Tests:
1. Teams-Benachrichtigung an Admin-Channel
2. GitLab Pipeline als "failed" markiert
3. Detaillierter Fehlerbericht in Artifacts

---

## 📋 Checkliste für neue Features

Vor jedem Merge zu `main`:
- [ ] Unit-Tests für neue Funktionen geschrieben
- [ ] Datenintegritäts-Test angepasst (falls neue Datenquellen)
- [ ] Security-Scan durchgeführt
- [ ] Manual Testing in Streamlit

---

*Erstellt: 22. Dezember 2025*

