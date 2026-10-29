# Évaluation de l'extraction d'intention (I79)

50 demandes annotées à la main · modèle `qwen2.5:3b` (Ollama 0.40.6, temperature 0) · 2026-10-22T23:54:15

## Comparaison des trois configurations

| Mesure | A. Règles seules | B. LLM seul | C. Système complet |
|---|---|---|---|
| Occasion exacte | 70 % | 76 % | 88 % |
| Saison explicite exacte | 100 % | 96 % | 100 % |
| Feedback exact | 94 % | 92 % | 94 % |
| « Une autre » exact | 96 % | 70 % | 96 % |
| Précision des exclusions | 100 % | 8 % | 100 % |
| Rappel des exclusions | 80 % | 100 % | 80 % |
| Contraintes inventées (exclusions en trop) | 0 | 117 | 0 |
| Demandes entièrement correctes | 29/50 | 4/50 | 39/50 |

Latence du LLM (B et C, un appel par demande, après préchauffage) : médiane 3.27 s, max 3.79 s. Réponses LLM inexploitables : 0. Demandes où le garde-fou a retiré quelque chose : 43.

B n'a pas de champ « feedback » dans son schéma : son score feedback ne mesure que les demandes sans retour.

## Par catégorie (occasion exacte · contraintes inventées · demandes entièrement correctes)

| Catégorie | n | A | B | C |
|---|---|---|---|---|
| simple | 15 | 100 % · 0 · 15/15 | 60 % · 36 · 1/15 | 100 % · 0 · 15/15 |
| paraphrase | 15 | 0 % · 0 · 0/15 | 73 % · 31 · 1/15 | 60 % · 0 · 9/15 |
| contrainte | 8 | 100 % · 0 · 6/8 | 75 % · 10 · 1/8 | 100 % · 0 · 6/8 |
| sans_occasion | 6 | 100 % · 0 · 6/6 | 100 % · 20 · 0/6 | 100 % · 0 · 6/6 |
| retour | 6 | 100 % · 0 · 2/6 | 100 % · 20 · 1/6 | 100 % · 0 · 3/6 |

## Erreurs du système complet (C)

| # | Catégorie | Message | Attendu | Prédit | Champs faux |
|---|---|---|---|---|---|
| 18 | paraphrase | Je retourne à l'amphi demain pour le TD de maths | occasion=university | occasion=casual | occasion |
| 23 | paraphrase | Je reste tranquille à la maison avec des amis dimanche | occasion=casual | occasion=None | occasion |
| 24 | paraphrase | On part pique-niquer au bord du lac | occasion=casual | occasion=None | occasion |
| 27 | paraphrase | J'ai un rendez-vous avec la DRH de l'entreprise | occasion=work | occasion=evening | occasion |
| 28 | paraphrase | Journée de TP au labo de chimie | occasion=university | occasion=work | occasion |
| 29 | paraphrase | I'm meeting my girlfriend's parents for the first time tonight | occasion=evening | occasion=work | occasion |
| 36 | contrainte | Une tenue pour un mariage, évite le blanc | occasion=evening · exclusions=white | occasion=evening | exclusions |
| 38 | contrainte | Soirée chez des amis : je préfère éviter les robes | occasion=evening · exclusions=dress | occasion=evening | exclusions |
| 46 | retour | La 2 me plaît beaucoup | occasion=None · feedback=like:2 | occasion=None | feedback |
| 47 | retour | J'aime bien la première | occasion=None · feedback=like:1 | occasion=None · autre=oui | feedback, wants_another |
| 49 | retour | Pas convaincu par la tenue 2, tu as mieux ? | occasion=None · feedback=dislike:2 · autre=oui | occasion=None | feedback, wants_another |

## Limites

- **50 phrases écrites par nous** : elles ne représentent pas la variété des vraies demandes (fautes, abréviations, messages longs, mélange de langues).
- **Un seul annotateur** : certaines étiquettes sont discutables (par exemple un jury de recrutement classé « work », une remise de diplôme avec cocktail classée « evening ») ; aucun accord inter-annotateurs n'est mesuré.
- **Petit modèle local** (`qwen2.5:3b`, quantifié, CPU/GPU modeste) : les résultats ne préjugent pas d'un modèle plus grand ; la latence dépend de la machine et de sa charge.
- Chaque demande est évaluée **isolément** : la mémoire de conversation (occasion reprise du tour précédent) n'est pas mesurée.
- Les pourcentages par catégorie portent sur 6 à 15 demandes : un écart d'une demande change le score de 7 à 17 points.

