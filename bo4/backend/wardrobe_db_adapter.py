
import os
import json
import getpass
import psycopg

from garment_attributes import extract_attributes
from outfit_engine import normalize, garment_role, recommend_outfits


# Champs des vêtements exposés par l'API (contrat JSON public). Les attributs
# internes (warmth, sleeve_length, provenance...) ne doivent pas en sortir.
PUBLIC_ITEM_FIELDS = (
    "id",
    "user_id",
    "article_id",
    "name",
    "category",
    "color",
    "style",
    "image_path",
)


CATEGORY_MAPPING = {
    "t_shirt": "tshirt",
    "vest_top": "top",
    "trousers": "trousers",
    "pants": "trousers",
    "jeans": "jeans",
    "sweater": "sweater",
    "shirt": "shirt",
    "blouse": "blouse",
    "top": "top",
    "shorts": "shorts",
    "skirt": "skirt",
    "hoodie": "hoodie",
    "jacket": "jacket",
    "coat": "coat",
    "cardigan": "cardigan",
    "blazer": "blazer",
}

COLOR_MAPPING = {
    "dark_blue": "navy_blue",
    "light_blue": "light_blue",
    "blue": "blue",
    "black": "black",
    "white": "white",
    "beige": "beige",
    "grey": "grey",
    "gray": "grey",
    "green": "green",
    "red": "red",
    "brown": "brown",
    "pink": "pink",
    "yellow": "yellow",
    "purple": "purple",
}


def normalize_category(raw):
    value = normalize(raw)
    return CATEGORY_MAPPING.get(value, value)


def normalize_color(raw):
    value = normalize(raw)

    # Exemple H&M : "Light Blue", "Dark Blue", etc.
    for key, mapped in COLOR_MAPPING.items():
        if value == key or value.startswith(key + "_"):
            return mapped

    return value


def load_user_wardrobe(conn, user_id):
    query = """
        SELECT
            w.id,
            w.user_id,
            w.article_id,
            COALESCE(w.image_path, p.image_path) AS image_path,
            p.prod_name,
            p.product_type_name,
            p.colour_group_name,
            p.detail_desc
        FROM wardrobe_items w
        LEFT JOIN catalog_products p
            ON w.article_id = p.article_id
        WHERE w.user_id = %s
          AND w.available = TRUE
        ORDER BY w.id
    """

    wardrobe = []

    with conn.cursor(row_factory=psycopg.rows.tuple_row) as cur:
        cur.execute(query, (user_id,))
        rows = cur.fetchall()

    for row in rows:
        (
            item_id,
            owner_id,
            article_id,
            image_path,
            prod_name,
            product_type,
            color_name,
            detail_desc,
        ) = row

        category = normalize_category(product_type)
        color = normalize_color(color_name)
        attributes = extract_attributes(prod_name, detail_desc, category)

        item = {
            "id": str(item_id),
            "user_id": owner_id,
            "article_id": article_id,
            "name": prod_name,
            "category": category,
            "color": color,
            "style": "unknown",
            "image_path": image_path,
            # Attributs internes (hors contrat public, voir public_item).
            # "unknown" laisse le moteur estimer d'après la catégorie.
            "warmth": attributes.warmth,
            "warmth_source": attributes.warmth_source,
            "warmth_evidence": list(attributes.warmth_evidence),
            "text_warmth_levels": list(attributes.text_warmth_levels),
            "sleeve_length": attributes.sleeve_length,
            "sleeve_source": attributes.sleeve_source,
        }

        if garment_role(item) is not None:
            wardrobe.append(item)

    return wardrobe


def public_item(item):
    """Projection d'un vêtement sur le contrat JSON public de l'API."""
    return {field: item.get(field) for field in PUBLIC_ITEM_FIELDS}


def main():
    password = os.environ.get("DRESSME_DB_PASSWORD")

    if not password:
        password = getpass.getpass(
            "Mot de passe PostgreSQL : "
        )

    conn = psycopg.connect(
        host="localhost",
        port=5432,
        dbname="dressme_db",
        user="postgres",
        password=password,
        connect_timeout=10,
    )

    try:
        user_id = int(input("ID utilisateur : "))

        wardrobe = load_user_wardrobe(conn, user_id)

        print("\n=== GARDE-ROBE POSTGRESQL ===")
        print(json.dumps(
            wardrobe,
            indent=2,
            ensure_ascii=False
        ))

        results = recommend_outfits(
            wardrobe,
            occasion="university",
            season="autumn",
            top_k=5
        )

        print("\n=== RECOMMANDATIONS BO4 ===")
        print(json.dumps(
            results,
            indent=2,
            ensure_ascii=False
        ))

        if not wardrobe:
            print(
                "\nAucun vêtement compatible trouvé "
                "pour cet utilisateur."
            )

    finally:
        conn.close()


if __name__ == "__main__":
    main()
