"""
Functions 2 & 9 — get_drug_profile(drug) and get_drugs_by_class(drug_class)
"""
from ._neo4j import connect, ok, not_found, err
from .resolve import resolve_drug_name


def get_drug_profile(drug: str) -> dict:
    """
    Return everything the graph knows about one drug.

    Traverses: molecule -> brand names, drug class, CYP relationships,
    INTERACTS_WITH edges, CONTRAINDICATED_FOR edges, allergy group,
    indicated conditions, adverse effects.

    Example:
        get_drug_profile("Coumadin") -> warfarin profile with all CYP, DDIs,
        contraindications, and brand names.
    """
    resolved = resolve_drug_name(drug)
    if resolved["status"] != "found":
        return resolved

    inn = resolved["data"]["canonical"]
    driver = connect()
    try:
        # ── Core molecule + brand names ────────────────────────────────────────
        mol_q = driver.execute_query(
            """
            MATCH (m:Molecule {inn: $inn})
            OPTIONAL MATCH (d:Drug)-[:BRAND_OF]->(m)
            RETURN m.inn            AS inn,
                   m.rxnorm_cui     AS rxnorm_cui,
                   m.chembl_id      AS chembl_id,
                   collect(DISTINCT {
                       brand:    d.brand_name,
                       brand_tn: d.brand_name_tn,
                       atc:      d.atc_code,
                       category: d.therapeutic_category,
                       form:     d.dosage_form,
                       dose_adult:    d.dose_adult,
                       dose_elderly:  d.dose_elderly,
                       dose_renal:    d.dose_renal_impairment,
                       dose_hepatic:  d.dose_hepatic_impairment
                   }) AS brands
            """,
            inn=inn,
        )
        if not mol_q.records:
            return not_found(f"Molecule '{inn}' not found in graph")

        mol_rec = mol_q.records[0]

        # ── Drug interactions ──────────────────────────────────────────────────
        ddi_q = driver.execute_query(
            """
            MATCH (m:Molecule {inn: $inn})-[r:INTERACTS_WITH]-(other:Molecule)
            RETURN other.inn           AS partner,
                   r.severity_active  AS severity,
                   r.clinical_effect  AS effect,
                   r.mechanism        AS mechanism,
                   r.source           AS source
            ORDER BY
              CASE r.severity_active
                WHEN 'contre_indique'      THEN 1
                WHEN 'major'               THEN 2
                WHEN 'deconseillee'        THEN 3
                WHEN 'moderate'            THEN 4
                WHEN 'precaution_emploi'   THEN 5
                WHEN 'a_prendre_en_compte' THEN 6
                ELSE 7
              END
            """,
            inn=inn,
        )

        # ── CYP relationships ──────────────────────────────────────────────────
        cyp_q = driver.execute_query(
            """
            MATCH (m:Molecule {inn: $inn})-[r:SUBSTRATE_OF|INHIBITS|INDUCES]->(cyp:CYPEnzyme)
            RETURN type(r) AS role, cyp.name AS enzyme, r.strength AS strength
            ORDER BY cyp.name
            """,
            inn=inn,
        )

        # ── Contraindications ─────────────────────────────────────────────────
        ci_q = driver.execute_query(
            """
            MATCH (m:Molecule {inn: $inn})-[r:CONTRAINDICATED_FOR]->(dc:DiseaseConcept)
            RETURN dc.condition_name AS condition,
                   dc.icd11_code     AS icd_code,
                   r.severity        AS severity,
                   r.reason          AS reason
            """,
            inn=inn,
        )

        # ── Drug class ────────────────────────────────────────────────────────
        class_q = driver.execute_query(
            """
            MATCH (m:Molecule {inn: $inn})-[:MEMBER_OF]->(c:DrugClass)
            RETURN c.class_name AS class_name, c.atc_code AS atc_code
            """,
            inn=inn,
        )

        # ── Allergy group ─────────────────────────────────────────────────────
        allergy_q = driver.execute_query(
            """
            MATCH (d:Drug)-[:BRAND_OF]->(m:Molecule {inn: $inn})
            MATCH (d)-[:BELONGS_TO_ALLERGY_GROUP]->(ag:AllergyGroup)
            OPTIONAL MATCH (ag)-[:CROSS_REACTS_WITH]->(cross:AllergyGroup)
            RETURN ag.name AS allergy_group,
                   collect(DISTINCT cross.name) AS cross_reactive
            LIMIT 1
            """,
            inn=inn,
        )

        profile = {
            "inn":        mol_rec["inn"],
            "rxnorm_cui": mol_rec["rxnorm_cui"],
            "chembl_id":  mol_rec["chembl_id"],
            "brands":     [b for b in mol_rec["brands"] if b.get("brand")],
            "drug_classes": [
                {"class_name": r["class_name"], "atc_code": r["atc_code"]}
                for r in class_q.records
            ],
            "interactions": [
                {
                    "partner":   r["partner"],
                    "severity":  r["severity"],
                    "effect":    r["effect"],
                    "mechanism": r["mechanism"],
                    "source":    r["source"],
                }
                for r in ddi_q.records
            ],
            "cyp_relationships": [
                {"role": r["role"], "enzyme": r["enzyme"], "strength": r["strength"]}
                for r in cyp_q.records
            ],
            "contraindications": [
                {
                    "condition": r["condition"],
                    "icd_code":  r["icd_code"],
                    "severity":  r["severity"],
                    "reason":    r["reason"],
                }
                for r in ci_q.records
            ],
            "allergy_group":    allergy_q.records[0]["allergy_group"]  if allergy_q.records else None,
            "cross_reactive_to": allergy_q.records[0]["cross_reactive"] if allergy_q.records else [],
        }

        return ok(profile, f"Profile for '{inn}'")

    except Exception as exc:
        return err(str(exc))
    finally:
        driver.close()


def get_drugs_by_class(drug_class: str) -> dict:
    """
    Return all molecules that are MEMBER_OF a DrugClass matching the given name
    or ATC prefix.

    Example:
        get_drugs_by_class("Statin")  -> atorvastatin, simvastatin, ...
        get_drugs_by_class("C10AA")   -> same, by ATC prefix
    """
    if not drug_class or not drug_class.strip():
        return err("Empty drug class provided")

    driver = connect()
    try:
        result = driver.execute_query(
            """
            MATCH (m:Molecule)-[:MEMBER_OF]->(c:DrugClass)
            WHERE toLower(c.class_name) CONTAINS toLower($name)
               OR c.atc_code STARTS WITH toUpper($name)
            RETURN m.inn AS drug, c.class_name AS class_name,
                   c.atc_code AS atc_code
            ORDER BY m.inn
            """,
            name=drug_class.strip(),
        )

        if not result.records:
            return not_found(f"No drugs found for class '{drug_class}'")

        drugs = [
            {"drug": r["drug"], "class_name": r["class_name"], "atc_code": r["atc_code"]}
            for r in result.records
        ]
        return ok(
            {"class_query": drug_class, "count": len(drugs), "drugs": drugs},
            f"{len(drugs)} drug(s) found in class '{drug_class}'",
        )

    except Exception as exc:
        return err(str(exc))
    finally:
        driver.close()
