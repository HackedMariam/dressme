"""Tests de l'interface web du Stylist Agent (API FastAPI, sans navigateur ni Ollama)."""

import datetime as dt
from pathlib import Path

import pytest

pytest.importorskip("langgraph")
pytest.importorskip("outfit_engine")
pytest.importorskip("fastapi")
testclient = pytest.importorskip("fastapi.testclient")

import bo1_api_adapter  # noqa: E402
import stylist_web  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "bo1_items_sample.json"


def fixture_loader():
    wardrobe, report = bo1_api_adapter.adapt_wardrobe(bo1_api_adapter.load_bo1_items_from_file(FIXTURE))
    report["source"] = "fixture"
    return wardrobe, report


@pytest.fixture
def client():
    stylist_web.configure(llm=None, loader=fixture_loader, today=lambda: dt.date(2026, 10, 22), weather=None)
    yield testclient.TestClient(stylist_web.app)
    stylist_web.configure()  # remet la configuration par défaut


def chat(client, message, thread_id=None):
    response = client.post("/api/chat", json={"message": message, "thread_id": thread_id})
    assert response.status_code == 200, response.text
    return response.json()


def test_page_is_served(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "DressMe" in response.text and "/api/chat" in response.text


def test_clarification_turn(client):
    data = chat(client, "Je veux une tenue")
    assert data["thread_id"]
    assert data["outfits"] == []
    assert data["visited"] == ["extract_intent", "clarify"]
    assert "class extract_intent,clarify visited" in data["mermaid"]


def test_full_turn_returns_outfits_with_items_and_subscores(client):
    data = chat(client, "Une tenue pour un entretien demain")
    assert 1 <= len(data["outfits"]) <= 3
    wardrobe_ids = {item["id"] for item in fixture_loader()[0]}
    for outfit in data["outfits"]:
        assert outfit["items"]
        assert {item["id"] for item in outfit["items"]} <= wardrobe_ids
        assert all(item["image"].startswith("http") for item in outfit["items"])
        assert 0 <= outfit["score"] <= 100
    assert data["visited"] == ["extract_intent", "get_weather", "fetch_wardrobe", "apply_constraints",
                               "recommend", "style_advice", "respond"]
    assert data["wardrobe"]["source"] == "fixture" and data["wardrobe"]["kept"] == 10
    assert data["request"]["occasion"] == "work"


def test_thread_keeps_conversation_memory(client):
    first = chat(client, "Je veux une tenue")
    second = chat(client, "Pour le travail", first["thread_id"])
    assert second["thread_id"] == first["thread_id"]
    assert second["request"]["occasion"] == "work"
    assert second["outfits"]


def test_separate_threads_are_independent(client):
    chat(client, "Une tenue pour le travail, sans veste", "a")
    other = chat(client, "Une tenue pour le travail", "b")
    assert other["request"]["exclude_categories"] == []


def test_empty_message_is_rejected(client):
    assert client.post("/api/chat", json={"message": "   "}).status_code == 400


def test_wardrobe_endpoint(client):
    data = client.get("/api/wardrobe").json()
    assert data["report"]["kept"] == 10 and len(data["items"]) == 10


def test_wardrobe_endpoint_distinguishes_duplicate_names(client):
    def twin_jackets():
        wardrobe, report = fixture_loader()
        for item in wardrobe:
            if item["category"] in {"blazer", "jacket"}:
                item["name"] = "Charcoal Jacket"
        return wardrobe, report
    stylist_web.configure(llm=None, loader=twin_jackets, weather=None)
    names = [item["name"] for item in client.get("/api/wardrobe").json()["items"]]
    jackets = [n for n in names if n.startswith("Charcoal Jacket")]
    assert len(jackets) == 2 and len(set(jackets)) == 2
    assert len(set(names)) == len(names)


def test_wardrobe_endpoint_reports_bo1_down(client):
    def broken():
        raise bo1_api_adapter.BO1UnavailableError("BO1 injoignable")
    stylist_web.configure(llm=None, loader=broken)
    assert client.get("/api/wardrobe").status_code == 503


def test_graph_endpoint(client):
    mermaid = client.get("/api/graph").json()["mermaid"]
    assert mermaid.startswith("flowchart TD")
    assert "\n  class " not in mermaid  # aucun node surligné avant le premier tour


def test_outfits_expose_formality_and_dress_code(client):
    data = chat(client, "J'ai un entretien demain")
    assert data["request"]["dress_code"] == "business"
    for outfit in data["outfits"]:
        assert outfit["formality"] >= 3.0 and outfit["dress_code_ok"] is True


def test_weather_is_exposed_to_the_page(client):
    stylist_web.configure(llm=None, loader=fixture_loader, today=lambda: dt.date(2026, 10, 22),
                          weather=lambda city, day: {"city": city, "date": day.isoformat(),
                                                     "t_min": 4, "t_max": 9, "rain_probability": 20})
    data = chat(client, "Une tenue pour le travail")
    assert data["weather"]["city"] == "Tunis"
    assert data["request"]["season"] == "winter"
    assert "get_weather" in data["mermaid"]


def test_feedback_buttons_endpoint(client):
    data = chat(client, "Une tenue pour le travail")
    response = client.post("/api/feedback", json={"thread_id": data["thread_id"], "rank": 1, "verdict": "like"})
    assert response.status_code == 200
    body = response.json()
    assert body["items"] == [item["name"] for item in data["outfits"][0]["items"]]
    assert body["profile"]["likes"] == 1
    assert client.get("/api/profile").json()["likes"] == 1


def test_feedback_endpoint_errors(client):
    data = chat(client, "Une tenue pour le travail")
    bad_rank = {"thread_id": data["thread_id"], "rank": 9, "verdict": "like"}
    assert client.post("/api/feedback", json=bad_rank).status_code == 404
    bad_verdict = {"thread_id": data["thread_id"], "rank": 1, "verdict": "love"}
    assert client.post("/api/feedback", json=bad_verdict).status_code == 400


def test_dislike_from_chat_hides_outfit(client):
    data = chat(client, "Une tenue pour le travail")
    rejected = {item["id"] for item in data["outfits"][0]["items"]}
    after = chat(client, "je n'aime pas la 1", data["thread_id"])
    assert after["visited"][:2] == ["extract_intent", "record_feedback"]
    assert all({item["id"] for item in o["items"]} != rejected for o in after["outfits"])
    assert after["profile"]["dislikes"] == 1


def test_style_advice_is_returned_and_drawn(client):
    def fake_advice(question):
        return {"answer": "Une chemise unie et un pantalon bien coupé.", "sources": ["Career Closet"]}
    stylist_web.configure(llm=None, loader=fixture_loader, today=lambda: dt.date(2026, 10, 22), weather=None,
                          advice=fake_advice)
    data = chat(client, "Une tenue pour un entretien demain")
    assert data["advice"]["answer"].startswith("Une chemise") and data["advice"]["sources"] == ["Career Closet"]
    assert "style_advice" in data["visited"]
    assert "style_advice -.->" in data["mermaid"] and "bo5_rag" in data["mermaid"]
    assert "Conseil BO5" in client.get("/").text


def test_style_advice_disabled_by_default_in_web(client):
    data = chat(client, "Une tenue pour un entretien demain")
    assert data["advice"] == {}
    assert "style_advice -> BO5 désactivé" in data["trace"]


def test_page_follows_the_dressme_template(client):
    page = client.get("/").text
    assert "AI Stylist" in page
    assert "Coulisses de l'agent" in page and "Garde-robe BO1" in page          # les deux onglets
    assert 'role="tablist"' in page and page.count('<button class="tab" role="tab"') == 2
    assert 'id="panel-backstage"' in page and 'id="panel-wardrobe"' in page
    assert "/api/wardrobe" in page                                              # onglet garde-robe alimenté par l'API
    assert "#556B2F" in page and "Playfair Display" in page                     # couleurs et polices du template
    # Modules de l'équipe : affichés mais non cliquables, sans fonctionnalité simulée.
    assert page.count("Module de l'équipe, dans l'application DressMe") == 7
    for module in ("Dashboard", "My Wardrobe", "Outfit Studio", "Help Me Pack", "Style Profile",
                   "Should I Buy?", "Find Similar"):
        assert module in page
    assert "Nouvelle conversation" in page and "/api/feedback" in page and "Conseil BO5" in page


def test_visited_nodes_are_olive(client):
    data = chat(client, "Je veux une tenue")
    assert "classDef visited fill:#556B2F" in data["mermaid"]


# ===================================================================== Schéma SVG du graphe (hors ligne)
FULL_PATH = ["extract_intent", "get_weather", "fetch_wardrobe", "apply_constraints", "recommend",
             "style_advice", "respond"]


def test_graph_svg_without_visited_nodes():
    svg = stylist_web.graph_svg([])
    assert svg.startswith("<svg") and svg.endswith("</svg>")
    assert 'class="n v"' not in svg and 'class="e v"' not in svg
    for name in stylist_web.GRAPH_NODES:                           # les 9 noms
        assert f">{name}</text>" in svg


def test_graph_svg_full_path_is_olive():
    svg = stylist_web.graph_svg(FULL_PATH)
    assert svg.count('class="n v"') == 7
    assert svg.count('class="e v"') == 8                           # START → 7 nodes → END
    assert 'fill="#556B2F"' in svg and 'fill="#FFFFFF"' in svg


def test_graph_svg_clarification_path():
    svg = stylist_web.graph_svg(["extract_intent", "clarify"])
    assert svg.count('class="n v"') == 2
    assert stylist_web.visited_edges(["extract_intent", "clarify"]) == {
        ("START", "extract_intent"), ("extract_intent", "clarify"), ("clarify", "END")}


def test_graph_text_fits_in_boxes():
    assert stylist_web.NAME_SIZE >= 11 and stylist_web.SUB_SIZE >= 11
    for name, (_, _, width, sub) in stylist_web.GRAPH_NODES.items():
        assert len(name) * 0.62 * stylist_web.NAME_SIZE <= width - 8, name
        assert len(sub) * 0.6 * stylist_web.SUB_SIZE <= width - 8, sub


def test_no_arrow_crosses_a_box():
    boxes = {name: (x, y, x + w, y + stylist_web.BOX_H) for name, (x, y, w, _) in stylist_web.GRAPH_NODES.items()}
    for (src, dst), (points, _, _) in stylist_web.GRAPH_EDGES.items():
        for (x1, y1), (x2, y2) in zip(points, points[1:]):
            for step in range(1, 50):
                t = step / 50
                px, py = x1 + (x2 - x1) * t, y1 + (y2 - y1) * t
                for name, (left, top, right, bottom) in boxes.items():
                    if name in (src, dst):
                        continue
                    inside = left + 1 < px < right - 1 and top + 1 < py < bottom - 1
                    assert not inside, f"{src}→{dst} traverse {name}"


def test_api_returns_the_svg(client):
    assert client.get("/api/graph").json()["graph_svg"].startswith("<svg")
    data = chat(client, "Une tenue pour un entretien demain")
    assert data["graph_svg"].count('class="n v"') == len(set(data["visited"]))
    assert "mermaid" in data                                       # champ conservé pour la compatibilité


def test_page_is_offline_and_graph_hidden_by_default(client):
    page = client.get("/").text
    assert "cdn.jsdelivr.net/npm/mermaid" not in page
    assert "Afficher le graphe" in page and "Masquer le graphe" in page and "Agrandir" in page
    assert '<div id="graph-box" hidden>' in page
    assert "Chemin :" in page and 'role="dialog"' in page
