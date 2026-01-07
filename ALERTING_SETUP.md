# ÖWA Alert System - Setup Guide

## Übersicht

Das Alert-System prüft täglich nach der Datenerfassung, ob kritische Schwellenwerte unterschritten wurden. Bei Alarm wird:

1. **Historische Daten analysiert** (letzte 14 Tage aus Airtable)
2. **Schwellenwerte geprüft** (absolut, prozentual, Z-Score)
3. **GPT-Analyse erstellt** (Trendverlauf, Ursachen, Empfehlungen)
4. **Alarm-Report an Teams gesendet**

---

## Schwellenwerte

### VOL.AT (größere Site)

| Metrik | Warning | Critical | Emergency |
|--------|---------|----------|-----------|
| **Page Impressions/Tag** | < 600.000 | < 400.000 | < 200.000 |
| **Visits/Tag** | < 200.000 | < 150.000 | < 80.000 |
| **% vs. Vorwoche** | ≤ -15% | ≤ -25% | ≤ -40% |
| **Z-Score** | ≤ -2.0 | ≤ -2.5 | ≤ -3.0 |

### VIENNA.AT (kleinere Site)

| Metrik | Warning | Critical | Emergency |
|--------|---------|----------|-----------|
| **Page Impressions/Tag** | < 150.000 | < 100.000 | < 50.000 |
| **Visits/Tag** | < 60.000 | < 40.000 | < 20.000 |
| **% vs. Vorwoche** | ≤ -15% | ≤ -25% | ≤ -40% |
| **Z-Score** | ≤ -2.0 | ≤ -2.5 | ≤ -3.0 |

---

## Airtable Automation einrichten

### Option A: Separater Alert-Check (empfohlen)

1. Gehe zu **Airtable → Automations**
2. Klicke **"Create automation"**
3. **Trigger:** Schedule → "Every day at 09:00 AM" (1 Stunde nach Daily Ingest)
4. **Action:** Run a script

```javascript
// ÖWA Alert Check - Airtable Automation Script
let response = await fetch(
    'https://gitlab.com/api/v4/projects/YOUR_PROJECT_ID/trigger/pipeline',
    {
        method: 'POST',
        headers: {
            'Content-Type': 'application/x-www-form-urlencoded'
        },
        body: 'token=glptt-XXXXXXXXXXXXX&ref=main&variables[JOB_TYPE]=alert_check'
    }
);

let result = await response.json();
console.log('Alert Check Pipeline gestartet:', result.id);
```

5. **Name:** "Daily ÖWA Alert Check"
6. **Aktivieren**

### Option B: Alert-Check nach Daily Ingest (in einer Pipeline)

Alternativ kann der Alert-Check direkt nach dem Daily Ingest laufen. Dafür die bestehende Daily-Automation so ändern:

```javascript
// Beide Jobs nacheinander triggern
let ingestResponse = await fetch(
    'https://gitlab.com/api/v4/projects/YOUR_PROJECT_ID/trigger/pipeline',
    {
        method: 'POST',
        headers: {'Content-Type': 'application/x-www-form-urlencoded'},
        body: 'token=glptt-XXXXXXXXXXXXX&ref=main'
    }
);
console.log('Daily Ingest gestartet');

// Warte 2 Minuten, dann Alert-Check
await new Promise(resolve => setTimeout(resolve, 120000));

let alertResponse = await fetch(
    'https://gitlab.com/api/v4/projects/YOUR_PROJECT_ID/trigger/pipeline',
    {
        method: 'POST',
        headers: {'Content-Type': 'application/x-www-form-urlencoded'},
        body: 'token=glptt-XXXXXXXXXXXXX&ref=main&variables[JOB_TYPE]=alert_check'
    }
);
console.log('Alert Check gestartet');
```

---

## Manuell testen

### Via GitLab UI

1. Gehe zu **GitLab → CI/CD → Pipelines**
2. Klicke **"Run pipeline"**
3. Wähle Branch `main`
4. Füge Variable hinzu: `JOB_TYPE` = `alert_check`
5. Klicke **"Run pipeline"**

### Via Terminal (lokal)

```bash
# Environment Variables setzen
export AIRTABLE_API_KEY="pat..."
export AIRTABLE_BASE_ID="app_your_base_id"
export TEAMS_WEBHOOK_URL="https://russmedia.webhook..."
export OPENAI_API_KEY="sk-proj-..."

# Alert-Check ausführen
python ci_scripts/alert_check.py

# Für spezifisches Datum
python ci_scripts/alert_check.py --date 2025-12-02
```

---

## Teams Benachrichtigung

Bei erkannten Alerts wird folgende Nachricht an Teams gesendet:

```
🚨 ÖWA CRITICAL ALERT
2 Anomalien erkannt

📅 Datum: 03.12.2025
🔔 Anzahl Alerts: 2
⚠️ Höchster Level: CRITICAL

📋 Erkannte Probleme:
🔴 VOL Page Impressions: CRITICAL - Starker Rückgang! -27.3% vs. Vorwoche
🟡 Vienna Visits: WARNING - Unter Minimum! Aktuell: 52.000 (Min: 60.000)

🤖 KI-Analyse & Empfehlung:
[GPT-generierter Text mit Analyse, Ursachen und Empfehlungen]
```

---

## Schwellenwerte anpassen

Die Schwellenwerte sind in `ci_scripts/alert_check.py` definiert:

```python
# VOL.AT Schwellenwerte
THRESHOLDS_VOL = {
    "Page Impressions": ThresholdConfig(
        min_warning=600000,     # Anpassen nach Bedarf
        min_critical=400000,
        min_emergency=200000,
        pct_warning=-0.15,      # -15%
        pct_critical=-0.25,     # -25%
        pct_emergency=-0.40     # -40%
    ),
    ...
}
```

---

## Troubleshooting

### Alert-Check findet keine Daten

- Prüfe ob `AIRTABLE_API_KEY` und `AIRTABLE_BASE_ID` korrekt sind
- Stelle sicher, dass der Daily Ingest vorher gelaufen ist

### Teams-Benachrichtigung kommt nicht an

- Prüfe `TEAMS_WEBHOOK_URL`
- Teste den Webhook manuell mit einem curl-Befehl

### GPT-Analyse fehlt

- Prüfe `OPENAI_API_KEY`
- Ohne API Key wird nur "GPT-Analyse nicht verfügbar" angezeigt

---

*Erstellt: 03.12.2025*

