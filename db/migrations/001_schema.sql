
CREATE TABLE disease_concepts (
    id                  SERIAL PRIMARY KEY,
    icd11_code          VARCHAR(20),
    snomed_code         VARCHAR(50),
    condition_name      VARCHAR(255) NOT NULL,
    description         TEXT,
    UNIQUE(icd11_code),
    UNIQUE(snomed_code)
);

CREATE INDEX idx_disease_concepts_icd11  ON disease_concepts(icd11_code);
CREATE INDEX idx_disease_concepts_snomed ON disease_concepts(snomed_code);

-- MOLECULES — The canonical drug entity (all interaction logic lives here)


CREATE TABLE molecules (
    id                  SERIAL PRIMARY KEY,
    inn                 VARCHAR(255) UNIQUE NOT NULL,   -- International Nonproprietary Name
    rxnorm_cui          VARCHAR(20),
    drugbank_id         VARCHAR(20),
    chembl_id           VARCHAR(50),
    molecular_class     VARCHAR(100),
    half_life_hours     NUMERIC,
    elimination_route   VARCHAR(50)
);

CREATE INDEX idx_molecules_rxnorm    ON molecules(rxnorm_cui);
CREATE INDEX idx_molecules_drugbank  ON molecules(drugbank_id);
CREATE INDEX idx_molecules_chembl    ON molecules(chembl_id);


-- DRUGS — Brand/market instances of a molecule


CREATE TABLE drugs (
    id                      SERIAL PRIMARY KEY,
    molecule_id             INT REFERENCES molecules(id) NOT NULL,
    brand_name              VARCHAR(255),
    brand_name_tn           VARCHAR(255),  -- Tunisian brand name
    brand_name_fr           VARCHAR(255),  -- French brand name
    atc_code                VARCHAR(10),   -- Display/lookup only; class membership via drug_class_members
    therapeutic_category    VARCHAR(100),
    dosage_form             VARCHAR(50),
    dose_adult              VARCHAR(100),
    dose_elderly            VARCHAR(100),
    dose_renal_impairment   VARCHAR(100),
    dose_hepatic_impairment VARCHAR(100)
);

CREATE INDEX idx_drugs_molecule    ON drugs(molecule_id);
CREATE INDEX idx_drugs_brand_name  ON drugs(brand_name);
CREATE INDEX idx_drugs_brand_tn    ON drugs(brand_name_tn);
CREATE INDEX idx_drugs_atc         ON drugs(atc_code);



-- DRUG INTERACTIONS — Direct pairwise molecule interactions

CREATE TABLE drug_interactions (
    id                      SERIAL PRIMARY KEY,
    molecule_a_id           INT REFERENCES molecules(id) NOT NULL,
    molecule_b_id           INT REFERENCES molecules(id) NOT NULL,
    severity_drugbank       VARCHAR(20),   -- DrugBank severity label
    severity_ansm           VARCHAR(40),   -- ANSM severity label
    severity_active         VARCHAR(40),   -- Conservative of the two (computed by loader)
    mechanism_type          VARCHAR(50),   -- pharmacokinetic | pharmacodynamic | combined
    mechanism_description   TEXT,
    clinical_effect         TEXT,
    management              TEXT,
    dose_dependent          BOOLEAN DEFAULT FALSE,
    onset                   VARCHAR(20),   -- rapid | delayed | unknown
    documentation_level     VARCHAR(20),   -- established | probable | suspected | theoretical
    condition_modifiers     TEXT,          -- e.g. "risk increases with renal impairment"
    source_confidence       VARCHAR(20),
    UNIQUE(molecule_a_id, molecule_b_id),
    CHECK (molecule_a_id <> molecule_b_id)
);

CREATE INDEX idx_interactions_mol_a ON drug_interactions(molecule_a_id);
CREATE INDEX idx_interactions_mol_b ON drug_interactions(molecule_b_id);
CREATE INDEX idx_interactions_severity_active ON drug_interactions(severity_active);



-- CYP RELATIONSHIPS — Metabolic pathway edges (enables indirect interaction detection)

CREATE TABLE cyp_relationships (
    id              SERIAL PRIMARY KEY,
    molecule_id     INT REFERENCES molecules(id) NOT NULL,
    enzyme          VARCHAR(20) NOT NULL,   -- CYP3A4 | CYP2C9 | CYP2D6 | etc.
    relationship    VARCHAR(20) NOT NULL,   -- SUBSTRATE | INHIBITOR | INDUCER
    strength        VARCHAR(10),            -- strong | moderate | weak
    UNIQUE(molecule_id, enzyme, relationship)
);

