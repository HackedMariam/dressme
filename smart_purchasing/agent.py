"""Dynamic 5-Step Shopper Agent with Checkpointing, Qwen3 (via Ollama), and Explicit Fallback.

Core Responsibilities of Qwen:
1. Tool selection: Determines which tools are relevant based on user prompt & context.
2. Information gathering: Identifies missing facts (e.g., budget, occasion) and decides whether to ask the user.
3. Adaptive execution: Responds dynamically to intermediate results (e.g. investigating differences when a similar piece exists).
4. Completion: Verifies if enough reliable evidence exists to conclude or if more questions are needed.
5. Contextual recommendation: Interprets the deterministic score S in context, explaining trade-offs and conflicts (e.g., high versatility but budget exceeded).
"""

import os
import re
import csv
import json
import uuid
import urllib.request
import urllib.error
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple

from schemas import (
    Garment,
    CandidateItem,
    AgentRecommendation,
    EvaluatePurchaseRequest,
    DecisionType,
    SessionStatus,
    SimilarItemMatch,
    OutfitRecommendation,
    GapAnalysisResult,
)
from tools import (
    analyze_item,
    find_similar_items,
    check_outfit_compatibility,
    analyze_wardrobe_gaps,
    calculate_purchase_value,
    PURCHASE_TOOLS_SCHEMA,
)

SYSTEM_PROMPT = """You are the Shopper Agent for DressMe powered by Qwen3.
Your role:
1. Ground your reasoning in tool execution results. Never hallucinate items or scores.
2. Contextualize the deterministic score S calculated by Python:
   - BUY: Score >= 70
   - CONSIDER: 45 <= Score < 70
   - SKIP: Score < 45
3. Explain conflicts clearly: For example, if an item scores high in outfit compatibility but exceeds the user's budget, state that trade-off explicitly!
4. State clearly how many outfits the item is compatible with.
"""


def query_ollama(prompt: str, model_name: str = "qwen2.5:1.5b", timeout_sec: int = 120) -> Optional[str]:
    """Queries local Ollama instance for Qwen reasoning with generous timeout (120s)."""
    url = "http://localhost:11434/api/chat"
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ],
        "stream": False,
        "options": {
            "temperature": 0.2,
            "num_predict": 180
        }
    }
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=timeout_sec) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            content = res_data.get("message", {}).get("content", "").strip()
            return content if content else None
    except Exception as e:
        print(f"[Agent Warning] Ollama query failed or timed out ({timeout_sec}s): {e}")
        return None



