import { useEffect, useMemo, useState } from "react";

import {
  continueTrip,
  createTrip,
  getGapAnalysis,
  getTrip,
  updateChecklist,
  updateTrip,
  type ChecklistItem,
  type DailyRequirement,
  type GapAnalysisResponse,
  type TripDetails,
  type TripPayload,
} from "../../api/tripAgent";
import { useAuth } from "../auth/AuthProvider";
import { useUserData } from "../profile/UserDataProvider";
import { dayLabels, readableSuggestion, recoveryItems, recoveryReason } from "./recovery";
import OutfitRepeatOption from "./OutfitRepeatOption";

const SESSION_KEY = "dressme.trip.session";

const TRIP_TYPE_ACTIVITIES: Record<string, string[]> = {
  Leisure: ["sightseeing", "shopping"],
  Business: ["business-meeting"],
  "Business + Leisure": ["business-meeting", "sightseeing", "shopping"],
  Adventure: ["hiking", "sightseeing"],
  Beach: ["beach", "sightseeing"],
  "Formal Event": ["formal-dinner", "sightseeing"],
};

const DRESS_CODE_VALUES: Record<string, string> = {
  Casual: "casual",
  "Smart Casual": "smart-casual",
  "Business Casual": "smart-casual",
  Formal: "formal",
  "Black Tie": "formal",
  Mixed: "",
};

const BAG_LIMITS_KG: Record<string, number> = {
  "Personal Item Only": 4,
  "1 Carry-On": 8,
  "1 Checked Bag": 15,
  "2 Checked Bags": 23,
  "No Limit": 30,
};

const DRESS_CODE_OPTIONS = [
  "Casual",
  "Smart Casual",
  "Business Casual",
  "Formal",
  "Black Tie",
  "Mixed",
];

const TRIP_TYPE_OPTIONS = [
  "Leisure",
  "Business",
  "Business + Leisure",
  "Adventure",
  "Beach",
  "Formal Event",
];

const BAG_OPTIONS = [
  "Personal Item Only",
  "1 Carry-On",
  "1 Checked Bag",
  "2 Checked Bags",
  "No Limit",
];

const SAMPLE_AI_TEXT =
  "I'm going to Paris for 5 days in November. I'll be sightseeing, shopping, and attending a formal dinner. I have an 8 kg luggage limit.";

function formatDate(value: string | null | undefined) {
  if (!value) return "—";
  const date = new Date(`${value}T00:00:00`);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function formatDay(value: string | null | undefined) {
  if (!value) return "—";
  const date = new Date(`${value}T00:00:00`);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
  });
}

function humanize(value: string) {
  return value.replace(/-/g, " ");
}

function weatherIcon(weather: string) {
  switch (weather.toLowerCase()) {
    case "sunny":
    case "hot":
      return "☀️";
    case "rainy":
      return "🌧️";
    case "snow":
    case "cold":
      return "❄️";
    case "windy":
      return "💨";
    default:
      return "⛅";
  }
}

function statusLabel(status: string) {
  switch (status) {
    case "optimized":
      return "Capsule Ready";
    case "infeasible":
      return "Needs Adjustments";
    case "needs_clarification":
      return "Needs Details";
    case "optimizing":
      return "Optimizing";
    case "failed":
      return "Failed";
    default:
      return status.replace(/_/g, " ");
  }
}

function statusClass(status: string) {
  if (status === "optimized") return "bg-[#E8EDE0] text-[#556B2F]";
  if (status === "infeasible") return "bg-amber-50 text-amber-700";
  if (status === "failed") return "bg-red-50 text-red-700";
  return "bg-white/10 text-white/70";
}

function inferTripType(activities: string[] | undefined) {
  if (!activities?.length) return "Business + Leisure";
  if (activities.includes("beach")) return "Beach";
  if (activities.includes("hiking")) return "Adventure";
  if (activities.includes("formal-dinner")) return "Formal Event";
  if (activities.includes("business-meeting")) return "Business";
  return "Leisure";
}

function inferBags(weight: number | null | undefined) {
  if (!weight) return "1 Carry-On";
  const closest = BAG_OPTIONS.reduce((best, option) =>
    Math.abs(BAG_LIMITS_KG[option] - weight) <
    Math.abs(BAG_LIMITS_KG[best] - weight)
      ? option
      : best,
  );
  return closest;
}

function inferDressCode(value: string | null | undefined) {
  if (!value) return "Smart Casual";
  if (value === "formal") return "Formal";
  if (value === "casual") return "Casual";
  if (value === "sporty") return "Casual";
  return "Smart Casual";
}

function protectionBadges(requirement: DailyRequirement | undefined) {
  if (!requirement) return [];
  const badges: string[] = [];
  if (requirement.needs_outerwear) badges.push("Outerwear");
  if (requirement.needs_warm_layer) badges.push("Warm layer");
  if (requirement.needs_rain_protection) badges.push("Rain protection");
  if (requirement.needs_sun_protection) badges.push("Sun protection");
  return badges;
}

