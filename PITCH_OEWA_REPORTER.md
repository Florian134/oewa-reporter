# ÖWA Reporter
## Automated Web Analytics Intelligence Platform

---

## The Problem

Media companies managing multiple web properties face a common challenge: **scattered analytics data, manual reporting processes, and delayed insights**. Teams spend hours each week compiling reports from various sources, often missing critical traffic anomalies until it's too late. The lack of automated monitoring means performance issues go unnoticed, and stakeholders receive outdated information that doesn't support real-time decision-making.

---

## The Solution

**ÖWA Reporter** is an end-to-end automated web analytics platform that transforms raw traffic data into actionable intelligence. Built specifically for Austrian media properties certified by ÖWA (Österreichische Webanalyse), it provides:

- 🔄 **Automated Daily Data Ingestion** — No manual exports, ever
- 📊 **Interactive Real-Time Dashboard** — Explore data with Google Analytics-style comparison periods
- 🚨 **Intelligent Alerting** — AI-powered anomaly detection with contextual analysis
- 📈 **Weekly Executive Reports** — Professional summaries delivered directly to Microsoft Teams
- 🤖 **GPT-Powered Insights** — Natural language explanations of trends and anomalies

---

## Tech Stack

| Layer | Technology | Purpose |
|-------|------------|---------|
| **Data Source** | INFOnline API | Official ÖWA-certified traffic metrics |
| **Orchestration** | GitLab CI/CD | Scheduled pipelines for data processing |
| **Database** | Airtable | Flexible NoSQL storage with built-in automations |
| **Dashboard** | Streamlit Cloud | Interactive Python-based web application |
| **AI Engine** | OpenAI GPT-4o-mini | Intelligent analysis and natural language summaries |
| **Notifications** | MS Teams Webhooks | Enterprise communication integration |
| **Visualization** | Plotly + Kaleido | Interactive charts with PNG export capability |
| **Image Hosting** | Imgur API | Public URLs for embedded report graphics |
| **Version Control** | GitLab + GitHub | Dual-repository architecture for CI/CD and hosting |

### Language & Frameworks
- **Python 3.11+** — Core application logic
- **Pandas** — Data manipulation and analysis
- **Requests** — API integrations
- **python-dotenv** — Environment configuration

---

## Architecture & Data Flow

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              ÖWA REPORTER SYSTEM                                 │
│                    Automated Web Analytics Intelligence Platform                 │
└─────────────────────────────────────────────────────────────────────────────────┘

                                    DATA FLOW
                                    ─────────

    ┌──────────────┐                                           ┌──────────────┐
    │  INFOnline   │                                           │   END USER   │
    │     API      │                                           │  Dashboard   │
    └──────┬───────┘                                           └──────▲───────┘
           │                                                          │
           │ REST API                                                 │ HTTPS
           │ (Page Impressions, Visits)                               │
           ▼                                                          │
    ┌──────────────┐      ┌──────────────┐      ┌──────────────┐     │
    │   GitLab     │      │   Airtable   │      │  Streamlit   │─────┘
    │    CI/CD     │─────▶│   Database   │─────▶│    Cloud     │
    │              │      │              │      │              │
    │ • daily_ingest│      │ • Measurements│      │ • Dashboard  │
    │ • weekly_report│     │ • Alerts     │      │ • Analytics  │
    │ • alert_check │      │ • Reports    │      │ • Export     │
    └──────┬───────┘      └──────┬───────┘      └──────────────┘
           │                     │
           │                     │ Automation Triggers
           ▼                     ▼
    ┌──────────────┐      ┌──────────────┐
    │   OpenAI     │      │   MS Teams   │
    │  GPT-4o-mini │      │   Webhook    │
    │              │      │              │
    │ • Alert      │      │ • Daily      │
    │   Analysis   │      │   Reports    │
    │ • Weekly     │      │ • Alerts     │
    │   Summaries  │      │ • Charts     │
    └──────────────┘      └──────────────┘
