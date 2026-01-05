"""
Konfigurationsmanagement
========================

Lädt Konfiguration aus Environment-Variablen oder .env Datei.
Mit erweiterter Validierung und Type Checking.
"""

import os
import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Union
from dotenv import load_dotenv

# .env Datei laden (falls vorhanden)
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)


# =============================================================================
# VALIDATION HELPERS
# =============================================================================

class ConfigError(Exception):
    """Konfigurationsfehler"""
    pass


def validate_url(url: str, name: str) -> str:
    """Validiert eine URL"""
    if not url:
        return url
    
    if not re.match(r'^https?://', url):
        raise ConfigError(f"{name}: URL muss mit http:// oder https:// beginnen")
    
    return url.rstrip('/')


def validate_positive_int(value: int, name: str, min_val: int = 1) -> int:
    """Validiert eine positive Ganzzahl"""
    if value < min_val:
        raise ConfigError(f"{name}: Muss mindestens {min_val} sein (ist: {value})")
    return value


def validate_range(value: float, name: str, min_val: float, max_val: float) -> float:
    """Validiert einen Wert im Bereich"""
    if not min_val <= value <= max_val:
        raise ConfigError(f"{name}: Muss zwischen {min_val} und {max_val} sein (ist: {value})")
    return value


def parse_bool(value: str) -> bool:
    """Parst einen String zu Boolean"""
    return value.lower() in ('true', '1', 'yes', 'on')


def parse_int(value: str, default: int = 0) -> int:
    """Parst einen String zu Integer mit Default"""
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def parse_float(value: str, default: float = 0.0) -> float:
    """Parst einen String zu Float mit Default"""
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


# =============================================================================
# CONFIG DATACLASSES
# =============================================================================

@dataclass
class APIConfig:
    """INFOnline API Konfiguration"""
    base_url: str = "https://reportingapi.infonline.de"
    api_key: str = ""
    timeout: int = 30
    max_retries: int = 3
    retry_delay: float = 1.0
    
    def validate(self) -> List[str]:
        """Validiert die API-Konfiguration"""
        errors = []
        
        if not self.api_key:
            errors.append("INFONLINE_API_KEY ist nicht gesetzt")
        elif len(self.api_key) < 10:
            errors.append("INFONLINE_API_KEY scheint zu kurz zu sein")
        
        if self.timeout < 5:
            errors.append(f"INFONLINE_TIMEOUT sollte mindestens 5 sein (ist: {self.timeout})")
        
        if self.max_retries < 0:
            errors.append(f"INFONLINE_MAX_RETRIES kann nicht negativ sein")
        
        return errors


@dataclass
class DatabaseConfig:
    """Datenbank Konfiguration"""
    url: str = ""
    echo: bool = False  # SQL Logging
    pool_size: int = 5
    max_overflow: int = 10
    
    def validate(self) -> List[str]:
        """Validiert die Datenbank-Konfiguration"""
        errors = []
        
        if not self.url:
            errors.append("DATABASE_URL ist nicht gesetzt")
        elif not re.match(r'^(postgresql|sqlite|mysql)', self.url):
            errors.append(f"DATABASE_URL: Unbekannter Datenbanktyp")
        
        if self.pool_size < 1:
            errors.append(f"DATABASE_POOL_SIZE muss mindestens 1 sein")
        
        return errors
    
    @property
    def is_sqlite(self) -> bool:
        """Prüft ob SQLite verwendet wird"""
        return 'sqlite' in self.url.lower()
    
    @property
    def is_postgres(self) -> bool:
        """Prüft ob PostgreSQL verwendet wird"""
        return 'postgresql' in self.url.lower() or 'postgres' in self.url.lower()


@dataclass
class TeamsConfig:
    """Microsoft Teams Webhook Konfiguration"""
    webhook_url: str = ""
    enabled: bool = True
    retry_attempts: int = 3
    retry_delay: float = 1.0
    
    def validate(self) -> List[str]:
        """Validiert die Teams-Konfiguration"""
        errors = []
        
        if self.enabled and not self.webhook_url:
            errors.append("TEAMS_WEBHOOK_URL ist nicht gesetzt (oder TEAMS_ENABLED=false setzen)")
        elif self.webhook_url and not self.webhook_url.startswith('https://'):
            errors.append("TEAMS_WEBHOOK_URL muss mit https:// beginnen")
        
        return errors