CREATE INDEX idx_cyp_molecule ON cyp_relationships(molecule_id);
CREATE INDEX idx_cyp_enzyme   ON cyp_relationships(enzyme);


-- CONTRAINDICATIONS — Molecule-level contraindications against disease concepts


CREATE TABLE contraindications (
    id                  SERIAL PRIMARY KEY,
    molecule_id         INT REFERENCES molecules(id) NOT NULL,   -- molecule level (not drug) for consistency with interaction engine
    disease_concept_id  INT REFERENCES disease_concepts(id) NOT NULL,
    reason              TEXT NOT NULL,
    severity            VARCHAR(20),   -- contraindicated | dose_adjustment | monitoring
    source              VARCHAR(50),   -- drugbank | openfda | ansm
    UNIQUE(molecule_id, disease_concept_id)
);

CREATE INDEX idx_contraindications_molecule ON contraindications(molecule_id);
CREATE INDEX idx_contraindications_disease  ON contraindications(disease_concept_id);


-- DRUG CLASSES — ATC classification nodes (enables class-level reasoning)


-- ATC classification. All NSAIDs interact with anticoagulants even if a specific
-- NSAID is not individually encoded — class-level edges catch this.
CREATE TABLE drug_classes (
    id          SERIAL PRIMARY KEY,
    atc_code    VARCHAR(10) UNIQUE NOT NULL,
    class_name  VARCHAR(255) NOT NULL,
    description TEXT
);

-- Links molecules to their ATC drug class (many-to-many).
-- This is the single source of truth for class membership.
CREATE TABLE drug_class_members (
    molecule_id     INT REFERENCES molecules(id),
    drug_class_id   INT REFERENCES drug_classes(id),
    PRIMARY KEY (molecule_id, drug_class_id)
);

-- Interaction edges between drug classes.
-- Used when a specific molecule pair has no direct drug_interactions entry.
CREATE TABLE class_interactions (
    id              SERIAL PRIMARY KEY,
    class_a_id      INT REFERENCES drug_classes(id) NOT NULL,
    class_b_id      INT REFERENCES drug_classes(id) NOT NULL,
    severity        VARCHAR(40) NOT NULL,
    mechanism_type  VARCHAR(50),
    clinical_effect TEXT,
    management      TEXT,
    UNIQUE(class_a_id, class_b_id),
    CHECK (class_a_id <> class_b_id)
);

CREATE INDEX idx_class_interactions_a ON class_interactions(class_a_id);
CREATE INDEX idx_class_interactions_b ON class_interactions(class_b_id);



-- ADVERSE EFFECTS — Real-world side effect data from OpenFDA / pharmacovigilance


CREATE TABLE adverse_effects (
    id                  SERIAL PRIMARY KEY,
    molecule_id         INT REFERENCES molecules(id) NOT NULL,
    meddra_code         VARCHAR(20),       -- MedDRA preferred term code (required by spec)
    snomed_code         VARCHAR(50),
    adverse_effect_name VARCHAR(255) NOT NULL,
    severity            VARCHAR(40),       -- mild | moderate | severe | life-threatening
    frequency           VARCHAR(50),       -- very_common | common | uncommon | rare | very_rare
    source              VARCHAR(50)        -- openfda | drugbank | literature
);

CREATE INDEX idx_adverse_effects_molecule ON adverse_effects(molecule_id);
CREATE INDEX idx_adverse_effects_meddra   ON adverse_effects(meddra_code);



-- MOLECULAR TARGETS — Protein/receptor targets (pharmacodynamic reasoning)


-- Two drugs targeting the same receptor → additive or antagonistic effects
-- even without a direct interaction entry.
CREATE TABLE molecular_targets (
    id          SERIAL PRIMARY KEY,
    target_name VARCHAR(255) UNIQUE NOT NULL,
    uniprot_id  VARCHAR(50)
);

CREATE TABLE molecule_molecular_targets (
    molecule_id         INT REFERENCES molecules(id),
    molecular_target_id INT REFERENCES molecular_targets(id),
    action_type         VARCHAR(50) NOT NULL,  -- agonist | antagonist | inhibitor | activator
    PRIMARY KEY (molecule_id, molecular_target_id)
);

CREATE INDEX idx_mol_targets_molecule ON molecule_molecular_targets(molecule_id);
CREATE INDEX idx_mol_targets_target   ON molecule_molecular_targets(molecular_target_id);


-- TREATS — What each molecule is indicated for (LLM needs this for reasoning)


CREATE TABLE treats (
    id                  SERIAL PRIMARY KEY,
    molecule_id         INT REFERENCES molecules(id) NOT NULL,
    disease_concept_id  INT REFERENCES disease_concepts(id) NOT NULL,
    indication_name     VARCHAR(255),       -- human-readable label
    evidence_level      VARCHAR(20),        -- approved | off-label | investigational
    source              VARCHAR(50),
    UNIQUE(molecule_id, disease_concept_id)
);

