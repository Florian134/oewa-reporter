# 🤖 Prompt für Airtable AI - ÖWA Reporting System

Kopiere diesen Prompt in Airtable AI, um die optimale Tabellenstruktur zu erstellen:

---

## PROMPT FÜR AIRTABLE AI:

```
Erstelle eine Airtable-Base für ein ÖWA/INFOnline Web-Analytics Reporting System mit folgenden Anforderungen:

## Tabelle 1: "Measurements" (Haupttabelle für Messdaten)

Erstelle folgende Felder:

1. **Datum** (Date)
   - Das Messdatum
   - Format: DD.MM.YYYY

2. **Brand** (Single Select)
   - Optionen: VOL, Vienna
   - Farben: VOL = Blau, Vienna = Grün

3. **Plattform** (Single Select)
   - Optionen: Web Desktop, Web Mobile, App
   - Farben: Web Desktop = Blau, Web Mobile = Cyan, App = Lila

4. **Metrik** (Single Select)
   - Optionen: Page Impressions, Visits
   - Farben: Page Impressions = Orange, Visits = Grün

5. **Wert** (Number)
   - Integer, keine Dezimalstellen
   - Tausendertrennzeichen aktivieren

6. **Site ID** (Single Line Text)
   - Technische ID z.B. "EA000004_desktop"

7. **Vorläufig** (Checkbox)
   - Ob die Daten noch vorläufig sind

8. **Erfasst am** (Date with Time)
   - Wann die Daten importiert wurden
   - Include time field

9. **Unique Key** (Single Line Text)
   - Kombination für Deduplizierung
   - Format: YYYY-MM-DD_Brand_Plattform_Metrik

## Tabelle 2: "Alerts" (Anomalie-Warnungen)

Erstelle folgende Felder:

1. **Datum** (Date)

2. **Brand** (Single Select)
   - Optionen: VOL, Vienna

3. **Plattform** (Single Select)
   - Optionen: Web Desktop, Web Mobile, App

4. **Metrik** (Single Select)
   - Optionen: Page Impressions, Visits

5. **Schweregrad** (Single Select)
   - Optionen: Warnung, Kritisch, Notfall
   - Farben: Warnung = Gelb, Kritisch = Rot, Notfall = Dunkelrot

6. **Aktueller Wert** (Number)

7. **Median** (Number)
   - Historischer Median als Baseline

8. **Abweichung %** (Percent)
   - Prozentuale Abweichung vom Median

9. **Z-Score** (Number)
   - Dezimalzahl mit 2 Nachkommastellen

10. **Meldung** (Long Text)
    - Beschreibung der Anomalie

11. **Bestätigt** (Checkbox)
    - Ob jemand die Anomalie geprüft hat

12. **Link zu Measurement** (Link to Measurements)
    - Verknüpfung zur Messung

## Tabelle 3: "Weekly Reports" (Wochenberichte)

1. **Kalenderwoche** (Number)
2. **Jahr** (Number)
3. **Woche Start** (Date)
4. **Woche Ende** (Date)
5. **Web PI Gesamt** (Number)
6. **App PI Gesamt** (Number)
7. **Änderung vs Vorwoche %** (Percent)
8. **KI-Zusammenfassung** (Long Text) - GPT-generierter Report
9. **An Teams gesendet** (Checkbox)
10. **Erstellt am** (Date with Time)

## Views erstellen:

1. **"Aktuelle Woche"** - Grid View
   - Filter: Datum >= Montag dieser Woche
   - Sortierung: Datum absteigend

2. **"Letzte 30 Tage"** - Grid View
   - Filter: Datum >= heute - 30 Tage
   - Gruppierung: Nach Datum

3. **"Nach Plattform"** - Grid View
   - Gruppierung: Nach Plattform
   - Zusammenfassung: Summe von Wert

4. **"Anomalien (Offen)"** - Grid View auf Alerts
   - Filter: Bestätigt = unchecked
   - Sortierung: Datum absteigend

5. **"Monatstrend"** - Calendar View
   - Datum-Feld: Datum

## Formatierung:
- Zahlenfelder mit Tausendertrennzeichen (Punkt als Trenner)
- Deutsche Datumsformate (DD.MM.YYYY)
- Farbkodierung für Schweregrade
```

---

## 📋 Nach dem Erstellen:

1. **Base ID kopieren** (aus der URL: airtable.com/appXXXXXX/...)
2. **API Key erstellen**: https://airtable.com/create/tokens
   - Scopes: `data.records:read`, `data.records:write`
3. **Mir mitteilen** für die finale Code-Konfiguration

---

## 🔗 Airtable Base Link:
https://airtable.com/appTIeod85xnBy7Vn

