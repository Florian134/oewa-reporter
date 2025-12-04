# ÖWA Reporter - Security Audit
## Datum: 04. Dezember 2025

---

## 🔐 Executive Summary

Die ÖWA Reporter Anwendung verarbeitet **sensible Verkehrsdaten** (Page Impressions, Visits) für VOL.AT und VIENNA.AT. Diese Daten sind **nicht zur öffentlichen Einsicht bestimmt** und erfordern einen angemessenen Zugriffsschutz.

### Aktueller Sicherheitsstatus: ⚠️ MITTEL

| Bereich | Status | Risiko | Priorität |
|---------|--------|--------|-----------|
| Streamlit Dashboard | 🔴 Öffentlich | HOCH | P1 |
| Airtable API | 🟢 Geschützt | NIEDRIG | P3 |
| GitLab Repository | 🟡 Prüfen | MITTEL | P2 |
| GitHub Repository | 🟡 Prüfen | MITTEL | P2 |
| MS Teams Webhook | 🟢 Intern | NIEDRIG | P3 |
| Imgur Charts | 🔴 Öffentlich | MITTEL | P2 |
| OpenAI API | 🟡 Daten-Sharing | MITTEL | P2 |

---

## 📊 Detaillierte Analyse aller Touchpoints

### 1. Streamlit Cloud Dashboard 🔴 KRITISCH

**Aktueller Status:**
- URL: `https://oewa-reporter-ucgucmpvryylvvkhefxyeq.streamlit.app`
- Zugriffsschutz: **KEINER**
- Jeder mit dem Link kann die kompletten ÖWA-Daten einsehen

**Risiko:**
- ÖWA-Zahlen sind geschäftskritische Daten
- Konkurrenten könnten Traffic-Entwicklungen einsehen
- Keine Kontrolle wer den Link weiterleitet

**Frage des Users: "Wenn ich die App per Link teile, wer hat Zugriff?"**
> **Antwort:** Aktuell hat JEDER mit dem Link vollen Zugriff auf alle Daten!
> Das ist ein erhebliches Sicherheitsrisiko.

**Lösungsoptionen:**

| Option | Komplexität | Kosten | Sicherheit |
|--------|-------------|--------|------------|
| A) Passwort-Schutz (st.secrets) | Einfach | Kostenlos | Basis |
| B) Google/Microsoft OAuth | Mittel | Kostenlos | Gut |
| C) Streamlit Teams (Private Apps) | Einfach | $250/Monat | Sehr gut |
| D) Self-Hosted mit Auth | Komplex | Server-Kosten | Sehr gut |

**Empfehlung:** Option A (Passwort) oder B (OAuth) implementieren

---

### 2. Airtable 🟢 GESCHÜTZT

**Aktueller Status:**
- API Key: Sicher in `st.secrets` und GitLab CI Variables
- Zugriff: Nur über authentifizierte API-Calls
- Base-Berechtigungen: Über Airtable-Einstellungen steuerbar

**Risiken:**
- API Key könnte durch Code-Leaks kompromittiert werden
- Keine automatische Key-Rotation

**Empfehlungen:**
- [ ] API Key regelmäßig rotieren (alle 90 Tage)
- [ ] Read-Only Token für Streamlit Dashboard erstellen
- [ ] Airtable Base auf "Private" setzen (falls nicht bereits)

---

### 3. GitLab Repository 🟡 PRÜFEN

**Zu prüfen:**
- Ist das Repository `gitlab.com/Florian1143/oewa-reporter` **public** oder **private**?
- Sind CI/CD Variables als "Masked" und "Protected" markiert?

**Risiken bei Public Repository:**
- Code ist einsehbar (unkritisch)
- .env.example könnte sensible Struktur verraten
- Pipeline-Logs könnten Daten leaken

**Empfehlungen:**
- [ ] Repository auf **Private** setzen
- [ ] Alle CI/CD Variables als "Masked" markieren
- [ ] Pipeline-Logs auf sensible Daten prüfen

---

### 4. GitHub Repository 🟡 PRÜFEN

**Zu prüfen:**
- Ist das Repository `github.com/Florian134/oewa-reporter` **public** oder **private**?

**Hinweis:** GitHub wird nur als Mirror für Streamlit Cloud verwendet.
Streamlit Cloud benötigt Lesezugriff auf das Repository.

**Empfehlungen:**
- [ ] Repository auf **Private** setzen
- [ ] Streamlit Cloud App-Connection prüfen (funktioniert auch mit Private Repos)

---

### 5. MS Teams Webhook 🟢 INTERN

**Aktueller Status:**
- Webhook-URL ist nur intern bekannt
- Nachrichten gehen an definierten Teams-Channel
- Empfänger sind Russmedia-Mitarbeiter

**Risiken:**
- Webhook-URL in Code/Logs könnte geleakt werden
- "Security through Obscurity" - keine echte Authentifizierung

**Empfehlungen:**
- [ ] Webhook-URL niemals in öffentlichen Code committen ✅ (bereits in Secrets)
- [ ] Webhook regelmäßig neu generieren (bei Verdacht auf Leak)

---

### 6. Imgur Image Hosting 🔴 ÖFFENTLICH

**Aktueller Status:**
- Charts werden anonym zu Imgur hochgeladen
- Generierte URLs sind **öffentlich zugänglich**
- Keine Authentifizierung erforderlich

**Beispiel-URL:** `https://i.imgur.com/ABC123.png`

**Risiken:**
- Jeder mit der URL kann die Charts sehen
- Charts enthalten ÖWA-Zahlen (Page Impressions, Visits)
- URLs könnten über Teams-Nachrichten geleakt werden

