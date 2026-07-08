"""
Functions 3 & 4 — detect_pairwise_interactions and detect_cyp_competition

These two functions together cover every interaction type the graph can
express: direct DDI edges (function 3) and enzyme-mediated 2-hop paths
that have no direct edge (function 4).
"""
from itertools import combinations
from ._neo4j import connect, ok, not_found, err
from .resolve import resolve_drug_name

# Severity ordering for sorting results (most severe first)
_SEV_RANK = {
    "contre_indique":      1,
    "major":               2,
    "deconseillee":        3,
    "moderate":            4,
    "precaution_emploi":   5,
    "a_prendre_en_compte": 6,
    "minor":               7,
}


def _rank(sev):
    return _SEV_RANK.get(sev or "", 99)


def detect_pairwise_interactions(drug_list: list[str]) -> dict:
    """
    For every pair in drug_list, find any direct INTERACTS_WITH edge between
    their molecules.  Returns all found interactions sorted by severity.

    Example:
        detect_pairwise_interactions(["warfarin", "aspirin", "omeprazole"])
        -> 1 interaction: warfarin+aspirin (major, additive bleeding risk)
           3 pairs checked, 0 interactions for aspirin+omeprazole and
           warfarin+omeprazole via direct edge
    """
    if len(drug_list) < 2:
        return err("Need at least 2 drugs to check interactions")

    # Resolve all names first
    resolved = {}
    unresolved = []
    for name in drug_list:
        r = resolve_drug_name(name)
        if r["status"] == "found":
            resolved[name] = r["data"]["canonical"]
        else:
            unresolved.append(name)

    inns = list(set(resolved.values()))
    pairs = list(combinations(inns, 2))

    if len(inns) < 2:
        return not_found(
            f"Could not resolve enough drugs to check pairs. "
            f"Unresolved: {unresolved}"
        )

    driver = connect()
    try:
        interactions = []
        for inn_a, inn_b in pairs:
            result = driver.execute_query(
                """
                MATCH (a:Molecule {inn: $inn_a})-[r:INTERACTS_WITH]-(b:Molecule {inn: $inn_b})
                RETURN a.inn AS drug_a, b.inn AS drug_b,
                       r.severity_active AS severity,
                       r.clinical_effect AS effect,
                       r.management      AS mechanism,
                       r.source_confidence AS source
                """,
                inn_a=inn_a, inn_b=inn_b,
            )
            for rec in result.records:
                interactions.append({
                    "drug_a":    rec["drug_a"],
                    "drug_b":    rec["drug_b"],
                    "severity":  rec["severity"],
                    "effect":    rec["effect"],
                    "mechanism": rec["mechanism"],
                    "source":    rec["source"],
                })

        interactions.sort(key=lambda x: _rank(x["severity"]))

        status = "found" if interactions else "not_found"
        msg = (
            f"{len(interactions)} interaction(s) found in {len(pairs)} pair(s) checked"
            + (f" | unresolved: {unresolved}" if unresolved else "")
        )
        return {
            "status": status,
            "data": {
                "drugs_resolved":     list(resolved.values()),
                "drugs_unresolved":   unresolved,
                "pairs_checked":      len(pairs),
                "interactions_found": len(interactions),
                "interactions":       interactions,
            },
            "message": msg,
        }

    except Exception as exc:
        return err(str(exc))
    finally:
        driver.close()


def detect_cyp_competition(drug_list: list[str]) -> dict:
    """
    Find dangerous CYP competition between drugs — substrate/inhibitor or
    substrate/inducer pairs that share an enzyme.

    This catches interactions the direct-edge check misses: e.g. simvastatin +
    clarithromycin have no INTERACTS_WITH edge, but clarithromycin strongly
    inhibits CYP3A4 which is simvastatin's primary metabolic pathway.

    For each ordered pair (substrate_drug, modulator_drug):
      - substrate drug has SUBSTRATE_OF -> CYP_X
      - modulator drug INHIBITS or INDUCES -> CYP_X

    Example:
        detect_cyp_competition(["simvastatin", "clarithromycin"])
        -> CYP3A4 competition: clarithromycin inhibits (strong), simvastatin
           is substrate -> simvastatin accumulation, rhabdomyolysis risk
    """
    if len(drug_list) < 2:
        return err("Need at least 2 drugs to check CYP competition")

    # Resolve all names
    resolved = {}
    unresolved = []
    for name in drug_list:
        r = resolve_drug_name(name)
        if r["status"] == "found":
            resolved[name] = r["data"]["canonical"]
        else:
            unresolved.append(name)

    inns = list(set(resolved.values()))
    if len(inns) < 2:
        return not_found(
            f"Could not resolve enough drugs. Unresolved: {unresolved}"
        )

    driver = connect()
    try:
        competitions = []
        # Check every ordered pair: A as substrate, B as modulator
        for inn_a, inn_b in combinations(inns, 2):
            for substrate, modulator in [(inn_a, inn_b), (inn_b, inn_a)]:
                result = driver.execute_query(
                    """
                    MATCH (sub:Molecule {inn: $substrate})-[:SUBSTRATE_OF]->(cyp:CYPEnzyme)
                          <-[r:INHIBITS|INDUCES]-(mod:Molecule {inn: $modulator})
                    RETURN sub.inn    AS substrate,
                           mod.inn    AS modulator,
                           cyp.name   AS enzyme,
                           type(r)    AS effect,
                           r.strength AS strength
                    """,
                    substrate=substrate, modulator=modulator,
                )
                for rec in result.records:
                    effect = rec["effect"]
                    strength = rec["strength"] or "unknown"
                    risk = (
                        f"{substrate} accumulation risk"
                        if effect == "INHIBITS"
                        else f"{substrate} subtherapeutic risk (accelerated clearance)"
                    )
                    competitions.append({
                        "substrate":  rec["substrate"],
                        "modulator":  rec["modulator"],
                        "enzyme":     rec["enzyme"],
                        "effect":     effect,
                        "strength":   strength,
                        "risk":       risk,
                    })

        # Deduplicate (same competition may appear from both loop iterations)
        seen = set()
        unique = []
        for c in competitions:
            key = (c["substrate"], c["modulator"], c["enzyme"], c["effect"])
            if key not in seen:
                seen.add(key)
                unique.append(c)

        # Sort: strong inhibitions first
        def sort_key(c):
            strength_rank = {"strong": 0, "moderate": 1, "weak": 2}.get(c["strength"], 3)
            effect_rank   = 0 if c["effect"] == "INHIBITS" else 1
            return (effect_rank, strength_rank)

        unique.sort(key=sort_key)

        status = "found" if unique else "not_found"
        msg = (
            f"{len(unique)} CYP competition(s) found across "
            f"{len(list(combinations(inns, 2)))} pair(s)"
            + (f" | unresolved: {unresolved}" if unresolved else "")
        )
        return {
            "status": status,
            "data": {
                "drugs_resolved":    list(resolved.values()),
                "drugs_unresolved":  unresolved,
                "competitions_found": len(unique),
                "competitions":      unique,
            },
            "message": msg,
        }

    except Exception as exc:
        return err(str(exc))
    finally:
        driver.close()