@dataclass
class OpenAIConfig:
    """OpenAI GPT Konfiguration für KI-Reports"""
    api_key: str = ""
    model: str = "gpt-4o-mini"  # Kosteneffizient
    max_tokens: int = 1000
    enabled: bool = True
    
    def validate(self) -> List[str]:
        """Validiert die OpenAI-Konfiguration"""
        errors = []
        
        if self.enabled and not self.api_key:
            errors.append("OPENAI_API_KEY ist nicht gesetzt (oder OPENAI_ENABLED=false setzen)")
        
        return errors


@dataclass
class AirtableConfig:
    """Airtable Synchronisation Konfiguration"""
    api_key: str = ""
    base_id: str = ""
    enabled: bool = False  # Default: deaktiviert
    measurements_table: str = "Measurements"
    alerts_table: str = "Alerts"
    
    def validate(self) -> List[str]:
        """Validiert die Airtable-Konfiguration"""
        errors = []
        
        if self.enabled:
            if not self.api_key:
                errors.append("AIRTABLE_API_KEY ist nicht gesetzt")
            if not self.base_id:
                errors.append("AIRTABLE_BASE_ID ist nicht gesetzt")
        
        return errors


@dataclass
class AlertThresholdsConfig:
    """Business-kritische Schwellenwerte für Alarming"""
    # Page Impressions - Absolute Mindestwerte
    pi_warning: int = 300000      # < 300.000 PI/Tag
    pi_critical: int = 200000     # < 200.000 PI/Tag
    pi_emergency: int = 100000    # < 100.000 PI/Tag
    
    # Visits - Absolute Mindestwerte
    visits_warning: int = 100000
    visits_critical: int = 70000
    visits_emergency: int = 40000
    
    # Prozentuale Abweichungen
    pct_warning: float = -0.15    # -15%
    pct_critical: float = -0.25   # -25%
    pct_emergency: float = -0.40  # -40%


@dataclass
class AnomalyConfig:
    """Anomalie-Erkennungs-Konfiguration"""
    lookback_days: int = 56  # 8 Wochen
    min_data_points: int = 7  # Mindestens 7 Datenpunkte
    
    # Warning Schwellwerte
    warning_zscore: float = 2.0
    warning_pct_delta: float = 0.15  # 15%
    
    # Critical Schwellwerte
    critical_zscore: float = 2.5
    critical_pct_delta: float = 0.20  # 20%
    
    def validate(self) -> List[str]:
        """Validiert die Anomalie-Konfiguration"""
        errors = []
        
        if self.lookback_days < 7:
            errors.append(f"ANOMALY_LOOKBACK_DAYS sollte mindestens 7 sein")
        
        if self.min_data_points < 3:
            errors.append(f"ANOMALY_MIN_DATA_POINTS sollte mindestens 3 sein")
        
        if self.warning_zscore >= self.critical_zscore:
            errors.append("ANOMALY_WARNING_ZSCORE sollte kleiner als CRITICAL sein")
        
        if self.warning_pct_delta >= self.critical_pct_delta:
            errors.append("ANOMALY_WARNING_PCT sollte kleiner als CRITICAL sein")
        
        return errors


@dataclass
class SiteConfig:
    """Site-Konfiguration"""
    site_id: str
    brand: str
    surface: str
    name: str
    
    def __post_init__(self):
        # Normalisierung
        self.brand = self.brand.lower()
        self.surface = self.surface.lower()


# =============================================================================
# SITE DEFINITIONS
# =============================================================================

# VOL.at Site-Definitionen
VOL_SITES: List[SiteConfig] = [
    SiteConfig(
        site_id="at_w_atvol",
        brand="vol",
        surface="web",
        name="VOL.at Web"
    ),
    SiteConfig(
        site_id="at_i_volat",
        brand="vol",
        surface="ios",
        name="VOL.at iOS"
    ),
    SiteConfig(
        site_id="at_a_volat",
        brand="vol",
        surface="android",
        name="VOL.at Android"
    ),
]

# Optional: Vienna.at Sites
VIENNA_SITES: List[SiteConfig] = [
    SiteConfig(
        site_id="at_w_atvienna",
        brand="vienna",
        surface="web",
        name="VIENNA.at Web"
    ),
    SiteConfig(
        site_id="at_i_viennaat",
        brand="vienna",
        surface="ios",
        name="VIENNA.at iOS"
    ),
    SiteConfig(
        site_id="at_a_viennaat",
        brand="vienna",
        surface="android",
        name="VIENNA.at Android"
    ),
]

