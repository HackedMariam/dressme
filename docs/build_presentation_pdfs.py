"""Builds the French and English DressMe presentation PDFs.

    .\\.venv\\Scripts\\python.exe docs\\build_presentation_pdfs.py
"""
from pathlib import Path

from pdf_presentation import content_en, content_fr
from pdf_presentation.common import build_doc

OUT = Path(__file__).resolve().parent


def build_fr():
    return build_doc(
        OUT / "DressMe_Presentation_FR.pdf",
        content_fr.build_story(),
        "fr",
        "DressMe - Presentation technique",
        "DressMe - presentation technique",
        "Dossier de presentation technique",
        "Architecture, agents, LLM, graphes et algorithmes",
        ["8 agents LangGraph, dont un orchestrateur conversationnel",
         "4 services FastAPI, 1 RAG cite, protocole A2A 0.3.0",
         "Architecture, LLM, entrees / sorties, graphes, algorithmes, limites"],
        "Projet de fin d'etudes - React 19, FastAPI, LangGraph, OpenAI, Supabase",
    )


def build_en():
    return build_doc(
        OUT / "DressMe_Presentation_EN.pdf",
        content_en.build_story(),
        "en",
        "DressMe - Technical presentation",
        "DressMe - technical presentation",
        "Technical presentation deck",
        "Architecture, agents, LLMs, graphs and algorithms",
        ["8 LangGraph agents, including one conversational orchestrator",
         "4 FastAPI services, 1 cited RAG, A2A 0.3.0 protocol",
         "Architecture, LLMs, inputs / outputs, graphs, algorithms, limits"],
        "Final-year project - React 19, FastAPI, LangGraph, OpenAI, Supabase",
    )


if __name__ == "__main__":
    build_fr()
    build_en()
