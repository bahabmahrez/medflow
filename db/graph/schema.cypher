// MedFlow — Neo4j Graph Schema
// Run via: python db/graph/init_graph.py
// Or paste into Neo4j Browser at http://localhost:7474
//
// Node labels:    Molecule · Drug · CYPEnzyme · DrugClass · DiseaseConcept
//                 AllergyGroup · MolecularTarget · Patient · LabResult
//
// Relationship types:
//   Knowledge layer:  BRAND_OF · INTERACTS_WITH · SUBSTRATE_OF · INHIBITS · INDUCES
//                     MEMBER_OF · CLASS_INTERACTS_WITH · CONTRAINDICATED_FOR
//                     INDICATED_FOR · BELONGS_TO_ALLERGY_GROUP · CROSS_REACTS_WITH
//                     TARGETS · HAS_ADVERSE_EFFECT
//   Patient layer:    TAKES · HAS_CONDITION · ALLERGIC_TO · HAS_LAB

// ─── UNIQUENESS CONSTRAINTS ──────────────────────────────────────────────────
// Each constraint also implicitly creates a lookup index on that property.

CREATE CONSTRAINT molecule_inn       IF NOT EXISTS FOR (n:Molecule)        REQUIRE n.inn IS UNIQUE;
CREATE CONSTRAINT drug_drug_id       IF NOT EXISTS FOR (n:Drug)            REQUIRE n.drug_id IS UNIQUE;
CREATE CONSTRAINT cyp_name           IF NOT EXISTS FOR (n:CYPEnzyme)       REQUIRE n.name IS UNIQUE;
CREATE CONSTRAINT drugclass_atc      IF NOT EXISTS FOR (n:DrugClass)       REQUIRE n.atc_code IS UNIQUE;
CREATE CONSTRAINT disease_icd11      IF NOT EXISTS FOR (n:DiseaseConcept)  REQUIRE n.icd11_code IS UNIQUE;
CREATE CONSTRAINT allergygroup_name  IF NOT EXISTS FOR (n:AllergyGroup)    REQUIRE n.name IS UNIQUE;
CREATE CONSTRAINT target_name        IF NOT EXISTS FOR (n:MolecularTarget) REQUIRE n.target_name IS UNIQUE;
CREATE CONSTRAINT patient_id         IF NOT EXISTS FOR (n:Patient)         REQUIRE n.patient_id IS UNIQUE;

// ─── LOOKUP INDEXES ───────────────────────────────────────────────────────────
// Secondary lookups that don't require uniqueness.

CREATE INDEX molecule_rxnorm   IF NOT EXISTS FOR (n:Molecule)       ON (n.rxnorm_cui);
CREATE INDEX molecule_drugbank IF NOT EXISTS FOR (n:Molecule)       ON (n.drugbank_id);
CREATE INDEX molecule_chembl   IF NOT EXISTS FOR (n:Molecule)       ON (n.chembl_id);
CREATE INDEX drug_brand_tn     IF NOT EXISTS FOR (n:Drug)           ON (n.brand_name_tn);
CREATE INDEX drug_brand        IF NOT EXISTS FOR (n:Drug)           ON (n.brand_name);
CREATE INDEX drug_atc          IF NOT EXISTS FOR (n:Drug)           ON (n.atc_code);
CREATE INDEX disease_snomed    IF NOT EXISTS FOR (n:DiseaseConcept) ON (n.snomed_code);
CREATE INDEX disease_name      IF NOT EXISTS FOR (n:DiseaseConcept) ON (n.condition_name);
CREATE INDEX patient_name      IF NOT EXISTS FOR (n:Patient)        ON (n.name);
CREATE INDEX patient_trap      IF NOT EXISTS FOR (n:Patient)        ON (n.is_trap);
CREATE INDEX patient_scenario  IF NOT EXISTS FOR (n:Patient)        ON (n.trap_scenario);

// ─── RELATIONSHIP PROPERTY INDEXES ───────────────────────────────────────────
// Allow fast filtering on severity when traversing interaction edges.

CREATE INDEX interacts_severity   IF NOT EXISTS FOR ()-[r:INTERACTS_WITH]-()       ON (r.severity_active);
CREATE INDEX contraind_severity   IF NOT EXISTS FOR ()-[r:CONTRAINDICATED_FOR]-()  ON (r.severity);
CREATE INDEX cyp_strength_sub     IF NOT EXISTS FOR ()-[r:SUBSTRATE_OF]-()         ON (r.strength);
CREATE INDEX cyp_strength_inh     IF NOT EXISTS FOR ()-[r:INHIBITS]-()             ON (r.strength);
CREATE INDEX cyp_strength_ind     IF NOT EXISTS FOR ()-[r:INDUCES]-()              ON (r.strength);
CREATE INDEX class_int_severity   IF NOT EXISTS FOR ()-[r:CLASS_INTERACTS_WITH]-() ON (r.severity);
