"""Mémoire persistante du Stylist (SqliteSaver) : le contexte survit au redémarrage, sans jamais le jeton."""
import pytest

import stylist_agent as sa
from test_stylist_agent import TODAY, fixture_loader

TOKEN = "jeton-secret-alice"


@pytest.fixture
def make_graph():
    pytest.importorskip("langgraph")
    pytest.importorskip("outfit_engine")
    pytest.importorskip("langgraph.checkpoint.sqlite")

    def factory(checkpointer):
        return sa.build_graph(llm=None, wardrobe_loader=lambda token=None: fixture_loader(), today=lambda: TODAY,
                              weather=None, checkpointer=checkpointer)
    return factory


def turn(graph, message, user="uuid-alice", thread="fil-1", token=TOKEN):
    config = sa.turn_config(thread, user, token)
    graph.invoke(sa.new_turn(message), config)
    return graph.get_state(config).values


def test_context_survives_a_restart_and_never_stores_the_token(make_graph, tmp_path):
    db = tmp_path / "stylist.sqlite"
    first = turn(make_graph(sa.sqlite_checkpointer(db)), "J'ai un entretien demain")
    assert first["request"]["occasion"] == "work" and first["outfits"]
    again = turn(make_graph(sa.sqlite_checkpointer(db)), "une autre")      # nouveau processus, même fichier
    assert again["request"]["occasion"] == "work"                          # occasion relue depuis le fichier
    shown = {frozenset(sa._outfit_ids(o)) for o in first["outfits"]}
    assert again["outfits"] and not shown & {frozenset(sa._outfit_ids(o)) for o in again["outfits"]}
    raw = b"".join(p.read_bytes() for p in tmp_path.glob("stylist.sqlite*"))
    assert TOKEN.encode() not in raw and b"__bo1_token" not in raw


def test_two_users_have_separate_memories(make_graph, tmp_path):
    graph = make_graph(sa.sqlite_checkpointer(tmp_path / "stylist.sqlite"))
    turn(graph, "J'ai un entretien demain", user="uuid-alice", thread="fil-1")
    bob = turn(graph, "une autre", user="uuid-bob", thread="fil-1", token="jeton-secret-bob")
    assert bob["request"].get("occasion") is None and not bob["outfits"]   # même fil, autre utilisatrice : rien
