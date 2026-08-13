"""Shared Neo4j connection + return-envelope helpers for all query functions."""
import atexit
import os
import threading

from neo4j import GraphDatabase

NEO4J_URI      = os.getenv("NEO4J_URI",      "bolt://localhost:7687")
NEO4J_USER     = os.getenv("NEO4J_USER",     "")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")

# Pool sized for the reactive engine, which fans several checks out across
# threads for a single prescription scan.
_POOL_SIZE = int(os.getenv("NEO4J_POOL_SIZE", "50"))

# The reactive engine answers a pharmacist standing at the counter within a
# 2-second budget, so a database that is down must fail *fast* rather than
# retry for the driver's 30-second default — a slow failure is worse than a
# clear one. Raise these via env vars for bulk loading or a remote instance.
_CONNECTION_TIMEOUT = float(os.getenv("NEO4J_CONNECTION_TIMEOUT", "5.0"))
_MAX_RETRY_TIME     = float(os.getenv("NEO4J_MAX_RETRY_TIME", "3.0"))

_driver = None
_driver_lock = threading.Lock()


class _SharedDriver:
    """
    Thin proxy over the process-wide Neo4j driver.

    Every query function follows the pattern::

        driver = connect()
        try:     driver.execute_query(...)
        finally: driver.close()

    Building a real driver per call costs a TCP connect plus handshake, and
    that dominated latency in the reactive engine (a 7-drug scan created
    40+ drivers). This proxy keeps that call pattern working while reusing a
    single pooled driver: ``close()`` is a deliberate no-op so one call site
    cannot tear down the pool other threads are still using.

    Use :func:`close_driver` for a real shutdown.
    """

    __slots__ = ("_driver",)

    def __init__(self, driver):
        self._driver = driver

    def execute_query(self, *args, **kwargs):
        return self._driver.execute_query(*args, **kwargs)

    def session(self, *args, **kwargs):
        return self._driver.session(*args, **kwargs)

    def verify_connectivity(self):
        return self._driver.verify_connectivity()

    def close(self) -> None:
        """No-op — the shared driver outlives any single query call."""
        return None


def _build_driver():
    auth = (NEO4J_USER, NEO4J_PASSWORD) if NEO4J_USER else None
    return GraphDatabase.driver(
        NEO4J_URI,
        auth=auth,
        max_connection_pool_size=_POOL_SIZE,
        connection_timeout=_CONNECTION_TIMEOUT,
        max_transaction_retry_time=_MAX_RETRY_TIME,
    )


def connect():
    """
    Return the process-wide pooled Neo4j driver.

    Thread-safe and lazily created. The returned object is a
    :class:`_SharedDriver` proxy, so calling ``.close()`` on it is safe.
    """
    global _driver
    if _driver is None:
        with _driver_lock:
            if _driver is None:
                _driver = _build_driver()
    return _SharedDriver(_driver)


def close_driver() -> None:
    """Really close the shared driver — for process shutdown and tests."""
    global _driver
    with _driver_lock:
        if _driver is not None:
            try:
                _driver.close()
            except Exception:
                pass
            _driver = None


atexit.register(close_driver)


def ok(data: dict, message: str = "") -> dict:
    return {"status": "found", "data": data, "message": message}


def not_found(message: str = "", data: dict | None = None) -> dict:
    return {"status": "not_found", "data": data or {}, "message": message}


def err(message: str = "") -> dict:
    return {"status": "error", "data": {}, "message": message}
