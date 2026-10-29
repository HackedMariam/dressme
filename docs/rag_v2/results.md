# RAG v2 : résultats avant / après

**Chiffres provisoires** : le gold set (`gold_set.jsonl`, 40 questions, 20 sujets en FR et en EN) est un brouillon non validé. Une exécution par ligne ; le LLM varie d'un appel à l'autre. `top_k = 5`.

## Ensemble (40 questions)

| Étape | Mode | Hit@5 | MRR@5 | Préc.@5 | Titre signalé (sources) | Avec citation | Citation pertinente | « I don't know » | Latence méd. (s) |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 0. Baseline (rag/try1) | retrieve, question brute | 57.5 % | 44.4 % | 36 % | 40 % | — | — | — | 0.63 |
| 0. Baseline (rag/try1) | ask (réécriture LLM) | 65 % | 50.5 % | 42 % | 27.5 % | 15 % | 7.5 % | — | 7.74 |
| 1. Traduction FR→EN | retrieve, question traduite | 87.5 % | 69.7 % | 55.5 % | 15 % | — | — | — | 0.63 |
| 1. Traduction FR→EN | ask | 87.5 % | 69.7 % | 56.1 % | 15 % | 37.5 % | 32.5 % | 0 % | 7.72 |
| 2. Prompt de citation | retrieve, question traduite | 87.5 % | 69.7 % | 55.5 % | 15 % | — | — | — | 0.59 |
| 2. Prompt de citation | ask | 87.5 % | 69.7 % | 56.1 % | 15 % | 92.5 % | 72.5 % | 7.5 % | 4.43 |

## Questions en français (20)

| Étape | Mode | Hit@5 | MRR@5 | Préc.@5 | Titre signalé (sources) | Avec citation | Citation pertinente | « I don't know » | Latence méd. (s) |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 0. Baseline (rag/try1) | retrieve, question brute | 25 % | 16.7 % | 15 % | 65 % | — | — | — | 0.65 |
| 0. Baseline (rag/try1) | ask (réécriture LLM) | 50 % | 37.5 % | 28.3 % | 35 % | 15 % | 5 % | — | 7.74 |
| 1. Traduction FR→EN | retrieve, question traduite | 85 % | 67.4 % | 54 % | 15 % | — | — | — | 0.91 |
| 1. Traduction FR→EN | ask | 85 % | 67.4 % | 54.2 % | 15 % | 35 % | 30 % | 0 % | 7.62 |
| 2. Prompt de citation | retrieve, question traduite | 85 % | 67.4 % | 54 % | 15 % | — | — | — | 0.73 |
| 2. Prompt de citation | ask | 85 % | 67.4 % | 54.2 % | 15 % | 90 % | 65 % | 10 % | 4.66 |

## Questions en anglais (20)

| Étape | Mode | Hit@5 | MRR@5 | Préc.@5 | Titre signalé (sources) | Avec citation | Citation pertinente | « I don't know » | Latence méd. (s) |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 0. Baseline (rag/try1) | retrieve, question brute | 90 % | 72.1 % | 57 % | 15 % | — | — | — | 0.62 |
| 0. Baseline (rag/try1) | ask (réécriture LLM) | 80 % | 63.5 % | 55.8 % | 20 % | 15 % | 10 % | — | 7.9 |
| 1. Traduction FR→EN | retrieve, question traduite | 90 % | 72.1 % | 57 % | 15 % | — | — | — | 0.42 |
| 1. Traduction FR→EN | ask | 90 % | 72.1 % | 58 % | 15 % | 40 % | 35 % | 0 % | 7.72 |
| 2. Prompt de citation | retrieve, question traduite | 90 % | 72.1 % | 57 % | 15 % | — | — | — | 0.33 |
| 2. Prompt de citation | ask | 90 % | 72.1 % | 58 % | 15 % | 95 % | 80 % | 5 % | 3.88 |

## Paires FR / EN (Hit@5 sur le même sujet)

| Étape | Mode | Les deux | Anglais seul | Français seul | Aucune |
|---|---|---:|---:|---:|---:|
| 0. Baseline (rag/try1) | retrieve, question brute | 4 | 14 | 1 | 1 |
| 0. Baseline (rag/try1) | ask (réécriture LLM) | 8 | 8 | 2 | 2 |
| 1. Traduction FR→EN | retrieve, question traduite | 17 | 1 | 0 | 2 |
| 1. Traduction FR→EN | ask | 17 | 1 | 0 | 2 |
| 2. Prompt de citation | retrieve, question traduite | 17 | 1 | 0 | 2 |
| 2. Prompt de citation | ask | 17 | 1 | 0 | 2 |
