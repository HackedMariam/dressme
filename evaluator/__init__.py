"""Evaluator Agent : évalue les autres agents de DressMe par leurs endpoints et contrats existants.

Ordre : contrôles du CODE d'abord (contrat, ancrage, règles métier, citations, routage, robustesse, performance),
puis un LLM-juge (Ollama qwen2.5:3b, température 0) pour la seule pertinence et utilité. Le juge ne contredit jamais
un échec détecté par le code. Aucun code d'un autre agent n'est modifié ni importé.
"""
