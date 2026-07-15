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

**LLM local avec Ollama :** le projet utilise un modèle LLM local via Ollama au lieu de clés API externes. Voir `docs/ollama_setup.md` pour l'installation détaillée. En résumé :

1. Installer Ollama depuis https://ollama.com
2. Télécharger le modèle : `ollama pull qwen2.5:7b-instruct`
3. Vérifier que le modèle est disponible : `ollama list`

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

## 9. Lancer toute la suite de tests unitaires (Semaines 1-3, sans clé API)

```powershell
python -m pytest query\tests\ llm\tests\ graphrag\tests\ evaluation\llm_eval\ -q -m "not live"
```

**Attendu : 82 tests passés.** Ces tests nécessitent Neo4j démarré (étape 2) — plusieurs tests de `query\tests\` et `graphrag\tests\` font des appels réels au graphe (non mockés). Sans Neo4j lancé, ils restent bloqués au lieu d'échouer proprement.

---

## 10. Tester l'agent (Semaine 4 — tool-calling)

Le pipeline `/ask` de la Semaine 3 décidait lui-même, en Python, quelles fonctions
de requête lancer. Le nouvel agent (`agent/`) inverse ce contrôle : c'est le LLM
qui choisit, parmi les 10 outils enregistrés, lesquels appeler et avec quels
arguments — en plusieurs tours si besoin — avant de répondre.

Le serveur (étape 6) doit déjà tourner. **Dans le second terminal :**

```powershell
$body = @{
    question = "New prescription is clarithromycin for a patient already on simvastatin and warfarin. Anything I should worry about?"
} | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:8000/agent/ask" -Method Post -Body $body -ContentType "application/json"
```

Réponse attendue (structure) :
```json
{
  "final_answer": "Two concerns. The serious one: clarithromycin blocks the enzyme...",
  "trace": {
    "question": "...",
    "iterations": 2,
    "stopped_reason": "final_answer",
    "steps": [
      { "step": 1, "tool_calls_requested": [
          {"name": "detect_pairwise_interactions", "arguments": {"drug_list": ["clarithromycin","simvastatin","warfarin"]}}
        ],
        "tool_executions": [ { "name": "detect_pairwise_interactions", "status": "found", ... } ]
      },
      { "step": 2, "tool_calls_requested": [
          {"name": "detect_cyp_competition", "arguments": {"drug_list": ["clarithromycin","simvastatin","warfarin"]}}
        ],
        "tool_executions": [ { "name": "detect_cyp_competition", "status": "found", ... } ]
      }
    ]
  }
}
```

`trace.steps` montre exactement quel outil le modèle a choisi, avec quels
arguments, et ce qui est revenu — c'est ce qui prouve que l'agent raisonne
correctement (et pas seulement sa réponse finale).

Tu peux aussi inspecter une trace lisible en Python :

```powershell
python -c "
from agent import run_agent, pretty_print
r = run_agent('Can I prescribe amiodarone to a patient already taking warfarin?')
print(pretty_print(r['trace']))
"
```

---

## 11. Lancer la suite d'évaluation de l'agent (25 scénarios)

```powershell
python -m evaluation.agent_eval.runner
```

Résultat attendu :
```
Multi-tool  : 10/10  (100%)
Ambiguity   :  x/7   ( x%)
Adversarial :  x/8   ( x%)
OVERALL     : xx/25  (xx%)
```

Pour ne lancer qu'un seul tier :
```powershell
python -m evaluation.agent_eval.runner --tier ambiguity
python -m evaluation.agent_eval.runner --tier adversarial
```

Les cas `ambiguity` vérifient que l'agent pose une question de clarification au
lieu de deviner (dose sans unité, classe de médicament vague, patient sans
données). Les cas `adversarial` incluent les 6 pièges de la Semaine 3
(question orientée, autorité revendiquée, médicament inventé, hors périmètre)
rejoués contre l'agent, plus 2 nouveaux cas de "tool misuse" : l'agent ne doit
jamais appeler un outil avec un médicament halluciné, ni inventer un résultat
quand un outil ne retourne rien.

---

## 12. Lancer toute la suite de tests unitaires (Semaines 1-4, sans clé API)

```powershell
python -m pytest query\tests\ llm\tests\ graphrag\tests\ evaluation\llm_eval\ agent\tests\ evaluation\agent_eval\ -q -m "not live"
```

**Attendu : 125 tests passés** (82 des Semaines 1-3 + 43 de la Semaine 4).
Nécessite Neo4j démarré, aucune clé API.

---

## 13. Serveur MCP (Semaine 5 — Model Context Protocol)

Le serveur MCP expose les 10 fonctions de requête comme outils MCP, accessibles
depuis n'importe quel client MCP (Claude Desktop, MCP Inspector, etc.).

**Installer les dépendances :**
```powershell
pip install "mcp>=1.25" "mcp[cli]>=1.25"
```

**Tester avec le MCP Inspector (debugging) :**
```powershell
mcp dev medflow_mcp/server.py
```
Ouvre http://localhost:5173 pour appeler les outils dans l'interface web.

**Lancer le serveur en mode stdio (pour Claude Desktop) :**
```powershell
mcp run medflow_mcp/server.py
```

**Configurer Claude Desktop :**

Ajouter dans `%APPDATA%\Claude\claude_desktop_config.json` :
```json
{
  "mcpServers": {
    "MedFlow": {
      "command": "mcp",
      "args": ["run", "medflow_mcp/server.py"],
      "cwd": "C:\\Users\\bahab\\OneDrive\\Desktop\\medflow"
    }
  }
}
```

Redémarrer Claude Desktop. Les 10 outils MedFlow apparaîtront dans la barre
latérale (icône 🔧). Claude peut maintenant interroger le graphe de connaissances
directement.

**Outils disponibles :**
| Outil | Description |
|---|---|
| `resolve_drug_name_tool` | Résoudre un nom (INN, marque) en INN canonique |
| `get_drug_profile_tool` | Profil complet d'un médicament |
| `detect_pairwise_interactions_tool` | Interactions directes entre 2+ médicaments |
| `detect_cyp_competition_tool` | Interactions médiées par CYP450 |
| `check_contraindications_tool` | Contre-indications vs conditions patient |
| `check_allergy_conflict_tool` | Conflits allergie + cross-réactivité |
| `check_therapeutic_duplication_tool` | Détection de thérapie en double |
| `check_dose_appropriateness_tool` | Ajustement de dose (âge, reins, foie) |
| `get_drugs_by_class_tool` | Lister les médicaments d'une classe |
| `full_prescription_check_tool` | Vérification complète en un appel |

**Ressources MCP :**
- `medflow://system-prompt` — Prompt système de l'agent
- `medflow://tools` — Liste des outils disponibles
- `medflow://graph-stats` — Statistiques du graphe Neo4j

**Prompts MCP :**
- `evaluate_prescription` — Structurer une évaluation de prescription
- `drug_info` — Consulter le profil d'un médicament
- `check_interactions` — Vérifier les interactions entre médicaments

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
10. Tester `/agent/ask` (agent tool-calling, Semaine 4)
11. `python -m evaluation.agent_eval.runner`
12. `python -m pytest query\tests\ llm\tests\ graphrag\tests\ evaluation\llm_eval\ agent\tests\ evaluation\agent_eval\ -q -m "not live"`
13. Tester le serveur MCP (`mcp dev medflow_mcp/server.py` ou configurer Claude Desktop)