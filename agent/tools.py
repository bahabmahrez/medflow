"""
Tool definitions for the MedFlow agent — wraps the 10 query-layer functions
as LLM-callable tools.

Each schema's "parameters" is a JSON Schema object (OpenAI/Groq's native tool
format; llm.provider translates it for Anthropic). Argument names match the
underlying Python function's kwargs exactly, so dispatch is func(**arguments)
with no remapping table.
"""
from query import (
    resolve_drug_name,
    get_drug_profile,
    detect_pairwise_interactions,
    detect_cyp_competition,
    check_contraindications,
    check_allergy_conflict,
    check_therapeutic_duplication,
    check_dose_appropriateness,
    get_drugs_by_class,
    full_prescription_check,
)

TOOLS: list[dict] = [
    {
        "name": "resolve_drug_name",
        "description": (
            "Resolve a drug name (INN, brand, Tunisian brand, or French brand) to its "
            "canonical INN molecule. Use FIRST whenever a name is unfamiliar, a brand, "
            "or you need to confirm it exists before reasoning about it — or when you "
            "need a normalized name to ask a good clarifying question. Other tools "
            "resolve internally, so you don't need to call this before every one of them."
        ),
        "parameters": {
            "type": "object",
            "properties": {"name": {"type": "string", "description": "Drug name as given by the pharmacist"}},
            "required": ["name"],
        },
    },
    {
        "name": "get_drug_profile",
        "description": (
            "Retrieve everything the graph knows about one drug: brands, drug class, "
            "CYP relationships, interactions, contraindications, allergy group. Use for "
            "general 'tell me about X' / 'what does X interact with' questions, or as an "
            "orientation step before deciding which specific safety checks are relevant."
        ),
        "parameters": {
            "type": "object",
            "properties": {"drug": {"type": "string", "description": "Drug name"}},
            "required": ["drug"],
        },
    },
    {
        "name": "detect_pairwise_interactions",
        "description": (
            "Check for direct, documented interactions between 2 or more named drugs. "
            "Use whenever the pharmacist names two or more specific drugs together. "
            "Only include drugs the pharmacist actually named."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "drug_list": {
                    "type": "array", "items": {"type": "string"},
                    "description": "Two or more drug names to check pairwise",
                },
            },
            "required": ["drug_list"],
        },
    },
    {
        "name": "detect_cyp_competition",
        "description": (
            "Check for enzyme-mediated (CYP450) interactions between 2 or more named "
            "drugs that have no direct interaction edge. Always run alongside "
            "detect_pairwise_interactions for any 2+-drug evaluation — some dangerous "
            "pairs (e.g. simvastatin+clarithromycin) only show up here."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "drug_list": {
                    "type": "array", "items": {"type": "string"},
                    "description": "Two or more drug names to check for CYP competition",
                },
            },
            "required": ["drug_list"],
        },
    },
    {
        "name": "check_contraindications",
        "description": (
            "Check whether a drug is contraindicated for one or more of the patient's "
            "conditions. Use whenever a condition/diagnosis and a candidate drug are "
            "both present in the question or patient context."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "drug": {"type": "string", "description": "Drug name"},
                "conditions": {
                    "type": "array", "items": {"type": "string"},
                    "description": "Patient conditions, free text or ICD-11 codes",
                },
            },
            "required": ["drug", "conditions"],
        },
    },
    {
        "name": "check_allergy_conflict",
        "description": (
            "Check whether a drug conflicts with the patient's allergies, including "
            "cross-reactivity (e.g. penicillin vs. cephalosporins). Use whenever an "
            "allergy and a candidate drug are both present."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "drug": {"type": "string", "description": "Drug name"},
                "allergies": {
                    "type": "array", "items": {"type": "string"},
                    "description": "Patient's stated allergies",
                },
            },
            "required": ["drug", "allergies"],
        },
    },
    {
        "name": "check_therapeutic_duplication",
        "description": (
            "Check whether a new drug is already being taken under a different "
            "brand/generic name. Use whenever the patient's current medication list "
            "and a new drug are both present."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "new_drug": {"type": "string", "description": "The new drug being considered"},
                "active_meds": {
                    "type": "array", "items": {"type": "string"},
                    "description": "Patient's current active medications, any name form",
                },
            },
            "required": ["new_drug", "active_meds"],
        },
    },
    {
        "name": "check_dose_appropriateness",
        "description": (
            "Check whether a prescribed dose needs adjustment for age, renal, or "
            "hepatic function. Use only when a specific dose, age, or lab value "
            "(creatinine, eGFR, ALT, AST) is present alongside a drug — the graph "
            "stores adjustment guidance, not first-line dosing tables, so don't call "
            "this for a bare 'what dose is X' with no patient parameters."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "drug": {"type": "string", "description": "Drug name"},
                "dose": {"type": "string", "description": "Prescribed dose as stated, e.g. '500mg'"},
                "age": {"type": "integer", "description": "Patient age in years"},
                "weight": {"type": "number", "description": "Patient weight in kg"},
                "labs": {
                    "type": "object",
                    "description": "Lab values: creatinine_umol_L, egfr, alt_iu_L, ast_iu_L",
                    "properties": {
                        "creatinine_umol_L": {"type": "number"},
                        "egfr": {"type": "number"},
                        "alt_iu_L": {"type": "number"},
                        "ast_iu_L": {"type": "number"},
                    },
                },
            },
            "required": ["drug"],
        },
    },
    {
        "name": "get_drugs_by_class",
        "description": (
            "List all drugs in a given drug class or ATC prefix. Use for 'what are "
            "the alternatives to X' questions, or to disambiguate a vague class "
            "reference (e.g. 'her statin') by presenting the pharmacist with the "
            "actual options — not to silently pick one."
        ),
        "parameters": {
            "type": "object",
            "properties": {"drug_class": {"type": "string", "description": "Class name or ATC code/prefix"}},
            "required": ["drug_class"],
        },
    },
    {
        "name": "full_prescription_check",
        "description": (
            "Run a full consolidated safety check (interactions, CYP competition, "
            "contraindications, allergy conflicts, duplications, dose flags) for one "
            "or more new drugs against the patient's active meds/conditions/allergies/"
            "labs in one call. Prefer this for open-ended 'review this new "
            "prescription' questions; prefer the individual tools when the question "
            "narrowly targets one check type."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "prescription": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "drug": {"type": "string"},
                            "dose": {"type": "string"},
                        },
                        "required": ["drug"],
                    },
                    "description": "New drugs being prescribed, each with optional dose",
                },
                "patient_meds": {"type": "array", "items": {"type": "string"}},
                "conditions": {"type": "array", "items": {"type": "string"}},
                "allergies": {"type": "array", "items": {"type": "string"}},
                "labs": {
                    "type": "object",
                    "properties": {
                        "creatinine_umol_L": {"type": "number"},
                        "egfr": {"type": "number"},
                        "alt_iu_L": {"type": "number"},
                        "ast_iu_L": {"type": "number"},
                    },
                },
            },
            "required": [],
        },
    },
]

