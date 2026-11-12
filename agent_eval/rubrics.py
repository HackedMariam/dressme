"""One rubric per agent: the criteria the judge scores from 1 (bad) to 5 (excellent).

A rubric is deliberately small (3-5 criteria): each one must be checkable from the case alone (the user's request, the
facts the agent had, and its answer). `hard` criteria are the ones where a low score is a failure whatever the average
(inventing a garment, claiming an edit was done without confirmation...).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Criterion:
    name: str
    question: str
    hard: bool = False        # a score below the rubric's `hard_min` fails the case outright


@dataclass(frozen=True)
class Rubric:
    agent: str
    purpose: str
    criteria: tuple
    pass_score: float = 3.5   # average needed to pass
    hard_min: int = 3         # minimum for every `hard` criterion


RUBRICS: dict = {r.agent: r for r in [
    Rubric("stylist", "Personal stylist: answers style questions from the user's real wardrobe, the weather and fashion books.",
           (Criterion("grounded", "Every garment named exists in the provided wardrobe; nothing is invented.", hard=True),
            Criterion("relevance", "The advice answers what the user actually asked (occasion, colours, piece)."),
            Criterion("weather", "The weather given in the context is respected (no shorts in the cold, layers when cold)."),
            Criterion("citations", "Style claims that come from the books cite the provided sources, and cite them correctly."),
            Criterion("tone", "Clear, concise, friendly, in the user's language."))),
    Rubric("outfit", "Outfit builder: three complete outfits from the wardrobe for an occasion and a season.",
           (Criterion("grounded", "Every piece in every outfit exists in the wardrobe.", hard=True),
            Criterion("completeness", "Each outfit is wearable: top and bottom (or dress) and shoes, plus a layer when cold."),
            Criterion("occasion_fit", "The outfits suit the requested occasion and season / weather."),
            Criterion("coordination", "Colours and styles within an outfit go together; the three outfits are distinct."),
            Criterion("explanations", "The reasons given are true to the pieces and useful."))),
    Rubric("wardrobe", "Wardrobe agent: searches and edits the wardrobe in plain language; edits need confirmation.",
           (Criterion("correct_retrieval", "The pieces returned really match the request, with no obvious piece missing.", hard=True),
            Criterion("no_hallucination", "Counts, colours and categories stated match the data provided.", hard=True),
            Criterion("confirmation", "A modification or deletion is proposed and confirmation asked: it is never claimed as already done."),
            Criterion("clarity", "The answer is short, readable and in the user's language."))),
    Rubric("similar", "Similar-piece agent: says whether each piece of a look is owned, close or missing in the wardrobe.",
           (Criterion("verdict_accuracy", "The owned / close / missing verdict of each piece is justified by the wardrobe provided.", hard=True),
            Criterion("evidence", "The closest wardrobe piece named really is in the wardrobe and really is the closest."),
            Criterion("no_hallucination", "Nothing is claimed about a piece that is not in the provided data.", hard=True),
            Criterion("clarity", "The explanation is concise and actionable."))),
    Rubric("orchestrator", "Orchestrator: routes a message to the right agent and relays its answer.",
           (Criterion("routing", "The chosen agent is the right one for the message (stylist, wardrobe, outfit, trip, gap...).", hard=True),
            Criterion("faithfulness", "The final answer faithfully relays the agent's answer, without adding or dropping facts."),
            Criterion("clarification", "When the message is ambiguous, it asks one short question instead of guessing."),
            Criterion("safety", "Off-topic or unsafe requests are redirected politely."))),
    Rubric("trip", "Trip agent (HelpMePack): extracts the trip and packs a capsule from the wardrobe.",
           (Criterion("extraction", "Destination, dates, duration and activities match what the user wrote.", hard=True),
            Criterion("weather_fit", "The capsule fits the weather of the destination and dates."),
            Criterion("grounded", "Every packed item exists in the wardrobe.", hard=True),
            Criterion("coverage", "Each day / activity is covered; the packing is not bloated."),
            Criterion("clarity", "The summary is clear and missing information is asked, not invented."))),
    Rubric("gap", "Gap agent: tells what the wardrobe is missing for a goal.",
           (Criterion("gap_relevance", "The gaps named are real for the goal, given the wardrobe."),
            Criterion("no_redundancy", "It does not recommend something the wardrobe already holds.", hard=True),
            Criterion("actionable", "Each gap is concrete (what to buy, why)."),
            Criterion("clarity", "Short and well organised."))),
    Rubric("purchase", "Purchase decision agent: buy / skip a candidate garment against the wardrobe.",
           (Criterion("decision_soundness", "The decision follows from the evidence (redundancy, colour match, budget).", hard=True),
            Criterion("evidence_use", "The reasons cite the real evidence the tools returned."),
            Criterion("no_hallucination", "No wardrobe piece or number is invented.", hard=True),
            Criterion("helpfulness", "The user can act on the verdict."))),
    Rubric("rag", "Fashion-book RAG: answers fashion questions with citations from the retrieved passages only.",
           (Criterion("faithfulness", "Every claim is supported by the retrieved passages; nothing comes from outside them.", hard=True),
            Criterion("answer_relevance", "The answer addresses the question."),
            Criterion("citations", "Citations point to passages that really support the claim."),
            Criterion("abstention", "When the passages do not answer, it says \"I don't know\" instead of guessing."))),
]}
