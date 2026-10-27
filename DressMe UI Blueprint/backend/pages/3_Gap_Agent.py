"""Chat page for the BO3 wardrobe gap agent, with a visible tool trace."""

import sys
from pathlib import Path
from tempfile import NamedTemporaryFile

import pandas as pd
import streamlit as st

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from agent.gap_agent import GapAgent, llm_settings
from agent.memory import AgentMemory
from agent.tools import GapAgentTools, load_profile, load_wardrobe

USER_ID = "demo_user"
EXAMPLE_PROMPTS = [
    "What am I missing for winter work days in Tunis?",
    "And for a summer wedding?",
    "What did you recommend last time?",
]

st.set_page_config(page_title="BO3 Gap Agent", page_icon="🧭", layout="wide")


@st.cache_resource
def get_memory() -> AgentMemory:
    return AgentMemory()


def new_conversation() -> None:
    st.session_state.conversation_id = get_memory().start_conversation(USER_ID)
    st.session_state.chat = []


if "conversation_id" not in st.session_state:
    new_conversation()


def show_ranking(ranking: dict) -> None:
    gaps = ranking.get("ranked_gaps", [])
    if not gaps:
        return
    table = pd.DataFrame(gaps)[
        ["rank", "name", "priority", "ranking_score", "owned_count", "required_count",
         "coverage_deficit", "use_frequency", "season_relevance", "outfit_gain",
         "preference_match", "redundancy_score", "closest_owned_item"]
    ]
    st.dataframe(table, hide_index=True, use_container_width=True)
    st.bar_chart(table.set_index("name")["ranking_score"])
    st.caption(f"Ranker: {ranking['ranker_model']} (trained on {ranking['ranker_trained_on']}).")


def show_trace(trace: list[dict]) -> None:
    with st.expander(f"Agent pipeline trace — {len(trace)} tool call(s)"):
        for entry in trace:
            st.markdown(f"**Step {entry['step']} · `{entry['tool']}`** `{entry['arguments']}`")
            st.json(entry["result"], expanded=False)


with st.sidebar:
    st.header("Context")
    profile = load_profile()
    st.write(f"**City:** {profile['city']}")
    st.write(f"**Styles:** {', '.join(profile['preferred_styles'])}")
    st.write(f"**Wardrobe:** {len(load_wardrobe())} items")
    _, base_url, model = llm_settings()
    st.write(f"**LLM:** `{model}`")
    st.caption(base_url)

    uploaded = st.file_uploader("Garment photo (optional)", type=["jpg", "jpeg", "png", "webp"])
    if uploaded is not None:
        st.image(uploaded, width=200)

    st.button("New conversation", on_click=new_conversation)
    st.subheader("Try")
    for prompt in EXAMPLE_PROMPTS:
        st.code(prompt, language=None)

st.title("Wardrobe Gap Agent (BO3)")
st.write("Ask what your wardrobe is missing. The agent calls coverage rules, FashionCLIP and the XGBoost ranker.")

for turn in st.session_state.chat:
    with st.chat_message(turn["role"]):
        st.markdown(turn["content"])
        if turn.get("ranking"):
            show_ranking(turn["ranking"])
        if turn.get("trace"):
            show_trace(turn["trace"])

if question := st.chat_input("e.g. What am I missing for winter work days?"):
    with st.chat_message("user"):
        st.markdown(question)

    memory = get_memory()
    conversation_id = st.session_state.conversation_id
    tools = GapAgentTools(memory, USER_ID, conversation_id)
    temporary_image: Path | None = None
    if uploaded is not None:
        with NamedTemporaryFile(suffix=Path(uploaded.name).suffix or ".jpg", delete=False) as image_file:
            image_file.write(uploaded.getvalue())
            temporary_image = Path(image_file.name)
        tools.uploaded_image = temporary_image

    history = [{"role": t["role"], "content": t["content"]} for t in st.session_state.chat]
    with st.chat_message("assistant"):
        try:
            with st.spinner("Thinking and calling tools..."):
                result = GapAgent(tools).run(question, history)
        except Exception as error:
            st.error(f"Agent error: {error}")
            st.stop()
        finally:
            if temporary_image is not None:
                temporary_image.unlink(missing_ok=True)

        st.markdown(result.answer)
        if result.ranking:
            show_ranking(result.ranking)
        show_trace(result.trace)

    st.session_state.chat += [
        {"role": "user", "content": question},
        {"role": "assistant", "content": result.answer, "ranking": result.ranking, "trace": result.trace},
    ]
    memory.add_message(conversation_id, "user", question)
    memory.add_message(conversation_id, "assistant", result.answer)
