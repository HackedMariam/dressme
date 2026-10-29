# E2 — Microbenchmark de faisabilité de Qwen3-VL 2B (Ollama local)

**But** : vérifier que Qwen3-VL 2B tourne de façon fiable sur la machine
(RTX 2050 4 Go, 7,7 Go de RAM) avec une sortie JSON stricte. **Aucune
exactitude n'est mesurée ici** : la qualité sera évaluée en E2-b, sur un
nouveau jeu annoté par des humains.

Isolé de BO1, BO4, PostgreSQL, ISSUE-08 et E1 (fichiers lus, jamais modifiés).

## Fichiers

| Fichier | Rôle |
|---|---|
| `taxonomy.py` | 9 dimensions, valeurs, libellés FR, questions, règles ; empreinte de version |
| `schema.py` | Modèle Pydantic strict (`extra="forbid"`, énumérations fermées) ; schéma pour `format` ; validation |
| `prompt.py` | Prompt système (questions, règles, schéma) ; empreinte |
| `ollama_client.py` | Client HTTP local (`requests`) : version, tags, ps, chat ; aucun téléchargement ; hôte local uniquement |
| `monitor.py` | VRAM (nvidia-smi, toutes les 1 s ; 0,25 s lors du benchmark initial) et RAM disponible (psutil) pendant chaque appel |
| `select_images.py` | Sélection déterministe des 10 images hors E1 ; registre `data/splits.json` |
| `run_microbench.py` | Orchestration, mesures, résumé et verdict d'acceptation |
| `run_single_check.py` | Diagnostic : un seul appel sur une image, `num_predict`/`num_ctx` élargis ; `/api/show` sans inférence ; écrit `output_single_check/` |
| `run_mini_bench.py` | Mini-benchmark : 3 images de la sélection, 1 appel chacune, mêmes options élargies et contrôles RAM avant chaque appel ; écrit `output_mini3/` |
| `run_optim.py` | Optimization protocol (A0 reference, A1 unload between images, R1/R2 reduced image, C1 reduced context) ; writes `output_optim/<run>/` and `comparison.json` |
| `human_eval.py` | E2-h : formulaire d'annotation humaine EN AVEUGLE des 4 images analysées (`build`) puis comparaison aux prédictions (`compare`) ; écrit `output_human_eval/` |
| `metadata_mapping.py` | Correspondance a priori métadonnées H&M → taxonomie (pour E2-b, non exécutée) |
| `data/microbench_e2.csv` | Les 10 images retenues (split `e2_microbench_dev`) |
| `data/splits.json` | 36 identifiants E1 scellés + 10 identifiants de développement E2 |
| `output/` | Généré par le benchmark : `results.jsonl`, `summary.json`, `metadata.json` |

Tests : `backend/tests/test_qwen3vl_e2.py` (faux client Ollama, sans réseau).

## Taxonomie : règles

- Dimensions **indépendantes** : une dentelle florale = `pattern=floral` ET `material_appearance=lace`.
- Une texture n'est pas un motif ; la coupe (`fit`) n'est pas un style.
- La formalité ne se déduit **jamais** de la catégorie.
- `style` est **exploratoire** : mesuré, jamais utilisé par BO4.
- `formality` et `thickness` sont **ordinales** (κ pondéré en E2-b).
- `not_visible` plutôt que deviner ; `certainty` n'est pas calibrée.

## Séparation des données

- `e1_test_sealed` : les 36 vêtements femme d'E1 — exclus de tout développement.
- `e2_microbench_dev` : les 10 images du microbenchmark — développement uniquement.
- Le futur jeu de test de qualité (E2-b) devra exclure **les deux** listes ; il
  nécessitera de nouvelles images (téléchargement à approuver).

## Paramètres du benchmark

`temperature=0`, `seed=0`, `num_ctx=4096`, `num_predict=256`, `think=false`,
`keep_alive=10m`, délai 120 s, image JPEG d'origine, schéma Pydantic dans
`format` **et** dans le prompt, revalidation de chaque réponse.

1 appel à froid (exclu des statistiques) puis 10 images × 3 répétitions = 30
appels à chaud, ordre mélangé par répétition (graine fixe).

## Diagnostic après le benchmark initial

Benchmark initial (`output/`, conservé tel quel) : 31/31 appels `done_reason=length`
avec `eval_count=256` ; tout le budget est consommé par le raisonnement
(`thinking`) malgré `think=false`, d'où un contenu vide. Entrée : 3 107 jetons.

Ajouts : `--num-predict` / `--num-ctx` (par défaut, configuration initiale ;
`num_ctx` doit couvrir 3 107 + `num_predict`), extraits de `content` et
`thinking` (200 caractères en début et fin), contrôle RAM préalable (≥ 1 500 Mio,
+ 418 Mio si le modèle n'est pas chargé), arrêt sous 300 Mio, refus d'écraser
des résultats existants.

## Critères d'acceptation (fixés avant exécution)

| Critère | Seuil |
|---|---|
| JSON conforme au schéma | ≥ 29/30 |
| `done_reason = stop` | ≥ 29/30 |
| Latence à chaud | p50 ≤ 10 s, p95 ≤ 20 s |
| RAM disponible minimale | ≥ 300 Mio |
| VRAM maximale | ≤ 4 096 Mio |
| Stabilité (accord moyen par champ sur 3 répétitions) | ≥ 90 % |

Tous respectés → GO pour E2-b (qualité). Sinon : rapport des points bloquants.

## Commandes (PowerShell, depuis `backend/`)

```powershell
cd C:\Users\Win11\DressMe\backend
# Tests (sans Ollama)
.\.venv\Scripts\python.exe -m pytest tests/test_qwen3vl_e2.py -v
# Sélection (déjà générée ; reproductible)
.\.venv\Scripts\python.exe -m experiments.qwen3vl_e2.select_images --seed 20261016
# Benchmark réel — UNIQUEMENT après validation :
#   1. fermer Chrome ; 2. Ollama lancé en local (OLLAMA_NO_CLOUD=1) ; 3. qwen3-vl:2b déjà présent
.\.venv\Scripts\python.exe -m experiments.qwen3vl_e2.run_microbench --model qwen3-vl:2b --repeats 3
```

Le script s'arrête sans rien télécharger si `qwen3-vl:2b` n'est pas déjà présent.

## Limites

- 10 images, surtout homme (et une robe enfant) : la faisabilité mesurée ne
  préjuge pas du comportement sur des vêtements femme.
- Les motifs H&M retenus incluent des textures (Slub, Treatment, Melange) ;
  aucun article rayé ou à pois dans la sélection.
- `certainty` et la stabilité ne disent rien de l'exactitude.