# Verfügbare Metriken
AVAILABLE_METRICS = ["pageimpressions", "visits", "clients", "uniqueclients", "usetime", "devices"]
DEFAULT_METRICS = ["pageimpressions", "visits"]


# =============================================================================
# MAIN CONFIG CLASS
# =============================================================================

@dataclass
class Config:
    """Hauptkonfiguration"""
    api: APIConfig = field(default_factory=APIConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    teams: TeamsConfig = field(default_factory=TeamsConfig)
    anomaly: AnomalyConfig = field(default_factory=AnomalyConfig)
    openai: OpenAIConfig = field(default_factory=OpenAIConfig)
    airtable: AirtableConfig = field(default_factory=AirtableConfig)
    alert_thresholds: AlertThresholdsConfig = field(default_factory=AlertThresholdsConfig)
    
    # Aktive Sites (Standard: nur VOL.at)
    sites: List[SiteConfig] = field(default_factory=lambda: VOL_SITES.copy())
    
    # Aktive Metriken
    metrics: List[str] = field(default_factory=lambda: DEFAULT_METRICS.copy())
    
    # Logging
    log_level: str = "INFO"
    
    @classmethod
    def from_env(cls) -> "Config":
        """Lädt Konfiguration aus Environment-Variablen"""
        config = cls()
        
        # API Konfiguration
        config.api.api_key = os.getenv("INFONLINE_API_KEY", "")
        config.api.base_url = os.getenv("INFONLINE_API_URL", config.api.base_url)
        config.api.timeout = parse_int(os.getenv("INFONLINE_TIMEOUT", "30"), 30)
        config.api.max_retries = parse_int(os.getenv("INFONLINE_MAX_RETRIES", "3"), 3)
        config.api.retry_delay = parse_float(os.getenv("INFONLINE_RETRY_DELAY", "1.0"), 1.0)
        
        # Datenbank
        config.database.url = os.getenv(
            "DATABASE_URL", 
            "postgresql+psycopg2://postgres:postgres@localhost:5432/oewa_reporting"
        )
        config.database.echo = parse_bool(os.getenv("DATABASE_ECHO", "false"))
        config.database.pool_size = parse_int(os.getenv("DATABASE_POOL_SIZE", "5"), 5)
        config.database.max_overflow = parse_int(os.getenv("DATABASE_MAX_OVERFLOW", "10"), 10)
        
        # Teams
        config.teams.webhook_url = os.getenv("TEAMS_WEBHOOK_URL", "")
        config.teams.enabled = parse_bool(os.getenv("TEAMS_ENABLED", "true"))
        config.teams.retry_attempts = parse_int(os.getenv("TEAMS_RETRY_ATTEMPTS", "3"), 3)
        config.teams.retry_delay = parse_float(os.getenv("TEAMS_RETRY_DELAY", "1.0"), 1.0)
        
        # Anomalie-Erkennung
        config.anomaly.lookback_days = parse_int(os.getenv("ANOMALY_LOOKBACK_DAYS", "56"), 56)
        config.anomaly.min_data_points = parse_int(os.getenv("ANOMALY_MIN_DATA_POINTS", "7"), 7)
        config.anomaly.warning_zscore = parse_float(os.getenv("ANOMALY_WARNING_ZSCORE", "2.0"), 2.0)
        config.anomaly.warning_pct_delta = parse_float(os.getenv("ANOMALY_WARNING_PCT", "0.15"), 0.15)
        config.anomaly.critical_zscore = parse_float(os.getenv("ANOMALY_CRITICAL_ZSCORE", "2.5"), 2.5)
        config.anomaly.critical_pct_delta = parse_float(os.getenv("ANOMALY_CRITICAL_PCT", "0.20"), 0.20)
        
        # Logging
        config.log_level = os.getenv("LOG_LEVEL", "INFO").upper()
        if config.log_level not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
            config.log_level = "INFO"
        
        # Sites aktivieren
        include_vienna = parse_bool(os.getenv("INCLUDE_VIENNA", "false"))
        if include_vienna:
            config.sites.extend(VIENNA_SITES)
        
        # Metriken
        metrics_env = os.getenv("METRICS", "pageimpressions,visits")
        config.metrics = [m.strip().lower() for m in metrics_env.split(",") if m.strip()]
        
        # Validiere Metriken
        invalid_metrics = [m for m in config.metrics if m not in AVAILABLE_METRICS]
        if invalid_metrics:
            import logging
            logging.getLogger(__name__).warning(
                f"Unbekannte Metriken ignoriert: {invalid_metrics}"
            )
            config.metrics = [m for m in config.metrics if m in AVAILABLE_METRICS]
        
        # OpenAI Konfiguration
        config.openai.api_key = os.getenv("OPENAI_API_KEY", "")
        config.openai.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        config.openai.max_tokens = parse_int(os.getenv("OPENAI_MAX_TOKENS", "1000"), 1000)
        config.openai.enabled = parse_bool(os.getenv("OPENAI_ENABLED", "true"))
        
        # Airtable Konfiguration
        config.airtable.api_key = os.getenv("AIRTABLE_API_KEY", "")
        config.airtable.base_id = os.getenv("AIRTABLE_BASE_ID", "appj6S8TQHMlKyahg")
        config.airtable.enabled = parse_bool(os.getenv("AIRTABLE_ENABLED", "false"))
        config.airtable.measurements_table = os.getenv("AIRTABLE_MEASUREMENTS_TABLE", "Measurements")
        config.airtable.alerts_table = os.getenv("AIRTABLE_ALERTS_TABLE", "Alerts")
        
        # Alert-Schwellenwerte
        config.alert_thresholds.pi_warning = parse_int(os.getenv("ALERT_PI_WARNING", "300000"), 300000)
        config.alert_thresholds.pi_critical = parse_int(os.getenv("ALERT_PI_CRITICAL", "200000"), 200000)
        config.alert_thresholds.pi_emergency = parse_int(os.getenv("ALERT_PI_EMERGENCY", "100000"), 100000)
        config.alert_thresholds.pct_warning = parse_float(os.getenv("ALERT_PCT_WARNING", "-0.15"), -0.15)
        config.alert_thresholds.pct_critical = parse_float(os.getenv("ALERT_PCT_CRITICAL", "-0.25"), -0.25)
        
        return config
    
    def validate(self) -> List[str]:
        """Validiert die gesamte Konfiguration und gibt Fehler zurück"""
        errors = []
        
        errors.extend(self.api.validate())
        errors.extend(self.database.validate())
        errors.extend(self.teams.validate())
        errors.extend(self.anomaly.validate())
        errors.extend(self.openai.validate())
        errors.extend(self.airtable.validate())
        
        if not self.sites:
            errors.append("Keine Sites konfiguriert")
        
        if not self.metrics:
            errors.append("Keine Metriken konfiguriert")
        
        return errors
    
    def is_valid(self) -> bool:
        """Prüft ob die Konfiguration valide ist"""
        return len(self.validate()) == 0
    
    def to_dict(self) -> dict:
        """Konvertiert zu Dictionary (ohne sensitive Daten)"""
        return {
            "api": {
                "base_url": self.api.base_url,
                "timeout": self.api.timeout,
                "max_retries": self.api.max_retries,
                "has_api_key": bool(self.api.api_key),
            },
            "database": {
                "type": "sqlite" if self.database.is_sqlite else "postgresql",
                "pool_size": self.database.pool_size,
                "echo": self.database.echo,
            },
            "teams": {
                "enabled": self.teams.enabled,
                "has_webhook": bool(self.teams.webhook_url),
            },
            "anomaly": {
                "lookback_days": self.anomaly.lookback_days,
                "warning_zscore": self.anomaly.warning_zscore,
                "critical_zscore": self.anomaly.critical_zscore,
            },
            "sites_count": len(self.sites),
            "metrics": self.metrics,
            "log_level": self.log_level,
        }


# =============================================================================
# SINGLETON MANAGEMENT
# =============================================================================

# Globale Konfiguration (Singleton)
_config: Optional[Config] = None


def get_config() -> Config:
    """Gibt die globale Konfiguration zurück"""
    global _config
    if _config is None:
        _config = Config.from_env()
    return _config


def reload_config() -> Config:
    """Lädt die Konfiguration neu"""
    global _config
    _config = Config.from_env()
    return _config


def set_config(config: Config):
    """Setzt eine benutzerdefinierte Konfiguration (für Tests)"""
    global _config
    _config = config
