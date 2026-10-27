"""Download the pinned FashionCLIP weights into backend/models/fashionclip/."""

from pathlib import Path

from huggingface_hub import snapshot_download

REPO_ID = "patrickjohncyh/fashion-clip"
REVISION = "7e3ba62ce16b379a1ab479346b66f192e76f51b7"
TARGET_DIR = Path(__file__).resolve().parent / "models" / "fashionclip"

if __name__ == "__main__":
    snapshot_download(
        repo_id=REPO_ID,
        revision=REVISION,
        local_dir=TARGET_DIR,
        allow_patterns=["*.json", "*.txt", "model.safetensors", "README.md"],
    )
    print(f"FashionCLIP downloaded to {TARGET_DIR}")