export default function HelpMePack({ onOpenWardrobe }: { onOpenWardrobe: () => void }) {
  const { user } = useAuth();
  const { preferences } = useUserData();
  const preferredDressCode = preferences?.preferred_styles?.some((style) => ["formal", "elegant"].includes(style.toLowerCase()))
    ? "Formal"
    : preferences?.preferred_styles?.some((style) => ["casual", "sporty"].includes(style.toLowerCase()))
      ? "Casual" : "Smart Casual";
  const sessionKey = `${SESSION_KEY}.${user?.id || "local"}`;
  const [inputMode, setInputMode] = useState<"manual" | "ai">("manual");
  const [destination, setDestination] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [tripType, setTripType] = useState("Business + Leisure");
  const [dresscode, setDresscode] = useState(preferredDressCode);
  const [bags, setBags] = useState("1 Carry-On");
  const [aiText, setAiText] = useState("");
  const [sessionId, setSessionId] = useState<string | null>(() =>
    localStorage.getItem(sessionKey),
  );
  const [trip, setTrip] = useState<TripPayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [restoring, setRestoring] = useState(() =>
    Boolean(localStorage.getItem(sessionKey)),
  );
  const [error, setError] = useState<string | null>(null);
  const [clarification, setClarification] = useState("");
  const [editing, setEditing] = useState(false);
  const [gap, setGap] = useState<GapAnalysisResponse | null>(null);
  const [gapLoading, setGapLoading] = useState(false);
  const [packingItem, setPackingItem] = useState<string | null>(null);

  const prefillForm = (details: TripDetails | null | undefined) => {
    if (!details) return;
    setDestination(details.destination || "");
    setStartDate(details.start_date || "");
    setEndDate(details.end_date || "");
    setTripType(inferTripType(details.activities));
    setDresscode(inferDressCode(details.dress_code));
    setBags(inferBags(details.max_luggage_weight_kg));
  };

  useEffect(() => {
    const stored = localStorage.getItem(sessionKey);
    if (!stored) {
      setRestoring(false);
      return;
    }
    let active = true;
    getTrip(stored)
      .then((payload) => {
        if (!active) return;
        setTrip(payload);
        setSessionId(payload.session_id);
        prefillForm(payload.trip_details);
      })
      .catch(() => {
        if (!active) return;
        localStorage.removeItem(sessionKey);
        setSessionId(null);
      })
      .finally(() => {
        if (active) setRestoring(false);
      });
    return () => {
      active = false;
    };
    // Restore only once on mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionKey]);

  const requirementsByDay = useMemo(() => {
    const map = new Map<number, DailyRequirement>();
    for (const requirement of trip?.daily_requirements || []) {
      map.set(requirement.day_number, requirement);
    }
    return map;
  }, [trip]);

  const applyResponse = (payload: TripPayload) => {
    setTrip(payload);
    setSessionId(payload.session_id);
    localStorage.setItem(sessionKey, payload.session_id);
    prefillForm(payload.trip_details);
    setGap(null);
    setClarification("");
    setEditing(false);
    if (payload.status === "failed") {
      setError(
        payload.errors[payload.errors.length - 1] ||
          "The Trip Agent could not complete the plan.",
      );
    } else {
      setError(null);
    }
  };

  const buildStructuredTrip = (): Record<string, unknown> => ({
    destination: destination.trim() || null,
    start_date: startDate || null,
    end_date: endDate || null,
    activities: TRIP_TYPE_ACTIVITIES[tripType] || ["sightseeing"],
    dress_code: DRESS_CODE_VALUES[dresscode] || null,
    max_luggage_weight_kg: BAG_LIMITS_KG[bags] || 8,
  });

  const submitManual = async () => {
    setLoading(true);
    setError(null);
    setGap(null);
    try {
      const payload = buildStructuredTrip();
      const response = sessionId
        ? await updateTrip(sessionId, payload, true)
        : await createTrip({ mode: "structured", trip: payload });
      applyResponse(response);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to reach the Trip Agent.");
    } finally {
      setLoading(false);
    }
  };

  const submitAi = async () => {
    if (!aiText.trim()) {
      setError("Describe your trip first, or switch to the manual form.");
      return;
    }
    setLoading(true);
    setError(null);
    setGap(null);
    try {
      const response =
        sessionId && trip?.status === "needs_clarification"
          ? await continueTrip(sessionId, aiText)
          : await createTrip({ mode: "text", text: aiText });
      applyResponse(response);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to reach the Trip Agent.");
    } finally {
      setLoading(false);
    }
  };

  const submitClarification = async () => {
    if (!sessionId || !clarification.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const response = await continueTrip(sessionId, clarification);
      applyResponse(response);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to continue this trip.");
    } finally {
      setLoading(false);
    }
  };

  const togglePacked = async (item: ChecklistItem, packed: boolean) => {
    if (!sessionId) return;
    setPackingItem(item.item_id);
    setError(null);
    try {
      const response = await updateChecklist(sessionId, item.item_id, packed);
      setTrip((current) =>
        current
          ? {
              ...current,
              checklist: response.checklist,
              capsule: current.capsule
                ? { ...current.capsule, checklist: response.checklist }
                : null,
            }
          : current,
      );
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to update the checklist.");
    } finally {
      setPackingItem(null);
    }
  };

  const requestGapAnalysis = async () => {
    if (!sessionId) return;
    setGapLoading(true);
    setError(null);
    try {
      setGap(await getGapAnalysis(sessionId));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Gap analysis failed.");
    } finally {
      setGapLoading(false);
    }
  };

  const startEditing = () => {
    prefillForm(trip?.trip_details);
    setInputMode("manual");
    setEditing(true);
    setGap(null);
  };

  const retryWithWardrobe = async (allowOutfitRepeats = false) => {
    if (!sessionId) return;
    setLoading(true);
    setError(null);
    try {
      const updates = allowOutfitRepeats ? { allow_outfit_repeats: true } : {};
      applyResponse(await updateTrip(sessionId, updates, true));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to retry the trip.");
    } finally {
      setLoading(false);
    }
  };

  const startNewTrip = () => {
    localStorage.removeItem(sessionKey);
    setSessionId(null);
    setTrip(null);
    setEditing(false);
    setGap(null);
    setError(null);
    setClarification("");
    setAiText("");
    setInputMode("manual");
    setDestination("");
    setStartDate("");
    setEndDate("");
    setTripType("Business + Leisure");
    setDresscode(preferredDressCode);
    setBags("1 Carry-On");
  };

  const showForm = !trip || trip.status === "needs_clarification" || editing;
  const capsule = trip?.capsule || null;
  const weather = trip?.weather || null;
  const syntheticWeather =
    weather?.source === "synthetic_fallback" ||
    Boolean(weather?.days.some((day) => day.synthetic));
  const checklist = trip?.checklist || capsule?.checklist || null;
  const missingItems = trip ? recoveryItems(trip.missing_items, trip.suggestions || []) : [];
  const oldPackingService = !!trip && (
    trip.missing_items === undefined || trip.can_repeat_outfits === undefined ||
    typeof trip.trip_details?.allow_outfit_repeats !== "boolean"
  );

  if (restoring) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="font-display text-3xl font-semibold text-[#1C1C1C]">Help Me Pack</h1>
          <p className="text-[#8C8A82] text-sm mt-1">Restoring your saved trip…</p>
        </div>
        <div className="bg-[#F0EFEA] rounded-xl p-10 text-sm text-[#8C8A82]">
          Loading your Trip Agent session.
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-3xl font-semibold text-[#1C1C1C]">Help Me Pack</h1>
        <p className="text-[#8C8A82] text-sm mt-1">
          Smart packing optimized by your Trip Agent and deterministic OR-Tools solver
        </p>
      </div>

      {error && (
        <div className="flex items-start justify-between gap-4 rounded-xl border border-red-200 bg-red-50 px-5 py-4">
          <p className="text-sm text-red-700">{error}</p>
          <button
            onClick={() => setError(null)}
            className="text-xs font-semibold text-red-700/70 hover:text-red-700"
          >
            Dismiss
          </button>
        </div>
      )}

      {trip?.errors && trip.errors.length > 0 && trip.status !== "failed" && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 px-5 py-4">
          <p className="text-xs font-semibold uppercase tracking-widest text-amber-700">
            Agent warnings
          </p>
          {trip.errors.slice(-3).map((item) => (
            <p key={item} className="mt-1 text-xs text-amber-700/80">
              {item}
            </p>
          ))}
        </div>
      )}

      {showForm && (
        <div className="grid grid-cols-[1fr_360px] gap-6">
          <div className="bg-[#F0EFEA] rounded-xl p-8 space-y-5">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <h2 className="font-display text-xl font-medium text-[#1C1C1C]">
                  {editing ? "Edit Trip" : "Trip Details"}
                </h2>
                <p className="text-xs text-[#8C8A82] mt-1">
                  Fill the form, or describe the trip and let the agent extract it.
                </p>
              </div>
              <div className="flex rounded-lg border border-[#E2E0D8] bg-white p-1">
                <button
                  onClick={() => setInputMode("manual")}
                  className={`rounded-md px-3 py-1.5 text-xs font-semibold transition-colors ${
                    inputMode === "manual"
                      ? "bg-[#1C1C1C] text-white"
                      : "text-[#8C8A82] hover:text-[#1C1C1C]"
                  }`}
                >
                  Manual form
                </button>
                <button
                  onClick={() => setInputMode("ai")}
                  disabled={editing}
                  className={`rounded-md px-3 py-1.5 text-xs font-semibold transition-colors ${
                    inputMode === "ai"
                      ? "bg-[#1C1C1C] text-white"
                      : "text-[#8C8A82] hover:text-[#1C1C1C]"
                  } disabled:cursor-not-allowed disabled:opacity-40`}
                >
                  AI description
                </button>
              </div>
            </div>

            {inputMode === "manual" ? (
              <>
                <div>
                  <label className="text-xs font-semibold text-[#8C8A82] uppercase tracking-widest block mb-2">
                    Destination
                  </label>
                  <input
                    value={destination}
                    onChange={(event) => setDestination(event.target.value)}
                    placeholder="City or country"
                    className="w-full px-4 py-3 bg-white border border-[#E2E0D8] rounded-lg text-sm text-[#1C1C1C] outline-none focus:border-[#556B2F] transition-colors"
                  />
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="text-xs font-semibold text-[#8C8A82] uppercase tracking-widest block mb-2">
                      Start date
                    </label>
                    <input
                      type="date"
                      value={startDate}
                      onChange={(event) => setStartDate(event.target.value)}
                      className="w-full px-4 py-3 bg-white border border-[#E2E0D8] rounded-lg text-sm text-[#1C1C1C] outline-none focus:border-[#556B2F] transition-colors"
                    />
                  </div>
                  <div>
                    <label className="text-xs font-semibold text-[#8C8A82] uppercase tracking-widest block mb-2">
                      End date
                    </label>
                    <input
                      type="date"
                      value={endDate}
                      onChange={(event) => setEndDate(event.target.value)}
                      className="w-full px-4 py-3 bg-white border border-[#E2E0D8] rounded-lg text-sm text-[#1C1C1C] outline-none focus:border-[#556B2F] transition-colors"
                    />
                  </div>
                </div>

                {[
                  {
                    label: "Trip Type",
                    value: tripType,
                    set: setTripType,
                    opts: TRIP_TYPE_OPTIONS,
                  },
                  {
                    label: "Dress Code",
                    value: dresscode,
                    set: setDresscode,
                    opts: DRESS_CODE_OPTIONS,
                  },
                  {
                    label: "Luggage Limit",
                    value: bags,
                    set: setBags,
                    opts: BAG_OPTIONS,
                  },
                ].map((field) => (
                  <div key={field.label}>
                    <label className="text-xs font-semibold text-[#8C8A82] uppercase tracking-widest block mb-2">
                      {field.label}
                    </label>
                    <select
                      value={field.value}
                      onChange={(event) => field.set(event.target.value)}
                      className="w-full px-4 py-3 bg-white border border-[#E2E0D8] rounded-lg text-sm text-[#1C1C1C] outline-none focus:border-[#556B2F] transition-colors"
                    >
                      {field.opts.map((option) => (
                        <option key={option}>{option}</option>
                      ))}
                    </select>
                  </div>
                ))}
              </>
            ) : (
              <>
                <div>
                  <div className="flex items-center justify-between gap-3 mb-2">
                    <label className="text-xs font-semibold text-[#8C8A82] uppercase tracking-widest">
                      Describe your trip
                    </label>
                    <button
                      onClick={() => setAiText(SAMPLE_AI_TEXT)}
                      className="text-xs font-semibold text-[#556B2F] hover:underline"
                    >
                      Use example
                    </button>
                  </div>
                  <textarea
                    value={aiText}
                    onChange={(event) => setAiText(event.target.value)}
                    rows={7}
                    placeholder="I'm going to Paris for 5 days in November. I'll be sightseeing, shopping, and attending a formal dinner. I have an 8 kg luggage limit."
                    className="w-full resize-none px-4 py-3 bg-white border border-[#E2E0D8] rounded-lg text-sm text-[#1C1C1C] outline-none focus:border-[#556B2F] transition-colors"
                  />
                </div>
                <div className="rounded-lg bg-white/60 border border-[#E2E0D8] px-4 py-3">
                  <p className="text-xs text-[#8C8A82]">
                    The agent will extract destination, dates, activities, dress code, and luggage
                    limit. If something essential is missing, it will ask a follow-up question.
                  </p>
                </div>
              </>
            )}

            <button
              onClick={inputMode === "manual" ? submitManual : submitAi}
              disabled={loading}
              className="w-full bg-[#1C1C1C] hover:bg-[#333] disabled:bg-[#8C8A82] text-white font-semibold py-3.5 rounded-lg transition-colors mt-2"
            >
              {loading
                ? "Trip Agent is working…"
                : editing
                  ? "Update & Reoptimize"
                  : "Generate Pack List"}
            </button>
            {sessionId && (
              <button
                onClick={startNewTrip}
                className="w-full text-xs text-[#8C8A82] hover:text-[#1C1C1C] transition-colors"
              >
                Start a new trip instead
              </button>
            )}
          </div>

          <div className="space-y-4">
            <div className="bg-[#1C1C1C] rounded-xl overflow-hidden h-48">
              <img
                src="https://images.unsplash.com/photo-1683392969197-17547ac3e06e?w=600&h=800&fit=crop&auto=format"
                alt="Travel fashion"
                className="w-full h-full object-cover opacity-60"
              />
            </div>
            <div className="bg-[#F0EFEA] rounded-xl p-5">
              <p className="text-xs font-semibold text-[#8C8A82] uppercase tracking-widest mb-3">
                Packing Intelligence
              </p>
              {[
                "Removes redundant items",
                "Maximizes outfit combinations",
                "Weather-aware selection",
                "Daily look generator",
              ].map((feature) => (
                <div
                  key={feature}
                  className="flex items-center gap-2 py-2 border-b border-[#E2E0D8] last:border-0"
                >
                  <span className="text-[#556B2F] text-sm">✓</span>
                  <span className="text-sm text-[#1C1C1C]">{feature}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {trip?.status === "needs_clarification" && (
        <div className="rounded-xl border border-[#556B2F]/30 bg-white p-6 space-y-3">
          <p className="text-xs font-semibold uppercase tracking-widest text-[#556B2F]">
            The agent needs one more detail
          </p>
          <p className="text-sm text-[#1C1C1C]">
            {trip.clarification_question ||
              trip.message ||
              "I need a little more information before I can build your capsule."}
          </p>
          <div className="flex gap-3">
            <input
              value={clarification}
              onChange={(event) => setClarification(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") void submitClarification();
              }}
              placeholder="Type the missing detail…"
              className="flex-1 px-4 py-2.5 bg-[#F0EFEA] border border-[#E2E0D8] rounded-lg text-sm text-[#1C1C1C] outline-none focus:border-[#556B2F] transition-colors"
            />
            <button
              onClick={() => void submitClarification()}
              disabled={loading || !clarification.trim()}
              className="bg-[#556B2F] hover:bg-[#6B8A3A] disabled:bg-[#8C8A82] text-white px-5 py-2.5 rounded-lg text-sm font-semibold transition-colors"
            >
              {loading ? "Sending…" : "Send answer"}
            </button>
          </div>
          <p className="text-[10px] text-[#8C8A82]">
            Session {sessionId || "not created"} · your answers stay in the same trip session.
          </p>
        </div>
      )}

      {!showForm && trip && (
        <>
          <div className="bg-[#1C1C1C] rounded-xl p-6 space-y-5">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <p className="text-[#556B2F] text-xs font-semibold uppercase tracking-widest">
                  {statusLabel(trip.status)}
                </p>
                <h2 className="font-display text-2xl font-medium text-white mt-1">
                  {capsule?.trip.destination || trip.trip_details?.destination || "Your trip"} ·{" "}
                  {capsule
                    ? `${formatDate(capsule.trip.start_date)} – ${formatDate(capsule.trip.end_date)}`
                    : trip.trip_details
                      ? `${formatDate(trip.trip_details.start_date)} – ${formatDate(trip.trip_details.end_date)}`
                      : "Dates pending"}
                </h2>
                <p className="text-white/50 text-sm mt-1">
                  {(capsule?.trip.activities || trip.trip_details?.activities || [])
                    .map(humanize)
                    .join(" · ") || "Activities pending"}
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  onClick={() => void requestGapAnalysis()}
                  disabled={gapLoading || !capsule}
                  className="text-white/70 hover:text-white disabled:text-white/30 text-xs border border-white/20 rounded-lg px-4 py-2 transition-colors"
                >
                  {gapLoading ? "Checking gaps…" : "Gap analysis"}
                </button>
                <button
                  onClick={startEditing}
                  className="text-white/70 hover:text-white text-xs border border-white/20 rounded-lg px-4 py-2 transition-colors"
                >
                  Edit trip
                </button>
                <button
                  onClick={startNewTrip}
                  className="text-white/70 hover:text-white text-xs border border-white/20 rounded-lg px-4 py-2 transition-colors"
                >
                  New trip
                </button>
              </div>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div className="rounded-lg bg-white/5 px-4 py-3">
                <p className="text-white/40 text-[10px] uppercase tracking-widest">Status</p>
                <p className="text-white text-sm font-semibold mt-1">
                  {trip.status === "infeasible" ? "Needs attention" : capsule?.optimization_status || trip.optimization_status || "Pending"}
                </p>
              </div>
              <div className="rounded-lg bg-white/5 px-4 py-3">
                <p className="text-white/40 text-[10px] uppercase tracking-widest">Unique items</p>
                <p className="text-white text-sm font-semibold mt-1">
                  {capsule?.number_of_items ?? "—"}
                </p>
              </div>
              <div className="rounded-lg bg-white/5 px-4 py-3">
                <p className="text-white/40 text-[10px] uppercase tracking-widest">Clothing weight</p>
                <p className="text-white text-sm font-semibold mt-1">
                  {capsule ? `${(capsule.total_weight_g / 1000).toFixed(2)} kg` : "—"}
                </p>
              </div>
              <div className="rounded-lg bg-white/5 px-4 py-3">
                <p className="text-white/40 text-[10px] uppercase tracking-widest">Weather source</p>
                <p className="text-white text-sm font-semibold mt-1">
                  {weather?.source === "open-meteo" ? "Open-Meteo" : "Synthetic fallback"}
                </p>
              </div>
            </div>
            {capsule?.metadata?.weight_estimated === true && (
              <p className="mt-3 text-xs text-amber-200">Garment weights and compatibility are estimates based on available wardrobe data.</p>
            )}

            {syntheticWeather && (
              <div className="rounded-lg border border-amber-300/30 bg-amber-300/10 px-4 py-3">
                <p className="text-xs font-semibold text-amber-200">Synthetic weather in use</p>
                <p className="text-xs text-amber-100/70 mt-1">
                  {weather?.warning ||
                    "A forecast was unavailable for these dates, so explicitly labeled synthetic weather was used."}
                </p>
              </div>
            )}
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-[1fr_360px] gap-6">
            <div className="bg-[#F0EFEA] rounded-xl p-6">
              <div className="flex items-center justify-between gap-4 mb-4">
                <div>
                  <p className="text-xs font-semibold text-[#8C8A82] uppercase tracking-widest">
                    Extracted trip details
                  </p>
                  <h3 className="font-display text-lg font-medium text-[#1C1C1C] mt-1">
                    What the agent understood
                  </h3>
                </div>
                <span
                  className={`text-[10px] font-semibold px-2.5 py-1 rounded-full ${statusClass(trip.status)}`}
                >
                  {statusLabel(trip.status)}
                </span>
              </div>
              <div className="grid grid-cols-2 gap-4">
                {[
                  ["Destination", trip.trip_details?.destination || "—"],
                  ["Duration", trip.trip_details?.duration_days ? `${trip.trip_details.duration_days} days` : "—"],
                  ["Dress code", trip.trip_details?.dress_code || "—"],
                  ["Luggage limit", trip.trip_details?.max_luggage_weight_kg ? `${trip.trip_details.max_luggage_weight_kg} kg` : "—"],
                ].map(([label, value]) => (
                  <div key={label}>
                    <p className="text-[10px] text-[#8C8A82] uppercase tracking-widest">{label}</p>
                    <p className="text-sm font-medium text-[#1C1C1C] mt-1">{value}</p>
                  </div>
                ))}
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                {(trip.trip_details?.activities || []).map((activity) => (
                  <span
                    key={activity}
                    className="rounded-full bg-white px-3 py-1 text-[11px] font-medium text-[#556B2F]"
                  >
                    {humanize(activity)}
                  </span>
                ))}
              </div>
            </div>

            <div className="bg-[#F0EFEA] rounded-xl p-6">
              <p className="text-xs font-semibold text-[#8C8A82] uppercase tracking-widest">
                Weather
              </p>
              {weather?.resolved_name && (
                <p className="mt-1 text-[10px] text-[#8C8A82]">
                  Forecast location: {weather.resolved_name}
                  {weather.resolved_country ? `, ${weather.resolved_country}` : ""}
                  {weather.requested_country ? " · country-level request" : ""}
                </p>
              )}
              {weather?.geocoding_note && !syntheticWeather && (
                <p className="mt-2 rounded-lg bg-white px-3 py-2 text-[10px] text-[#8C8A82]">
                  {weather.geocoding_note}
                </p>
              )}
              {weather?.days.length ? (
                <div className="mt-3 space-y-2">
                  {weather.days.map((day) => (
                    <div
                      key={`${day.date}-${day.weather}`}
                      className="flex items-center gap-3 rounded-lg bg-white px-3 py-2"
                    >
                      <span className="text-lg">{weatherIcon(day.weather)}</span>
                      <div className="min-w-0 flex-1">
                        <p className="text-xs font-semibold text-[#1C1C1C]">
                          {formatDay(day.date)}
                        </p>
                        <p className="text-[10px] text-[#8C8A82] capitalize">
                          {day.weather} · {Math.round(day.temperature_c)}°C ·{" "}
                          {day.precipitation_mm.toFixed(1)} mm
                        </p>
                      </div>
                      {day.synthetic && (
                        <span className="rounded-full bg-amber-50 px-2 py-0.5 text-[9px] font-semibold text-amber-700">
                          synthetic
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-[#8C8A82] mt-3">Weather is not available yet.</p>
              )}
            </div>
          </div>

          {trip.status === "infeasible" ? (
            <div className="space-y-4">
              <section className="rounded-xl border border-amber-200 bg-amber-50 p-6">
                <p className="text-xs font-semibold uppercase tracking-widest text-amber-700">Let’s finish your packing plan</p>
                <h3 className="mt-2 font-display text-xl font-semibold text-[#1C1C1C]">Here’s what needs attention</h3>
                <p className="mt-2 text-sm leading-relaxed text-amber-900">
                  Your current wardrobe doesn’t yet provide a suitable plan for every day. Here’s what you can do next.
                </p>

                {missingItems.length > 0 && (
                  <div className="mt-5 space-y-3">
                    {missingItems.map((item) => (
                      <article key={item.key} className="rounded-xl border border-amber-100 bg-white p-4">
                        <div className="flex flex-wrap items-start justify-between gap-2">
                          <p className="text-sm font-semibold text-[#1C1C1C]">{item.title}</p>
                          {item.days.length > 0 && <span className="rounded-full bg-amber-50 px-2.5 py-1 text-xs font-semibold text-amber-800">{dayLabels(item.days)}</span>}
                        </div>
                        <p className="mt-2 text-sm leading-relaxed text-[#4C4A45]">{recoveryReason(item, trip.daily_requirements || [])}</p>
                        {item.key === "rain" && item.covers.includes("outerwear") && (
                          <p className="mt-2 text-xs leading-relaxed text-[#4C4A45]">The same raincoat can also serve as an outer layer on other days that need one.</p>
                        )}
                        <p className="mt-3 text-xs leading-relaxed text-[#4C4A45]"><b>For example:</b> {item.examples.join(" or ")}.</p>
                        {item.note && <p className="mt-2 text-xs leading-relaxed text-[#6C5A32]">{item.note}</p>}
                      </article>
                    ))}
                    <p className="text-xs leading-relaxed text-amber-900">Add something you own, or update its details if it is already in your wardrobe. Then retry the same trip.</p>
                  </div>
                )}

                {missingItems.length === 0 && (trip.suggestions || []).length > 0 && (
                  <div className="mt-5 space-y-2">
                    {(trip.suggestions || []).map((suggestion) => (
                      <p key={suggestion} className="rounded-lg bg-white px-4 py-3 text-sm leading-relaxed text-[#4C4A45]">
                        {readableSuggestion(suggestion)}
                      </p>
                    ))}
                  </div>
                )}

                <div className="mt-5 flex flex-wrap gap-2">
                  <button onClick={onOpenWardrobe} className="rounded-lg bg-[#1C1C1C] px-4 py-2.5 text-xs font-semibold text-white hover:bg-[#333]">Open wardrobe</button>
                  <button onClick={() => void retryWithWardrobe()} disabled={loading} className="rounded-lg bg-[#556B2F] px-4 py-2.5 text-xs font-semibold text-white hover:bg-[#6B8A3A] disabled:opacity-50">
                    {loading ? "Checking wardrobe…" : "Retry this trip"}
                  </button>
                  <button onClick={startEditing} className="rounded-lg border border-amber-200 bg-white px-4 py-2.5 text-xs font-semibold text-amber-900">Edit trip</button>
                  <button onClick={startNewTrip} className="rounded-lg border border-amber-200 bg-white px-4 py-2.5 text-xs font-semibold text-amber-900">Start over</button>
                </div>

                <OutfitRepeatOption
                  allowed={trip.trip_details?.allow_outfit_repeats === true}
                  confirmed={trip.can_repeat_outfits === true}
                  legacyService={oldPackingService}
                  otherRequirements={missingItems.some((item) => item.key !== "variety")}
                  loading={loading}
                  onAllow={() => void retryWithWardrobe(true)}
                />
              </section>

              {trip.daily_requirements.length > 0 && (
                <div className="bg-[#F0EFEA] rounded-xl p-6">
                  <h3 className="font-display text-lg font-semibold text-[#1C1C1C]">What the plan checks</h3>
                  <div className="mt-3 grid gap-2 text-xs leading-relaxed text-[#4C4A45] sm:grid-cols-2">
                    <p className="rounded-lg bg-white p-3"><b>Complete outfit:</b> Shoes plus either a dress or a top and bottom.</p>
                    <p className="rounded-lg bg-white p-3"><b>Weather:</b> Each day needs the protection listed below.</p>
                    <p className="rounded-lg bg-white p-3"><b>Luggage:</b> Estimated clothing weight must fit within {trip.trip_details?.max_luggage_weight_kg ?? "your"} kg.</p>
                    <p className="rounded-lg bg-white p-3"><b>Outfit repeats:</b> {trip.trip_details?.allow_outfit_repeats ? "Allowed." : "Different complete outfits are required unless you allow repeats."}</p>
                  </div>
                  <p className="mt-5 text-xs font-semibold uppercase tracking-widest text-[#8C8A82]">Weather and activities by day</p>
                  <div className="grid grid-cols-2 gap-3 mt-4">
                    {trip.daily_requirements.map((requirement) => (
                      <div key={requirement.day_number} className="rounded-lg bg-white p-3">
                        <p className="text-xs font-semibold text-[#1C1C1C]">
                          Day {requirement.day_number} · {humanize(requirement.activity)}
                        </p>
                        <p className="text-[10px] text-[#8C8A82] mt-1">
                          {requirement.required_style} · {requirement.weather} ·{" "}
                          {Math.round(requirement.temperature_c)}°C
                        </p>
                        <p className="mt-2 text-xs text-[#4C4A45]">{protectionBadges(requirement).length ? `Needs: ${protectionBadges(requirement).join(", ")}` : "No extra weather protection required"}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : capsule ? (
            <>
              <div className="space-y-3">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-widest text-[#8C8A82]">
                    Optimized capsule
                  </p>
                  <h3 className="font-display text-xl font-medium text-[#1C1C1C] mt-1">
                    Daily outfits
                  </h3>
                </div>
                <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                  {capsule.days.map((day) => {
                    const requirement = requirementsByDay.get(day.day_number);
                    const badges = protectionBadges(requirement);
                    return (
                      <div key={day.day_number} className="bg-[#F0EFEA] rounded-xl p-5">
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <p className="text-[10px] uppercase tracking-widest text-[#8C8A82]">
                              Day {day.day_number} · {formatDay(day.date)}
                            </p>
                            <p className="text-sm font-semibold text-[#1C1C1C] mt-1 capitalize">
                              {humanize(day.activity)}
                            </p>
                            <p className="text-[10px] text-[#8C8A82] mt-0.5">
                              {day.required_style} · {day.weather} ·{" "}
                              {Math.round(day.temperature_c)}°C ·{" "}
                              {day.precipitation_mm.toFixed(1)} mm
                            </p>
                          </div>
                          <span className="text-lg">{weatherIcon(day.weather)}</span>
                        </div>

                        {badges.length > 0 && (
                          <div className="mt-3 flex flex-wrap gap-1.5">
                            {badges.map((badge) => (
                              <span
                                key={badge}
                                className="rounded-full bg-white px-2 py-0.5 text-[9px] font-semibold text-[#556B2F]"
                              >
                                {badge}
                              </span>
                            ))}
                          </div>
                        )}

                        <div className="mt-3 space-y-1.5">
                          {day.outfit_items.map((item) => (
                            <div
                              key={item.item_id}
                              className="flex items-center justify-between gap-3 rounded-lg bg-white px-3 py-2"
                            >
                              {item.image_url && <img src={item.image_url} alt="" className="h-10 w-10 object-contain rounded" />}
                              <div className="min-w-0">
                                <p className="text-xs font-medium text-[#1C1C1C] truncate">
                                  {item.name}
                                </p>
                                <p className="text-[10px] text-[#8C8A82] capitalize">
                                  {item.category}
                                  {item.item_type ? ` · ${humanize(item.item_type)}` : ""}
                                </p>
                              </div>
                              <span className="text-[10px] font-semibold text-[#556B2F] shrink-0">
                                {item.weight_estimated ? "~" : ""}{item.weight_g} g
                              </span>
                            </div>
                          ))}
                        </div>

                        <div className="mt-3 flex items-center justify-between text-[10px] text-[#8C8A82]">
                          <span>Estimated compatibility {day.compatibility ?? "—"}</span>
                          <span>Quality {day.quality ?? "—"}</span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-[1fr_340px] gap-6">
                <div className="bg-[#F0EFEA] rounded-xl overflow-hidden">
                  <div className="px-6 py-4 border-b border-[#E2E0D8] flex items-center justify-between gap-3">
                    <div>
                      <p className="font-medium text-[#1C1C1C] text-sm">Smart Checklist</p>
                      <p className="text-[10px] text-[#8C8A82] mt-0.5">
                        Check items off without rerunning the optimizer.
                      </p>
                    </div>
                    <span className="text-[10px] font-semibold text-[#556B2F] bg-[#E8EDE0] px-2.5 py-1 rounded-full">
                      {checklist?.packed_items ?? 0}/{checklist?.total_items ?? 0} packed
                    </span>
                  </div>
                  {checklist?.items.map((item) => (
                    <label
                      key={item.item_id}
                      className="flex items-center gap-4 px-6 py-3.5 border-b border-[#E2E0D8] last:border-0 hover:bg-[#E2E0D8]/50 transition-colors cursor-pointer"
                    >
                      <input
                        type="checkbox"
                        checked={item.packed}
                        disabled={packingItem === item.item_id}
                        onChange={(event) => void togglePacked(item, event.target.checked)}
                        className="rounded accent-[#556B2F] h-4 w-4"
                      />
                      {item.image_url && <img src={item.image_url} alt="" className="h-10 w-10 object-contain rounded" />}
                      <div className="min-w-0 flex-1">
                        <p
                          className={`text-sm font-medium ${
                            item.packed ? "text-[#8C8A82] line-through" : "text-[#1C1C1C]"
                          }`}
                        >
                          {item.name}
                        </p>
                        <p className="text-[10px] text-[#8C8A82] capitalize">
                          {item.category} · {item.weight_estimated ? "~" : ""}{item.weight_g} g
                        </p>
                      </div>
                      <span
                        className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${
                          item.packed
                            ? "bg-[#E8EDE0] text-[#556B2F]"
                            : "bg-white text-[#8C8A82]"
                        }`}
                      >
                        {packingItem === item.item_id ? "saving…" : item.packed ? "Packed" : "To pack"}
                      </span>
                    </label>
                  ))}
                </div>

                <div className="space-y-4">
                  <div className="bg-[#1C1C1C] rounded-xl p-5">
                    <p className="text-[#556B2F] text-xs font-semibold uppercase tracking-widest">
                      Capsule summary
                    </p>
                    <div className="mt-4 space-y-3">
                      {[
                        ["Status", capsule.optimization_status],
                        ["Unique items", String(capsule.number_of_items)],
                        ["Estimated clothing weight", `${(capsule.total_weight_g / 1000).toFixed(2)} kg`],
                        ["Luggage limit", `${capsule.trip.max_luggage_weight_kg} kg`],
                        ["Weather", capsule.trip.weather_source === "open-meteo" ? "Open-Meteo" : "Synthetic fallback"],
                      ].map(([label, value]) => (
                        <div key={label} className="flex items-center justify-between gap-3">
                          <span className="text-white/40 text-[10px] uppercase tracking-widest">
                            {label}
                          </span>
                          <span className="text-white/80 text-xs font-medium text-right">
                            {value}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="bg-[#E8EDE0] rounded-xl p-5">
                    <p className="text-xs font-semibold text-[#556B2F] uppercase tracking-widest mb-2">
                      Deterministic optimizer
                    </p>
                    <p className="text-sm text-[#1C1C1C]">
                      Packed {capsule.number_of_items} unique items into {capsule.days.length} daily
                      outfits, reusing pieces where possible.
                      {capsule.metadata?.allow_outfit_repeats === true && " Full outfits may repeat, as requested."}
                    </p>
                  </div>

                  {gap && !gap.gap_analysis.available && (
                    <div className="bg-white border border-[#E2E0D8] rounded-xl p-5 text-sm text-[#8C8A82]">
                      {gap.gap_analysis.message || "Gap analysis is not available yet."}
                    </div>
                  )}
                  {gap?.gap_analysis.findings && (
                    <div className="bg-white border border-[#E2E0D8] rounded-xl p-5">
                      <div className="flex items-center justify-between gap-3">
                        <p className="text-xs font-semibold text-[#556B2F] uppercase tracking-widest">
                          Gap analysis
                        </p>
                        <span className="text-[9px] font-semibold text-[#8C8A82] bg-[#F0EFEA] px-2 py-0.5 rounded-full">
                          optional
                        </span>
                      </div>
                      <p className="text-sm text-[#1C1C1C] mt-3">
                        {gap.gap_analysis.findings.summary}
                      </p>
                      <div className="mt-3 space-y-2">
                        {gap.gap_analysis.findings.gaps.map((item) => (
                          <div
                            key={`${item.type}-${item.category}`}
                            className="rounded-lg bg-[#F0EFEA] px-3 py-2"
                          >
                            <p className="text-[10px] font-semibold uppercase tracking-widest text-[#8C8A82]">
                              {item.severity} · {item.category}
                            </p>
                            <p className="text-xs text-[#1C1C1C] mt-1">{item.suggestion}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </>
          ) : (
            <div className="bg-[#F0EFEA] rounded-xl p-6">
              <p className="text-sm text-[#8C8A82]">
                The agent has not produced a capsule yet. Try editing the trip or sending more
                details.
              </p>
            </div>
          )}
        </>
      )}
    </div>
  );
}
