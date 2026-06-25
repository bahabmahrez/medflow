import csv
import time
import requests


#allergy-to-drug contraindications
BASE = "https://rxnav.nlm.nih.gov/REST/rxclass"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; DrugPipeline/1.0)",
    "Accept": "application/json",
}


def fetch_all_epc_classes() -> list[dict]:
    print("Step 1: Fetching all EPC class definitions...")
    r = requests.get(
        f"{BASE}/allClasses.json",
        params={"classTypes": "EPC"},
        headers=HEADERS,
        timeout=30,
    )
    r.raise_for_status()

    data = r.json()
    concept_list = data.get("rxclassMinConceptList", {})
    classes = concept_list.get("rxclassMinConcept", [])

    # Normalize: API returns dict when only 1 result, list otherwise
    if isinstance(classes, dict):
        classes = [classes]

    # Keep only EPC type (safety filter)
    epc_classes = [c for c in classes if c.get("classType") == "EPC"]
    print(f"  → Found {len(epc_classes)} EPC classes\n")
    return epc_classes


def fetch_class_members(class_id: str) -> list[dict]:
    for rela_source in ("FDASPL", "DAILYMED"):
        r = requests.get(
            f"{BASE}/classMembers.json",
            params={
                "classId":    class_id,
                "relaSource": rela_source,
                "rela":       "has_EPC",
            },
            headers=HEADERS,
            timeout=15,
        )

        if r.status_code != 200:
            continue

        data = r.json()
        group = data.get("drugMemberGroup", {})

        # Empty list means no members for this source — try next
        if not group or group == []:
            continue

        members = group.get("drugMember", [])
        if not members:
            continue

        # API returns a dict (not list) when there's only 1 member
        if isinstance(members, dict):
            members = [members]

        return [
            {
                "name":  m.get("minConcept", {}).get("name"),
                "rxcui": m.get("minConcept", {}).get("rxcui"),
                "tty":   m.get("minConcept", {}).get("tty", ""),
            }
            for m in members
            if m.get("minConcept", {}).get("name") and m.get("minConcept", {}).get("rxcui")
        ]

    return []  # no members found in either source


def extract_all_epc_drugs(output_filename="all_epc_allergy_groups.csv"):

    # ── Step 1: get all class definitions 
    epc_classes = fetch_all_epc_classes()

    # ── Step 2: loop through each class 
    csv_headers = ["EPC_Class_ID", "EPC_Class_Name", "Drug_Name", "RxCUI", "Drug_Type"]
    total_drugs = 0
    classes_with_drugs = 0
    classes_empty = 0

    print(f"Step 2: Fetching drug members for each EPC class...")
    print(f"  (This will make ~{len(epc_classes)} API calls — estimated "
          f"{len(epc_classes) * 0.35 / 60:.1f} minutes)\n")

    with open(output_filename, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(csv_headers)

        for i, epc_class in enumerate(epc_classes, 1):
            class_id   = epc_class["classId"]
            class_name = epc_class["className"]

            members = fetch_class_members(class_id)

            if members:
                for drug in members:
                    writer.writerow([
                        class_id, class_name,
                        drug["name"], drug["rxcui"], drug["tty"]
                    ])
                total_drugs += len(members)
                classes_with_drugs += 1
                status = f" {len(members):4d} drugs"
            else:
                classes_empty += 1
                status = "  —  no members"

            # Progress every 10 classes
            if i % 10 == 0 or i == len(epc_classes):
                print(f"  [{i:4d}/{len(epc_classes)}] {status}  ← {class_name}")

            time.sleep(0.3)  # polite rate limiting — ~3 req/sec

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f" Done!")
    print(f"   EPC classes processed : {len(epc_classes)}")
    print(f"   Classes with drugs    : {classes_with_drugs}")
    print(f"   Classes with no drugs : {classes_empty}")
    print(f"   Total drug records    : {total_drugs}")
    print(f"   Output file           : {output_filename}")


if __name__ == "__main__":
    extract_all_epc_drugs()