# ÖWA Reporter - Alerting & Testing Dokumentation
## Erweiterungen vom 03.12.2025

---

## 📋 Inhaltsverzeichnis

1. [Neue Features](#1-neue-features)
2. [Alerting-System](#2-alerting-system)
3. [Test-Suite](#3-test-suite)
4. [Schwellenwerte](#4-schwellenwerte)
5. [GPT-Integration](#5-gpt-integration)
6. [Teams Webhook Tests](#6-teams-webhook-tests)
7. [Konfiguration](#7-konfiguration)
8. [Airtable Automations](#8-airtable-automations)

---

## 1. Neue Features

### Implementiert am 03.12.2025

| Feature | Datei | Beschreibung |
|---------|-------|--------------|
| **Tägliches Alerting** | `ci_scripts/alert_check.py` | Prüft Schwellenwerte nach Daily Ingest |
| **GPT Alert-Analyse** | (integriert) | KI analysiert Trendverlauf bei Alerts |
| **Notification Tests** | `ci_scripts/test_all_notifications.py` | Testet alle Teams + GPT Funktionen |
| **GitLab CI Jobs** | `.gitlab-ci.yml` | Neue Jobs: `alert_check`, `test_notifications` |

---

## 2. Alerting-System

### Funktionsweise

```
┌─────────────────────────────────────────────────────────────────┐
│                     DAILY INGEST                                 │
│                    (08:00 UTC)                                   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     ALERT CHECK                                  │
│                    (09:00 UTC)                                   │
│                                                                  │
│  1. Lade letzte 14 Tage aus Airtable                            │
│  2. Prüfe Schwellenwerte:                                       │
│     - Absolute Mindestwerte                                     │
│     - Prozentuale Abweichung vs. Vorwoche                       │
│     - Z-Score Anomalien                                         │
│  3. Bei Alert → GPT analysiert Trend                            │
│  4. Sende Alarm-Report an Teams                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Alert-Levels

| Level | Farbe | Beschreibung |
|-------|-------|--------------|
| 🟡 **WARNING** | Gelb | Unter Minimum oder -15% vs. Vorwoche |
| 🔴 **CRITICAL** | Rot | Unter kritischem Minimum oder -25% |
| 🚨 **EMERGENCY** | Dunkelrot | Unter Notfall-Schwelle oder -40% |

---

## 3. Test-Suite

### `ci_scripts/test_all_notifications.py`

Testet alle Benachrichtigungs-Funktionen mit simulierten Daten.

### Verwendung

```bash
# Alle Tests
python ci_scripts/test_all_notifications.py --all

# Einzelne Tests
python ci_scripts/test_all_notifications.py --daily      # Daily Ingest
python ci_scripts/test_all_notifications.py --weekly     # Weekly Report
python ci_scripts/test_all_notifications.py --alert      # Alert Check
python ci_scripts/test_all_notifications.py --emergency  # Emergency Alert
python ci_scripts/test_all_notifications.py --gpt-only   # Nur GPT API
```

### Test-Ergebnisse (03.12.2025)

| Test | Status | Details |
|------|--------|---------|
| GPT API | ❌ FAILED | API Key ungültig (401) |
| Daily Ingest | ✅ PASSED | Teams Nachricht gesendet |
| Weekly Report | ✅ PASSED | Teams Nachricht gesendet |
| Alert Check | ⚠️ Timeout | Netzwerk-Timeout |
| Emergency Alert | ✅ PASSED | Teams Nachricht gesendet |

**Teams Webhook: ✅ Funktioniert**
**GPT API: ❌ Neuer API Key erforderlich**

---

## 4. Schwellenwerte

### VOL.AT (größere Site)

| Metrik | WARNING | CRITICAL | EMERGENCY |
|--------|---------|----------|-----------|
| **Page Impressions/Tag** | < 600.000 | < 400.000 | < 200.000 |
| **Visits/Tag** | < 200.000 | < 150.000 | < 80.000 |
| **% vs. Vorwoche** | ≤ -15% | ≤ -25% | ≤ -40% |
| **Z-Score** | ≤ -2.0 | ≤ -2.5 | ≤ -3.0 |

### VIENNA.AT (kleinere Site)

| Metrik | WARNING | CRITICAL | EMERGENCY |
|--------|---------|----------|-----------|
| **Page Impressions/Tag** | < 150.000 | < 100.000 | < 50.000 |
| **Visits/Tag** | < 60.000 | < 40.000 | < 20.000 |
| **% vs. Vorwoche** | ≤ -15% | ≤ -25% | ≤ -40% |
| **Z-Score** | ≤ -2.0 | ≤ -2.5 | ≤ -3.0 |

### Schwellenwerte anpassen

In `ci_scripts/alert_check.py`:

```python
THRESHOLDS_VOL = {
    "Page Impressions": ThresholdConfig(
        min_warning=600000,     # Anpassen
        min_critical=400000,
        min_emergency=200000,
        pct_warning=-0.15,      # -15%
        pct_critical=-0.25,
        pct_emergency=-0.40
    ),
    ...
}
```

---

## 5. GPT-Integration

### Prompts

#### Alert-Analyse Prompt

```
Du bist ein erfahrener Web-Analytics-Experte für österreichische Medienunternehmen.

Es wurden kritische Alerts für die ÖWA-Metriken erkannt:

ALERTS:
- CRITICAL: VOL Page Impressions - Starker Rückgang! -27.3% vs. Vorwoche

TRENDVERLAUF DER LETZTEN 7 TAGE:
VOL.AT Page Impressions: 850.000, 870.000, 820.000, ...

Aufgaben:
1. Analysiere die Alerts und den Trendverlauf
2. Identifiziere mögliche Ursachen
3. Bewerte die Kritikalität
4. Gib eine klare Handlungsempfehlung

Formatiere als kurzen, professionellen Alarm-Report (max. 200 Wörter).
```

#### Weekly Report Prompt

```
Analysiere die folgenden ÖWA-Wochendaten und erstelle eine prägnante Zusammenfassung.

DATEN DER LETZTEN WOCHE:
VOL.AT: PI 6.1 Mio (Woche), -12.5% vs. Vorwoche
VIENNA.AT: PI 1.1 Mio (Woche), -18.7% vs. Vorwoche

ANOMALIEN:
- VIENNA.AT PI: Rückgang von 18.7% (Z-Score: -2.3)

Erstelle Zusammenfassung mit:
1. Überblick Wochenperformance
2. Wichtige Veränderungen
3. Kurze Empfehlung
```

### GPT Model

- **Modell:** `gpt-4o-mini`
- **Max Tokens:** 500-600
- **Temperature:** 0.7

---

## 6. Teams Webhook Tests

### Test-Nachrichten

Die Test-Suite sendet 4 verschiedene Nachrichten an Teams:

#### 1. Daily Ingest (Grün)
```
📥 ÖWA Daily Ingest - TEST
⚠️ Dies ist ein Testlauf

Datum: 2025-12-03
Datensätze: 4
Status: ✅ Erfolgreich (TEST)
```

#### 2. Weekly Report (Gelb)
```
📊 ÖWA Wochenbericht - TEST
⚠️ Dies ist ein Testlauf mit simulierten Daten

📅 Zeitraum: KW 49 (TEST)
📊 VOL.AT PI: 6.124.566
👥 VOL.AT Visits: 2.187.192
...

🤖 KI-Analyse:
[GPT-generierte Zusammenfassung]
```

#### 3. Alert Check (Rot)
```
🚨 ÖWA CRITICAL ALERT - TEST
⚠️ Dies ist ein Testlauf mit simulierten Daten

📅 Datum: 2025-12-03
🔔 Anzahl Alerts: 2
⚠️ Höchster Level: CRITICAL

📋 Erkannte Probleme:
🔴 VOL Page Impressions: Starker Rückgang: -12.5% vs. Vorwoche
🟡 Vienna Page Impressions: Unter Minimum: 156.234 (Min: 150.000)

🤖 KI-Analyse & Empfehlung:
[GPT-generierte Analyse]
```

#### 4. Emergency Alert (Dunkelrot)
```
🚨🚨🚨 EMERGENCY ALERT - TEST
⚠️ Dies ist ein Testlauf - KEIN ECHTER NOTFALL

📅 Datum: 2025-12-03
🌐 Site: VOL.AT
📊 Metrik: Page Impressions
📉 Aktuell: 180.000
⚠️ Minimum: 200.000
📊 Veränderung: -45.2%

🚨 SOFORTMASSNAHMEN ERFORDERLICH:
[GPT-generierte Empfehlungen]
```

---

## 7. Konfiguration

### Environment Variables

| Variable | Beschreibung | Erforderlich |
|----------|-------------|--------------|
| `AIRTABLE_API_KEY` | Airtable Personal Access Token | ✅ Ja |
| `AIRTABLE_BASE_ID` | Über GitLab CI/CD Variables | ✅ Ja |
| `TEAMS_WEBHOOK_URL` | MS Teams Incoming Webhook | ✅ Ja |
| `OPENAI_API_KEY` | OpenAI API Key | ⚠️ Für GPT |

### GitLab CI/CD Variables

Alle Variablen müssen in GitLab → Settings → CI/CD → Variables eingetragen sein.

**Status (03.12.2025):**
- ✅ AIRTABLE_API_KEY: Funktioniert
- ✅ AIRTABLE_BASE_ID: Funktioniert
- ✅ TEAMS_WEBHOOK_URL: Funktioniert
- ❌ OPENAI_API_KEY: Ungültig (neuer Key erforderlich)

---

## 8. Airtable Automations

### Bestehende Automations

| Name | Trigger | Aktion |
|------|---------|--------|
| Daily ÖWA Ingestion | Täglich 08:00 | Pipeline `daily_ingest` |
| Weekly ÖWA Report | Montag 09:00 | Pipeline `weekly_report` |

### Neue Automation: Alert Check

1. Gehe zu **Airtable → Automations**
2. Erstelle neue Automation
3. **Trigger:** Täglich um 09:00 (1h nach Daily Ingest)
4. **Action:** Run a script

```javascript
// ÖWA Alert Check
let response = await fetch(
    'https://gitlab.com/api/v4/projects/YOUR_PROJECT_ID/trigger/pipeline',
    {
        method: 'POST',
        headers: {'Content-Type': 'application/x-www-form-urlencoded'},
        body: 'token=glptt-XXXXXXXXXXXXX&ref=main&variables[JOB_TYPE]=alert_check'
    }
);
console.log('Alert Check gestartet:', await response.json());
```

### Neue Automation: Notification Test (Optional)

```javascript
// Notification Test (manuell triggern)
let response = await fetch(
    'https://gitlab.com/api/v4/projects/YOUR_PROJECT_ID/trigger/pipeline',
    {
        method: 'POST',
        headers: {'Content-Type': 'application/x-www-form-urlencoded'},
        body: 'token=glptt-XXXXXXXXXXXXX&ref=main&variables[JOB_TYPE]=test_notifications'
    }
);
console.log('Notification Test gestartet:', await response.json());
```

---

## 📁 Neue Dateien

| Datei | Beschreibung |
|-------|--------------|
| `ci_scripts/alert_check.py` | Tägliches Alerting mit GPT |
| `ci_scripts/test_all_notifications.py` | Test-Suite für alle Notifications |
| `ALERTING_SETUP.md` | Alerting Setup Guide |
| `ALERTING_UND_TESTING_DOKUMENTATION.md` | Diese Dokumentation |

---

## 🔧 Nächste Schritte

1. **Neuen OpenAI API Key erstellen**
   - https://platform.openai.com/api-keys
   - In GitLab CI/CD Variables aktualisieren

2. **Alert Check Automation einrichten**
   - In Airtable neue Automation erstellen
   - Trigger: Täglich 09:00

3. **Schwellenwerte validieren**
   - Basierend auf echten Daten anpassen
   - Nach 1-2 Wochen Betrieb feintunen

---

## 📊 Architektur-Übersicht (Final)

```
┌─────────────────────────────────────────────────────────────────┐
│                         ZEITPLAN                                 │
├─────────────────────────────────────────────────────────────────┤
│  08:00 UTC │ Daily Ingest      → INFOnline API → Airtable       │
│  09:00 UTC │ Alert Check       → GPT Analyse → Teams Alarm      │
│  09:00 Mo  │ Weekly Report     → GPT Summary → Teams Report     │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                      DATENFLUSS                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Airtable Automation ──► GitLab Pipeline ──► Python Script      │
│         │                      │                    │            │
│         ▼                      ▼                    ▼            │
│    [Trigger]              [CI/CD Job]        [Ausführung]        │
│                                                    │             │
│                                                    ▼             │
│                          ┌─────────────────────────────┐        │
│                          │      Bei Erfolg:            │        │
│                          │  • Daten → Airtable         │        │
│                          │  • Report → Teams           │        │
│                          │                             │        │
│                          │      Bei Alert:             │        │
│                          │  • Analyse → GPT            │        │
│                          │  • Alarm → Teams            │        │
│                          └─────────────────────────────┘        │
└─────────────────────────────────────────────────────────────────┘
```

---

*Dokumentation erstellt am 03.12.2025 18:20 UTC*
*Projekt: ÖWA Reporter für Russmedia*

