# Évaluation des agents DressMe

> **Contexte : BO1 relancé avec le LLM local qwen2.5:3b (Ollama) à la place de GPT-4o**, en variables de processus. Les agents de BO1 sont conçus pour GPT-4o : un petit modèle local rend leurs échecs plus nombreux que prévu. Compte de test (15 pièces + 3 paires de chaussures ajoutées le temps de l'évaluation). Services : BO1, Stylist BO4, orchestrateur 8070, Purchase, RAG démarrés ; **Trip (8020) et Gap BO3 (8001) non démarrés** (pas d'environnement Python avec `ortools` ni `xgboost`) : leurs cas mesurent donc la robustesse (échec propre), pas la qualité. L'orchestrateur 8070 est celui de `main`, où la route RAG est encore désactivée dans `services.yaml`. Juge : qwen2.5:3b, température 0 (petit juge, bruité : à lire comme un signal, pas comme une vérité).

Généré le 2026-11-10T16:15:45.

**Global : 27.0 % de réussite** (20 PASS, 17 WARN, 37 FAIL sur 74 pas de test).

> FAIL = un contrôle du code échoue (le juge ne peut pas l'effacer) ; WARN = code OK mais note du juge < 3 ; taux de réussite = PASS / pas de test

## Score par agent

| Agent | Pas | Réussite | contract | grounding | rules | citations | routing | robustness | performance | Latence méd. (s) | Juge pert./util. |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Stylist BO4 (`bo4`) | 6 | 16.7 % | 100.0 % | 100.0 % | 52.0 % | — | — | 100.0 % | 100.0 % | 1.72 | 2 / 2 (n=1) |
| Gap Agent (BO3) (`gap`) | 5 | 20.0 % | 60.0 % | — | — | — | — | 100.0 % | 100.0 % | — | — |
| Orchestrateur (8070) + RAG (`orchestrator`) | 9 | 33.3 % | 90.5 % | — | 0.0 % | — | 100.0 % | 100.0 % | 100.0 % | 1.24 | 3.4 / 2 (n=5) |
| Orchestrateur BO1 (`orchestrator_bo1`) | 9 | 44.4 % | 95.5 % | — | 0.0 % | — | 85.7 % | 100.0 % | 100.0 % | 3.34 | 3 / 1.67 (n=3) |
| Outfit Builder (`outfit`) | 6 | 16.7 % | 95.2 % | 100.0 % | 81.2 % | — | — | 100.0 % | 100.0 % | 23.89 | 2 / 1.5 (n=2) |
| Purchase Redundancy (via l'orchestrateur) (`purchase`) | 5 | 20.0 % | 100.0 % | — | — | — | 100.0 % | 100.0 % | 100.0 % | 1.09 | 2.5 / 1.25 (n=4) |
| RAG BO5 (livres de mode) (`rag`) | 7 | 14.3 % | 50.0 % | — | 0.0 % | — | — | 60.0 % | 100.0 % | 58.27 | — |
| Similar Agent (`similar`) | 5 | 40.0 % | 100.0 % | 100.0 % | — | — | — | 100.0 % | 80.0 % | 11.42 | 3 / 2.33 (n=3) |
| AI Stylist (`stylist`) | 7 | 28.6 % | 100.0 % | — | 45.5 % | — | — | 100.0 % | 100.0 % | 2.57 | 5 / 5 (n=1) |
| Trip Agent (`trip`) | 6 | 16.7 % | 66.7 % | — | 0.0 % | — | — | 100.0 % | 100.0 % | — | — |
| Wardrobe Agent (`wardrobe`) | 9 | 33.3 % | 92.9 % | 100.0 % | 57.1 % | — | — | 100.0 % | 100.0 % | 2.25 | 3.8 / 2.2 (n=5) |

## Échecs et avertissements

- **bo4 / bo4-interview-fr#1** [rules] tenue 1 complète : pas de chaussures
- **bo4 / bo4-interview-fr#1** [rules] tenue 2 complète : pas de chaussures
- **bo4 / bo4-interview-fr#1** [rules] tenue 3 complète : pas de chaussures
- **bo4 / bo4-business-meeting-en#1** [rules] tenue 1 complète : pas de chaussures
- **bo4 / bo4-business-meeting-en#1** [rules] tenue 2 complète : pas de chaussures
- **bo4 / bo4-business-meeting-en#1** [rules] tenue 3 complète : pas de chaussures
- **bo4 / bo4-wedding-black-tie-fr#1** [judge] pertinence / utilité < 3 : Answer provides suggestions but does not directly address the user's question about what to wear for a black tie wedding.
- **bo4 / bo4-rain-office-fr#1** [rules] tenue 1 complète : pas de chaussures
- **bo4 / bo4-rain-office-fr#1** [rules] tenue 2 complète : pas de chaussures
- **bo4 / bo4-rain-office-fr#1** [rules] tenue 3 complète : pas de chaussures
- **bo4 / bo4-casual-weekend-en#1** [rules] tenue 1 complète : pas de chaussures
- **bo4 / bo4-casual-weekend-en#1** [rules] tenue 2 complète : pas de chaussures
- **bo4 / bo4-casual-weekend-en#1** [rules] tenue 3 complète : pas de chaussures
- **gap / gap-winter-work-fr#1** [contract] état attendu : état « failed », attendu « completed »
- **gap / gap-winter-work-en#1** [contract] état attendu : état « failed », attendu « completed »
- **gap / gap-summer-holiday-en#1** [contract] état attendu : état « failed », attendu « completed »
- **gap / gap-weekend-fr#1** [contract] état attendu : état « failed », attendu « completed »
- **orchestrator / orch-route-wardrobe-fr#1** [judge] pertinence / utilité < 3 : The answer provides the total number of items in the wardrobe but does not specifically address the number of tops.
- **orchestrator / orch-route-purchase-fr#1** [judge] pertinence / utilité < 3 : The answer does not directly address whether the user should purchase the black blazer or not, instead discussing the redundancy of owning a black blazer in their wardrobe.
- **orchestrator / orch-route-knowledge-wool-fr#1** [contract] état attendu : état « failed », attendu « completed »
- **orchestrator / orch-route-knowledge-wool-fr#1** [rules] has_citations : l'agent a échoué : règle non vérifiable
- **orchestrator / orch-wedding-black-tie-fr#1** [judge] pertinence / utilité < 3 : Answer is partially relevant and somewhat useful, but lacks concrete and complete suggestions based on the user's initial question.
- **orchestrator / orch-trends-refusal-fr#1** [rules] refus (« I don't know ») : l'agent répond au lieu de refuser une question sans source
- **orchestrator / orch-knowledge-en#1** [contract] état attendu : état « failed », attendu « completed »
- **orchestrator / orch-knowledge-en#1** [rules] has_citations : l'agent a échoué : règle non vérifiable
- **orchestrator_bo1 / obo1-route-wardrobe-fr#1** [judge] pertinence / utilité < 3 : Answer does not directly show jupes but suggests alternatives instead
- **orchestrator_bo1 / obo1-route-outfit-en#1** [judge] pertinence / utilité < 3 : The assistant's response is irrelevant and useless as it does not provide any information or suggestions for outfits.
- **orchestrator_bo1 / obo1-route-redirect-en#1** [routing] route attendue : route « gap », attendue « redirect »
- **orchestrator_bo1 / obo1-small-talk-clarify-fr#1** [contract] état attendu : état « completed », attendu « input-required »
- **orchestrator_bo1 / obo1-trends-refusal-fr#1** [rules] refus (« I don't know ») : l'agent répond au lieu de refuser une question sans source
- **outfit / outfit-work-winter-fr#1** [contract] champ « weather » : champ obligatoire « weather » absent
- **outfit / outfit-work-winter-fr#1** [rules] tenue complète : aucune tenue dans la réponse
- **outfit / outfit-everyday-autumn-en#1** [rules] tenue complète : aucune tenue dans la réponse
- **outfit / outfit-business-spring-fr#1** [judge] pertinence / utilité < 3 : Answer provides multiple outfit suggestions but does not directly address the request for business attire for spring.
- **outfit / outfit-wedding-summer-en#1** [judge] pertinence / utilité < 3 : The assistant provided casual outfit suggestions instead of formal ones, which is off-topic.
- **outfit / outfit-party-winter-text-only#1** [rules] tenue complète : aucune tenue dans la réponse
- **purchase / purchase-blazer-fr#1** [judge] pertinence / utilité < 3 : The answer does not directly address whether to purchase a black blazer or provide useful advice on how to use it.
- **purchase / purchase-blazer-en#1** [judge] pertinence / utilité < 3 : The answer is off-topic and useless as it does not provide a clear buy or don't buy opinion for the black blazer.
- **purchase / purchase-duplicate-skirt-fr#1** [judge] pertinence / utilité < 3 : The answer addresses the user's question about whether to buy a black pleated midi skirt, but it does so in a confusing and unrelated manner, focusing on wardrobe duplication instead of the skirt's value.
- **purchase / purchase-sweater-en#1** [judge] pertinence / utilité < 3 : The answer is partly relevant but does not provide useful advice.
- **rag / rag-wash-wool-en#1** [contract] état attendu : état « failed », attendu « completed »
- **rag / rag-wash-wool-en#1** [contract] champ « sources » : champ obligatoire « sources » absent
- **rag / rag-wash-wool-en#1** [robustness] aucune erreur HTTP 5xx : HTTP 500
- **rag / rag-wash-wool-en#1** [rules] has_citations : l'agent a échoué : règle non vérifiable
- **rag / rag-wash-wool-fr#1** [contract] état attendu : état « failed », attendu « completed »
- **rag / rag-wash-wool-fr#1** [contract] champ « sources » : champ obligatoire « sources » absent
- **rag / rag-wash-wool-fr#1** [robustness] aucune erreur HTTP 5xx : HTTP 500
- **rag / rag-wash-wool-fr#1** [rules] has_citations : l'agent a échoué : règle non vérifiable
- **rag / rag-black-tie-en#1** [contract] état attendu : état « failed », attendu « completed »
- **rag / rag-black-tie-en#1** [robustness] aucune erreur HTTP 5xx : HTTP 500
- **rag / rag-black-tie-en#1** [rules] has_citations : l'agent a échoué : règle non vérifiable
- **rag / rag-colours-navy-en#1** [contract] état attendu : état « failed », attendu « completed »
- **rag / rag-colours-navy-en#1** [robustness] aucune erreur HTTP 5xx : HTTP 500
- **rag / rag-colours-navy-en#1** [rules] has_citations : l'agent a échoué : règle non vérifiable
- **rag / rag-trends-refusal-en#1** [contract] état attendu : état « failed », attendu « completed »
- **rag / rag-trends-refusal-en#1** [robustness] aucune erreur HTTP 5xx : HTTP 500
- **rag / rag-trends-refusal-en#1** [rules] refus (« I don't know ») : l'agent répond au lieu de refuser une question sans source
- **rag / rag-trends-refusal-fr#1** [contract] état attendu : état « failed », attendu « completed »
- **rag / rag-trends-refusal-fr#1** [robustness] aucune erreur HTTP 5xx : HTTP 500
- **rag / rag-trends-refusal-fr#1** [rules] refus (« I don't know ») : l'agent répond au lieu de refuser une question sans source
- **similar / similar-missing-jacket-en#1** [judge] pertinence / utilité < 3 : The answer is partly relevant but does not provide actionable information.
- **similar / similar-full-look-fr#1** [performance] latence ≤ 15 s : 20.4 s
- **similar / similar-no-pieces-input-required#1** [judge] pertinence / utilité < 3 : The assistant's answer is not relevant or useful as it does not provide a clear action or information on how to send pieces.
- **stylist / stylist-interview-fr#1** [rules] pièces trouvées : 0 pièce(s) trouvée(s), 2 attendue(s)
- **stylist / stylist-interview-fr#1** [rules] tenue complète : aucune tenue dans la réponse
- **stylist / stylist-interview-en#1** [rules] tenue complète : aucune tenue dans la réponse
- **stylist / stylist-rain-fr#1** [rules] tenue complète : aucune tenue dans la réponse
- **stylist / stylist-search-black-skirt-en#1** [rules] pièces trouvées : 0 pièce(s) trouvée(s), 1 attendue(s)
- **stylist / stylist-trends-refusal-fr#1** [rules] refus (« I don't know ») : l'agent répond au lieu de refuser une question sans source
- **trip / trip-paris-business-fr#1** [contract] état attendu : état « failed », attendu « completed ou input-required »
- **trip / trip-beach-en#1** [contract] état attendu : état « failed », attendu « completed ou input-required »
- **trip / trip-vague-fr#1** [contract] état attendu : état « failed », attendu « input-required »
- **trip / trip-missing-destination-en#1** [contract] état attendu : état « failed », attendu « input-required »
- **trip / trip-infeasible-constraint-en#1** [rules] trip_constraints : l'agent a échoué : règle non vérifiable
- **wardrobe / wardrobe-search-skirts-fr#1** [judge] pertinence / utilité < 3 : Answer lists different types of skirts instead of the user's jupes.
- **wardrobe / wardrobe-list-structured#1** [judge] pertinence / utilité < 3 : The answer only provides a vague count of pieces without context or actionable information.
- **wardrobe / wardrobe-correct-color-with-confirmation-fr#1** [contract] état attendu : état « completed », attendu « input-required »
- **wardrobe / wardrobe-correct-color-with-confirmation-fr#1** [rules] aucune modification sans confirmation : état « completed », 0 pièce(s) modifiée(s) avant toute confirmation
- **wardrobe / wardrobe-correct-color-with-confirmation-fr#2** [rules] modification appliquée après confirmation : aucune modification après le « oui »
- **wardrobe / wardrobe-correct-then-refuse-en#1** [contract] état attendu : état « completed », attendu « input-required »
- **wardrobe / wardrobe-correct-then-refuse-en#1** [rules] aucune modification sans confirmation : état « completed », 0 pièce(s) modifiée(s) avant toute confirmation
- **wardrobe / wardrobe-correct-then-refuse-en#2** [judge] pertinence / utilité < 3 : The assistant's response does not address the user's request and is not useful for the user.
