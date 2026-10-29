# Évaluation de la qualité des recommandations BO4 (ISSUE-08)

Ce dossier outille une **évaluation humaine en aveugle** des tenues recommandées
par le moteur BO4. Les tests logiciels (`backend/tests`) vérifient que le code
fait ce qui est prévu ; ils ne disent **rien** de la qualité perçue des tenues.
Seules des annotations humaines peuvent en juger.

**État : phase 1 (pilote).** Aucune annotation n'existe encore. Aucune métrique
de performance n'est calculée à ce stade.

## Principes

- **Vérité terrain humaine uniquement.** Le score du moteur sert à stratifier
  l'échantillon et à l'analyse future ; il n'est jamais une référence.
- **Aveugle.** L'annotateur ne voit ni score, ni rang, ni explication du moteur,
  ni la méthode de tirage (vérifié par les tests).
- **Reproductible.** Graine fixe, plan d'échantillonnage écrit, empreintes
  SHA-256 du moteur et du catalogue dans le manifeste.
- **Lecture seule.** Les données H&M, PostgreSQL, BO1 et le moteur ne sont pas modifiés.

## Fichiers

| Fichier | Rôle |
|---|---|
| `common.py` | Chemins, segment, graine par défaut, empreintes, connexion en mémoire pour réutiliser `load_user_wardrobe` |
| `build_pools.py` | Pool de vêtements du segment femme avec image valide + rapport de couverture |
| `sample_outfits.py` | Échantillon pilote de 20 couples tenue-contexte + manifeste |
| `annotation_pack.py` | Outil d'annotation HTML autonome (images intégrées) |
| `guide_annotation_fr.md` | Consignes pour les annotateurs |
| `data/pool_femme.csv` | Pool généré |
| `data/couverture_femme.md` | Rapport de couverture généré |
| `data/manifeste_pilote.csv` | Manifeste généré (réservé à l'analyse : contient les scores) |
| `data/annotation_pilote.html` | Outil à envoyer aux annotateurs (sans scores) |

## Reproduire le pilote (PowerShell, depuis `backend/`)

```powershell
cd C:\Users\Win11\DressMe\backend
.\.venv\Scripts\python.exe -m evaluation.build_pools
.\.venv\Scripts\python.exe -m evaluation.sample_outfits --seed 20261015
.\.venv\Scripts\python.exe -m evaluation.annotation_pack
.\.venv\Scripts\python.exe -m pytest tests/test_evaluation_pilot.py -v
```

Avec la même graine, les mêmes données et le même moteur (mêmes empreintes),
le manifeste produit est identique.

## Segment

Vêtements dont `index_group_name` (fichier `articles.csv`, absent de PostgreSQL)
vaut `Ladieswear` ou `Divided`, ayant un rôle BO4 et une image qui existe et se
décode. Exclus : homme, bébé/enfant, sport (genre non garanti).

## Plan d'échantillonnage du pilote (20 couples)

Les tenues sont générées par `recommend_outfits(..., diversify=False)` sur le pool.

| Tirages | Méthode | Détail |
|---|---|---|
| 16 | stratifié | 4 saisons × 4 structures (haut+bas, haut+bas+veste, robe, robe+veste) ; tercile de score en rotation `(indice saison + indice structure) mod 3` ; occasion `university` |
| 4 | aléatoire | 1 par saison, parmi toutes les tenues de la saison ; occasions `work`, `evening`, `casual`, `university` |

- **Tercile positionnel** : position dans l'ordre du moteur (score décroissant,
  départage ISSUE-06) au sein de la strate (saison, structure). Avec de nombreux
  ex aequo, deux tenues de même score peuvent tomber dans deux terciles voisins.
- Une tenue déjà tirée n'est reprise dans un autre contexte que si la strate
  n'offre aucune alternative (signalé à l'exécution). Un couple tenue-contexte
  n'est jamais dupliqué.
- Chaque tirage utilise un générateur dérivé de `graine:emplacement:saison:occasion`.

## Manifeste (`data/manifeste_pilote.csv`)

Identifiant opaque (`sample_id`), emplacement, saison, occasion, structure,
méthode, strate, tercile, taille de la strate, rang dans la strate, identifiants,
catégories, types, noms et chemins d'images des vêtements, score moteur et ses
composantes, explications du moteur (JSON), graine, segment, empreintes SHA-256
de `outfit_engine.py`, `garment_attributes.py`, `wardrobe_db_adapter.py` et
`catalog_products.csv`.

**Ne pas transmettre le manifeste aux annotateurs.**

## Annotation

1. Envoyer `data/annotation_pilote.html` et `guide_annotation_fr.md`.
2. L'annotateur ouvre le fichier HTML par double-clic (aucun serveur, aucune
   connexion), choisit un pseudonyme, note les 20 tenues, puis clique sur
   « Exporter mes réponses (CSV) ».
3. L'ordre des tenues dépend du pseudonyme (mélange reproductible).
4. Les réponses sont sauvegardées dans le navigateur (localStorage) pour
   reprendre plus tard avec le même pseudonyme.

Colonnes exportées : `annotateur, sample_id, ordre_presentation, harmonie, style,
occasion, saison, globale, image_illisible, impossible_a_evaluer, commentaire,
horodatage, version_manifeste`.

## Limites connues du pilote

- Pool réduit : 36 vêtements (20 hauts, 8 bas, 5 vestes, 3 robes) faute
  d'images ; robes très peu nombreuses.
- Le style est toujours inconnu dans les données : le moteur ne distingue pas
  les occasions (scores style et occasion constants). Les notes « occasion »
  mesureront ce manque, pas une capacité du moteur.
- Certains articles H&M sont mal catégorisés dans le catalogue (ex. brassière
  de sport en « Top », doudoune en « Hoodie ») : ils sont conservés tels quels,
  car ce sont les entrées réelles du moteur.
- 20 couples servent à **tester le protocole** (consignes, outil, accord entre
  annotateurs), pas à conclure sur la qualité du moteur.

## Phases suivantes (non implémentées)

Métriques (accord inter-annotateurs, corrélations, NDCG@5, exactitude par
paires), baselines et analyse : après validation du pilote.
