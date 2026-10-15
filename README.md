# Dress Me — AI Style Intelligence

Garde-robe intelligente :
photo → **modèle YOLO11m-seg** (`backend/models/dressme_best.pt` : catégorie + détourage) →
**couleur mesurée sur les pixels** → **GPT-4 (OpenAI)** qui classe l'article par **occasion, style,
couleur**, saison, motif, matière → **stockage par utilisateur** → **garde-robe 3D**.

```
 ┌──────────┐   photo   ┌──────────────────────── backend (FastAPI) ─────────────────────────┐
 │ Frontend │ ────────▶ │ 1. dressme_best.pt (YOLO11m-seg) → catégorie + masque + confiance │
 │  React   │  + JWT    │ 2. masque → fond supprimé (PNG) + couleurs k-means (Lab)           │
 │  + 3D    │ ◀──────── │ 3. GPT-4 (voit la sortie du modèle + le détourage, JSON strict)    │
 │ three.js │   item    │    → occasions, style, couleur + famille, saisons, motif, matière  │
 └──────────┘           │ 4. Supabase Storage + table `items` (filtrés par user_id)          │
                        │ 5. corrections → table `corrections` → précision réelle            │
                        └────────────────────────────────────────────────────────────────────┘
```

## Ce que fait chaque brique

| Étape | Qui | Résultat |
|---|---|---|
| Détection | `dressme_best.pt` (20 classes : top, sweater, jacket, vest, pants, shorts, skirt, dress, glasses, hat, headband, scarf, glove, watch, belt, sock, tights, shoe, bag, umbrella) | catégorie + confiance + masque |
| Détourage | masque de segmentation | PNG transparent (cartes + texture 3D) |
| Couleur mesurée | k-means en espace Lab sur les pixels **du vêtement seulement** | couleur dominante + palette |
| Classification | **GPT-4** (`gpt-4o` par défaut), sortie JSON stricte (structured outputs), puis re-validée côté serveur | occasions, style, couleur (palette fixe) + famille de couleur, saisons, motif, matière, formalité, chaleur, description, conseils, tags, **confiance par champ** |
| Revue | confiance détecteur < 60 %, GPT-4 en désaccord avec le modèle, ou GPT-4 peu sûr de l'occasion/style/saison | badge **Needs review** |
| Corrections | « Save correction » / « Looks right » | table `corrections` → précision réelle par champ (Dashboard) |

Si l'appel GPT-4 échoue (clé absente, timeout, refus), l'article est quand même enregistré avec des
règles par catégorie, et peut être reclassé plus tard (« Re-run AI »).

## Deux modes

| | Local (dev) | Production |
|---|---|---|
| Activé quand | `SUPABASE_SERVICE_ROLE_KEY` vide | `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` remplis |
| Utilisateurs | un seul, pas de connexion | comptes Supabase Auth (email + mot de passe), chacun ne voit que sa garde-robe |
| Données | `backend/local_data/` | Postgres + Storage Supabase |

## Installation

### 1. Clés
```bash
cp .env.example .env                    # OPENAI_API_KEY (+ Supabase en production)
cp frontend/.env.example frontend/.env  # VITE_SUPABASE_ANON_KEY en production
```

### 2. Supabase (production)
1. Dashboard → **SQL Editor** → colle `supabase/schema.sql` → **Run**
   (tables `items`, `corrections`, policies RLS, bucket `wardrobe`). Le script peut être relancé sans risque.
2. **Project Settings → API** : clé `service_role` → `.env` ; clé `anon public` → `frontend/.env`.
3. **Authentication → Providers → Email** activé. **URL Configuration** : ajoute l'URL du frontend.

### 3. Backend
```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate                  # macOS/Linux : source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --port 8000
```
Doc interactive : http://localhost:8000/docs — Tests : `pip install -r requirements-dev.txt && pytest`

### 4. Frontend
```bash
cd frontend
npm install
npm run dev        # http://localhost:5173
npm run build      # build de production dans frontend/dist
```

## API (toutes les routes `/api/items*` et `/api/stats*` exigent `Authorization: Bearer <JWT Supabase>` en production)

| Méthode | Route | Rôle |
|---|---|---|
| POST | `/api/items/analyze?all_items=false` | photo → détection → GPT-4 → enregistrement. `all_items=true` : un article par vêtement détecté |
| GET | `/api/items` | liste de l'utilisateur |
| PATCH | `/api/items/{id}` | `{fields:{...}, confirm:true}` corrige / confirme (valeurs validées), journalise les corrections |
| POST | `/api/items/{id}/reclassify` | relance GPT-4 sur un article existant |
| DELETE | `/api/items/{id}` | supprime l'article et ses images |
| GET | `/api/stats/accuracy` | précision réelle par champ |
| GET | `/api/health`, `/api/taxonomy`, `/api/me` | état, vocabulaires, utilisateur courant |

## Garde-robe 3D (`frontend/src/components/Wardrobe3D.jsx`)
- Armoire three.js, portes animées. **Penderie** : vestes → hauts → robes → bas, chaque section rangée du clair au foncé, avec la vraie photo détourée en texture. **Étagères** : sacs et accessoires. **Bas** : chaussures.
- « Highlight what fits » : filtre par saison, **occasion, style, couleur** — les autres articles s'assombrissent.

## Déploiement
- Backend : n'importe quel hôte Python (VM, Render, Railway, Fly…) avec au moins 2 Go de RAM (torch + modèle). Mets `CORS_ORIGINS` et `PUBLIC_API_URL` sur les vraies URL.
- Frontend : `npm run build` puis héberge `frontend/dist` (Vercel, Netlify, Supabase hosting…), avec `VITE_API_URL` pointant vers le backend.
- Le bucket `wardrobe` est public en lecture (les chemins contiennent des UUID non devinables) pour que la vue 3D charge les textures.

## Conseils
- Photos d'un seul vêtement, à plat ou sur cintre, fond uni : meilleure détection et meilleur détourage. HEIC (iPhone) accepté.
- `LLM_MODEL=gpt-4o` (défaut), `gpt-4.1`, ou `gpt-4o-mini` pour réduire les coûts. `LLM_IMAGE_DETAIL=high` aide sur les motifs fins.
- La table `corrections` est un jeu de données prêt pour ré-entraîner le YOLO sur ses erreurs.
- Licence : Ultralytics/YOLO11 est AGPL-3.0 — à prendre en compte si l'app devient commerciale.