TOOL_REGISTRY: dict[str, callable] = {
    "resolve_drug_name": resolve_drug_name,
    "get_drug_profile": get_drug_profile,
    "detect_pairwise_interactions": detect_pairwise_interactions,
    "detect_cyp_competition": detect_cyp_competition,
    "check_contraindications": check_contraindications,
    "check_allergy_conflict": check_allergy_conflict,
    "check_therapeutic_duplication": check_therapeutic_duplication,
    "check_dose_appropriateness": check_dose_appropriateness,
    "get_drugs_by_class": get_drugs_by_class,
    "full_prescription_check": full_prescription_check,
}

_REQUIRED_ARGS: dict[str, list[str]] = {
    t["name"]: t["parameters"].get("required", []) for t in TOOLS
}


def call_tool(name: str, arguments: dict) -> dict:
    """
    Safely dispatch a tool call. Never raises — every failure mode (unknown
    tool, missing argument, malformed arguments, an exception from the
    underlying query function) becomes a normal {"status":"error", ...}
    envelope so the agent loop can log it and the model can react to it.
    """
    if name not in TOOL_REGISTRY:
        return {"status": "error", "data": {}, "message": f"Unknown tool '{name}' — not in registry"}

    if arguments.get("parse_error") or "_raw" in arguments:
        return {
            "status": "error", "data": {},
            "message": f"Tool call arguments for '{name}' were not valid JSON: {arguments.get('_raw')!r}",
        }

    missing = [a for a in _REQUIRED_ARGS.get(name, []) if a not in arguments or arguments[a] is None]
    if missing:
        return {
            "status": "error", "data": {},
            "message": f"Missing required argument(s) {missing} for tool '{name}'",
        }

    try:
        return TOOL_REGISTRY[name](**arguments)
    except Exception as exc:
        return {"status": "error", "data": {}, "message": str(exc)}
