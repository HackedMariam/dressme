"""Données et doubles de test BO4 partagés, importables par les modules de test."""


# Garde-robe de référence (utilisateur de test 1), au format produit par
# wardrobe_db_adapter.load_user_wardrobe.
REFERENCE_WARDROBE = [
    {
        "id": "1",
        "user_id": 1,
        "article_id": "0399201042",
        "name": "Shaping Skinny H.W",
        "category": "trousers",
        "color": "dark_grey",
        "style": "unknown",
        "image_path": "images/039/0399201042.jpg",
    },
    {
        "id": "2",
        "user_id": 1,
        "article_id": "0552473028",
        "name": "DENISE S.8",
        "category": "shirt",
        "color": "light_blue",
        "style": "unknown",
        "image_path": "images/055/0552473028.jpg",
    },
    {
        "id": "3",
        "user_id": 1,
        "article_id": "0635510002",
        "name": "Huffel puffer jacket",
        "category": "jacket",
        "color": "black",
        "style": "unknown",
        "image_path": "images/063/0635510002.jpg",
    },
    {
        "id": "4",
        "user_id": 1,
        "article_id": "0656677022",
        "name": "Legolas SS",
        "category": "shirt",
        "color": "white",
        "style": "unknown",
        "image_path": "images/065/0656677022.jpg",
    },
    {
        "id": "5",
        "user_id": 1,
        "article_id": "0702784001",
        "name": "American Beauty intarsia",
        "category": "sweater",
        "color": "grey",
        "style": "unknown",
        "image_path": "images/070/0702784001.jpg",
    },
]

# Mêmes vêtements, sous forme de lignes SQL brutes (tuple_row), dans l'ordre
# des colonnes de la requête de load_user_wardrobe (detail_desc réel du catalogue).
REFERENCE_DB_ROWS = [
    (1, 1, "0399201042", "images/039/0399201042.jpg", "Shaping Skinny H.W", "Trousers", "Dark Grey",
     "5-pocket jeans in washed, stretch denim with a high waist, zip fly and button and skinny legs. "
     "Shaping – denim with a stretch function that holds in and shapes the waist, thighs and bum "
     "while keeping the jeans in shape."),
    (2, 1, "0552473028", "images/055/0552473028.jpg", "DENISE S.8", "Shirt", "Light Blue",
     "Straight-cut shirt in a soft viscose weave with a collar, buttons down the front, long sleeves "
     "with narrow, buttoned cuffs, and a rounded hem."),
    (3, 1, "0635510002", "images/063/0635510002.jpg", "Huffel puffer jacket", "Jacket", "Black",
     "Short, padded jacket in woven fabric with a zip and wind flap with press-studs down the front and "
     "a lined hood with a collar and adjustable drawstring. Zipped side pockets, a zipped inner pocket, "
     "long sleeves with inner ribbing at the cuffs, and an elasticated drawstring at the hem. Lined."),
    (4, 1, "0656677022", "images/065/0656677022.jpg", "Legolas SS", "Shirt", "White",
     "Short-sleeved shirt in a patterned viscose weave with a resort collar, French front and "
     "straight-cut hem. Relaxed Fit – a straight fit with good room for movement creating a "
     "comfortable, relaxed silhouette."),
    (5, 1, "0702784001", "images/070/0702784001.jpg", "American Beauty intarsia", "Sweater", "Grey",
     "Jumper knitted in a soft cotton blend with a round neckline, an intarsia text motif on the front, "
     "long raglan sleeves and ribbing around the neckline, cuffs and hem."),
]

# Les 5 robes du catalogue ayant une image (ISSUE-05), mêmes colonnes que
# REFERENCE_DB_ROWS. Elles ne font pas partie de la garde-robe réelle de l'utilisateur 1.
DRESS_DB_ROWS = [
    (6, 1, "0651558012", "images/065/0651558012.jpg", "Panda Dress", "Dress", "Black",
     "Short, sleeveless dress in sturdy jersey with a low-cut back, seam at the waist and flared "
     "skirt. The polyester content of the dress is partly recycled."),
    (7, 1, "0665481011", "images/066/0665481011.jpg", "Swift Dress(1)", "Dress", "Black",
     "Knee-length dress in jersey crêpe with a V-neck and sewn-in wrapover at the top. Seam with "
     "a sewn-in tie belt at the waist, long, slightly wider cuffed sleeves and a flared skirt. "
     "Lined at the front of the bodice."),
    (8, 1, "0697051002", "images/069/0697051002.jpg", "2-PACK Justin dress", "Dress", "Light Grey",
     "Short-sleeved dresses in patterned cotton jersey with a seam at the hips and a flounced skirt."),
    (9, 1, "0713783002", "images/071/0713783002.jpg", "Mara off shoulder dress", "Dress", "Red",
     "Short, off-the-shoulder dress in ribbed jersey with a V-neck front and back, long sleeves, "
     "a seam at the waist and a flared skirt."),
    (10, 1, "0801843006", "images/080/0801843006.jpg", "Elva Dress", "Dress", "Light Pink",
     "A-line dress in airy seersucker with covered elastication at the top and shoulder straps "
     "with decorative ties."),
]

# Noms courts pour des assertions lisibles.
SKINNY = "Shaping Skinny H.W"
DENISE = "DENISE S.8"
HUFFEL = "Huffel puffer jacket"
LEGOLAS = "Legolas SS"
AMERICAN = "American Beauty intarsia"


def outfit_key(result):
    """Tenue -> tuple des noms de vêtements, dans l'ordre top, bottom, outerwear."""
    return tuple(item["name"] for item in result["items"])


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, query, params=None):
        self.connection.executed.append((query, params))

    def fetchall(self):
        return list(self.connection.rows)


class FakeConnection:
    """Connexion psycopg simulée : enregistre les appels, renvoie des lignes préparées."""

    def __init__(self, rows):
        self.rows = rows
        self.executed = []
        self.row_factories = []

    def cursor(self, row_factory=None):
        self.row_factories.append(row_factory)
        return FakeCursor(self)
