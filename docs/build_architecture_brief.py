"""A short PDF: the architecture, the orchestrator, how agents are called over A2A, how each agent is built.

    python docs/build_architecture_brief.py   ->  docs/DressMe_Architecture_En_Bref.pdf
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import Image, KeepTogether, PageBreak, SimpleDocTemplate, Spacer

from build_architecture_pdf import BODY, CAP, CODEST, H1, H2, P, bullets, table

HERE = Path(__file__).resolve().parent
OUT = HERE / "DressMe_Architecture_En_Bref.pdf"


def build() -> None:
    doc = SimpleDocTemplate(str(OUT), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
                            title="DressMe - L'architecture en bref", author="DressMe")
    s = [P("DressMe : l'architecture en bref", H1),
         P("Les agents sont des <b>graphes LangGraph</b>. Ils echangent par le protocole <b>A2A</b>. Un <b>orchestrateur</b> choisit quel agent repond. "
           "Dans tous les agents, le LLM decide et redige ; le code verifie et calcule."),
         Image(str(HERE / "DressMe_Architecture.png"), width=174 * mm, height=174 * mm * 226 / 320),
         P("Figure : interface, orchestrateur, agents par service, protocole A2A et briques partagees.", CAP),
         PageBreak()]

    s += [P("1. L'orchestrateur", H1),
          P("<b>Role.</b> C'est le chef d'orchestre : il recoit chaque message de la page AI Stylist (<font face='Courier'>POST /api/assistant/chat</font>), "
            "choisit l'agent qui doit repondre, lui delegue la demande et renvoie sa reponse. Il decide qui repond ; il ne repond pas lui-meme."),
          table([["Noeud du graphe", "Ce qu'il fait"],
                 ["route", "GPT-4o choisit l'agent (seuls les agents de la liste sont acceptes). Si le LLM tombe, des regles FR/EN prennent le relais."],
                 ["stylist | wardrobe | outfit | trip | gap", "appelle l'agent choisi."],
                 ["redirect", "\"Should I buy\" et \"Find Similar\" ont besoin d'une photo : la reponse ouvre la bonne page."],
                 ["clarify", "demande ce que l'utilisateur veut quand la demande est trop vague."],
                 ["respond", "garde l'echange en memoire (un fil par utilisateur). Une question restee ouverte (valise, correction a confirmer) est reprise par le meme agent."]],
                [52, 118]),
          P("Comment il appelle les agents", H2),
          table([["Agent", "Appel"],
                 ["AI Stylist, Wardrobe Agent, Outfit Builder", "direct, dans le meme service (BO1)"],
                 ["Trip Agent (Help Me Pack), Gap Agent (BO3)", "A2A avec le jeton de l'utilisateur : ce sont d'autres services"]],
                [82, 88]),
          Spacer(1, 6),
          P("2. A2A : appeler un agent en trois temps", H2),
          *bullets(["<b>La carte</b> : <font face='Courier'>GET /a2a/&lt;agent&gt;/.well-known/agent-card.json</font> donne le nom, les competences et la securite de l'agent (publique).",
                    "<b>La tache</b> : <font face='Courier'>POST /a2a/&lt;agent&gt;</font>, message JSON-RPC <font face='Courier'>message/send</font>, avec le jeton Supabase.",
                    "<b>Le resultat</b> : une tache <font face='Courier'>completed</font>, <font face='Courier'>failed</font> ou <font face='Courier'>input-required</font>, avec un texte et des donnees. "
                    "Pour continuer une question ouverte, on renvoie le meme <font face='Courier'>contextId</font>."]),
          P("<font face='Courier'>client = A2AClient(url, token)  ;  tache = client.send(\"Prepare ma valise pour Paris\")  ;  client.text_of(tache)</font>", CODEST),
          P("Chaque agent expose sa carte : <font face='Courier'>/a2a/stylist</font>, <font face='Courier'>/a2a/wardrobe</font>, <font face='Courier'>/a2a/similar</font>, "
            "<font face='Courier'>/a2a/outfit</font> (BO1), <font face='Courier'>/a2a/trip</font> (8020), <font face='Courier'>/a2a/gap</font> (BO3). "
            "Le Trip Agent appelle lui-meme le Wardrobe Agent (lire le placard) et le Gap Agent (lacunes) par A2A. Dans BO1, l'AI Stylist, le Similar Agent, l'Outfit Builder et l'orchestrateur demandent aussi le placard au Wardrobe Agent par A2A (actions list et ask), avec un repli en appel direct."),
          PageBreak()]

    s += [P("3. Comment chaque agent est construit", H1),
          P("Tous suivent le meme modele. La boucle commune est dans <font face='Courier'>agent_kit/tool_loop.py</font> : "
            "<font face='Courier'>llm &rarr; tools &rarr; llm</font>, avec un rappel unique et une fin."),
          table([["Agent", "Construction"],
                 ["AI Stylist", "boucle d'outils GPT-4o : ask_wardrobe_agent, get_weather (Open-Meteo), fashion_advice (RAG). Reponse JSON : choix, meteo, tenue, raisons, sources [S#]."],
                 ["Wardrobe Agent", "graphe gate &rarr; apply | cancel | assist. 4 outils : recherche, pieces proches, statistiques, update_item. update_item propose seulement : le code n'ecrit qu'apres le oui de l'utilisateur."],
                 ["Similar Agent", "demande au Wardrobe Agent ce que l'utilisateur possede pour chaque piece d'un look ; juge owned / close / missing ; le code verifie que la piece citee existe."],
                 ["Outfit Builder", "graphe weather &rarr; closet &rarr; knowledge (RAG) &rarr; compose &rarr; validate. Le code rejette les tenues invalides et renvoie le LLM une fois."],
                 ["Trip Agent", "GPT-4o, 10 outils, deux graphes. Le solveur OR-Tools choisit la valise, pas le LLM."],
                 ["Gap Agent", "boucle de 5 outils. Des regles decident ce qui est une lacune ; XGBoost ne fait que les ordonner."],
                 ["Purchase Agent", "Qwen2.5-3B + LoRA (Hugging Face) pilote les outils d'achat et rend un verdict JSON verifie ; GPT-4o le reecrit seulement. Repli deterministe sans HF_TOKEN."]],
                [34, 136]),
          P("Briques partagees", H2),
          *bullets(["<b>agent_kit</b> (boucle LangGraph) et <b>a2a_protocol</b> (carte, serveur, client) : le code commun.",
                    "<b>GPT-4o</b>, <b>Open-Meteo</b> (meteo, sans cle), le <b>RAG</b> (38 PDF de mode, reponses citees) et <b>Supabase</b> (auth, base, stockage)."]),
          P("A retenir", H2),
          *bullets(["L'orchestrateur est le seul a choisir qui repond. Les agents ne s'appellent entre eux que pour deux raisons voulues : demander le placard au Wardrobe Agent (AI Stylist, Similar Agent, Trip Agent) et, pour le Trip Agent, demander les lacunes au Gap Agent.",
                    "Les ecritures exigent toujours la confirmation de l'utilisateur.",
                    "Limites : le Purchase Agent n'est actif qu'avec HF_TOKEN et un modele executable ; le Gap Agent lit le placard par A2A avec repli sur Supabase."])]
    doc.build(s)
    print("written", OUT)


if __name__ == "__main__":
    build()
