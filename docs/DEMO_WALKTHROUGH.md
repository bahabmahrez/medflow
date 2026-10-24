# MedFlow — Silent Demo Recording Script & Walkthrough Guide

> **Context:** This guide is designed for a video demonstration recorded without a microphone. It provides an exact, step-by-step click-and-type sequence, visual cues to pause on, and full explanatory text that can be used for on-screen captions, video description, or an accompanying project report.

---

## Demo Overview & Architecture Highlights

| Visual Feature | Technical Capability | Clinical Value |
| :--- | :--- | :--- |
| **Calm Green Banner** | High Specificity (100%) | Eliminates alert fatigue; silence looks like a considered answer, not a system failure. |
| **Color-Coded Alert Cards** | Canonical Severity Grading | Directs pharmacist eyes immediately to `CONTRAINDICATED` (Red) or `MAJOR` (Orange) actions. |
| **Reasoning Chains** | Deterministic Graph Provenance | 1-click evidence trail showing exact ANSM / CYP rules without LLM hallucinations. |
| **`IS_A` Hierarchy Traversal** | Neo4j Multi-Hop Expansion | Maps granular patient conditions (e.g., CKD Stage 4) to broader contraindications (Renal impairment). |
| **Memory Recall Badges** | Relational PostgreSQL Memory | Softens reviewed alerts into `ALREADY REVIEWED` reminders while keeping Contraindicated alerts prominent (`NEVER_DEMOTED`). |
| **Prescriber Letter Draft** | Deterministic Template Synthesis | 1-click pre-composed query letter containing patient details, drug pair, mechanism, and monitoring notes. |
| **Latency Benchmark** | Latency Separation SLA | Graph queries return in **~25 ms**, proving hardware/LLM synthesis isolation. |

---

## Step-by-Step Recording Sequence (Total Time: ~3 to 4 Minutes)

```
[Screen 1: Web Browser at http://localhost:8501]
  Step 1: Specificity & Clean Scan
  Step 2: Direct DDI Trap & Reasoning Chain
  Step 3: CYP450 2-Hop Metabolic Trap
  Step 4: Disease Concept Hierarchy (IS_A)
  Step 5: Pharmacist Memory & Prescriber Letter Generation
[Screen 2: Terminal / PowerShell]
  Step 6: Latency Separation Proof (engine/demo.py)
  Step 7: Unified Evaluation Suite (final_eval/run_all.py)
```

---

### Step 1: The Clean Prescription (Specificity & Alert Fatigue Prevention)
* **Goal:** Prove the system does not "cry wolf" on safe, routine prescriptions.
* **Exact Actions on Screen:**
  1. In the sidebar dropdown **"Select patient"**, pick any routine patient (e.g., a patient with no high-risk interacting meds, or leave default).
  2. In the **"Prescription"** text area, type:
     ```text
     amoxicillin 1g
     ```
  3. Click the **"Run Safety Check"** button.
* **What Appears on Screen (Pause 3-4 seconds):**
  - A prominent green banner: **`DISPENSE — No safety alerts found for this prescription.`**
* **Companion Explanation (What you are demonstrating):**
  > *"MedFlow avoids alert fatigue. For safe prescriptions, it renders a clean, unambiguous green verdict with zero noise, giving the pharmacist confidence to dispense immediately."*

---

### Step 2: Direct Drug-Drug Interaction Trap & Reasoning Chain
* **Goal:** Demonstrate instant detection of high-risk pairwise interactions and explainable graph provenance.
* **Exact Actions on Screen:**
  1. In the sidebar dropdown, select trap patient: **`Karim Ben Salah`** (look at the right column: his active meds show **Warfarin**).
  2. In the prescription box, replace the text with:
     ```text
     aspirin 100mg
     ```
  3. Click **"Run Safety Check"**.
  4. On the alert card titled **`Direct Interaction: Aspirin + Warfarin`**, click the **`▶ Reasoning Chain`** collapsible arrow to expand it.
* **What Appears on Screen (Pause 4-5 seconds):**
  - An orange banner: **`CONTACT PRESCRIBER`**.
  - A major severity alert card flagged with **`NEW`**.
  - The expanded reasoning chain displaying step-by-step provenance:
    1. Direct interaction edge between aspirin and warfarin.
    2. ANSM severity classification: *deconseillee* mapped to *MAJOR*.
    3. Clinical Effect: *Increased risk of hemorrhage due to additive anticoagulant/antiplatelet effects*.
    4. Management recommendation: *Avoid combination or monitor INR closely*.
* **Companion Explanation:**
  > *"When a dangerous combination is prescribed, MedFlow immediately flags it as ACTION REQUIRED. Rather than a black-box answer, clicking the Reasoning Chain reveals the exact deterministic rule path from authoritative clinical sources (ANSM)."*

---

### Step 3: CYP450 Metabolic Trap (No Direct Edge in Literature)
* **Goal:** Demonstrate catching hidden 2-hop metabolic interactions that standard pairwise checkers miss.
* **Exact Actions on Screen:**
  1. In the sidebar dropdown, select trap patient: **`Nabil Chaabane`** (active medication: **Simvastatin**).
  2. In the prescription box, type:
     ```text
     clarithromycin 500mg
     ```
  3. Click **"Run Safety Check"**.
* **What Appears on Screen (Pause 3-4 seconds):**
  - A bright red banner: **`DO NOT DISPENSE`**.
  - A red alert card: **`CONTRAINDICATED — Simvastatin + Clarithromycin`**.
  - Detail text explaining: Clarithromycin strongly inhibits CYP3A4, blocking simvastatin metabolism and creating a severe risk of rhabdomyolysis.
