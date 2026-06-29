"""
Function 1 — resolve_drug_name(name)

Resolves any drug name (INN, brand, Tunisian brand, French brand) to the
canonical INN stored in the graph.  Everything else in this layer calls this
first so the rest of the system never worries about name variations.
"""
from ._neo4j import connect, ok, not_found, err


def resolve_drug_name(name: str) -> dict:
    """
    Resolve any drug name to its canonical INN molecule.

    Tries in order:
      1. Direct INN match on Molecule.inn
      2. Brand name match on Drug.brand_name or Drug.brand_name_tn or Drug.brand_name_fr

    Returns envelope with canonical INN, RxNorm CUI, and how it was matched.

    Examples:
        resolve_drug_name("Tahor")     -> atorvastatin  (brand match)
        resolve_drug_name("warfarin")  -> warfarin       (inn match)
        resolve_drug_name("Coumadin")  -> warfarin       (brand match)
        resolve_drug_name("zyboxithol")-> not_found
    """
    if not name or not name.strip():
        return err("Empty drug name provided")

    name_clean = name.strip()
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
            return not_found(f"'{name}' not found in knowledge base")

        rec = result.records[0]
        return ok(
            {
                "canonical":   rec["canonical"],
                "rxnorm_cui":  rec["rxnorm"],
                "match_type":  rec["match_type"],
                "input":       name,
            },
            f"Resolved '{name}' -> '{rec['canonical']}' (via {rec['match_type']})",
        )

    except Exception as exc:
        return err(str(exc))
    finally:
        driver.close()
