"""Démonstration autonome de BO4 (recommandation de tenues), sans base de données.

Utilise uniquement les fonctions publiques du moteur (outfit_engine.py), sans
rien modifier : les scores et explications affichés sont ceux du moteur.
Score global = 0,30 couleur + 0,20 style + 0,30 occasion + 0,20 saison
(score heuristique sur 100, pas une probabilité).

Usage (depuis backend/) :
    .\\.venv\\Scripts\\python.exe -X utf8 demo_bo4.py
    .\\.venv\\Scripts\\python.exe -X utf8 demo_bo4.py --season winter --occasion work
"""

import argparse

from outfit_engine import OCCASION_STYLES, SEASONS, garment_role, recommend_outfits

# Les 5 vêtements d'exemple déjà utilisés par outfit_engine.main().
WARDROBE = [
    {"id": "1", "category": "shirt", "color": "light_blue", "style": "formal"},
    {"id": "2", "category": "trousers", "color": "beige", "style": "formal"},
    {"id": "3", "category": "blazer", "color": "navy_blue", "style": "formal"},
    {"id": "4", "category": "jeans", "color": "black", "style": "casual"},
    {"id": "5", "category": "tshirt", "color": "white", "style": "casual"},
]
ROLE_FR = {"top": "haut", "bottom": "bas", "outerwear": "veste", "dress": "robe"}


def describe(items):
    return " + ".join(f"{i['category']} {i['color']} (#{i['id']})" for i in items)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", choices=list(SEASONS), default="autumn")
    parser.add_argument("--occasion", choices=list(OCCASION_STYLES), default="university")
    args = parser.parse_args()

    print("=" * 72)
    print("DressMe · BO4 · Démonstration du moteur de recommandation")
    print("=" * 72)
    print("\nVêtements en entrée :")
    for item in WARDROBE:
        print(f"  #{item['id']}  {item['category']:9} {item['color']:11} style={item['style']:7} "
              f"rôle={ROLE_FR.get(garment_role(item), '?')}")
    print(f"\nContexte : saison = {args.season} · occasion = {args.occasion}")
    print("Score global = 0,30 couleur + 0,20 style + 0,30 occasion + 0,20 saison (sur 100)")

    # Classement complet, non diversifié : toutes les combinaisons générées.
    ranked = recommend_outfits(WARDROBE, occasion=args.occasion, season=args.season, top_k=1000, diversify=False)
    print(f"\nCombinaisons générées : {len(ranked)} (haut + bas, avec ou sans veste)")
    for rank, outfit in enumerate(ranked, 1):
        print(f"  {rank:2}. {outfit['score']:6.2f}  {describe(outfit['items'])}")

    # Recommandation réelle du moteur : top 3 diversifié.
    top3 = recommend_outfits(WARDROBE, occasion=args.occasion, season=args.season, top_k=3)
    print("\n" + "=" * 72)
    print("TOP 3 DES TENUES RECOMMANDÉES (diversifié)")
    print("=" * 72)
    for rank, outfit in enumerate(top3, 1):
        print(f"\n#{rank}  {describe(outfit['items'])}")
        print(f"    Score global : {outfit['score']:.2f} / 100")
        print(f"    Couleur {outfit['color_score']:6.2f} · Style {outfit['style_score']:6.2f} · "
              f"Occasion {outfit['occasion_score']:6.2f} · Saison {outfit['season_score']:6.2f}")
        print("    Explications :")
        for line in outfit["explanations"]:
            print(f"      - {line}")
    print()


if __name__ == "__main__":
    main()