**Lösungsoptionen:**

| Option | Beschreibung | Sicherheit |
|--------|--------------|------------|
| A) Akzeptieren | Charts sind "nur" aggregierte Wochendaten | Niedrig |
| B) Imgur Account | Private Uploads mit Account | Mittel |
| C) Azure Blob Storage | Eigene Infrastruktur mit SAS-Tokens | Hoch |
| D) Base64 in Teams | Bilder direkt einbetten (Größenlimit!) | Mittel |

**Empfehlung:** Option A akzeptieren ODER Option C für höhere Sicherheit

---

### 7. OpenAI API 🟡 DATEN-SHARING

**Aktueller Status:**
- ÖWA-Daten werden an OpenAI gesendet für GPT-Analyse
- Daten: Tägliche PI/Visits-Werte, Brand-Namen, Datumsangaben

**Was wird an OpenAI gesendet:**
```
VOL.AT: 838,874 Page Impressions, 281,775 Visits
VIENNA.AT: 88,743 Page Impressions, 44,923 Visits
Veränderung: VOL -6.4%, Vienna +6.6%
```

**Risiken:**
- OpenAI speichert möglicherweise Daten (je nach API-Nutzungsbedingungen)
- Daten könnten für Training verwendet werden (opt-out möglich)

**Empfehlungen:**
- [ ] OpenAI Data Usage Policy prüfen
- [ ] API-Einstellungen: "Don't train on my data" aktivieren
- [ ] Alternativ: Azure OpenAI Service (GDPR-konform, EU-Rechenzentren)

---

## 🛡️ Empfohlene Sofortmaßnahmen

### Priorität 1: Streamlit Authentication (KRITISCH)

**Einfachste Lösung: Passwort-Schutz**

```python
# Am Anfang von streamlit_app.py einfügen:

def check_password():
    """Returns `True` if the user had the correct password."""

    def password_entered():
        """Checks whether a password entered by the user is correct."""
        if st.session_state["password"] == st.secrets["app_password"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # Don't store password
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        # First run, show input for password
        st.text_input(
            "Passwort", type="password", on_change=password_entered, key="password"
        )
        st.info("🔐 Bitte Passwort eingeben um auf das Dashboard zuzugreifen.")
        return False
    elif not st.session_state["password_correct"]:
        # Password incorrect, show input + error
        st.text_input(
            "Passwort", type="password", on_change=password_entered, key="password"
        )
        st.error("❌ Falsches Passwort")
        return False
    else:
        # Password correct
        return True

# Hauptanwendung nur anzeigen wenn Passwort korrekt
if not check_password():
    st.stop()

# ... Rest der Anwendung ...
```

**Streamlit Secrets hinzufügen:**
```toml
# In Streamlit Cloud → Settings → Secrets
app_password = "sicheres_passwort_hier"
```

---

### Priorität 2: Repository-Sichtbarkeit

**GitLab:**
1. Gehe zu: `gitlab.com/Florian1143/oewa-reporter` → Settings → General
2. Unter "Visibility, project features, permissions"
3. Setze auf: **Private**

**GitHub:**
1. Gehe zu: `github.com/Florian134/oewa-reporter` → Settings
2. Unter "Danger Zone" → "Change repository visibility"
3. Setze auf: **Private**

---

### Priorität 3: CI/CD Variable Security

**GitLab CI Variables prüfen:**
1. Gehe zu: Project → Settings → CI/CD → Variables
2. Für jede Variable:
   - ✅ "Mask variable" aktivieren
   - ✅ "Protect variable" aktivieren (nur auf protected branches)

---

## 📋 Security Checklist

### Sofort umsetzen:
- [ ] Streamlit Passwort-Schutz implementieren
- [ ] GitLab Repository auf Private setzen
- [ ] GitHub Repository auf Private setzen
- [ ] CI/CD Variables als Masked markieren

### Kurzfristig (1-2 Wochen):
- [ ] Airtable API Key rotieren
- [ ] Read-Only Token für Streamlit erstellen
- [ ] OpenAI Data Usage Settings prüfen

### Mittelfristig (1-3 Monate):
- [ ] OAuth-Integration evaluieren (Google/Microsoft SSO)
- [ ] Imgur durch Azure Blob Storage ersetzen
- [ ] Audit-Logging implementieren

---

## 🔑 Zugriffsmatrix (Ziel-Zustand)

| Ressource | Öffentlich | Mit Passwort | Mit SSO | Nur Intern |
|-----------|------------|--------------|---------|------------|
| Streamlit Dashboard | ❌ | ✅ | ✅ | - |
| Airtable Daten | ❌ | - | - | ✅ |
| GitLab Repository | ❌ | - | - | ✅ |
| GitHub Repository | ❌ | - | - | ✅ |
| Teams Nachrichten | ❌ | - | - | ✅ |
| Imgur Charts | ⚠️ | - | - | - |

---

## 📞 Nächste Schritte

1. **Entscheidung:** Welche Authentifizierungsmethode für Streamlit?
   - [ ] Einfaches Passwort (schnell, für kleine Teams)
   - [ ] Google OAuth (für Google Workspace Nutzer)
   - [ ] Microsoft OAuth (für Microsoft 365 Nutzer)
   - [ ] Streamlit Teams (kostenpflichtig, beste UX)

2. **Repository-Status prüfen:** Sind GitLab/GitHub aktuell public oder private?

3. **Implementierung:** Nach Entscheidung kann die gewählte Lösung umgesetzt werden.

---

*Security Audit erstellt am 04.12.2025 • ÖWA Reporter v2.0*