## Après corrections

Corrections apportées à `stylist_agent.py` après l'évaluation ci-dessus :
1. négation « éviter » (évite, éviter, évitez + le/la/les/l'/de/des) dans les règles et le garde-fou ;
2. le garde-fou n'accepte plus « aime » seul comme demande d'une autre tenue ;
3. retours reformulés (« me plait », « j'aime bien », « pas convaincu(e) », « bof », ordinaux, « la dernière ») et « tu as mieux » → autre tenue ;
4. mots-clés d'occasion ambigus (rendez-vous, meeting) : s'ils sont seuls, l'occasion du LLM l'emporte.

B (LLM seul, sans règles ni garde-fou) n'est pas concerné par ces corrections : ses chiffres ne changent pas.

### Les 50 phrases (2026-10-23T00:06:30)

**Chiffre optimiste** : les corrections ont été écrites en regardant les erreurs de ces 50 phrases.

| Mesure | A avant | A après | B avant | B après | C avant | C après |
|---|---|---|---|---|---|---|
| Occasion exacte | 70 % | 70 % | 76 % | 76 % | 88 % | 92 % |
| Saison explicite exacte | 100 % | 100 % | 96 % | 96 % | 100 % | 100 % |
| Feedback exact | 94 % | 100 % | 92 % | 92 % | 94 % | 100 % |
| « Une autre » exact | 96 % | 98 % | 70 % | 70 % | 96 % | 100 % |
| Précision des exclusions | 100 % | 100 % | 8 % | 8 % | 100 % | 100 % |
| Rappel des exclusions | 80 % | 100 % | 100 % | 100 % | 80 % | 100 % |
| Contraintes inventées | 0 | 0 | 117 | 117 | 0 | 0 |
| Demandes entièrement correctes | 29/50 | 34/50 | 4/50 | 4/50 | 39/50 | 46/50 |

Erreurs restantes du système complet (C) :

| # | Message | Attendu | Prédit | Champs faux |
|---|---|---|---|---|
| 18 | Je retourne à l'amphi demain pour le TD de maths | occasion=university | occasion=casual | occasion |
| 23 | Je reste tranquille à la maison avec des amis dimanche | occasion=casual | occasion=None | occasion |
| 24 | On part pique-niquer au bord du lac | occasion=casual | occasion=None | occasion |
| 28 | Journée de TP au labo de chimie | occasion=university | occasion=work | occasion |

### Jeu mis de côté : 15 nouvelles demandes (`intent_holdout.jsonl`)

**Chiffre honnête** : ces demandes ont été écrites et annotées à la main, et mesurées « avant », AVANT toute modification du code ; elles n'ont servi à écrire aucune correction. Attention : leur composition (2 « éviter », 3 retours reformulés, 3 mots ambigus) cible volontairement les défauts corrigés, ce qui avantage les corrections ; 15 demandes, c'est peu (une demande = 7 points).

| Mesure | A avant | A après | B avant | B après | C avant | C après |
|---|---|---|---|---|---|---|
| Occasion exacte | 60 % | 60 % | 93 % | 93 % | 87 % | 93 % |
| Saison explicite exacte | 100 % | 100 % | 100 % | 100 % | 100 % | 100 % |
| Feedback exact | 80 % | 100 % | 80 % | 80 % | 80 % | 100 % |
| « Une autre » exact | 87 % | 100 % | 80 % | 80 % | 87 % | 100 % |
| Précision des exclusions | n/a | 100 % | 5 % | 5 % | n/a | 100 % |
| Rappel des exclusions | 0 % | 100 % | 100 % | 100 % | 0 % | 100 % |
| Contraintes inventées | 0 | 0 | 37 | 37 | 0 | 0 |
| Demandes entièrement correctes | 4/15 | 9/15 | 1/15 | 1/15 | 8/15 | 14/15 |

Erreurs restantes du système complet (C) :

| # | Message | Attendu | Prédit | Champs faux |
|---|---|---|---|---|
| 103 | Je file au partiel de droit dans une heure | occasion=university | occasion=casual | occasion |

Latence du LLM après corrections : médiane 3.26 s (50 phrases), 3.25 s (jeu mis de côté) ; les corrections ne touchent que les règles et le garde-fou.
