
import os
import getpass
from contextlib import asynccontextmanager
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import psycopg
from psycopg.rows import dict_row
from fastapi import FastAPI, HTTPException, Query


# ==========================================
# DATABASE CONFIGURATION
# ==========================================

DATABASE_PASSWORD = os.getenv("POSTGRES_PASSWORD")

if not DATABASE_PASSWORD:
    DATABASE_PASSWORD = getpass.getpass(
        "Mot de passe PostgreSQL : "
    )


def get_connection():
    return psycopg.connect(
        host="localhost",
        port=5432,
        dbname="dressme_db",
        user="postgres",
        password=DATABASE_PASSWORD,
        row_factory=dict_row,
    )


# ==========================================
# APPLICATION STARTUP
# ==========================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    with get_connection() as conn:
        conn.execute("SELECT 1")

    print("DressMe connected to PostgreSQL!")
    yield


app = FastAPI(
    title="DressMe API",
    description="AI Fashion Assistant - Backend API",
    version="0.1.0",
    lifespan=lifespan,
)


BASE_DIR = Path(__file__).resolve().parent.parent
IMAGES_DIR = BASE_DIR / "data" / "hm" / "images"

app.mount(
    "/images",
    StaticFiles(directory=str(IMAGES_DIR)),
    name="images"
)

# ==========================================
# HOME
# ==========================================

@app.get("/")
def home():
    return {
        "message": "Welcome to DressMe API"
    }


# ==========================================
# DATABASE HEALTH CHECK
# ==========================================

@app.get("/health")
def health():
    with get_connection() as conn:
        conn.execute("SELECT 1")

    return {
        "status": "ok",
        "database": "connected"
    }


# ==========================================
# GET PRODUCTS
# ==========================================

@app.get("/products")
def get_products(
    limit: int = Query(default=10, ge=1, le=100),
    category: str | None = None,
    only_with_image: bool = True,
):
    conditions = []
    params = []

    if only_with_image:
        conditions.append(
            "image_path IS NOT NULL AND image_path <> ''"
        )

    if category is not None:
        conditions.append("product_group_name = %s")
        params.append(category)

    sql = """
        SELECT
            article_id,
            prod_name,
            product_type_name,
            product_group_name,
            colour_group_name,
            image_path
        FROM catalog_products
    """

    if conditions:
        sql += " WHERE " + " AND ".join(conditions)

    sql += " ORDER BY article_id LIMIT %s"
    params.append(limit)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            products = cur.fetchall()

    return products



# ==========================================
# BO4 - OUTFIT RECOMMENDATIONS
# ==========================================

from wardrobe_db_adapter import load_user_wardrobe, public_item
from outfit_engine import recommend_outfits


@app.get("/users/{user_id}/recommendations")
def get_user_recommendations(
    user_id: int,
    occasion: str = Query(default="university"),
    season: str = Query(default="autumn"),
    top_k: int = Query(default=5, ge=1, le=20),
):
    allowed_occasions = {
        "university", "work", "evening", "casual"
    }

    allowed_seasons = {
        "spring", "summer", "autumn", "winter"
    }

    if occasion not in allowed_occasions:
        raise HTTPException(
            status_code=422,
            detail="Invalid occasion"
        )

    if season not in allowed_seasons:
        raise HTTPException(
            status_code=422,
            detail="Invalid season"
        )

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM app_users WHERE id = %s",
                (user_id,),
            )
            user_exists = cur.fetchone() is not None

        if not user_exists:
            raise HTTPException(
                status_code=404,
                detail="User not found"
            )

        wardrobe = load_user_wardrobe(conn, user_id)

    recommendations = recommend_outfits(
        wardrobe,
        occasion=occasion,
        season=season,
        top_k=top_k,
    )

    return {
        "user_id": user_id,
        "occasion": occasion,
        "season": season,
        "wardrobe_count": len(wardrobe),
        "recommendations_count": len(recommendations),
        # Les attributs internes des vêtements restent hors du JSON public.
        "recommendations": [
            {**r, "items": [public_item(i) for i in r["items"]]}
            for r in recommendations
        ],
    }



# ==========================================
# GET PRODUCT BY ID
# ==========================================

@app.get("/products/{article_id}")
def get_product(article_id: str):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM catalog_products
                WHERE article_id = %s
                """,
                (article_id,),
            )
            product = cur.fetchone()

    if product is None:
        raise HTTPException(
            status_code=404,
            detail="Product not found"
        )

    return product