```

---

## Pipeline Details

### 1. Daily Data Ingestion Pipeline
**Trigger:** GitLab Schedule (Daily at 01:00 CET)

```
INFOnline API → daily_ingest.py → Airtable → MS Teams Notification
```

**Process:**
1. Fetches yesterday's metrics for all properties (VOL.AT, VIENNA.AT)
2. Validates data integrity and checks for duplicates
3. Stores records with unique keys to prevent data duplication
4. Sends confirmation notification to Teams channel

### 2. Alert Monitoring Pipeline
**Trigger:** GitLab Schedule (Daily at 08:00 CET)

```
Airtable → alert_check.py → OpenAI GPT → MS Teams Alert
```

**Process:**
1. Retrieves latest measurements from Airtable
2. Calculates statistical anomalies using Z-Score (MAD-based)
3. Compares against configurable thresholds (WARNING/CRITICAL/EMERGENCY)
4. Generates GPT-powered contextual analysis
5. Sends color-coded alert cards to Teams

**Alert Thresholds:**
| Level | Criteria |
|-------|----------|
| ⚠️ WARNING | -15% vs. previous week OR Z-Score > 2.0 |
| 🔴 CRITICAL | -25% vs. previous week OR Z-Score > 2.5 |
| 🚨 EMERGENCY | -40% vs. previous week OR Z-Score > 3.0 |

### 3. Weekly Report Pipeline
**Trigger:** Airtable Automation → GitLab Pipeline (Weekly on Monday)

```
Airtable → weekly_report.py → Plotly Charts → Imgur → GPT Summary → MS Teams
```

**Process:**
1. Aggregates 7-day metrics for current and previous week
2. Generates interactive Plotly visualizations:
   - Weekday Performance Analysis (by property)
   - 7-Day Trend Charts (with rolling averages)
3. Exports charts as PNG via Kaleido
4. Uploads images to Imgur for public URLs
5. Generates executive summary using GPT-4o-mini
6. Composes rich MessageCard with embedded charts
7. Delivers to MS Teams channel

### 4. Interactive Dashboard
**Hosting:** Streamlit Cloud (Auto-deploy from GitHub)

**Features:**
- Real-time data from Airtable API
- Google Analytics-style date range selection
- Automatic comparison period calculation
- Property-level analysis (VOL.AT vs. VIENNA.AT)
- Weekday pattern analysis
- Time series visualization with 7-day moving averages
- CSV export functionality

---

## Key Differentiators

### 🎯 Purpose-Built for Austrian Media
Unlike generic analytics tools, ÖWA Reporter is specifically designed for ÖWA-certified properties, understanding the nuances of Page Impressions and Visits metrics as defined by Austrian web analytics standards.

### 🤖 AI-Native Architecture
GPT integration isn't an afterthought—it's woven into the core workflow. Every alert includes contextual analysis, and weekly reports feature executive summaries that highlight what matters.

### 🔗 Zero-Touch Operations
Once configured, the system runs autonomously. Daily ingestion, weekly reports, and anomaly detection all happen without human intervention, while still providing immediate notifications when attention is needed.

### 📊 Comparison-First Analytics
Every metric is shown in context. The dashboard doesn't just show numbers—it shows how today compares to last week, how this Monday compares to previous Mondays, and how trends are developing over time.

### 🏗️ Modern, Maintainable Stack
Built entirely on cloud-native services with no servers to manage. GitLab handles orchestration, Airtable provides flexible storage, and Streamlit Cloud hosts the dashboard—all with generous free tiers for cost-effective operation.

---

## Sample Outputs

### Daily Ingest Notification
```
✅ ÖWA Daily Ingest Complete

VOL.AT Web
├── Page Impressions: 838,874
└── Visits: 281,775

VIENNA.AT Web
├── Page Impressions: 88,743
└── Visits: 44,923

