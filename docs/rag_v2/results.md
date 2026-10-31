# RAG v2 : résultats avant / après

Gold set (`gold_set.jsonl`, 40 questions, 20 sujets en FR et en EN) validé pour l'étape 4 ; annotation par une seule personne. Une exécution par ligne ; le LLM varie d'un appel à l'autre. `top_k = 5`.

Depuis l'étape 4, le sujet « tendances » (2 questions) n'a plus de source : réponse attendue « I don't know », hors Hit@5 / MRR / précision (38 questions mesurées). Les lignes 0 à 3 utilisent l'ancien gold set (40 questions mesurées, attendus de la v1, livres z-library compris) : la comparaison avec la ligne 4 est indicative, les documents attendus ne sont pas les mêmes.

**Couverture fragile** : questions 23-24 (talons confortables, un seul document attendu : « woman shoes ») et 35-36 (essentiels de la garde-robe masculine, couverture partielle : Suit, accessories men, Dress Shoes).

## Ensemble (40 questions)

| Étape | Mode | Hit@5 | MRR@5 | Préc.@5 | Titre signalé (sources) | Avec citation | Citation pertinente | « I don't know » injustifié | Refus attendu respecté | Latence méd. (s) |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0. Baseline (rag/try1) | retrieve, question brute | 57.5 % | 44.4 % | 36 % | 40 % | — | — | — | — | 0.63 |
| 0. Baseline (rag/try1) | ask (réécriture LLM) | 65 % | 50.5 % | 42 % | 27.5 % | 15 % | 7.5 % | — | — | 7.74 |
| 1. Traduction FR→EN | retrieve, question traduite | 87.5 % | 69.7 % | 55.5 % | 15 % | — | — | — | — | 0.63 |
| 1. Traduction FR→EN | ask | 87.5 % | 69.7 % | 56.1 % | 15 % | 37.5 % | 32.5 % | 0 % | — | 7.72 |
| 2. Prompt de citation | retrieve, question traduite | 87.5 % | 69.7 % | 55.5 % | 15 % | — | — | — | — | 0.59 |
| 2. Prompt de citation | ask | 87.5 % | 69.7 % | 56.1 % | 15 % | 92.5 % | 72.5 % | 7.5 % | — | 4.43 |
| 3. Corpus v2 (SIMULATION, table non créée) | retrieve, question traduite | 67.5 % | 56.7 % | 42.2 % | 0 % | — | — | — | — | 0.65 |
| 4. Corpus v2 + nouvelles sources | retrieve, question traduite | 92.1 % | 76.8 % | 63.7 % | 0 % | — | — | — | — | 0.48 |
| 4. Corpus v2 + nouvelles sources | ask | 92.1 % | 76.8 % | 60.6 % | 0 % | 97.4 % | 81.6 % | 5.3 % | 100 % | 4.57 |

## Questions en français (20)

| Étape | Mode | Hit@5 | MRR@5 | Préc.@5 | Titre signalé (sources) | Avec citation | Citation pertinente | « I don't know » injustifié | Refus attendu respecté | Latence méd. (s) |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0. Baseline (rag/try1) | retrieve, question brute | 25 % | 16.7 % | 15 % | 65 % | — | — | — | — | 0.65 |
| 0. Baseline (rag/try1) | ask (réécriture LLM) | 50 % | 37.5 % | 28.3 % | 35 % | 15 % | 5 % | — | — | 7.74 |
| 1. Traduction FR→EN | retrieve, question traduite | 85 % | 67.4 % | 54 % | 15 % | — | — | — | — | 0.91 |
| 1. Traduction FR→EN | ask | 85 % | 67.4 % | 54.2 % | 15 % | 35 % | 30 % | 0 % | — | 7.62 |
| 2. Prompt de citation | retrieve, question traduite | 85 % | 67.4 % | 54 % | 15 % | — | — | — | — | 0.73 |
| 2. Prompt de citation | ask | 85 % | 67.4 % | 54.2 % | 15 % | 90 % | 65 % | 10 % | — | 4.66 |
| 3. Corpus v2 (SIMULATION, table non créée) | retrieve, question traduite | 65 % | 57.5 % | 41.3 % | 0 % | — | — | — | — | 0.79 |
| 4. Corpus v2 + nouvelles sources | retrieve, question traduite | 89.5 % | 75 % | 63.2 % | 0 % | — | — | — | — | 0.67 |
| 4. Corpus v2 + nouvelles sources | ask | 89.5 % | 75 % | 59.7 % | 0 % | 94.7 % | 73.7 % | 5.3 % | 100 % | 4.68 |

## Questions en anglais (20)

| Étape | Mode | Hit@5 | MRR@5 | Préc.@5 | Titre signalé (sources) | Avec citation | Citation pertinente | « I don't know » injustifié | Refus attendu respecté | Latence méd. (s) |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0. Baseline (rag/try1) | retrieve, question brute | 90 % | 72.1 % | 57 % | 15 % | — | — | — | — | 0.62 |
| 0. Baseline (rag/try1) | ask (réécriture LLM) | 80 % | 63.5 % | 55.8 % | 20 % | 15 % | 10 % | — | — | 7.9 |
| 1. Traduction FR→EN | retrieve, question traduite | 90 % | 72.1 % | 57 % | 15 % | — | — | — | — | 0.42 |
| 1. Traduction FR→EN | ask | 90 % | 72.1 % | 58 % | 15 % | 40 % | 35 % | 0 % | — | 7.72 |
| 2. Prompt de citation | retrieve, question traduite | 90 % | 72.1 % | 57 % | 15 % | — | — | — | — | 0.33 |
| 2. Prompt de citation | ask | 90 % | 72.1 % | 58 % | 15 % | 95 % | 80 % | 5 % | — | 3.88 |
| 3. Corpus v2 (SIMULATION, table non créée) | retrieve, question traduite | 70 % | 55.8 % | 43 % | 0 % | — | — | — | — | 0.36 |
| 4. Corpus v2 + nouvelles sources | retrieve, question traduite | 94.7 % | 78.5 % | 64.2 % | 0 % | — | — | — | — | 0.29 |
| 4. Corpus v2 + nouvelles sources | ask | 94.7 % | 78.5 % | 61.5 % | 0 % | 100 % | 89.5 % | 5.3 % | 100 % | 4.47 |

## Paires FR / EN (Hit@5 sur le même sujet)

| Étape | Mode | Les deux | Anglais seul | Français seul | Aucune |
|---|---|---:|---:|---:|---:|
| 0. Baseline (rag/try1) | retrieve, question brute | 4 | 14 | 1 | 1 |
| 0. Baseline (rag/try1) | ask (réécriture LLM) | 8 | 8 | 2 | 2 |
| 1. Traduction FR→EN | retrieve, question traduite | 17 | 1 | 0 | 2 |
| 1. Traduction FR→EN | ask | 17 | 1 | 0 | 2 |
| 2. Prompt de citation | retrieve, question traduite | 17 | 1 | 0 | 2 |
| 2. Prompt de citation | ask | 17 | 1 | 0 | 2 |
| 3. Corpus v2 (SIMULATION, table non créée) | retrieve, question traduite | 13 | 1 | 0 | 6 |
| 4. Corpus v2 + nouvelles sources | retrieve, question traduite | 17 | 1 | 0 | 1 |
| 4. Corpus v2 + nouvelles sources | ask | 17 | 1 | 0 | 1 |