* **Companion Explanation:**
  > *"Simvastatin and Clarithromycin share no direct interaction edge in basic databases. MedFlow performs multi-hop enzyme pathfinding: Clarithromycin strongly inhibits CYP3A4, preventing Simvastatin clearance and triggering an immediate red Contraindicated alert."*

---

### Step 4: Disease Concept Hierarchy Traversal (`IS_A` Reasoning)
* **Goal:** Show knowledge graph expansion from granular diagnosis to general contraindication.
* **Exact Actions on Screen:**
  1. In the sidebar dropdown, select trap patient: **`Fatma Trabelsi`** (look at her chronic conditions: **Chronic kidney disease stage 4**).
  2. In the prescription box, type:
     ```text
     metformin 1000mg
     ```
  3. Click **"Run Safety Check"**.
* **What Appears on Screen (Pause 3-4 seconds):**
  - A red **`DO NOT DISPENSE`** banner.
  - Alert: **`CONTRAINDICATED — Metformin in Renal Impairment`**.
  - Highlight the concept match: The graph traversed `-[:IS_A*0..3]->` from "CKD Stage 4" to general "Renal impairment", preventing lactic acidosis.
* **Companion Explanation:**
  > *"Doctors rarely write 'Renal Impairment' on a chart; they record specific diagnoses like 'CKD Stage 4'. MedFlow uses graph ontological reasoning to traverse disease hierarchies so granular conditions inherit broad safety contraindications."*

---

### Step 5: Pharmacist Memory Recall & 1-Click Prescriber Message
* **Goal:** Demonstrate decision persistence, alert fatigue reduction, and automated prescriber communication.
* **Exact Actions on Screen:**
  1. Look at the left sidebar: enter **`ph-042`** in the **"Pharmacist code"** field (press Enter).
     - Notice the caption: *Memory active (pharmacist #1)*.
  2. Switch back to patient **`Karim Ben Salah`** with `aspirin 100mg` and click **"Run Safety Check"**.
  3. Scroll down on the Aspirin alert card to the decision form:
     - Select **`Prescriber Contacted`** from the decision dropdown.
     - In the justification note box, type:
       ```text
       Called Dr. Ahmed - approved low-dose aspirin with weekly INR monitoring.
       ```
     - Click **"Record Decision"**.
  4. Click **"Run Safety Check"** again to simulate the patient returning or re-opening the file.
     - **Pause on the badge:** The dark `NEW` badge is now replaced by a gray **`ALREADY REVIEWED`** badge with your recorded note and timestamp!
  5. Click the button: **`Draft Prescriber Message`**.
* **What Appears on Screen (Pause 4-5 seconds):**
  - A pre-formatted, clinical letter ready to copy, containing:
    - Subject with patient name, ID, and age.
    - Triggering drugs and severity level.
    - Full reasoning chain.
    - Reference to previous review notes.
    - Specific recommended action request.
* **Companion Explanation:**
  > *"MedFlow remembers past pharmacist interventions. Re-scans tag previous rulings as ALREADY REVIEWED, sinking them below fresh risks. Pharmacists can generate an instant, zero-hallucination communication letter to send to the prescriber with one click."*

---

### Step 6: Terminal Latency Separation Proof (Graph vs LLM)
* **Goal:** Prove database safety checks execute in **~25 ms**, proving downstream delays are isolated to LLM text generation.
* **Exact Actions on Screen:**
  1. Switch your window to the terminal / PowerShell in the `medflow` folder.
  2. Run the live latency demo command:
     ```powershell
     .venv\Scripts\python.exe engine/demo.py
     ```
* **What Appears on Screen (Pause 3-4 seconds on the output table):**
  ```text
  LATENCY BREAKDOWN:
    Deterministic Graph Query Latency: 24.12 ms
    LLM Synthesis Latency:             4,288.10 ms
    Total Analysis Latency:            4,312.22 ms
  ```
* **Companion Explanation:**
  > *"MedFlow separates deterministic graph querying from generative synthesis. The database rules execute in just 24 milliseconds — providing counter-speed safety guarantees regardless of local LLM speed."*

---

### Step 7: Final Automated Benchmark Suite
* **Goal:** Show rigorous end-to-end evaluation results across sensitivity, specificity, and load.
* **Exact Actions on Screen:**
  1. In the terminal, execute the unified benchmark:
     ```powershell
     .venv\Scripts\python.exe -m evaluation.final_eval.run_all
     ```
* **What Appears on Screen (Scroll smoothly and pause on FINAL VERDICT):**
  ```text
  ##############################################################################
  #  FINAL VERDICT
  ##############################################################################
      sensitivity          PASS  (8/8 trap patients detected - 100%)
      specificity          PASS  (10/10 safe cases clean - 0 false alarms)
      severity             PASS  (100% detection, 0 engine bugs)
      latency_load         PASS  (p99 304 ms under 8 concurrent streams)

    RESULT: PASS - every executed suite met its bar.
  ##############################################################################
  ```
* **Companion Explanation:**
  > *"The evaluation battery verifies 100% sensitivity across all clinical traps, 100% specificity with zero false alarms, and a 304ms p99 latency under heavy 8-worker concurrent load."*

---

## Ready to Record

- Open your browser at **`http://localhost:8501`** on the left half of your screen.
- Keep PowerShell open on the right half of your screen (or switch between them with `Alt + Tab`).
- Follow the exact 7 steps above!
