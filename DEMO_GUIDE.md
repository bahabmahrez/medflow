# MedFlow — Guide d'exécution et de test du LLM

> Étapes exactes pour lancer le projet et tester le pipeline GraphRAG.
> Environnement : Windows / PowerShell.

---

## 1. Prérequis (à installer une seule fois)

```powershell
pip install -r requirements.txt
pip install -r requirements-graph.txt
```

Vérifie que Docker Desktop est lancé (nécessaire pour PostgreSQL et Neo4j).

---

## 2. Démarrer les bases de données

```powershell
docker compose up -d
```

Vérifie que les deux conteneurs tournent :

```powershell
docker ps
```

Tu dois voir `medflow-postgres-1` et `medflow-neo4j-1` avec le statut `Up`.

---

## 3. Charger les données

**PostgreSQL (couche relationnelle) :**
```powershell
python run_loaders.py
```
Doit se terminer par : `All 12 loaders completed successfully.`

**Neo4j — créer le schéma du graphe :**
```powershell
python db\graph\init_graph.py
```
Doit afficher : `Schema applied: 8 constraints, 11 property indexes`

**Neo4j — charger les données dans le graphe :**
```powershell
python run_loaders_graph.py
```
Doit se terminer par : `All 12 loaders completed successfully.`

---

## 4. Vérifier que le graphe est bien peuplé

```powershell
python -c "
from neo4j import GraphDatabase
d = GraphDatabase.driver('bolt://localhost:7687', auth=None)
r = d.execute_query('MATCH (n) RETURN labels(n)[0] AS l, count(n) AS c ORDER BY c DESC')
for rec in r.records: print(f'{rec[\"l\"]:25s}  {rec[\"c\"]}')
d.close()
"
```

Compte attendu (approximatif) :

| Label | Attendu |
|---|---|
| Molecule | ~51 |
| Drug | ~183 |
| CYPEnzyme | 6 |
| DrugClass | ~40 |
| AllergyGroup | 5 |
| Patient | 50 |

⚠️ Si ces comptes sont à 0 ou très bas, le problème vient d'ici (données non chargées), pas du code d'extraction ou du LLM.

---

## 5. Lancer les tests de la couche de requêtes (query layer)

```powershell
python -m pytest query\tests\ -v --tb=short
```

**Attendu : 45 tests passés.** Ces tests nécessitent que Neo4j soit démarré (étape 2).

---

## 6. Démarrer le serveur GraphRAG (API)

```powershell
python -m uvicorn graphrag.server:app --reload --port 8000
```

Laisse ce terminal ouvert — c'est le serveur. Il doit afficher :
```
INFO:     Application startup complete.
```

---

## 7. Tester le LLM — requêtes de base

**Dans un second terminal**, active le venv puis teste `/health` :

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/health"
```

Réponse attendue : `{"status":"ok","service":"MedFlow GraphRAG"}`

**Teste une vraie question clinique :**

```powershell
$body = @{ question = "Can I prescribe amiodarone to a patient already taking warfarin?" } | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:8000/ask" -Method Post -Body $body -ContentType "application/json"
```

Réponse attendue (structure) :
```json
{
  "answer": "This combination is CONTRAINDICATED...",
  "drugs_detected": ["warfarin", "amiodarone"],
  "risk_level": "HIGH",
  "context": "=== PAIRWISE INTERACTIONS ===..."
}
```

**Teste un cas plus difficile (interaction indirecte via CYP, pas d'arête directe) :**

```powershell
$body2 = @{ question = "Is simvastatin safe with clarithromycin?" } | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:8000/ask" -Method Post -Body $body2 -ContentType "application/json"
```

`risk_level` doit être `HIGH` même sans interaction directe — détecté via le chemin CYP3A4.

---

## 8. Lancer la suite d'évaluation complète (30 cas cliniques)

```powershell
python -m evaluation.llm_eval.runner
```

Résultat attendu :
```
Tier 1 — Factual     : 10/10  (100%)
Tier 2 — Multi-hop   : 10/10  (100%)
Tier 3 — Adversarial :  x/10  ( x%)
OVERALL              : xx/30  (xx%)
```

Pour ne lancer qu'un seul tier (ex: les cas adversariaux, qui testent la résistance du LLM à la manipulation) :
```powershell
python -m evaluation.llm_eval.runner --tier T3
```

---

## 9. Lancer toute la suite de tests unitaires (sans clé API)

```powershell
python -m pytest query\tests\ llm\tests\ graphrag\tests\ evaluation\llm_eval\ -q -m "not live"
```

**Attendu : 82 tests passés.** Ceux-ci tournent sans clé API, sans Docker, en moins de 10 secondes.

---

## Résumé — ordre d'exécution complet

1. `docker compose up -d`
2. `python run_loaders.py`
3. `python db\graph\init_graph.py`
4. `python run_loaders_graph.py`
5. `python -m pytest query\tests\ -v --tb=short`
6. `python -m uvicorn graphrag.server:app --reload --port 8000` (garder ouvert)
7. Dans un second terminal : tester `/health` puis `/ask`
8. `python -m evaluation.llm_eval.runner`
9. `python -m pytest query\tests\ llm\tests\ graphrag\tests\ evaluation\llm_eval\ -q -m "not live"`