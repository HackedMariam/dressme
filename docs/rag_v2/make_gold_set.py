"""RAG v2, phase 1 : gold set de 40 questions (20 sujets, chacun en français et en anglais).

`expected` : sous-chaînes (insensibles à la casse) du titre OU du nom de fichier des documents jugés pertinents,
choisis d'après l'inventaire du corpus v2 (documents conservés + nouvelles sources Wikipedia / Wikivoyage).
`expected` vide : aucune source ne traite le sujet (tendances, documents retirés) ; réponse attendue « I don't know »,
question exclue des mesures de recherche (Hit@5, MRR, précision). Ce sont des PROPOSITIONS : statut « draft » tant qu'un
humain ne les a pas validées ; les scores calculés avec elles sont provisoires.
Écrit gold_set.jsonl à côté de ce script.
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

# (id, thème, question FR, question EN, documents attendus)
TOPICS = [
    ("capsule-30", "garde-robe / capsule",
     "Comment construire une garde-robe capsule d'environ 30 pièces ?",
     "How do I build a capsule wardrobe of about 30 pieces?",
     ["capsule wardrobe", "wardrobe capsules"]),
    ("capsule-winter", "garde-robe / capsule",
     "Que mettre dans une garde-robe capsule d'hiver pour une femme ?",
     "What should a women's winter capsule wardrobe include?",
     ["wardrobe capsules", "capsule wardrobe"]),
    ("pack-week", "voyage / valise",
     "Comment faire une valise légère pour une semaine de voyage ?",
     "How do I pack a light suitcase for a one-week trip?",
     ["packing list"]),
    ("pack-business-trip", "voyage / valise",
     "Quels vêtements emporter pour un voyage d'affaires de trois jours ?",
     "Which clothes should I take on a three-day business trip?",
     ["packing list", "business casual"]),
    ("interview-women", "travail / dress code",
     "Comment s'habiller pour un entretien d'embauche quand on est une femme ?",
     "How should a woman dress for a job interview?",
     ["career closet", "dressing for success", "dress to impress", "well-dressed lady", "business casual"]),
    ("business-casual", "travail / dress code",
     "Que signifie le dress code business casual ?",
     "What does a business casual dress code mean?",
     ["business casual", "dress_code", "dress code", "dressing for success", "career closet"]),
    ("black-tie", "travail / dress code",
     "Que porter pour une soirée avec un dress code black tie ?",
     "What should I wear to a black tie event?",
     ["dress_code", "dress code", "well-dressed lady", "wiki/suit"]),
    ("navy-colors", "couleurs",
     "Quelles couleurs associer au bleu marine dans une tenue ?",
     "Which colours go well with navy blue in an outfit?",
     ["color harmony", "slide 1", "color scheme", "complementary colors"]),
    ("analogous", "couleurs",
     "Qu'est-ce qu'une harmonie de couleurs analogues et comment l'utiliser dans une tenue ?",
     "What is an analogous colour scheme and how do I use it in an outfit?",
     ["color harmony", "slide 1", "color scheme"]),
    ("wool-care", "textiles",
     "Comment laver et entretenir un pull en laine ?",
     "How do I wash and care for a wool sweater?",
     ["wool", "laundry symbol"]),
    ("linen-cotton", "textiles",
     "Quelle différence entre le lin et le coton pour l'été ?",
     "What is the difference between linen and cotton for summer clothes?",
     ["linen", "cotton"]),
    ("heels-fit", "chaussures",
     "Comment choisir des talons confortables qui tiennent bien le pied ?",
     "How do I choose comfortable high heels that fit well?",
     ["woman shoes"]),
    ("leather-shoes", "chaussures",
     "Comment entretenir des chaussures en cuir ?",
     "How do I take care of leather shoes?",
     ["dress shoes"]),
    ("scarf", "accessoires",
     "Comment nouer et porter un foulard ?",
     "How do I tie and wear a scarf?",
     ["scarves", "art of fashion accessories", "accessories"]),
    ("jewelry-neckline", "accessoires",
     "Quels bijoux choisir selon le décolleté ?",
     "Which jewellery should I choose for each neckline?",
     ["jewelry", "art of fashion accessories"]),
    ("body-shape", "conseils femmes",
     "Comment choisir des vêtements selon sa silhouette ?",
     "How do I choose clothes for my body shape?",
     ["clothing for women", "well-dressed lady", "design your own clothes", "female body shape"]),
    ("sustainable", "durabilité",
     "Comment rendre sa garde-robe plus durable et circulaire ?",
     "How can I make my wardrobe more sustainable and circular?",
     ["sustainable-fashion", "sustainable fashion"]),
    ("men-essentials", "conseils hommes",
     "Quels sont les vêtements essentiels de la garde-robe masculine ?",
     "What are the essential garments in a man's wardrobe?",
     ["wiki/suit", "accessories men", "dress shoes"]),
    ("budget", "garde-robe / capsule",
     "Comment bien s'habiller avec un petit budget ?",
     "How can I dress well on a small budget?",
     ["capsule wardrobe", "wardrobe capsules"]),
    ("trends", "théorie / tendances",
     "Comment les tendances de mode sont-elles prévues ?",
     "How are fashion trends forecast?",
     []),
]


def main() -> None:
    rows = []
    for topic_id, theme, fr, en, expected in TOPICS:
        for lang, question in (("fr", fr), ("en", en)):
            rows.append({"id": f"{topic_id}-{lang}", "pair": topic_id, "lang": lang, "theme": theme,
                         "question": question, "expected": expected, "answerable": bool(expected),
                         "status": "draft"})
    assert len(rows) == 40 and len({r["id"] for r in rows}) == 40
    (HERE / "gold_set.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
                                         encoding="utf-8")
    print("gold_set.jsonl : 40 questions (20 FR, 20 EN), statut draft")


if __name__ == "__main__":
    main()
