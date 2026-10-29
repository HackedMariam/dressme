# E1 — FashionCLIP zéro-shot sur des attributs vestimentaires

**Question** : FashionCLIP peut-il identifier de façon suffisamment fiable des
attributs qui manquent à BO4 (motif, formalité, registre, épaisseur apparente) ?

**État** : prédictions produites ; **aucune précision n'est connue** tant que
deux évaluateurs humains indépendants n'ont pas annoté les mêmes vêtements.
Ce dossier ne modifie ni le moteur BO4, ni l'API, ni PostgreSQL, ni BO1, ni
les fichiers ISSUE-08 (le pool femme y est seulement lu).

## Fichiers

| Fichier | Rôle |
|---|---|
| `attributes.py` | Schéma d'attributs, classes, libellés anglais zéro-shot, seuil d'ambiguïté, empreinte du schéma |
| `zero_shot.py` | Calculs purs : normalisation, moyenne des formulations, prédiction, marge, préparation d'image |
| `run_e1.py` | Exécution : contrôle des images, FashionCLIP hors ligne en CPU, sorties et métadonnées |
| `annotation_form.py` | Formulaire HTML autonome pour les évaluateurs (images seules, sans prédiction) |
| `agreement.py` | Calculs prévus (kappa de Cohen, consensus, exactitude, confusion) ; refuse de tourner sans 2 annotations réelles |
| `output/predictions.csv` | Prédiction, 2e classe, marge et indicateur d'ambiguïté par vêtement et attribut |
| `output/similarities.csv` | Similarités cosinus brutes (vêtement × attribut × classe) |
| `output/embeddings.npz` | Embeddings image (36 × 512) |
| `output/metadata.json` | Modèle, versions, mode d'image, empreintes (schéma, images, pool, fichiers BO4) |
| `output/annotation_attributs.html` | Formulaire à envoyer aux évaluateurs |

Tests : `backend/tests/test_fashionclip_e1.py`.

## Méthode

- **Données** : les 36 vêtements de `evaluation/data/pool_femme.csv` (images
  contrôlées : existence et décodage).
- **Modèle** : `fashion-clip` (ViT-B/32), poids lus dans le cache Hugging Face
  local avec `HF_HUB_OFFLINE=1` ; CPU ; aucun entraînement.
- **Image** : mode `pad` par défaut — l'image est complétée en carré sur fond
  blanc pour que le recadrage central 224×224 de CLIP n'ampute pas le vêtement
  (les photos H&M sont verticales). Le mode `crop` reste disponible.
- **Zéro-shot** : chaque classe a ≥ 2 formulations ; leurs embeddings texte
  normalisés sont moyennés. Prédiction = classe de plus grande similarité
  cosinus ; **marge** = écart avec la 2e classe.
- **Ambiguïté** : marge < 0,01 (seuil fixé a priori, non ajusté sur les
  résultats). Une prédiction ambiguë est conservée mais signalée.
- **Les similarités ne sont pas des probabilités** et ne sont pas comparables
  d'un attribut à l'autre.

## Annotation humaine

1. Envoyer `output/annotation_attributs.html` à **deux évaluateurs indépendants**.
2. Chacun l'ouvre par double-clic, saisit un pseudonyme, répond pour les 36
   vêtements (« Incertain » et « Non visible » toujours possibles) et exporte
   `annotations_attributs_<pseudo>.csv`.
3. Les évaluateurs ne voient que l'image (comme le modèle) : ni nom, ni type,
   ni description, ni prédiction.
4. Ces annotations sont **distinctes** des annotations de tenues ISSUE-08.

## Reproduire (PowerShell, depuis `backend/`)

```powershell
cd C:\Users\Win11\DressMe\backend
.\.venv\Scripts\python.exe -m experiments.fashionclip_e1.run_e1 --image-mode pad
.\.venv\Scripts\python.exe -m experiments.fashionclip_e1.annotation_form
.\.venv\Scripts\python.exe -m pytest tests/test_fashionclip_e1.py -v
# Après réception de DEUX fichiers d'annotations réels :
.\.venv\Scripts\python.exe -m experiments.fashionclip_e1.agreement annotations_attributs_A1.csv annotations_attributs_B2.csv
```

## Limites connues

- 36 vêtements seulement : estimations d'exactitude très imprécises.
- Libellés anglais choisis a priori ; d'autres formulations donneraient
  d'autres résultats (sensibilité non mesurée).
- « Registre » et « formalité » sont subjectifs et se recouvrent partiellement.
- L'épaisseur est jugée sur une photo : information souvent peu visible.
- Biais possible vers les photos produit sur fond blanc (données d'entraînement
  de FashionCLIP).
