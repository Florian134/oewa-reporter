"""
INFOnline/ÖWA API Client
========================

Robuster HTTP-Client für die INFOnline Reporting API mit:
- Retry-Logik mit exponentiellem Backoff
- Rate Limiting (Token Bucket)
- Fehlerbehandlung
- Response-Parsing
"""

import logging
import time
import threading
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from collections import deque
from functools import wraps

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import get_config, SiteConfig

logger = logging.getLogger(__name__)


# =============================================================================
# RATE LIMITER (Token Bucket Algorithm)
# =============================================================================

class RateLimiter:
    """
    Token Bucket Rate Limiter für API-Calls.
    
    Verhindert API-Überlastung durch Begrenzung der Requests pro Zeiteinheit.
    Thread-safe Implementation.
    """
    
    def __init__(
        self, 
        max_requests: int = 10, 
        time_window: float = 1.0,
        min_interval: float = 0.1
    ):
        """
        Args:
            max_requests: Maximale Anzahl Requests im Zeitfenster
            time_window: Zeitfenster in Sekunden
            min_interval: Minimales Intervall zwischen Requests
        """
        self.max_requests = max_requests
        self.time_window = time_window
        self.min_interval = min_interval
        self.requests: deque = deque()
        self.lock = threading.Lock()
        self.last_request_time = 0.0
    
    def acquire(self) -> float:
        """
        Wartet bis ein Request erlaubt ist.
        
        Returns:
            Wartezeit in Sekunden
        """
        with self.lock:
            now = time.time()
            wait_time = 0.0
            
            # Entferne alte Requests außerhalb des Zeitfensters
            while self.requests and self.requests[0] < now - self.time_window:
                self.requests.popleft()
            
            # Prüfe ob Rate Limit erreicht
            if len(self.requests) >= self.max_requests:
                # Warte bis der älteste Request aus dem Fenster fällt
                wait_time = self.requests[0] + self.time_window - now
                if wait_time > 0:
                    time.sleep(wait_time)
                    now = time.time()
                    # Nochmals aufräumen
                    while self.requests and self.requests[0] < now - self.time_window:
                        self.requests.popleft()
            
            # Prüfe Mindestintervall
            time_since_last = now - self.last_request_time
            if time_since_last < self.min_interval:
                additional_wait = self.min_interval - time_since_last
                time.sleep(additional_wait)
                wait_time += additional_wait
                now = time.time()
            
            # Request registrieren
            self.requests.append(now)
            self.last_request_time = now
            
            return wait_time


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class APIResponse:
    """Strukturierte API-Response"""
    success: bool
    status_code: int
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    response_time_ms: float = 0
    retry_count: int = 0
    rate_limit_wait_ms: float = 0
    
    @property
    def metadata(self) -> Optional[Dict]:
        """Gibt Metadata aus Response zurück"""
        if self.data and isinstance(self.data, dict):
            return self.data.get("metadata")
        return None
    
    @property
    def measurements(self) -> Optional[Dict]:
        """Gibt die Messdaten zurück"""
        if self.data and isinstance(self.data, dict):
            return self.data.get("data")
        return None


@dataclass
class MetricData:
    """Geparste Metrik-Daten"""
    site_id: str
    metric: str
    date: str
    aggregation: str
    
    # IOM Daten (hochgerechnet)
    iom_total: Optional[int] = None
    iom_national: Optional[int] = None
    iom_international: Optional[int] = None
    iom_preliminary: bool = True
    
    # IOMp Daten (Consent/Pseudonym)
    iomp_total: Optional[int] = None
    iomp_national: Optional[int] = None
    iomp_international: Optional[int] = None
    
    # IOMb Daten (Zensus/Consentless)
    iomb_total: Optional[int] = None
    
    # Metadaten
    exported_at: Optional[datetime] = None
    version: Optional[str] = None


# =============================================================================
# API CLIENT
# =============================================================================

