"""Small local UI for comparing clothing images with text using FashionCLIP."""

from pathlib import Path
from tempfile import NamedTemporaryFile

import streamlit as st

from fashionclip import FashionCLIPEncoder


@st.cache_resource
def load_encoder() -> FashionCLIPEncoder:
    return FashionCLIPEncoder(device="cpu")


st.set_page_config(page_title="FashionCLIP Tester", page_icon="👕", layout="centered")
st.title("FashionCLIP tester")
st.write("Upload a clothing photo and compare it with candidate descriptions.")

uploaded_image = st.file_uploader(
    "Clothing image", type=["jpg", "jpeg", "png", "webp"]
)
if uploaded_image is not None:
    st.image(uploaded_image, caption=uploaded_image.name, width=320)

description_text = st.text_area(
    "Candidate descriptions (one per line)",
    value=(
        "a blue denim jacket\n"
        "a camel wool coat\n"
        "a black leather jacket\n"
        "a cream knit sweater\n"
        "a white button-down shirt"
    ),
    height=160,
)

descriptions = [line.strip() for line in description_text.splitlines() if line.strip()]
if st.button(
    "Compare image and descriptions",
    type="primary",
    disabled=uploaded_image is None or not descriptions,
):
    temporary_image: Path | None = None
    try:
        with NamedTemporaryFile(
            suffix=Path(uploaded_image.name).suffix or ".jpg", delete=False
        ) as image_file:
            image_file.write(uploaded_image.getvalue())
            temporary_image = Path(image_file.name)

        with st.spinner("Loading FashionCLIP and comparing..."):
            encoder = load_encoder()
            image_embedding = encoder.encode_images([temporary_image])
            text_embeddings = encoder.encode_text(descriptions)
            similarities = (image_embedding @ text_embeddings.T)[0]

        ranked_indices = similarities.argsort(descending=True).tolist()
        best_index = ranked_indices[0]
        st.subheader("Closest match")
        st.write(
            f"**{descriptions[best_index]}** — "
            f"similarity {similarities[best_index].item():.4f}"
        )

        st.subheader("Ranking")
        st.dataframe(
            [
                {
                    "Rank": rank,
                    "Description": descriptions[index],
                    "Similarity": round(similarities[index].item(), 4),
                }
                for rank, index in enumerate(ranked_indices, start=1)
            ],
            hide_index=True,
            use_container_width=True,
        )
        st.caption(
            "Similarity scores rank these descriptions for this image; they are "
            "not probabilities or wardrobe-gap decisions."
        )
    except Exception as error:
        st.error(f"Could not run FashionCLIP: {error}")
    finally:
        if temporary_image is not None:
            temporary_image.unlink(missing_ok=True)

if not (Path(__file__).parent / "models" / "fashionclip" / "model.safetensors").is_file():
    st.info("Download the model first with: python backend/download_fashionclip.py")
