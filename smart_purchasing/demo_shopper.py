"""Interactive CLI demonstration of the 5-Step Shopper Agent with Checkpointing."""

import time
from schemas import CandidateItem, EvaluatePurchaseRequest
from agent import PurchaseAgent


def run_interactive_demo():
    print("======================================================================")
    print("      DRESSME SHOPPER AGENT — 5-STEP DYNAMIC EVALUATION DEMO")
    print("======================================================================")
    agent = PurchaseAgent()

    print("\n--- STEP 1 & 2: User provides candidate garment (price known, budget unknown) ---")
    candidate = CandidateItem(
        name="Tailored Camel Blazer",
        category="blazer",
        color="camel",
        style=["smart_casual", "formal"],
        seasons=["autumn", "spring"],
        occasions=["work", "dinner"],
        price=149.99,
        # Notice: budget is intentionally left None!
        image_path="data/sample_camel_blazer.jpg"
    )
    print(f"Candidate: {candidate.name} (${candidate.price:.2f})")
    print("Calling Agent: 'Should I buy this camel blazer?'...")

    # First Turn: Steps 1 -> 4
    result = agent.evaluate(EvaluatePurchaseRequest(
        candidate=candidate,
        user_query="Should I buy this camel blazer for work?"
    ))

    print("\n[AGENT OBSERVATIONS SO FAR]:")
    for finding in result.interim_findings:
        print(f" * {finding}")

    if result.clarification_question:
        print(f"\n[STEP 4: AGENT ASKS CLARIFYING QUESTION (Checkpointed)]")
        print(f"  Session ID: {result.session_id}")
        print(f"  Status: {result.status.value}")
        print(f"  Question: \"{result.clarification_question}\"")

        print("\n--- Simulating User Response ---")
        user_answer = "My budget is $150"
        print(f"User replies: \"{user_answer}\"")

        print("\n--- STEP 5: Resuming from checkpoint, calculating score & calling Qwen ---")
        time.sleep(1)
        final_result = agent.evaluate(EvaluatePurchaseRequest(
            session_id=result.session_id,
            user_response=user_answer
        ))

        print(f"\n[ENGINE ATTRIBUTION]: [{final_result.engine_source}]")
        print(f"[FINAL DECISION]: {final_result.decision.value} (Score: {final_result.overall_score}/100)")
        print(f"\n[AGENT EXPLANATION]:\n\"{final_result.summary}\"")

        print(f"\n[OUTFIT COMPATIBILITY]:")
        count = final_result.compatible_outfits_count or len(final_result.outfit_examples)
        print(f" * This item is compatible with {count} outfit(s) in your wardrobe.")
        for outfit in final_result.outfit_examples:
            print(f"   - {outfit.description} (Compatibility: {outfit.compatibility_score:.0f}%)")

        print("\n[GROUNDED EVIDENCE]:")
        for ev in final_result.evidence:
            print(f" * {ev}")

    print("\n======================================================================")
    print("Demo completed successfully!")


if __name__ == "__main__":
    run_interactive_demo()
