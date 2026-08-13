"""
Function 1 — resolve_drug_name(name)

Resolves any drug name (INN, brand, Tunisian brand, French brand) to the
canonical INN stored in the graph.  Everything else in this layer calls this
first so the rest of the system never worries about name variations.

Because every other check resolves its inputs, name resolution is by far the
most repeated query in the system. Results are cached in-process (drug names
are static reference data) and :func:`resolve_many` resolves a whole
prescription in one round-trip — both are what keep the reactive engine
inside its latency budget.
"""
import copy
import threading

from neo4j.exceptions import Neo4jError

from ._neo4j import connect, ok, not_found, err

# ── Drug-reference cache ──────────────────────────────────────────────────────
# Keyed by the lower-cased, stripped input name. Holds both hits and misses:
# the drug catalogue does not change while the process is running.
_cache: dict[str, dict] = {}
_cache_lock = threading.Lock()


def clear_resolve_cache() -> None:
    """Empty the resolution cache (call after reloading the graph, or in tests)."""
    with _cache_lock:
        _cache.clear()


def resolve_cache_size() -> int:
    """Number of cached name resolutions — used by the benchmark harness."""
    with _cache_lock:
        return len(_cache)


def _cache_get(key: str) -> dict | None:
    with _cache_lock:
        hit = _cache.get(key)
    return copy.deepcopy(hit) if hit is not None else None


def _cache_put(key: str, envelope: dict) -> None:
    with _cache_lock:
        _cache[key] = copy.deepcopy(envelope)


def _found_envelope(name: str, canonical: str, rxnorm, match_type: str) -> dict:
    return ok(
        {
            "canonical":  canonical,
            "rxnorm_cui": rxnorm,
            "match_type": match_type,
            "input":      name,
        },
        f"Resolved '{name}' -> '{canonical}' (via {match_type})",
    )


def resolve_drug_name(name: str) -> dict:
    """
    Resolve any drug name to its canonical INN molecule.

    Tries in order:
      1. Direct INN match on Molecule.inn
      2. Brand name match on Drug.brand_name or Drug.brand_name_tn or Drug.brand_name_fr

    Returns envelope with canonical INN, RxNorm CUI, and how it was matched.
    Successful and not-found resolutions are cached in-process; transient
    errors are not.

    Examples:
        resolve_drug_name("Tahor")     -> atorvastatin  (brand match)
        resolve_drug_name("warfarin")  -> warfarin       (inn match)
        resolve_drug_name("Coumadin")  -> warfarin       (brand match)
        resolve_drug_name("zyboxithol")-> not_found
    """
    if not name or not name.strip():
        return err("Empty drug name provided")

    name_clean = name.strip()
    key = name_clean.lower()

    cached = _cache_get(key)
    if cached is not None:
        # Keep the caller's spelling in the echoed envelope.
        if cached.get("status") == "found":
            cached["data"]["input"] = name
        return cached

    driver = connect()
    try:
        result = driver.execute_query(
            """
            MATCH (m:Molecule)
            WHERE toLower(m.inn) = toLower($name)
            RETURN m.inn AS canonical, m.rxnorm_cui AS rxnorm,
                   'inn' AS match_type
            UNION
            MATCH (d:Drug)-[:BRAND_OF]->(m:Molecule)
            WHERE toLower(d.brand_name)    = toLower($name)
               OR toLower(d.brand_name_tn) = toLower($name)
               OR toLower(d.brand_name_fr) = toLower($name)
            RETURN m.inn AS canonical, m.rxnorm_cui AS rxnorm,
                   'brand' AS match_type
            """,
            name=name_clean,
        )

        if not result.records:
            envelope = not_found(f"'{name}' not found in knowledge base")
            _cache_put(key, envelope)
            return envelope

        rec = result.records[0]
        envelope = _found_envelope(name, rec["canonical"], rec["rxnorm"], rec["match_type"])
        _cache_put(key, envelope)
        return envelope

    except Exception as exc:
        # Transient failures are never cached.
        return err(str(exc))
    finally:
        driver.close()


def resolve_many(names: list[str]) -> dict[str, dict]:
    """
    Resolve a list of drug names in a single round-trip and warm the cache.

    This is the reactive engine's preload step: one query for the whole
    prescription plus the patient's active medications, so the per-check
    ``resolve_drug_name`` calls that follow are all cache hits.

    Falls back to sequential resolution if the batched query fails, so
    behaviour is always correct even if the batch form is unsupported.

    Returns:
        ``{original_name: envelope}`` for every requested name.
    """
    wanted = [n for n in (names or []) if n and n.strip()]
    if not wanted:
        return {}

    out: dict[str, dict] = {}
    pending: list[str] = []
    for name in wanted:
        cached = _cache_get(name.strip().lower())
        if cached is not None:
            if cached.get("status") == "found":
                cached["data"]["input"] = name
            out[name] = cached
        else:
            pending.append(name)

    if not pending:
        return out

    driver = connect()
    try:
        result = driver.execute_query(
            """
            UNWIND $names AS raw
            WITH raw, toLower(trim(raw)) AS key
            OPTIONAL MATCH (m:Molecule)
              WHERE toLower(m.inn) = key
            OPTIONAL MATCH (d:Drug)-[:BRAND_OF]->(bm:Molecule)
              WHERE toLower(d.brand_name)    = key
                 OR toLower(d.brand_name_tn) = key
                 OR toLower(d.brand_name_fr) = key
            WITH raw,
                 coalesce(m.inn, bm.inn)               AS canonical,
                 coalesce(m.rxnorm_cui, bm.rxnorm_cui) AS rxnorm,
                 CASE WHEN m IS NOT NULL THEN 'inn' ELSE 'brand' END AS match_type
            WHERE canonical IS NOT NULL
            RETURN raw AS input, canonical, rxnorm, match_type
            """,
            names=pending,
        )

        matched: dict[str, dict] = {}
        for rec in result.records:
            original = rec["input"]
            if original in matched:
                continue  # first match wins, mirroring resolve_drug_name
            matched[original] = _found_envelope(
                original, rec["canonical"], rec["rxnorm"], rec["match_type"]
            )

        for name in pending:
            envelope = matched.get(name) or not_found(f"'{name}' not found in knowledge base")
            _cache_put(name.strip().lower(), envelope)
            out[name] = envelope
        return out

    except Neo4jError:
        # The server answered but rejected the batched form (e.g. an older
        # Cypher version). It is reachable, so resolving one-by-one still works.
        for name in pending:
            out[name] = resolve_drug_name(name)
        return out
    except Exception as exc:
        # Transport/connectivity failure. Retrying each name individually would
        # just repeat the same timeout N times, so report the failure at once —
        # a fast, clear error beats a slow one.
        for name in pending:
            out[name] = err(str(exc))
        return out
    finally:
        driver.close()