Data stored in Airtable ✓
```

### Weekly Report Summary (GPT-Generated)
> "This week showed stable performance for VOL.AT with Page Impressions at 5.3M 
> (-6.4% vs. last week), while VIENNA.AT demonstrated growth with +6.6% in 
> Page Impressions. The mid-week dip on Wednesday aligns with historical 
> patterns. No anomalies detected—traffic is within expected ranges."

### Alert Card
```
🚨 CRITICAL ALERT: VOL.AT Traffic Drop

Page Impressions: 618,489 (-28.7% vs. last week)
Z-Score: 2.8 (significantly below median)

GPT Analysis: "The sharp decline coincides with a national holiday. 
Historical data suggests recovery within 24-48 hours. Monitor closely 
but no immediate action required."
```

---

## Deployment Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    DEPLOYMENT TOPOLOGY                          │
└─────────────────────────────────────────────────────────────────┘

    DEVELOPMENT                CI/CD                  PRODUCTION
    ───────────               ─────                  ──────────

    ┌─────────┐            ┌─────────┐            ┌─────────────┐
    │  Local  │───push────▶│ GitLab  │───mirror──▶│   GitHub    │
    │   Dev   │            │  Repo   │            │    Repo     │
    └─────────┘            └────┬────┘            └──────┬──────┘
                                │                        │
                                │ CI/CD                  │ Auto-deploy
                                │ Pipelines              │
                                ▼                        ▼
                          ┌─────────┐            ┌─────────────┐
                          │ GitLab  │            │  Streamlit  │
                          │ Runners │            │    Cloud    │
                          └────┬────┘            └─────────────┘
                               │
                    ┌──────────┼──────────┐
                    ▼          ▼          ▼
              ┌─────────┐ ┌─────────┐ ┌─────────┐
              │Airtable │ │ OpenAI  │ │ MS Teams│
              │   API   │ │   API   │ │ Webhook │
              └─────────┘ └─────────┘ └─────────┘
```

**Dual-Repository Strategy:**
- **GitLab** → CI/CD pipeline execution, scheduled jobs, trigger handling
- **GitHub** → Streamlit Cloud source (required by Streamlit's deployment model)

Both repositories are kept in sync via automated pushes, ensuring code consistency across platforms.

---

## Security & Configuration

All sensitive credentials are managed through environment variables:

| Variable | Purpose |
|----------|---------|
| `AIRTABLE_API_KEY` | Database access token |
| `AIRTABLE_BASE_ID` | Target database identifier |
| `INFONLINE_API_KEY` | Data source authentication |
| `OPENAI_API_KEY` | GPT API access |
| `TEAMS_WEBHOOK_URL` | Notification endpoint |

Credentials are stored in:
- GitLab CI/CD Variables (for pipelines)
- Streamlit Cloud Secrets (for dashboard)
- Airtable Automations (for triggers)

---

## Scalability & Extensibility

The architecture supports easy expansion:

- **New Properties:** Add site configurations to the ingestion script
- **New Metrics:** Extend the API calls and database schema
- **New Channels:** Webhook integration pattern works for Slack, Discord, etc.
- **New Dashboards:** Streamlit's component model allows rapid UI development
- **New Reports:** Python scripts can generate any output format (PDF, Excel, etc.)

---

## Conclusion

ÖWA Reporter transforms web analytics from a manual, reactive process into an automated, intelligent system. By combining modern cloud services with AI capabilities, it delivers the insights media teams need—when they need them—without the overhead of traditional BI infrastructure.

**The result:** More informed decisions, faster response to anomalies, and hours saved every week on manual reporting.

---

*Built with Python, powered by AI, delivered through the cloud.*

**Repository:** [GitLab](https://gitlab.com/Florian1143/oewa-reporter) | [GitHub](https://github.com/Florian134/oewa-reporter)  
**Dashboard:** [Streamlit Cloud](https://oewa-reporter-ucgucmpvryylvvkhefxyeq.streamlit.app)

---

© 2025 Russmedia Digital | ÖWA Reporter v2.0

