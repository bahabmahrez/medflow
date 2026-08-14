# Real Pharmacist Test - Session Kit

**Milestone 4 bar-raiser.** One real Tunisian pharmacist, sitting with the system,
using it on realistic cases. This is the single piece of validation worth more
than any synthetic metric, so it is worth running properly.

**Everything below is preparation. The session itself is not something the team
can simulate - it needs a real pharmacist.**

---

## 1. Before they arrive (15 min)

```bash
docker compose up -d
python -m memory                       # ensure the memory tables exist
python -m evaluation.final_eval.run_all --quick   # confirm the system is healthy
streamlit run interface/app.py         # opens http://localhost:8501
```

In the sidebar, set the pharmacist code to something real (e.g. their initials) so
their decisions are recorded under their own identity, and check that a scan of
*clarithromycin* for patient **Nabil Chaabane** raises the red contraindication.

Have ready: this document, the observation sheet (§4), and a way to record audio
or take notes without slowing them down.

---

## 2. How to run it (45-60 min)

**Do not demo the system to them.** The instinct is to show it working; resist it.
What you need is their unguided reaction, and a guided tour destroys exactly that.

Say roughly: *"This is a prescription safety checker. I would like you to use it
the way you would at your counter, and to say out loud what you are thinking -
including when something annoys you or you do not trust it. I am testing the
software, not you. There are no wrong reactions."*

Then hand over the keyboard and stay quiet. When they pause, ask only open
questions: *"What are you looking at?"*, *"What would you do now?"*, *"Is that what
you expected?"*

### The cases, in this order

Start easy, so they learn the screen on something low-stakes.

| # | Patient | Prescribe | What it tests | Watch for |
|---|---|---|---|---|
| 1 | Any non-trap patient | `amoxicillin 1g` | The calm "no issues" screen | Do they trust a green result? Do they look for a second opinion? |
| 2 | **Karim Ben Salah** | `aspirin 100mg` | A classic major interaction | Do they read the reasoning chain or just the title? |
| 3 | **Nabil Chaabane** | `clarithromycin 500mg` | Contraindicated + CYP, red | Does the severity ordering match their own priority? |
| 4 | **Fatma Trabelsi** | `metformin 1000mg` | Contraindication reached through the concept hierarchy | Does "classifies CKD stage 4 as a form of renal impairment" read as sound, or as the system guessing? |
| 5 | **Amira Khelifi** | `amoxicillin 1g` | Allergy, do-not-dispense | Is the allergy alert prominent enough? |
| 6 | **Bechir Hajji** (or the heavy case) | `clarithromycin 500mg` + `ibuprofen 400mg` | ~26 alerts on a polypharmacy patient | **The alert-fatigue question.** Where do their eyes go? At what point do they stop reading? |
| 7 | Re-scan case 3 after recording a decision | Same | Memory: reminder vs fresh alert | Does the softened presentation feel helpful or unsafe? |
| 8 | Their own case | Anything they choose | Realism | Does it hold up on something we did not design for? |

Case 6 is the most important. Case 7 is the second most important, because it is
the design decision we are least sure about.

---

## 3. Questions to ask at the end

Ask these after the hands-on part, not during.

**Trust**
1. Was there a moment you did not believe what it told you? What was it?
2. If this disagreed with your own judgement, what would you do?
3. Would you dispense against a red alert if the prescriber insisted? What would
   you want the system to do then?

**The reasoning chains**
4. Did you read the explanations, or only the headline? (Watch what they actually
   did, not only what they say.)
5. Was anything worded in a way that felt wrong, or too confident?

**Alert volume**
6. On the polypharmacy patient, how many alerts is too many? What should we have
   hidden?
7. Is a "moderate" CYP note useful to you, or noise?

**The design decisions we are unsure about** - see §5
8. When you have already reviewed an interaction for a patient, should it come
   back quieter next time? For how long?
9. Should a *contraindicated* finding ever be softened, even if you personally
   overrode it last week?

**Fit**
10. Where would this sit in your day - every prescription, or only the ones that
    already worry you?
11. What is missing that would stop you using it?
12. Would you rather have it faster and less thorough, or as it is?

---

## 4. Observation sheet (fill during, not after)

For each case: what they said, what they did, where they hesitated.

```
Case __  Patient ________________  Prescription ________________

Time to first understanding:  ____ s     (when did they know the verdict?)
Read the reasoning chain?     yes / skimmed / no
Trusted the verdict?          yes / no / checked elsewhere
Their own decision:           dispense / note / contact prescriber / refuse
Did it match the system's?    yes / no  ->  if no, why:

Quotes (verbatim, do not tidy them up):


Moments of hesitation or confusion:
```

Verbatim quotes matter more than scores. "I would never trust this on a
polypharmacy patient" is worth more than a rating of 3/5.

---

## 5. The three decisions we most want challenged

State these plainly and invite disagreement. They are judgement calls made by the
team, not clinical standards, and each is a one-line change:

1. **Contraindicated alerts are never softened by memory**, even after the
   pharmacist overrides them ([memory/recall.py](../memory/recall.py),
   `NEVER_DEMOTED`). Safe, or patronising?
2. **A decision stops softening an alert after 90 days**
   (`DEFAULT_WINDOW_DAYS`). Too short, too long?
3. **A pair flagged both directly and by enzyme competition is shown as one
   alert**, more severe finding leading ([engine/alerts.py](../engine/alerts.py),
   `merge_pair_alerts`). Does that hide something they would want to see?

Also worth raising: the four severity gradings the evaluation flagged as
debatable - `omeprazole + clopidogrel`, `diclofenac + methotrexate`,
`verapamil + simvastatin`, `rifampicin + warfarin`. Ask which grade they would
give each.

---

## 6. Afterwards

Write the session up the same day, while the tone is still fresh, into
[WEEK6_M4_FINAL_EVALUATION.md](WEEK6_M4_FINAL_EVALUATION.md) §7 covering:

- what they trusted, and what they did not
- what they would want changed before using it
- where it felt off, in their words
- which of the §5 decisions they disagreed with

Record disagreements even where we think we are right - especially there. An
honest account of a pharmacist rejecting part of the design is a stronger
result than a polished demo, and it is what turns this from a student build into
something with early validation.
