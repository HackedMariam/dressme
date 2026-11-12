Nous avons tous un placard plein et « rien à me mettre ». 👗

Point de départ de DressMe, l'application que nous avons construite en équipe.

🎯 L'objectif
Mieux utiliser ce que l'on possède déjà :
• savoir quoi porter aujourd'hui, selon la météo et l'occasion ;
• faire sa valise sans trop emporter ;
• repérer ce qui manque vraiment dans sa garde-robe ;
• éviter d'acheter une pièce de plus qui ressemble à une pièce déjà possédée.

🧠 Comment : des agents IA sur votre vraie garde-robe
Règle : le LLM comprend et rédige, le code vérifie et calcule. Un agent ne peut ni citer un vêtement que vous n'avez pas, ni inventer la météo.

🗄️ Au centre : le Wardrobe Agent (LangGraph)
Les autres agents passent par lui pour lire la garde-robe.
• Recherche par la voix (Web Speech API) ou par le texte : « montre-moi mes vestes chaudes ». Le LLM choisit les filtres, appelle l'outil de recherche, regarde le résultat et recommence si c'est vide ou trop large.
• Comptage, pièces proches, corrections : toujours recherche → proposition → confirmation → écriture. Le LLM n'a aucun outil d'écriture.

🤖 Les agents qui l'utilisent
• AI Stylist : tenue du jour avec la météo (Open-Meteo) et des conseils tirés de 38 livres de mode (RAG, sources citées).
• Outfit Builder : graphe LangGraph qui compose des tenues puis les valide (pièces réelles, cohérence, chaussures, veste).
• Help Me Pack : la valise est calculée par un solveur OR-Tools CP-SAT, pas par le LLM. Si c'est impossible, il le dit.
• Wardrobe Gaps : des règles calculent la couverture, puis un modèle XGBoost classe ce qu'il faut acheter en premier (déficit, usage, saison, similarité FashionCLIP).
• Should I buy this ? : un moteur XGBoost + règles évalue la redondance avant l'achat. L'IA ne fait qu'expliquer le verdict.
• Live scan : YOLO + GPT-4o vision reconnaissent le vêtement, et l'agent anti-doublon vérifie, via le Wardrobe Agent, qu'il n'est pas déjà possédé.
• Avatar 3D et essayage virtuel : une photo en pied devient un modèle 3D (Hunyuan3D, three.js). Un modèle de try-on (FASHN) l'habille avec une pièce de la garde-robe ou d'une boutique. Consentement explicite, suppression des données à la demande.

🔗 Tous les agents parlent le protocole A2A (JSON-RPC sur HTTP) : Stylist, Wardrobe, Outfit Builder, Similar, Trip et Gap publient une Agent Card et s'appellent entre eux. Ex. : Help Me Pack lit la garde-robe via le Wardrobe Agent, puis interroge le Gap Agent. Un orchestrateur route les demandes.

⚠️ Le classeur XGBoost est entraîné sur des données synthétiques : son score n'est pas une probabilité, et l'application le dit.

🛠️ React 19 · three.js · FastAPI · LangGraph · OR-Tools · XGBoost · FashionCLIP · YOLO · GPT-4o · fal.ai · Supabase

Démo en 2 minutes dans la vidéo. 🎥

Merci à l'équipe : @Mariem Gharbi @Zied Heshmi @Mohamed Mahmoud @Mariem Ben Abdallah @Nourhene Mraieh

#IntelligenceArtificielle #AgentsIA #LangGraph #A2A #XGBoost #RAG #LLM #MachineLearning #ORTools #FastAPI #React #ComputerVision
