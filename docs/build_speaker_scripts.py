"""Builds printable FR and EN speaker scripts from the Markdown sources.

    .\\.venv\\Scripts\\python.exe docs\\build_speaker_scripts.py
"""
import re
import sys
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import PageBreak, Paragraph, Spacer

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from pdf_presentation.common import (BODY, BUL, GREY, H1, H2, H3, OLIVE_DARK, build_doc)  # noqa: E402

QUOTE = ParagraphStyle("QUOTE", parent=BODY, leftIndent=10, textColor=OLIVE_DARK,
                       fontName="Helvetica-Oblique")

BOLD = re.compile(r"\*\*(.+?)\*\*")
CODE = re.compile(r"`(.+?)`")
NUMBERED = re.compile(r"^(\d+)\.\s+(.*)$")


def inline(text):
    text = escape(text)
    text = BOLD.sub(r"<b>\1</b>", text)
    text = CODE.sub(r'<font name="Courier" size="8.2">\1</font>', text)
    return text


def story_from(markdown):
    story = []
    first_h1 = True
    for raw in markdown.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped:
            continue
        if stripped == "<!-- pagebreak -->":
            story.append(PageBreak())
        elif stripped == "---":
            story.append(Spacer(1, 4))
        elif stripped.startswith("# "):
            if not first_h1:
                story.append(Spacer(1, 12))
            first_h1 = False
            story.append(Paragraph(inline(stripped[2:]), H1))
        elif stripped.startswith("## "):
            story.append(Paragraph(inline(stripped[3:]), H2))
        elif stripped.startswith("### "):
            story.append(Paragraph(inline(stripped[4:]), H3))
        elif stripped.startswith("> "):
            story.append(Paragraph(inline(stripped[2:]), QUOTE))
        elif stripped.startswith("- "):
            story.append(Paragraph(inline(stripped[2:]), BUL, bulletText="\u2022"))
        elif NUMBERED.match(stripped):
            number, text = NUMBERED.match(stripped).groups()
            story.append(Paragraph(inline(text), BUL, bulletText="%s." % number))
        else:
            story.append(Paragraph(inline(stripped), BODY))
    return story


CONFIG = {
    "fr": {
        "source": HERE / "speaker_script_FR.md",
        "out": HERE / "DressMe_Speaker_Script_FR.pdf",
        "footer": "DressMe - script du présentateur",
        "cover_title": "Script du présentateur",
        "cover_sub": "Présentation technique - 18 minutes - 15 slides",
        "cover_lines": ["8 agents LangGraph, dont un orchestrateur conversationnel",
                        "4 services FastAPI, 1 RAG cité, protocole A2A 0.3.0",
                        "Plan de contrôle / plan de données, entrées-sorties, questions du jury"],
        "cover_footer": "Projet de fin d'études - React 19, FastAPI, LangGraph, OpenAI, Supabase",
    },
    "en": {
        "source": HERE / "speaker_script_EN.md",
        "out": HERE / "DressMe_Speaker_Script_EN.pdf",
        "footer": "DressMe - speaker script",
        "cover_title": "Speaker script",
        "cover_sub": "Technical presentation - 18 minutes - 15 slides",
        "cover_lines": ["8 LangGraph agents, including one conversational orchestrator",
                        "4 FastAPI services, 1 cited RAG, A2A 0.3.0 protocol",
                        "Control plane / data plane, inputs-outputs, jury questions"],
        "cover_footer": "Final-year project - React 19, FastAPI, LangGraph, OpenAI, Supabase",
    },
}


def build(lang):
    cfg = CONFIG[lang]
    markdown = cfg["source"].read_text(encoding="utf-8-sig")
    return build_doc(
        cfg["out"],
        story_from(markdown),
        lang,
        "DressMe - %s" % cfg["cover_title"],
        cfg["footer"],
        cfg["cover_title"],
        cfg["cover_sub"],
        cfg["cover_lines"],
        cfg["cover_footer"],
    )


if __name__ == "__main__":
    build("fr")
    build("en")
