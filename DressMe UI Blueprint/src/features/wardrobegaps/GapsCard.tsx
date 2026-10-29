import { useEffect, useState } from "react";
import { fetchGaps, type GapRanking } from "./api";

const priorityStyle = {
  high: "text-amber-700 bg-amber-50",
  medium: "text-[#556B2F] bg-[#E8EDE0]",
  low: "text-[#8C8A82] bg-[#E2E0D8]",
};

// Dashboard card: live BO3 gaps for the default goal.
export default function GapsCard({ onOpen }: { onOpen: () => void }) {
  const [ranking, setRanking] = useState<GapRanking | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchGaps("winter_work").then(setRanking).catch((e: Error) => setError(e.message));
  }, []);

  return (
    <div className="bg-[#F0EFEA] rounded-xl p-6">
      <div className="flex items-start justify-between">
        <div>
          <h3 className="font-display text-lg font-medium text-[#1C1C1C]">Wardrobe Gaps</h3>
          <p className="text-[#8C8A82] text-xs mt-1 mb-4">
            {ranking?.goal_label ?? "Winter work days"} · ranked by the BO3 agent
          </p>
        </div>
        <button onClick={onOpen} className="text-xs font-semibold text-[#556B2F] hover:underline">
          Open agent →
        </button>
      </div>

      {error && <p className="text-xs text-[#8C8A82]">Gap agent unavailable: {error}</p>}
      {!ranking && !error && <p className="text-xs text-[#8C8A82]">Analysing your wardrobe…</p>}

      {ranking?.ranked_gaps.slice(0, 4).map((gap) => {
        const coverage = Math.round((gap.owned_count / gap.required_count) * 100);
        return (
          <div key={gap.candidate_id} className="mb-3">
            <div className="flex justify-between items-center text-xs mb-1">
              <span className="text-[#1C1C1C] font-medium">
                {gap.rank}. {gap.name}
              </span>
              <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${priorityStyle[gap.priority]}`}>
                {gap.priority} · {gap.owned_count}/{gap.required_count} owned
              </span>
            </div>
            <div className="h-1.5 bg-[#E2E0D8] rounded-full overflow-hidden">
              <div className="h-full bg-[#556B2F] rounded-full" style={{ width: `${coverage}%` }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}
