"""
Expert Optimized Prompts for Claude 3.5 Sonnet
Production-grade prompts for all features
"""

from typing import Dict, Optional

class OptimizedPrompts:
    """Collection of expert-optimized prompts for Claude"""

    # ========================================================================
    # SYSTEM PROMPTS
    # ========================================================================

    SYSTEM_ANALYZER = """You are a wardrobe advisor inside a purchase-redundancy app. Shoppers use the app
before buying a clothing item, to find out whether they already own something that does the same job.

The app has already computed the numbers (CLIP similarity, a 0-100 redundancy score, category saturation,
outfit contribution) and the recommendation (buy / consider / skip). Your job is to turn those results
into advice a shopper can act on. Treat the computed scores and the recommendation as ground truth:
do not recompute or contradict them, and do not invent owned items that are not listed.

Write like a knowledgeable friend: direct, specific, never judgmental about spending. Refer to the
owned items by name. When the verdict is "buy", say what the item adds; when it is "consider" or
"skip", say which owned item already covers the need and how to restyle it."""

    SYSTEM_AGENT = """You are the personal wardrobe advisor of a French app that helps people stop buying clothes they
already own. You work with tools over the user's real wardrobe (photos analysed by CLIP) and a real product catalog.

<user_profile>
{profile}
</user_profile>

Pick the tools that answer the question:
- The wardrobe as a whole (diagnosis, "is my wardrobe OK", score, advice): get_wardrobe_insights.
- "Should I buy X?": analyze_redundancy on that item (it is the basis of the verdict); search_catalog to compare offers.
- "What should I wear for ...": suggest_outfits with the occasion and season.
- "What should I buy / what is missing / budget": plan_shopping.
- "What should I sell, donate, get rid of": plan_declutter.
- "Does this outfit work / rate my look": score_outfit with the piece ids from get_wardrobe.
- "Are these two pieces the same / too similar": compare_items.
- "Which pieces are duplicates / my closest pieces / what is redundant": get_wardrobe_insights - its duplicate groups
  compare the whole wardrobe with CLIP. Never guess a pair yourself; compare_items can then detail one of its groups.
- Extra angles only when they help (run_feature: 23 quality, 25 resale value, 29 care, 31 market price...).

You can act, not only advise:
- save_outfit when the user asks to save or keep a look.
- propose_remove_items to remove pieces (e.g. the extra pieces of duplicates) and propose_add_items for products the
  user says they bought. These create a proposal card: the user approves or rejects it in the app. Never say a piece
  was removed or added - say that the proposal is waiting for their approval.
- Only propose removing pieces a tool flagged (a duplicate group, compare_items with duplicate true, plan_declutter)
  or that the user named. If compare_items says duplicate false, say the pieces are different and propose nothing.
- Use get_wardrobe first whenever you need piece ids.
Call several tools when the question needs it; do not call tools that add nothing.

Rules:
- Every fact about the wardrobe, a product or a price comes from a tool result. Never invent pieces, brands or prices;
  if something could not be checked, say so.
- Respect the profile: never suggest dresses or heels to a man, use the user's sizes and favorite colors when relevant.
- The conversation may continue: use the earlier turns for context ("and for winter?" refers to the previous question),
  but answer ONLY the latest message - never repeat or summarize an earlier answer, and only call the tools
  this latest question needs.

Answer in French and address the user as "vous" (never "tu"), warm and direct, like a stylist who respects the
user's money:
- start with the conclusion in one sentence (verdict, health score, or the outfit to wear);
- then 2 to 4 short bullet points with the reasons or the steps, naming the actual pieces;
- end with one concrete next action.
Keep it under 150 words. No headings, no tables; the app already shows the tool results as pictures."""

    # ========================================================================
    # FEATURE PROMPTS
    # ========================================================================

    PROMPT_SIMILARITY = """Analyze the visual and functional similarity between these two clothing items.

Item 1:
{item1}

Item 2:
{item2}

Consider:
- Color similarity (exact match, close, different)
- Style similarity (same style category)
- Material similarity (same/similar materials)
- Function similarity (same use case)
- Overall visual resemblance

Provide a similarity score from 0-100 where:
- 0-30: Very different items
- 30-60: Some overlap
- 60-80: Similar items (potential redundancy)
- 80-100: Nearly identical

Format your response as JSON:
{{
    "similarity_score": <number>,
    "color_match": "<exact|close|different>",
    "style_match": "<exact|close|different>",
    "material_match": "<same|similar|different>",
    "function_match": "<same|similar|different>",
    "overall_assessment": "<brief explanation>"
}}"""

    PROMPT_REDUNDANCY = """Calculate the redundancy score for a new clothing item against a user's wardrobe.

New Item:
{new_item}

Wardrobe Context:
- Total items: {wardrobe_count}
- Category distribution: {categories}
- Similar items found: {similar_items}

Calculate redundancy using 4 factors:
1. Visual Redundancy (0-100): How visually similar to existing items
2. Functional Redundancy (0-100): How similar in use case
3. Category Saturation (0-100): % of category already owned
4. Outfit Impact (0-100): How much new variety it adds

Formula: Final Score = (Visual*0.4 + Functional*0.3 + Saturation*0.2 + Impact*0.1)

Interpretation:
- 0-35: Good purchase (low redundancy)
- 35-60: Consider carefully (moderate redundancy)
- 60-80: Redundant (high similarity exists)
- 80-100: Strong redundancy (nearly identical exists)

Provide JSON response:
{{
    "visual_redundancy": <number>,
    "functional_redundancy": <number>,
    "category_saturation": <number>,
    "outfit_impact": <number>,
    "final_score": <number>,
    "recommendation": "<buy|consider|skip>",
    "confidence": <0-1>
}}"""

    PROMPT_EXPLANATION = """<analysis>
Candidate item: {item_name}
Redundancy score: {score}/100 (0-35 low, 35-60 moderate, 60-80 high, 80-100 near-duplicate)
Recommendation: {recommendation}
Category saturation: {saturation}/100
Outfit contribution: {contribution}/100
Similar items already owned:
{similar_items}
</analysis>

Explain this result to the shopper in 2 short paragraphs, plain text, no headings or bullet lists:
1. The verdict and the main reason, naming the most similar owned item if there is one.
2. What to do instead: how to restyle an owned item, or, for a "buy", what new outfits it unlocks.
Keep it under 120 words. Answer in {language}."""

    PROMPT_ALTERNATIVES = """Suggest alternatives from the user's existing wardrobe for a new item.

New Item: {new_item}

Existing Wardrobe:
{wardrobe_items}

Find 2-3 existing items that could serve the same purpose.

Format:
- Item name and reason why it's similar
- How to style it differently to create variety
- When to use it instead of buying the new item

Be specific and practical."""

    # ========================================================================
    # ANALYSIS PROMPTS
    # ========================================================================

    PROMPT_COLOR_HARMONY = """Analyze color harmony for a clothing item in the user's wardrobe.

New Item Color: {new_color}
Existing Colors: {existing_colors}

Do these colors work together?
- Color wheel compatibility
- Seasonal appropriateness
- Overall wardrobe balance

Provide assessment in JSON:
{{
    "color_harmony": <score 0-100>,
    "compatible_with": [<colors>],
    "outfit_suggestions": [<suggested combinations>],
    "verdict": "<good|needs_care|problematic>"
}}"""

    PROMPT_STYLE_CONSISTENCY = """Analyze if a new item maintains style consistency.

New Item: {new_item}
Existing Style Palette: {style_palette}

Questions:
- Does it match the user's style aesthetic?
- Will it fit into existing outfits?
- Does it create jarring contrasts?

Provide consistency score (0-100) and recommendations."""

    PROMPT_BUDGET_OPTIMIZATION = """Calculate optimal budget allocation for wardrobe expansion.

Current Wardrobe Value: ${current_value}
Budget Available: ${budget}
Spending Patterns: {patterns}
Priority Categories: {priorities}

Recommend:
- How much to spend on each category
- Which items to prioritize
- Areas to avoid spending in

Format as JSON with recommendations."""

    PROMPT_SEASONAL_ROTATION = """Create seasonal rotation strategy for wardrobe.

Items: {wardrobe_items}
Current Season: {season}
Climate: {climate}

Recommend:
- What to wear this season
- What to store
- Gap areas to fill

Provide rotation schedule."""

    PROMPT_OUTFIT_MATCHING = """Generate outfit combinations from wardrobe items.

Item to Style: {main_item}
Available Items: {wardrobe}
Occasion: {occasion}

Create 3 outfit combinations:
- Main pieces
- Accessories
- Color harmony explanation
- Occasion suitability

Format each as detailed outfit guide."""

    PROMPT_QUALITY_ASSESSMENT = """Assess quality indicators in a clothing item.

Item: {item}
Material: {material}
Price Point: {price}
Brand: {brand}

Evaluate:
- Material quality
- Construction quality
- Expected durability
- Value for money
- Care requirements

Provide quality score (0-100) and assessment."""

    PROMPT_SUSTAINABILITY = """Assess sustainability factors in clothing choice.

Item: {item}
Brand: {brand}
Material: {material}
Production: {production_info}

Evaluate:
- Material sustainability
- Brand ethics
- Durability/longevity
- End-of-life disposal

Provide sustainability score (0-100) and recommendations."""

    PROMPT_TREND_ANALYSIS = """Analyze trend alignment for a clothing item.

Item: {item}
Current Trends: {trends}
User Age: {age}
User Style: {style}

Questions:
- Is this trendy or timeless?
- Will it still be wearable in 2 years?
- Does it suit the user's style?

Provide trend viability score (0-100)."""

    PROMPT_RESALE_VALUE = """Estimate resale value potential.

Item: {item}
Brand: {brand}
Material: {material}
Condition: {condition}
Market: {market_context}

Estimate:
- Resale value
- Market demand
- Timing for selling
- Where to sell

Provide valuation and recommendations."""

    # ========================================================================
    # HELPER METHODS
    # ========================================================================

    @staticmethod
    def get_system_prompt(prompt_type: str = "analyzer") -> str:
        """Get system prompt by type"""
        prompts = {
            "analyzer": OptimizedPrompts.SYSTEM_ANALYZER,
            "agent": OptimizedPrompts.SYSTEM_AGENT,
        }
        return prompts.get(prompt_type, OptimizedPrompts.SYSTEM_ANALYZER)

    @staticmethod
    def agent_user_message(wardrobe_text: str, question: str, follow_up: bool) -> str:
        """Latest user turn: the wardrobe, then the question in its own tag. In a follow-up, the instruction
        sits right next to the question - a rule in the system prompt alone did not stop GPT-4.1 from
        re-answering the previous turn before the new one."""
        text = f"<wardrobe>\n{wardrobe_text}\n</wardrobe>\n\n<question>\n{question}\n</question>"
        if follow_up:
            text += ("\n\nThis is a follow-up: answer only the <question> above. The earlier messages are context; "
                     "do not repeat or summarize your previous answer.")
        return text

    @staticmethod
    def agent_system(profile: Optional[Dict] = None) -> str:
        """SYSTEM_AGENT with the user's profile filled in (never guess a gender that was not given)"""
        profile = profile or {}
        gender = {"Women": "woman", "Men": "man"}.get(profile.get("gender"), "not specified - do not assume one")
        lines = [f"Gender: {gender}"]
        if profile.get("display_name"):
            lines.append(f"Name: {profile['display_name']}")
        if profile.get("clothing_size"):
            lines.append(f"Clothing size: {profile['clothing_size']}")
        if profile.get("shoe_size"):
            lines.append(f"Shoe size (EU): {profile['shoe_size']}")
        if profile.get("style_preferences"):
            lines.append("Preferred styles: " + ", ".join(profile["style_preferences"]))
        if profile.get("favorite_colors"):
            lines.append("Favorite colors: " + ", ".join(profile["favorite_colors"]))
        return OptimizedPrompts.format_prompt(OptimizedPrompts.SYSTEM_AGENT, profile="\n".join(lines))

    @staticmethod
    def format_prompt(template: str, **kwargs) -> str:
        """Format prompt with variables - raises ValueError if a variable is missing
        (never send a half-formatted prompt to the model)"""
        try:
            return template.format(**kwargs)
        except KeyError as e:
            raise ValueError(f"Missing prompt variable: {e}") from e

    @staticmethod
    def get_all_prompts() -> dict:
        """Get all available prompts"""
        return {
            "SYSTEM_ANALYZER": OptimizedPrompts.SYSTEM_ANALYZER,
            "SYSTEM_AGENT": OptimizedPrompts.SYSTEM_AGENT,
            "PROMPT_SIMILARITY": OptimizedPrompts.PROMPT_SIMILARITY,
            "PROMPT_REDUNDANCY": OptimizedPrompts.PROMPT_REDUNDANCY,
            "PROMPT_EXPLANATION": OptimizedPrompts.PROMPT_EXPLANATION,
            "PROMPT_ALTERNATIVES": OptimizedPrompts.PROMPT_ALTERNATIVES,
            "PROMPT_COLOR_HARMONY": OptimizedPrompts.PROMPT_COLOR_HARMONY,
            "PROMPT_STYLE_CONSISTENCY": OptimizedPrompts.PROMPT_STYLE_CONSISTENCY,
            "PROMPT_BUDGET_OPTIMIZATION": OptimizedPrompts.PROMPT_BUDGET_OPTIMIZATION,
            "PROMPT_SEASONAL_ROTATION": OptimizedPrompts.PROMPT_SEASONAL_ROTATION,
            "PROMPT_OUTFIT_MATCHING": OptimizedPrompts.PROMPT_OUTFIT_MATCHING,
            "PROMPT_QUALITY_ASSESSMENT": OptimizedPrompts.PROMPT_QUALITY_ASSESSMENT,
            "PROMPT_SUSTAINABILITY": OptimizedPrompts.PROMPT_SUSTAINABILITY,
            "PROMPT_TREND_ANALYSIS": OptimizedPrompts.PROMPT_TREND_ANALYSIS,
            "PROMPT_RESALE_VALUE": OptimizedPrompts.PROMPT_RESALE_VALUE,
        }

# ============================================================================
# INITIALIZATION
# ============================================================================

if __name__ == "__main__":
    print("✅ Optimized prompts loaded successfully")
    print(f"   Total prompts: {len(OptimizedPrompts.get_all_prompts())}")
    for name in OptimizedPrompts.get_all_prompts().keys():
        print(f"   - {name}")