class INFOnlineAPIClient:
    """
    Client für die INFOnline Reporting API.
    
    Features:
    - Automatische Retry-Logik mit exponentiellem Backoff
    - Rate Limiting (Token Bucket)
    - Response-Parsing
    - Thread-safe
    - Detailliertes Logging
    """
    
    # Mapping von internen Metrik-Namen zu API-Endpoints
    METRIC_ENDPOINTS = {
        "pageimpressions": "/api/v1/pageimpressions",
        "pi": "/api/v1/pageimpressions",
        "visits": "/api/v1/visits",
        "clients": "/api/v1/clients",
        "uniqueclients": "/api/v1/uniqueclients",
        "usetime": "/api/v1/usetime",
        "devices": "/api/v1/devices",
    }
    
    # HTTP Status Codes die einen Retry rechtfertigen
    RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
    
    def __init__(
        self, 
        api_key: str = None, 
        base_url: str = None,
        rate_limit_requests: int = 10,
        rate_limit_window: float = 1.0
    ):
        """
        Initialisiert den API Client.
        
        Args:
            api_key: INFOnline API Key (optional, aus Config)
            base_url: API Base URL (optional, aus Config)
            rate_limit_requests: Max Requests pro Zeitfenster
            rate_limit_window: Zeitfenster in Sekunden
        """
        config = get_config()
        
        self.api_key = api_key or config.api.api_key
        self.base_url = base_url or config.api.base_url
        self.timeout = config.api.timeout
        self.max_retries = config.api.max_retries
        self.retry_delay = config.api.retry_delay
        
        # Rate Limiter initialisieren
        self.rate_limiter = RateLimiter(
            max_requests=rate_limit_requests,
            time_window=rate_limit_window,
            min_interval=0.1  # 100ms Mindestabstand
        )
        
        # Session mit Retry-Logik
        self.session = self._create_session()
        
        # Request Counter für Statistiken
        self._request_count = 0
        self._error_count = 0
        self._total_wait_time = 0.0
    
    def _create_session(self) -> requests.Session:
        """Erstellt eine Session mit Retry-Strategie"""
        session = requests.Session()
        
        # Headers setzen
        session.headers.update({
            "authorization": self.api_key,
            "Accept": "application/json",
            "User-Agent": "OEWA-Reporting/1.0"
        })
        
        # Retry-Strategie
        retry_strategy = Retry(
            total=self.max_retries,
            backoff_factor=self.retry_delay,
            status_forcelist=list(self.RETRYABLE_STATUS_CODES),
            allowed_methods=["GET"],
            raise_on_status=False  # Wir behandeln Status selbst
        )
        
        adapter = HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=10,
            pool_maxsize=20
        )
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        
        return session
    
    def _make_request(
        self, 
        endpoint: str, 
        params: Dict[str, Any]
    ) -> APIResponse:
        """
        Führt einen API-Request durch mit Rate Limiting.
        
        Args:
            endpoint: API-Endpoint (z.B. "/api/v1/pageimpressions")
            params: Query-Parameter
            
        Returns:
            APIResponse mit Daten oder Fehler
        """
        url = f"{self.base_url}{endpoint}"
        
        # Rate Limiting anwenden
        rate_limit_wait = self.rate_limiter.acquire()
        self._total_wait_time += rate_limit_wait
        
        if rate_limit_wait > 0.01:  # Nur loggen wenn nennenswerte Wartezeit
            logger.debug(f"Rate limit: {rate_limit_wait*1000:.0f}ms gewartet")
        
        try:
            start_time = time.time()
            self._request_count += 1
            
            response = self.session.get(
                url,
                params=params,
                timeout=self.timeout
            )
            
            response_time = (time.time() - start_time) * 1000
            
            # Response parsen
            if response.status_code == 200:
                try:
                    data = response.json()
                except (ValueError, requests.exceptions.JSONDecodeError) as e:
                    logger.warning(f"JSON Parse Error: {e}")
                    data = {"raw": response.text}
                
                logger.debug(
                    f"API OK: {endpoint} | {params.get('site')} | "
                    f"{params.get('date')} | {response_time:.0f}ms"
                )
                
                return APIResponse(
                    success=True,
                    status_code=200,
                    data=data,
                    response_time_ms=response_time,
                    rate_limit_wait_ms=rate_limit_wait * 1000
                )
            else:
                self._error_count += 1
                error_msg = f"HTTP {response.status_code}"
                
                try:
                    error_data = response.json()
                    if isinstance(error_data, dict) and "detail" in error_data:
                        error_msg = f"{error_msg}: {error_data['detail']}"
                except (ValueError, requests.exceptions.JSONDecodeError):
                    # JSON Parsing fehlgeschlagen - verwende Text
                    if response.text:
                        error_msg = f"{error_msg}: {response.text[:200]}"
                except Exception as e:
                    # Andere Fehler beim Parsen
                    logger.debug(f"Error parsing response: {type(e).__name__}: {e}")
                
                logger.warning(f"API Fehler: {endpoint} | {error_msg}")
                
                return APIResponse(
                    success=False,
                    status_code=response.status_code,
                    error=error_msg,
                    response_time_ms=response_time,
                    rate_limit_wait_ms=rate_limit_wait * 1000
                )
                
        except requests.exceptions.Timeout as e:
            self._error_count += 1
            logger.error(f"API Timeout: {endpoint} nach {self.timeout}s")
            return APIResponse(
                success=False,
                status_code=0,
                error=f"Timeout nach {self.timeout}s"
            )
            
        except requests.exceptions.ConnectionError as e:
            self._error_count += 1
            logger.error(f"API Verbindungsfehler: {endpoint} | {e}")
            return APIResponse(
                success=False,
                status_code=0,
                error=f"Verbindungsfehler: {str(e)[:100]}"
            )
        
        except requests.exceptions.RequestException as e:
            self._error_count += 1
            logger.error(f"Request Fehler: {endpoint} | {type(e).__name__}: {e}")
            return APIResponse(
                success=False,
                status_code=0,
                error=f"Request Fehler: {str(e)[:100]}"
            )
            
        except Exception as e:
            self._error_count += 1
            logger.error(f"Unerwarteter Fehler: {endpoint} | {type(e).__name__}: {e}")
            return APIResponse(
                success=False,
                status_code=0,
                error=f"Unerwarteter Fehler: {type(e).__name__}"
            )
    
    def health_check(self) -> bool:
        """Prüft ob die API erreichbar ist"""
        try:
            response = self._make_request("/health", {})
            return response.success or response.status_code in (200, 404)
        except Exception as e:
            logger.error(f"Health check fehlgeschlagen: {e}")
            return False
    
    def fetch_metric(
        self,
        metric: str,
        site_id: str,
        date: str,
        aggregation: str = "DAY"
    ) -> APIResponse:
        """
        Holt eine Metrik von der API.
        
        Args:
            metric: Metrik-Name (pageimpressions, visits, etc.)
            site_id: Site-Identifier (z.B. EA000004_desktop)
            date: Datum im Format YYYY-MM-DD
            aggregation: Aggregations-Level (HOUR, DAY, MONTH)
            
        Returns:
            APIResponse mit den Daten
        """
        endpoint = self.METRIC_ENDPOINTS.get(metric.lower())
        
        if not endpoint:
            logger.error(f"Unbekannte Metrik: {metric}")
            return APIResponse(
                success=False,
                status_code=0,
                error=f"Unbekannte Metrik: {metric}"
            )
        
        params = {
            "site": site_id,
            "aggregation": aggregation,
            "date": date,
            "returntype": "json"
        }
        
        return self._make_request(endpoint, params)
    
    def fetch_metric_parsed(
        self,
        metric: str,
        site_id: str,
        date: str,
        aggregation: str = "DAY"
    ) -> Optional[MetricData]:
        """
        Holt und parst eine Metrik.
        
        Returns:
            MetricData Objekt oder None bei Fehler
        """
        response = self.fetch_metric(metric, site_id, date, aggregation)
        
        if not response.success:
            return None
        
        return self._parse_metric_response(response, metric, site_id, date, aggregation)
    
    def _parse_metric_response(
        self,
        response: APIResponse,
        metric: str,
        site_id: str,
        date: str,
        aggregation: str
    ) -> Optional[MetricData]:
        """Parst die API-Response zu MetricData"""
        
        if not response.data or "data" not in response.data:
            logger.warning(f"Keine Daten in Response für {site_id} / {metric} / {date}")
            return None
        
        data = response.data["data"]
        metadata = response.data.get("metadata", {})
        
        metric_data = MetricData(
            site_id=site_id,
            metric=metric,
            date=date,
            aggregation=aggregation,
            version=metadata.get("version"),
        )
        
        # Exported_at parsen (mit Timezone-Awareness)
        if "exported_at" in metadata:
            try:
                exported_str = metadata["exported_at"]
                # Ersetze Z durch +00:00 für ISO-Format
                if exported_str.endswith("Z"):
                    exported_str = exported_str[:-1] + "+00:00"
                metric_data.exported_at = datetime.fromisoformat(exported_str)
            except (ValueError, TypeError) as e:
                logger.debug(f"Konnte exported_at nicht parsen: {e}")
        
        # IOM Daten (hochgerechnet)
        if "iom" in data and data["iom"]:
            iom = data["iom"][0] if isinstance(data["iom"], list) else data["iom"]
            metric_data.iom_total = iom.get("pis") or iom.get("visits") or iom.get("clients")
            metric_data.iom_national = iom.get("pisnat") or iom.get("visitsnat")
            metric_data.iom_international = iom.get("pisint") or iom.get("visitsint")
            metric_data.iom_preliminary = iom.get("preliminary", True)
        
        # IOMp Daten (Consent/Pseudonym)
        if "iomp" in data and data["iomp"]:
            iomp = data["iomp"][0] if isinstance(data["iomp"], list) else data["iomp"]
            metric_data.iomp_total = iomp.get("pis") or iomp.get("visits") or iomp.get("clients")
            metric_data.iomp_national = iomp.get("pisnat") or iomp.get("visitsnat")
            metric_data.iomp_international = iomp.get("pisint") or iomp.get("visitsint")
        
        # IOMb Daten (Zensus/Consentless)
        if "iomb" in data and data["iomb"]:
            iomb = data["iomb"][0] if isinstance(data["iomb"], list) else data["iomb"]
            metric_data.iomb_total = iomb.get("pis")
        
        return metric_data
    
    def fetch_all_metrics_for_site(
        self,
        site_config: SiteConfig,
        date: str,
        metrics: List[str] = None
    ) -> Dict[str, Optional[MetricData]]:
        """
        Holt alle konfigurierten Metriken für eine Site.
        
        Args:
            site_config: Site-Konfiguration
            date: Datum
            metrics: Liste der Metriken (optional, aus Config)
            
        Returns:
            Dict mit Metrik-Namen als Keys und MetricData als Values
        """
        if metrics is None:
            metrics = get_config().metrics
        
        results = {}
        
        for metric in metrics:
            logger.info(f"Hole {metric} für {site_config.name} ({date})")
            
            metric_data = self.fetch_metric_parsed(
                metric=metric,
                site_id=site_config.site_id,
                date=date
            )
            
            results[metric] = metric_data
            # Rate Limiting wird automatisch in _make_request angewendet
        
        return results
    
    def get_stats(self) -> Dict[str, Any]:
        """Gibt Statistiken über die API-Nutzung zurück"""
        return {
            "total_requests": self._request_count,
            "total_errors": self._error_count,
            "error_rate": self._error_count / max(1, self._request_count),
            "total_rate_limit_wait_seconds": self._total_wait_time
        }
    
    def close(self):
        """Schließt die Session"""
        if self.session:
            self.session.close()
            logger.debug(f"API Client geschlossen. Stats: {self.get_stats()}")
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
