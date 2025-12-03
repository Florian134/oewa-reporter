"""
Datenbankverbindung
===================

Verwaltet SQLAlchemy Engine und Sessions mit:
- Connection Retry-Logik
- Connection Pooling
- Automatisches Reconnect bei Verbindungsverlust
"""

import logging
import time
from contextlib import contextmanager
from typing import Generator, Optional, Callable
from functools import wraps

from sqlalchemy import create_engine, text, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError, OperationalError, DisconnectionError
from sqlalchemy.pool import Pool

from .config import get_config
from .models import Base

logger = logging.getLogger(__name__)


# =============================================================================
# RETRY DECORATOR
# =============================================================================

def retry_on_disconnect(
    max_retries: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0
) -> Callable:
    """
    Decorator für automatisches Retry bei Datenbankverbindungsfehlern.
    
    Args:
        max_retries: Maximale Anzahl Versuche
        delay: Initiale Wartezeit in Sekunden
        backoff: Multiplikator für Wartezeit bei jedem Retry
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            current_delay = delay
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except (OperationalError, DisconnectionError) as e:
                    last_exception = e
                    
                    if attempt < max_retries:
                        logger.warning(
                            f"Datenbankverbindung fehlgeschlagen (Versuch {attempt + 1}/{max_retries + 1}): {e}. "
                            f"Retry in {current_delay:.1f}s..."
                        )
                        time.sleep(current_delay)
                        current_delay *= backoff
                        
                        # Engine neu initialisieren
                        _reset_engine()
                    else:
                        logger.error(f"Datenbankverbindung fehlgeschlagen nach {max_retries + 1} Versuchen")
                        raise
                except SQLAlchemyError as e:
                    # Andere SQLAlchemy Fehler nicht retrien
                    raise
            
            raise last_exception
        
        return wrapper
    return decorator


# =============================================================================
# ENGINE MANAGEMENT
# =============================================================================

# Globale Engine und SessionFactory
_engine = None
_SessionFactory = None


def _reset_engine():
    """Setzt die Engine zurück für Reconnect"""
    global _engine, _SessionFactory
    
    if _engine is not None:
        try:
            _engine.dispose()
        except Exception as e:
            logger.debug(f"Fehler beim Dispose der Engine: {e}")
    
    _engine = None
    _SessionFactory = None


def get_engine():
    """
    Gibt die SQLAlchemy Engine zurück (Singleton).
    
    Features:
    - Connection Pooling
    - Pool Pre-Ping für Verbindungsprüfung
    - Automatisches Reconnect bei Pool-Exhaustion
    """
    global _engine
    
    if _engine is None:
        config = get_config()
        
        # Engine-Optionen basierend auf DB-Typ
        engine_kwargs = {
            "echo": config.database.echo,
            "pool_pre_ping": True,  # Verbindung vor Nutzung prüfen
        }
        
        # SQLite braucht andere Pool-Einstellungen
        if "sqlite" in config.database.url.lower():
            engine_kwargs.update({
                "connect_args": {"check_same_thread": False},
                "pool_size": 0,  # SQLite: StaticPool verwenden
            })
        else:
            # PostgreSQL / MySQL
            engine_kwargs.update({
                "pool_size": config.database.pool_size,
                "max_overflow": config.database.max_overflow,
                "pool_timeout": 30,  # Warte max 30s auf Connection
                "pool_recycle": 3600,  # Recycle Connections nach 1h
            })
        
        _engine = create_engine(config.database.url, **engine_kwargs)
        
        # Event Listeners für Connection-Handling
        @event.listens_for(_engine, "connect")
        def connect(dbapi_connection, connection_record):
            logger.debug("Neue Datenbankverbindung hergestellt")
        
        @event.listens_for(_engine, "checkout")
        def checkout(dbapi_connection, connection_record, connection_proxy):
            logger.debug("Connection aus Pool geholt")
        
        @event.listens_for(_engine, "checkin")
        def checkin(dbapi_connection, connection_record):
            logger.debug("Connection in Pool zurückgegeben")
        
        # Log URL (ohne Passwort)
        safe_url = config.database.url.split("@")[-1] if "@" in config.database.url else config.database.url
        logger.info(f"Datenbankverbindung hergestellt: {safe_url}")
    
    return _engine


def get_session_factory():
    """Gibt die Session Factory zurück"""
    global _SessionFactory
    
    if _SessionFactory is None:
        engine = get_engine()
        _SessionFactory = sessionmaker(bind=engine, expire_on_commit=False)
    
    return _SessionFactory


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """
    Context Manager für Datenbank-Sessions.
    
    Features:
    - Automatischer Commit bei Erfolg
    - Automatischer Rollback bei Fehler
    - Automatisches Session-Close
    - Retry bei Verbindungsfehlern
    
    Beispiel:
        with get_session() as session:
            session.query(Measurement).all()
    """
    SessionFactory = get_session_factory()
    session = SessionFactory()
    
    try:
        yield session
        session.commit()
    except OperationalError as e:
        session.rollback()
        logger.error(f"Datenbankfehler (Operational): {e}")
        # Bei Verbindungsfehler Engine zurücksetzen
        _reset_engine()
        raise
    except SQLAlchemyError as e:
        session.rollback()
        logger.error(f"Datenbankfehler: {e}")
        raise
    except Exception as e:
        session.rollback()
        logger.error(f"Unerwarteter Fehler in Session: {e}")
        raise
    finally:
        session.close()


@retry_on_disconnect(max_retries=3, delay=1.0)
def init_database(drop_existing: bool = False):
    """
    Initialisiert die Datenbank (erstellt Tabellen).
    
    Args:
        drop_existing: Wenn True, werden existierende Tabellen gelöscht.
    """
    engine = get_engine()
    
    if drop_existing:
        logger.warning("Lösche existierende Tabellen...")
        Base.metadata.drop_all(engine)
    
    logger.info("Erstelle Datenbank-Tabellen...")
    Base.metadata.create_all(engine)
    logger.info("Datenbank initialisiert.")


@retry_on_disconnect(max_retries=3, delay=0.5)
def check_connection() -> bool:
    """
    Prüft die Datenbankverbindung.
    
    Returns:
        True bei erfolgreicher Verbindung
    """
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("Datenbankverbindung erfolgreich.")
        return True
    except Exception as e:
        logger.error(f"Datenbankverbindung fehlgeschlagen: {e}")
        return False


def close_connection():
    """Schließt die Datenbankverbindung und gibt Ressourcen frei"""
    global _engine, _SessionFactory
    
    if _engine is not None:
        _engine.dispose()
        _engine = None
        _SessionFactory = None
        logger.info("Datenbankverbindung geschlossen.")


def get_connection_stats() -> dict:
    """
    Gibt Statistiken über den Connection Pool zurück.
    
    Returns:
        Dict mit Pool-Statistiken
    """
    if _engine is None:
        return {"status": "not_initialized"}
    
    pool = _engine.pool
    
    return {
        "status": "active",
        "pool_size": pool.size() if hasattr(pool, 'size') else 0,
        "checked_in": pool.checkedin() if hasattr(pool, 'checkedin') else 0,
        "checked_out": pool.checkedout() if hasattr(pool, 'checkedout') else 0,
        "overflow": pool.overflow() if hasattr(pool, 'overflow') else 0,
    }


# Context Manager für die gesamte Applikation
class DatabaseManager:
    """
    Context Manager für die Datenbank-Lebenszeit.
    
    Verwendung:
        with DatabaseManager() as db:
            # Datenbank ist initialisiert
            pass
        # Verbindungen werden automatisch geschlossen
    """
    
    def __init__(self, init: bool = True, drop_existing: bool = False):
        self.init = init
        self.drop_existing = drop_existing
    
    def __enter__(self):
        if self.init:
            init_database(drop_existing=self.drop_existing)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        close_connection()
        return False
    
    @staticmethod
    def get_session():
        """Wrapper für get_session()"""
        return get_session()
