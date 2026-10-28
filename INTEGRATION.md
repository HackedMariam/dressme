# Intégration DressMe (branche `integration`)

Branche créée le 28/10/2026 depuis `main` (`16d4238`) par Nourhene. **Ne pas pousser directement sur `main`** : on
intègre ici, branche par branche, puis une PR `integration` → `main` quand tout démarre.

**Nourhene est indisponible demain matin (forum).** Détails des conflits, des services et des endpoints :
rapport de simulation `docs/integration_dryrun.md` (dépôt local de Nourhene, à demander).

## Déjà fusionné

| Branche | Résultat |
|---|---|
| `wardrobe`, `user`, `Purchase-Redundancy` | déjà dans `main` (vérifié : ancêtres de `main`) |
| `recommendation/stylist-agent` (BO4) | fusion sans conflit ; tout est sous `bo4/` ; 289 tests Stylist et 301 tests BO4 réussis |
| `shoppingAssistant` | conflits de `.env.example`, `.gitignore` et `README.md` résolus **en gardant les deux côtés** (lignes ajoutées seulement) |

Vérifié après ces fusions : BO1 démarre (`GET /api/health` → 200 en mode local, sans `.env`) et aucun fichier de
`backend/` (BO1), de `frontend/` ni de `purchase-redundancy-ai/` n'a changé.

## Plan des ports proposé

| Service | Port |
|---|---|
| BO1 Garde-robe (`backend/app`) | 8000 |
| Avatar | 8001 |
| BO5 RAG | 8010 |
| HelpMePack | 8020 |
| BO3 Manques de la garde-robe | 8030 |
| Purchase Redundancy | 8040 |
| BO4 Stylist | 8061 |
| Front DressMe (`DressMe UI Blueprint`) | 5173 |

Aujourd'hui, BO1, BO5, HelpMePack, BO3 et Purchase Redundancy démarrent tous sur 8000 par défaut ; le front démarre
sur 8443 (`PORT`) et l'ancien `frontend/` sur 5173.

## Décisions d'équipe à prendre

1. **Ports et proxy** : le plan ci-dessus, et un proxy Vite **par préfixe** (`/api/items` → BO1, `/api/trips` →
   HelpMePack, `/api/bo3` → BO3, `/api/avatar` et `/api/body` → Avatar, `/ask` → BO5) au lieu d'un seul backend.
2. **Un dossier par service** : `backend/` reste à BO1 ; Avatar, HelpMePack et BO3 dans leurs propres dossiers.
3. **Page Stylist du front** : celle de `main`, le chat BO5 de `rag/try1`, ou deux pages distinctes.
4. **`helpmepack/prototype`** : remplacée par `helpmepack/try1`, à ne pas fusionner.
5. **Fichiers lourds** : les 38 PDF de `rag/try1` (460 Mo, dont 19 « z-library ») hors du dépôt ; Git LFS pour
   l'avatar ; ne pas recopier `dressme_best.pt`.
6. **Configuration** : un `.env` par service, pas de `.env` racine commun (`LLM_MODEL` n'a pas le même sens partout) ;
   un seul nom pour la clé service_role (`SUPABASE_SERVICE_ROLE_KEY`).
7. **Assistant d'achat** : l'exposer en API HTTP s'il doit apparaître dans le front ; le situer par rapport à
   Purchase Redundancy.
8. **Table de garde-robe** : `items` (BO1, BO3, BO4) ou `wardrobe_items` (migrations de `rag/try1`).

## Ce qui reste, par personne

**Mariam**

- `avatar/try1` : **pas encore fusionnée**. Elle modifie le code de BO1 (`backend/app/main.py`, `config.py`,
  `storage.py`, nouveau `item_mesh.py`, `requirements.txt`) et des fichiers de `user` (`App.tsx`, `package.json`,
  `database.types.ts`). À valider avec Arij (BO1) avant la fusion. Déplacer aussi `backend/main.py` (service avatar)
  dans son propre dossier (ex. `avatar_backend/`) et le passer sur le port 8001.
- `rag/try1` : à fusionner **sans les PDF** du corpus ; port 8010 ; résoudre `App.tsx` (page Stylist, décision 3),
  `.env.example`, `README.md`, `vite-env.d.ts`, `supabase/.gitignore`.
- `helpmepack/try1` : mettre son `backend/main.py` et `packing_backend/` dans leur propre dossier (ex.
  `helpmepack_backend/`), port 8020 ; résoudre `App.tsx`, `.env.example`, `README.md`, `package.json`.

**Mouhamed**

- `wardrobe-gaps` : résoudre `DressMe UI Blueprint/src/App.tsx` (import, carte du tableau de bord, page
  `wardrobe-gaps`) et `DressMe UI Blueprint/vite.config.ts` (proxy) ; sortir le backend BO3 de
  `DressMe UI Blueprint/backend` ; port 8030.

**Ensuite (équipe)**

- Proxy du front par préfixe (décision 1) et front sur 5173.
- Script de lancement de tous les services (un venv par service : les versions d'`openai`, de `supabase` et de
  `torch` sont incompatibles entre parties).

## Réglages Git sous Windows

- `git config core.longpaths true` (noms de fichiers trop longs dans `rag/try1`).
- `git lfs install` (fichiers MediaPipe de l'avatar).
