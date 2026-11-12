👗 DressMe : un assistant de garde-robe construit autour d'agents IA

Après plusieurs semaines de travail, je suis fière de présenter DressMe, une application qui aide à choisir quoi porter, quoi emporter en voyage et quoi acheter, à partir des vêtements que l'on possède réellement.

Le principe qui guide toute l'architecture : le LLM décide et rédige, le code déterministe vérifie et calcule. Aucun agent ne peut citer une pièce absente de la garde-robe, inventer la météo ou fabriquer une source.

🧠 Une architecture multi-agents
• AI Stylist : agent à appel d'outils (GPT-4o) qui cherche dans la vraie garde-robe, consulte la météo (Open-Meteo) et s'appuie sur des conseils de mode sourcés.
• Outfit Builder : graphe LangGraph à 5 nœuds (météo, garde-robe, connaissances, composition, validation). Les tenues invalides sont renvoyées une fois au modèle avec la liste précise des erreurs.
• Trip Agent (Help Me Pack) : 10 outils validés par Pydantic, deux graphes LangGraph, et une valise choisie par le solveur OR-Tools CP-SAT. En cas de contraintes impossibles, l'agent le dit au lieu de les relâcher en silence.
• Gap Agent (Wardrobe Gaps) : calcule la couverture de la garde-robe par des règles, puis classe les pièces manquantes avec un modèle XGBoost.
• Agent anti-doublon pour le Live scan : détecte si un vêtement scanné existe déjà.

🔎 Vision et connaissances
• Catalogage automatique : détection YOLO, puis GPT-4o en vision avec sortie JSON stricte (catégorie, couleur, matière, saison, occasion), et règles de secours si le modèle est indisponible.
• RAG : 38 livres de mode indexés (OCR Tesseract pour les scans, recherche hybride sur pgvector). Les réponses citent leurs sources.
• Should I buy this ? : un moteur d'achat (XGBoost et règles) mesure la redondance et les tenues possibles. Le LLM ne fait que rédiger le verdict.

🔗 Interopérabilité
Les agents communiquent entre eux par le protocole A2A : le Trip Agent interroge le Gap Agent avec le jeton de l'utilisateur pour repérer ce qui manque avant un voyage. Un orchestrateur LangGraph route les demandes entre stylisme, garde-robe, achat et RAG.

🛠️ Stack
React 19, Vite, Tailwind · FastAPI · LangGraph · OR-Tools · XGBoost · FashionCLIP · YOLO · Supabase (auth, base, stockage, pgvector) · Ollama (Qwen 2.5)

✅ Fiabilité avant tout
Validation des sorties des outils, garde-fous dans les prompts, tests automatisés et repli propre quand un service est indisponible.

Un grand merci à mon équipe pour ce travail collectif :
@Mariem Gharbi @Zied Heshmi @Mohamed Mahmoud @Mariem Ben Abdallah @Nourhene Mraieh

Je serais ravie d'échanger sur l'architecture ou de vous faire une démonstration. 🙌

#IntelligenceArtificielle #AgentsIA #LangGraph #RAG #FastAPI #React #MachineLearning #XGBoost #Mode #Innovation