CREATE INDEX idx_treats_molecule ON treats(molecule_id);
CREATE INDEX idx_treats_disease  ON treats(disease_concept_id);


-- ALLERGY GROUPS — Cross-reactivity network


CREATE TABLE allergy_groups (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(100) UNIQUE NOT NULL,
    description TEXT
);

-- Cross-reactivity between allergy groups (e.g. penicillin ↔ cephalosporin)
CREATE TABLE allergy_cross_reactivities (
    group_a_id  INT REFERENCES allergy_groups(id),
    group_b_id  INT REFERENCES allergy_groups(id),
    PRIMARY KEY (group_a_id, group_b_id),
    CHECK (group_a_id <> group_b_id)
);

-- Links a drug (brand instance) to its allergy group
CREATE TABLE drug_allergy_groups (
    drug_id         INT REFERENCES drugs(id),
    allergy_group_id INT REFERENCES allergy_groups(id),
    PRIMARY KEY (drug_id, allergy_group_id)
);


-- PATIENTS — Clinical patient records


CREATE TABLE patients (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(255),
    dob             DATE,
    sex             CHAR(1),
    weight_kg       NUMERIC,
    is_trap         BOOLEAN DEFAULT FALSE,
    trap_scenario   VARCHAR(100)   -- e.g. 'trap_1_warfarin_aspirin'
);

-- Patient-specific condition instances (not to be confused with disease_concepts)
CREATE TABLE conditions (
    id              SERIAL PRIMARY KEY,
    patient_id      INT REFERENCES patients(id) NOT NULL,
    disease_concept_id INT REFERENCES disease_concepts(id),  -- links to canonical concept
    icd11_code      VARCHAR(20),   -- denormalized for fast lookup
    snomed_code     VARCHAR(50),   -- denormalized for fast lookup
    condition_name  VARCHAR(255),
    onset_date      DATE
);

CREATE INDEX idx_conditions_patient ON conditions(patient_id);
CREATE INDEX idx_conditions_concept ON conditions(disease_concept_id);



-- ACTIVE MEDICATIONS — What a patient is currently taking


CREATE TABLE active_medications (
    id              SERIAL PRIMARY KEY,
    patient_id      INT REFERENCES patients(id) NOT NULL,
    drug_id         INT REFERENCES drugs(id) NOT NULL,
    rxnorm_cui      VARCHAR(20),
    dose_mg         NUMERIC,
    frequency       VARCHAR(50),
    start_date      DATE,
    prescriber_id   INT
);

CREATE INDEX idx_active_meds_patient ON active_medications(patient_id);
CREATE INDEX idx_active_meds_drug    ON active_medications(drug_id);
CREATE INDEX idx_active_meds_rxnorm  ON active_medications(rxnorm_cui);



-- ALLERGIES — Patient allergy records


CREATE TABLE allergies (
    id              SERIAL PRIMARY KEY,
    patient_id      INT REFERENCES patients(id) NOT NULL,
    allergy_group_id INT REFERENCES allergy_groups(id) NOT NULL,
    reaction_type   VARCHAR(50),   -- anaphylaxis | rash | urticaria | unknown
    documented_at   DATE
);

CREATE INDEX idx_allergies_patient ON allergies(patient_id);


-- LAB RESULTS — For contraindication checks (e.g. eGFR for metformin)


CREATE TABLE lab_results (
    id              SERIAL PRIMARY KEY,
    patient_id      INT REFERENCES patients(id) NOT NULL,
    loinc_code      VARCHAR(20),
    test_name       VARCHAR(100),
    value           NUMERIC,
    unit            VARCHAR(20),
    collected_at    TIMESTAMP
);

CREATE INDEX idx_lab_patient ON lab_results(patient_id);



-- PRESCRIPTION HISTORY & REFILLS

CREATE TABLE prescription_history (
    id              SERIAL PRIMARY KEY,
    patient_id      INT REFERENCES patients(id) NOT NULL,
    drug_id         INT REFERENCES drugs(id) NOT NULL,
    prescribed_at   DATE,
    prescriber_id   INT,
    dose_mg         NUMERIC,
    frequency       VARCHAR(50)
);

CREATE TABLE refill_records (
    id                  SERIAL PRIMARY KEY,
    patient_id          INT REFERENCES patients(id) NOT NULL,
    drug_id             INT REFERENCES drugs(id) NOT NULL,
    expected_refill_date DATE,
    actual_refill_date   DATE
);

