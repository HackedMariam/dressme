from __future__ import annotations

from conversations import ConversationStore


def test_conversation_round_trip(tmp_path):
    store = ConversationStore(tmp_path / "chat.sqlite3")
    conversation_id = store.create()

    store.append(conversation_id, "user", "What should I wear?")
    store.append(
        conversation_id,
        "assistant",
        "Wear the blazer [S1].",
        sources=[{"source": "a.pdf", "page": 1}],
        citations=[{"marker": "[S1]", "source": "a.pdf", "page": 1}],
    )

    messages = store.messages(conversation_id)
    assert [message["role"] for message in messages] == ["user", "assistant"]
    assert messages[1]["citations"][0]["marker"] == "[S1]"
    assert store.history(conversation_id)[0]["content"] == "What should I wear?"

    assert store.delete(conversation_id) is True
    assert store.exists(conversation_id) is False


def test_append_creates_missing_conversation(tmp_path):
    store = ConversationStore(tmp_path / "chat.sqlite3")
    store.append("missing-id", "user", "hello")
    assert store.exists("missing-id")