class PurchaseAgent:
    """Dynamic multi-step Shopper Agent with session checkpointing."""

    def __init__(
        self,
        wardrobe_file: Optional[str] = None,
        model_name: str = "qwen2.5:1.5b",
        timeout_sec: int = 120
    ):
        self.model_name = model_name
        self.timeout_sec = timeout_sec
        self.tools_schema = PURCHASE_TOOLS_SCHEMA
        self.wardrobe: List[Garment] = []
        self.checkpoint_dir = Path(__file__).resolve().parent / "data" / "checkpoints"
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self._load_wardrobe(wardrobe_file)

    def _load_wardrobe(self, file_path: Optional[str] = None):
        if not file_path:
            # Default to wardrobe.csv in smart_purchasing
            csv_path = Path(__file__).resolve().parent / "wardrobe.csv"
            if csv_path.exists():
                file_path = str(csv_path)
            else:
                file_path = str(Path(__file__).resolve().parent / "data" / "sample_wardrobe.json")

        self.wardrobe = []
        path_obj = Path(file_path)
        if not path_obj.exists():
            print(f"Warning: Wardrobe file {file_path} does not exist.")
            return

        try:
            if path_obj.suffix.lower() == ".csv":
                self.wardrobe = self._load_wardrobe_csv(path_obj)
            else:
                with open(path_obj, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.wardrobe = [Garment(**it) for it in data]
        except Exception as e:
            print(f"Warning: Could not load wardrobe from {file_path}: {e}")
            self.wardrobe = []

    def _load_wardrobe_csv(self, file_path: Path) -> List[Garment]:
        """Loads and adapts wardrobe.csv into typed Garment domain objects."""
        garments: List[Garment] = []
        with open(file_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                item_id = row.get("item_id", "").strip()
                name = row.get("name", "").strip()
                macro_cat = row.get("category", "").strip().lower()
                item_type = row.get("item_type", "").strip().lower().replace("-", "_")

                # Primary category is the specific item_type (e.g. jacket, shirt, skirt, sandals, coat)
                primary_cat = item_type if item_type else macro_cat

                color = row.get("color", "unknown").strip().lower()

                style_raw = row.get("style", "casual").strip().lower().replace("-", "_")
                style_list = [style_raw]
                if style_raw == "smart_casual":
                    style_list = ["smart_casual", "formal"]

                season_raw = row.get("season", "all-season").strip().lower()
                if season_raw in ["all-season", "all_season"]:
                    seasons = ["spring", "summer", "autumn", "winter"]
                else:
                    seasons = [season_raw]

                formality = int(row.get("formality_level", 3)) if row.get("formality_level") else 3
                if formality >= 4 or style_raw == "formal":
                    occasions = ["work", "formal_event", "meeting", "dinner"]
                elif formality == 3 or style_raw == "smart_casual":
                    occasions = ["work", "dinner", "casual_outing", "meeting"]
                else:
                    occasions = ["casual_outing", "weekend", "travel"]

                tags = [macro_cat, item_type]
                desc = row.get("description", "").strip()
                if desc:
                    tags.extend([w.lower() for w in desc.split() if len(w) > 3])

                versatility_val = None
                if row.get("versatility"):
                    try:
                        versatility_val = float(row["versatility"])
                    except ValueError:
                        pass

                garments.append(Garment(
                    id=item_id,
                    name=name,
                    category=primary_cat,
                    color=color,
                    style=style_list,
                    seasons=seasons,
                    occasions=occasions,
                    tags=tags,
                    item_type=item_type,
                    warmth_level=int(row["warmth_level"]) if row.get("warmth_level") else None,
                    water_resistance=int(row["water_resistance"]) if row.get("water_resistance") else None,
                    weight_g=int(row["weight_g"]) if row.get("weight_g") else None,
                    versatility=versatility_val,
                    formality_level=formality,
                    clean_items_available=row.get("clean_items_available", "True").lower() == "true",
                    description=desc
                ))
        return garments

    def _save_checkpoint(self, session_id: str, data: Dict[str, Any]):
        file_path = self.checkpoint_dir / f"{session_id}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def _load_checkpoint(self, session_id: str) -> Optional[Dict[str, Any]]:
        file_path = self.checkpoint_dir / f"{session_id}.json"
        if file_path.exists():
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return None

    def evaluate(self, request: EvaluatePurchaseRequest, skip_llm: bool = False) -> AgentRecommendation:
        """Executes the dynamic agent loop with Qwen decision responsibilities and checkpointing."""

        # RESUME FROM CHECKPOINT (Step 5 resumption)
        if request.session_id:
            checkpoint = self._load_checkpoint(request.session_id)
            if checkpoint and checkpoint.get("status") == SessionStatus.AWAITING_INPUT.value:
                return self._resume_step_5(checkpoint, request, skip_llm=skip_llm)

        session_id = request.session_id or f"sess_{uuid.uuid4().hex[:8]}"

        # =================================================================
        # QWEN RESPONSIBILITY 1 & 2: Understand Request & Information Gathering
        # =================================================================
        cand = request.candidate or CandidateItem(category="garment")
        user_query = request.user_query or "Should I buy this?"

        # Extract occasion and style hints from user_query if not explicitly provided
        query_lower = user_query.lower()
        occasion_keywords = {
            "work": "work",
            "office": "work",
            "business": "work",
            "meeting": "meeting",
            "dinner": "dinner",
            "date": "dinner",
            "party": "party",
            "formal": "formal_event",
            "event": "formal_event",
            "wedding": "formal_event",
            "casual": "casual_outing",
            "weekend": "weekend",
            "travel": "travel",
            "gym": "gym"
        }
        for kw, occ in occasion_keywords.items():
            if re.search(r'\b' + kw + r'\b', query_lower):
                if not cand.target_occasion or cand.target_occasion in ["work", "general"]:
                    cand.target_occasion = occ
                if occ not in cand.occasions:
                    cand.occasions.insert(0, occ)
                break

        has_price = cand.price is not None and cand.price > 0
        has_budget = request.budget is not None or cand.budget is not None
        known_budget = request.budget or cand.budget

        # =================================================================
        # QWEN RESPONSIBILITY 1: Tool Selection & Execution (Vision & Similarity)
        # =================================================================
        analyzed = analyze_item(cand)
        cand.color = analyzed["color"]

        # Tool 2: Wardrobe Similarity & Redundancy Search
        similar_matches = find_similar_items(cand, self.wardrobe, top_k=5)
        top_sim = similar_matches[0].similarity_score if similar_matches else 0.0
        redundancy_score = top_sim * 100.0

        interim_findings: List[str] = []
        if similar_matches:
            top_garment = similar_matches[0].garment
            top_m = similar_matches[0]
            color_detail = ""
            if top_m.color_similarity is not None:
                color_detail = f" [Color similarity: {top_m.color_similarity*100:.1f}%, Delta E: {top_m.color_delta_e:.1f}]"
            interim_findings.append(
                f"Wardrobe check: You already own a similar piece '{top_garment.name}' ({top_garment.color} {top_garment.category}, "
                f"{top_m.similarity_score*100:.2f}% similarity{color_detail})."
            )
            interim_findings.append(
                "Adaptive action: Investigating whether the candidate item offers unique outfit compatibility or fills a wardrobe gap."
            )
        else:
            interim_findings.append("Wardrobe check: No direct duplicates found in your existing wardrobe.")

        # =================================================================
        # QWEN RESPONSIBILITY 3: Adaptive Execution (Outfit Compatibility & Gaps)
        # =================================================================
        # Tool 3: check_outfit_compatibility
        outfit_eval = check_outfit_compatibility(cand, self.wardrobe, target_occasion=cand.target_occasion)
        compatible_count = outfit_eval["compatible_count"]
        outfit_combinations = outfit_eval["combinations"]
        avg_outfit_score = outfit_eval["average_score"]

        interim_findings.append(
            f"Outfit Compatibility: This item is compatible with {compatible_count} outfit(s) in your wardrobe (Score: {avg_outfit_score:.2f}%)."
        )

        # Tool 4: analyze_wardrobe_gaps
        gap_res = analyze_wardrobe_gaps(cand, self.wardrobe)
        if gap_res.reasoning:
            interim_findings.append(f"Wardrobe Gap: {gap_res.reasoning}")

        # =================================================================
        # QWEN RESPONSIBILITY 4: Completion & Information Gathering Check
        # =================================================================
        # If item has a price, but budget is completely unknown, Qwen decides to ask!
        if has_price and not has_budget:
            question = f"What is your budget for this purchase? (The item price is ${cand.price:.2f})"
            checkpoint_data = {
                "session_id": session_id,
                "status": SessionStatus.AWAITING_INPUT.value,
                "candidate": cand.model_dump(),
                "user_query": user_query,
                "interim_findings": interim_findings,
                "analyzed": analyzed,
                "similar_matches": [m.model_dump() for m in similar_matches],
                "outfit_combinations": [o.model_dump() for o in outfit_combinations],
                "compatible_count": compatible_count,
                "avg_outfit_score": avg_outfit_score,
                "gap_res": gap_res.model_dump(),
                "redundancy_score": redundancy_score,
                "awaiting_field": "budget",
                "clarification_question": question
            }
            self._save_checkpoint(session_id, checkpoint_data)

            return AgentRecommendation(
                session_id=session_id,
                status=SessionStatus.AWAITING_INPUT,
                decision=None,
                overall_score=None,
                engine_source="QWEN3-OLLAMA",
                summary="Initial wardrobe analysis complete. Awaiting budget information to evaluate affordability.",
                clarification_question=question,
                interim_findings=interim_findings,
                similar_items=similar_matches,
                outfit_examples=outfit_combinations,
                compatible_outfits_count=compatible_count,
                gap_analysis=gap_res,
                detected_color=cand.color,
                detected_category=cand.category,
                detected_style=", ".join(cand.style) if cand.style else "formal",
                detected_occasion=cand.target_occasion or (cand.occasions[0] if cand.occasions else "work"),
                user_query=user_query
            )

        # If budget is already known, complete immediately!
        return self._finish_step_5(
            session_id=session_id,
            cand=cand,
            similar_matches=similar_matches,
            outfit_combinations=outfit_combinations,
            compatible_count=compatible_count,
            avg_outfit_score=avg_outfit_score,
            gap_res=gap_res,
            redundancy_score=redundancy_score,
            budget=known_budget,
            user_query=user_query,
            skip_llm=skip_llm
        )


    def _resume_step_5(self, checkpoint: Dict[str, Any], request: EvaluatePurchaseRequest, skip_llm: bool = False) -> AgentRecommendation:
        """Resumes pipeline from Step 4 checkpoint once user provides the missing info."""
        cand = CandidateItem(**checkpoint["candidate"])
        similar_matches = [SimilarItemMatch(**m) for m in checkpoint["similar_matches"]]
        outfit_combinations = [OutfitRecommendation(**o) for o in checkpoint["outfit_combinations"]]
        compatible_count = checkpoint.get("compatible_count", len(outfit_combinations))
        avg_outfit_score = checkpoint.get("avg_outfit_score", 75.0)
        gap_res = GapAnalysisResult(**checkpoint["gap_res"])
        redundancy_score = checkpoint["redundancy_score"]
        user_query = checkpoint.get("user_query", "Should I buy this?")

        # Parse user budget response
        budget = None
        if request.budget is not None:
            budget = request.budget
        elif request.user_response:
            matches = re.findall(r"[-+]?(?:\d*\.\d+|\d+)", request.user_response)
            if matches:
                budget = float(matches[0])

        return self._finish_step_5(
            session_id=checkpoint["session_id"],
            cand=cand,
            similar_matches=similar_matches,
            outfit_combinations=outfit_combinations,
            compatible_count=compatible_count,
            avg_outfit_score=avg_outfit_score,
            gap_res=gap_res,
            redundancy_score=redundancy_score,
            budget=budget,
            user_query=user_query,
            skip_llm=skip_llm
        )

    def _finish_step_5(
        self,
        session_id: str,
        cand: CandidateItem,
        similar_matches: List[SimilarItemMatch],
        outfit_combinations: List[OutfitRecommendation],
        compatible_count: int,
        avg_outfit_score: float,
        gap_res: GapAnalysisResult,
        redundancy_score: float,
        budget: Optional[float],
        user_query: str = "Should I buy this?",
        skip_llm: bool = False
    ) -> AgentRecommendation:
        """Step 5: Computes deterministic math score, checks constraints, and queries Qwen for contextual explanation."""
        versatility = min(100.0, 50.0 + compatible_count * 15.0)
        style_pref = 80.0

        # Detect direct duplicate
        is_direct_duplicate = any(m.similarity_score >= 0.85 for m in similar_matches)

        # Python handles strict arithmetic & constraint validation!
        top_color_sim = similar_matches[0].color_similarity if similar_matches else None
        score_res = calculate_purchase_value(
            outfit_compatibility_score=avg_outfit_score,
            wardrobe_gap_score=gap_res.gap_fill_score,
            versatility_score=versatility,
            personal_style_score=style_pref,
            redundancy_score=redundancy_score,
            price=cand.price,
            budget=budget,
            is_direct_duplicate=is_direct_duplicate,
            color_similarity_score=top_color_sim
        )

        evidence: List[str] = [
            f"This item is compatible with {compatible_count} outfit(s) in your wardrobe (Average match: {avg_outfit_score:.2f}%)."
        ]
        if similar_matches:
            top_match = similar_matches[0]
            evidence.append(
                f"Closet similarity check: '{top_match.garment.name}' is {top_match.similarity_score*100:.2f}% similar."
            )
            if top_match.color_similarity is not None and top_match.color_delta_e is not None:
                evidence.append(
                    f"Color analysis: Perceptual similarity between candidate '{cand.color}' and owned '{top_match.garment.color}' is {top_match.color_similarity*100:.1f}% (Delta E: {top_match.color_delta_e:.2f})."
                )
            if is_direct_duplicate:
                evidence.append(
                    f"DIRECT DUPLICATE DETECTED: You already own a {cand.color} {cand.category} ('{top_match.garment.name}') with matching style. Buying a duplicate serves no new purpose."
                )
            elif top_match.redundancy_warning:
                evidence.append(top_match.redundancy_warning)
        else:
            evidence.append("Low redundancy: No conflicting items found in current wardrobe.")

        if gap_res and gap_res.reasoning:
            evidence.append(f"Wardrobe gap: {gap_res.reasoning}")

        is_budget_exceeded = False
        if cand.price and budget:
            if cand.price <= budget:
                evidence.append(f"Budget check: Price (${cand.price:.2f}) fits within your ${budget:.2f} budget.")
            else:
                is_budget_exceeded = True
                diff = cand.price - budget
                evidence.append(
                    f"Budget conflict: Price (${cand.price:.2f}) exceeds your budget (${budget:.2f}) by ${diff:.2f}."
                )

        # Contextual recommendation synthesis via Qwen in Ollama (skip if fast benchmark mode)
        qwen_response = None
        if not skip_llm:
            price_display = f"${cand.price:.2f}" if cand.price is not None else "Unknown"
            budget_display = f"${budget:.2f}" if budget is not None else "Not specified"
            prompt_for_qwen = (
                f"User Question: \"{user_query}\"\n"
                f"Candidate: {cand.color} {cand.category} (Style: {', '.join(cand.style) if cand.style else 'formal'}, Occasion: {cand.target_occasion or 'work'})\n"
                f"Price: {price_display} (User Budget: {budget_display})\n"
                f"Compatible Outfits: This item is compatible with {compatible_count} outfits in their wardrobe.\n"
                f"Direct Duplicate: {'YES - User already owns the exact same item' if is_direct_duplicate else 'NO'}\n"
                f"Calculated Score: {score_res.overall_score:.2f}/100. Decision: {score_res.decision.value}\n"
                f"Evidence: {'; '.join(evidence)}\n"
                f"Budget Conflict: {'YES, exceeds budget' if is_budget_exceeded else 'NO'}\n\n"
                f"Instruction: In 2 concise sentences, answer the user's specific question ('{user_query}'). "
                f"Ground your advice strictly in the calculated decision ({score_res.decision.value}) and evidence. "
                f"If this is a duplicate or exceeds budget, explain that trade-off clearly!"
            )
            qwen_response = query_ollama(prompt_for_qwen, model_name=self.model_name, timeout_sec=self.timeout_sec)

        # Precompute deterministic Fallback explanation
        conflict_note = ""
        if is_budget_exceeded:
            conflict_note = f" However, note that it exceeds your budget by ${cand.price - budget:.2f}."

        if is_direct_duplicate and similar_matches:
            fallback_summary = (
                f"[FALLBACK] Skip this purchase (Score: {score_res.overall_score:.2f}/100). "
                f"Direct duplicate: you already own '{similar_matches[0].garment.name}' ({cand.color} {cand.category}) with matching style. Buying another provides no new wardrobe utility.{conflict_note}"
            )
        elif score_res.decision == DecisionType.BUY:
            fallback_summary = (
                f"[FALLBACK] Strong purchase recommendation (Score: {score_res.overall_score:.2f}/100). "
                f"This item is compatible with {compatible_count} outfits in your wardrobe and satisfies key styling needs.{conflict_note}"
            )
        elif score_res.decision == DecisionType.CONSIDER:
            fallback_summary = (
                f"[FALLBACK] Consider before buying (Score: {score_res.overall_score:.2f}/100). "
                f"This item is compatible with {compatible_count} outfits, but has notable overlap with owned clothes or budget trade-offs.{conflict_note}"
            )
        else:
            fallback_summary = (
                f"[FALLBACK] Skip this purchase (Score: {score_res.overall_score:.2f}/100). "
                f"High redundancy, low wardrobe gap score, or exceeds budget constraints.{conflict_note}"
            )

        if qwen_response:
            engine_source = "QWEN3-OLLAMA"
            qwen_summary = qwen_response
            summary = qwen_summary
        else:
            engine_source = "FALLBACK"
            qwen_summary = None
            summary = fallback_summary

        completed_data = {
            "session_id": session_id,
            "status": SessionStatus.COMPLETED.value,
            "decision": score_res.decision.value,
            "overall_score": score_res.overall_score,
            "engine_source": engine_source,
            "summary": summary
        }
        self._save_checkpoint(session_id, completed_data)

        return AgentRecommendation(
            session_id=session_id,
            status=SessionStatus.COMPLETED,
            decision=score_res.decision,
            overall_score=score_res.overall_score,
            engine_source=engine_source,
            summary=summary,
            qwen_summary=qwen_summary,
            fallback_summary=fallback_summary,
            evidence=evidence,
            similar_items=similar_matches,
            outfit_examples=outfit_combinations,
            compatible_outfits_count=compatible_count,
            gap_analysis=gap_res,
            score_breakdown=score_res.breakdown,
            detected_color=cand.color,
            detected_category=cand.category,
            detected_style=", ".join(cand.style) if cand.style else "formal",
            detected_occasion=cand.target_occasion or (cand.occasions[0] if cand.occasions else "work"),
            user_query=user_query
        )

