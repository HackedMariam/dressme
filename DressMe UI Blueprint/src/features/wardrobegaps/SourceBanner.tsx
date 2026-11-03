import type { GapRanking } from "./api";

// Tells the user when the analysed wardrobe is not their real one, or when nothing could be analysed.
export default function SourceBanner({ ranking }: { ranking: GapRanking }) {
  const wardrobe = ranking.wardrobe_source;
  if (wardrobe && wardrobe.source !== "supabase" && wardrobe.message) {
    const blocked = wardrobe.source === "empty" || wardrobe.source === "error";
    return (
      <div
        role="status"
        className={`rounded-xl border px-4 py-2.5 text-xs ${
          blocked ? "border-[#E6C9BA] bg-[#F7ECE6] text-[#9A5A3C]" : "border-[#E2D6BE] bg-[#F6EFE4] text-[#6B5B3E]"
        }`}
      >
        <strong className="font-semibold">{blocked ? "No analysis" : "Sample data"}</strong> · {wardrobe.message}
      </div>
    );
  }
  if (ranking.profile_source === "default") {
    return (
      <div role="status" className="rounded-xl border border-[#E2E0D8] bg-white px-4 py-2.5 text-xs text-[#8C8A82]">
        Your style preferences are empty, so suggestions are not personalised yet. Fill in your style profile to improve them.
      </div>
    );
  }
  return null;
}
