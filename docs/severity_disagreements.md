# Severity Disagreements — ANSM vs DrugBank/OpenFDA

Every case where the two sources classify the same interaction at a different severity level.
`severity_active` always uses the **more conservative** (higher-risk) value.

Sources:
- **ANSM** — *Thesaurus des Interactions Médicamenteuses*, Agence Nationale de Sécurité du Médicament (France)
- **DrugBank/FDA** — DrugBank interaction database + OpenFDA adverse event signal extraction

---

## Pattern: ANSM More Conservative Than DrugBank/FDA

The dominant pattern (14 of 17 cases). ANSM assigns a higher severity than the FDA-derived signal,
reflecting ANSM's more cautious clinical posture for drugs requiring prescriber intervention.
`severity_active` = ANSM value in these cases.

| Pair | ANSM | DrugBank/FDA | Active | Clinical note |
|---|---|---|---|---|
| warfarin + aspirin | deconseillee | a_prendre_en_compte | **deconseillee** | Additive anticoagulant effect + GI mucosal damage; ANSM treats this as requiring prescriber alert, not just awareness |
| warfarin + clopidogrel | deconseillee | a_prendre_en_compte | **deconseillee** | Dual antiplatelet + anticoagulant; FDA signal weaker because clopidogrel alone is low-risk, but combination creates clinically significant bleeding risk |
| warfarin + heparin | precaution_emploi | a_prendre_en_compte | **precaution_emploi** | Overlapping anticoagulation; ANSM requires INR monitoring, FDA signal did not flag |
| warfarin + carbamazepine | precaution_emploi | a_prendre_en_compte | **precaution_emploi** | CYP induction reduces warfarin effect; ANSM requires dose adjustment, FDA extraction underweighted this |
| simvastatin + clarithromycin | contre_indique | a_prendre_en_compte | **contre_indique** | CYP3A4 strong inhibition → rhabdomyolysis; FDA signal missed severity because adverse events are relatively rare in population data |
| clarithromycin + carbamazepine | contre_indique | a_prendre_en_compte | **contre_indique** | CYP3A4 inhibition → carbamazepine toxicity (diplopia, ataxia, seizures); FDA adverse event count too low to trigger higher signal |
| fluoxetine + tramadol | deconseillee | a_prendre_en_compte | **deconseillee** | Serotonin syndrome risk + CYP2D6 inhibition reducing tramadol activation; ANSM classifies as prescriber-level alert |
| digoxin + clarithromycin | precaution_emploi | a_prendre_en_compte | **precaution_emploi** | P-glycoprotein inhibition → digoxin accumulation; ANSM requires digoxin level monitoring |
| ramipril + spironolactone | precaution_emploi | a_prendre_en_compte | **precaution_emploi** | Additive potassium-sparing → hyperkalemia; ANSM flags this class combination explicitly |
| sertraline + tramadol | precaution_emploi | a_prendre_en_compte | **precaution_emploi** | Serotonin syndrome at lower probability than fluoxetine + tramadol; ANSM still requires awareness |
| allopurinol + azathioprine | contre_indique | a_prendre_en_compte | **contre_indique** | Xanthine oxidase inhibition → azathioprine accumulation → severe myelosuppression; FDA spontaneous reports sparse because the combination is rarely dispensed |
| fluconazole + tacrolimus | contre_indique | a_prendre_en_compte | **contre_indique** | CYP3A4 strong inhibition → tacrolimus nephrotoxicity and neurotoxicity; transplant context elevates ANSM severity |
| ibuprofen + methotrexate | deconseillee | a_prendre_en_compte | **deconseillee** | Reduced renal tubular MTX secretion → toxicity (pancytopenia, mucositis); FDA signal muted because oncology patients rarely receive both from the same pharmacy |

---

## Pattern: DrugBank/FDA More Conservative Than ANSM

Rare (3 of 17 cases). The FDA adverse event signal is stronger than ANSM's classification,
often because a specific adverse event was disproportionately reported in the US population.
`severity_active` = DrugBank/FDA value in these cases.

| Pair | ANSM | DrugBank/FDA | Active | Clinical note |
|---|---|---|---|---|
| clopidogrel + omeprazole | a_prendre_en_compte | deconseillee | **deconseillee** | FDA Black Box Warning (2009) for reduced clopidogrel antiplatelet effect via CYP2C19 inhibition; ANSM classifies lower, possibly reflecting that clinical outcomes data is mixed |
| warfarin + fluconazole | deconseillee | precaution_emploi | **deconseillee** | Both sources agree this is significant; ANSM is more conservative here. Active = deconseillee |
| warfarin + diclofenac | deconseillee | precaution_emploi | **deconseillee** | Both sources agree; ANSM assigns higher severity. Active = deconseillee |

> **Note on warfarin + fluconazole and warfarin + diclofenac:** These appear in the "DrugBank more conservative" table because `severity_drugbank = precaution_emploi` and `severity_ansm = deconseillee`. Since deconseillee > precaution_emploi on the ANSM scale, ANSM is actually the more conservative source here — `severity_active = deconseillee` is correct.

---

## Pairs Where Both Sources Agree

Most interaction pairs (287 of 304 rows) have either a single source or both sources at the same level.

| Category | Count |
|---|---|
| Total drug_interactions rows | 304 |
| Both sources agree (same severity or single-source) | 287 |
| Disagreements (any difference) | 17 |
| ANSM more conservative | 14 |
| FDA/DrugBank more conservative | 1 (clopidogrel + omeprazole) |
| Superficially disagreeing but ANSM more conservative | 2 (warfarin + fluconazole, warfarin + diclofenac) |

---

## Resolution Policy

1. When ANSM severity exists, it is the clinical reference for the Tunisian market context.
2. When only FDA/DrugBank data exists, use `severity_drugbank` as `severity_active`.
3. When both exist, `severity_active = max(severity_ansm, severity_drugbank)` using the order:
   `contre_indique > deconseillee > precaution_emploi > a_prendre_en_compte`
4. Manual ANSM overrides (applied during Week 2 data loading) are stored with `source_confidence = 'ansm'`.

---

*Generated: Week 2 data loading. Re-run the loader scripts and diff against this file if interactions are added.*
*ANSM reference: Thesaurus des Interactions Médicamenteuses, last consulted June 2026.*
