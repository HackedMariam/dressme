import type { ReactNode } from "react";

export function FieldLabel({ children, hint }: { children: ReactNode; hint?: string }) {
  return (
    <div className="mb-2 flex items-baseline justify-between gap-3">
      <label className="text-sm font-semibold text-[#1C1C1C]">{children}</label>
      {hint && <span className="text-xs text-[#8C8A82]">{hint}</span>}
    </div>
  );
}

// A row of pill buttons: quicker to read and to pick than a drop-down with three to six choices.
export function ChoiceGroup({
  label,
  hint,
  options,
  value,
  onChange,
}: {
  label: string;
  hint?: string;
  options: string[];
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div>
      <FieldLabel hint={hint}>{label}</FieldLabel>
      <div className="flex flex-wrap gap-2" role="radiogroup" aria-label={label}>
        {options.map((option) => (
          <button
            key={option}
            type="button"
            role="radio"
            aria-checked={option === value}
            onClick={() => onChange(option)}
            className={`rounded-full border px-4 py-2 text-sm transition-colors ${
              option === value
                ? "border-[#556B2F] bg-[#556B2F] font-semibold text-white"
                : "border-[#E2E0D8] bg-white text-[#1C1C1C] hover:border-[#556B2F]"
            }`}
          >
            {option}
          </button>
        ))}
      </div>
    </div>
  );
}

export function TripSummary({
  destination,
  dates,
  days,
  tripType,
  dressCode,
  bags,
}: {
  destination: string;
  dates: string;
  days: number | null;
  tripType: string;
  dressCode: string;
  bags: string;
}) {
  const rows: [string, string][] = [
    ["Destination", destination.trim() || "Not set yet"],
    ["Dates", dates || "Not set yet"],
    ["Length", days ? `${days} day${days === 1 ? "" : "s"}` : "-"],
    ["Trip", tripType],
    ["Dress code", dressCode],
    ["Luggage", bags],
  ];
  return (
    <div className="rounded-2xl bg-[#1C1C1C] p-6 text-white">
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[#8FAE5A]">Your trip</p>
      <dl className="mt-4 space-y-3">
        {rows.map(([name, value]) => (
          <div key={name} className="flex items-baseline justify-between gap-4 border-b border-white/10 pb-2 last:border-0">
            <dt className="text-xs text-white/45">{name}</dt>
            <dd className={`text-right text-sm ${value.startsWith("Not set") ? "text-white/35" : "font-medium"}`}>
              {value}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

export function WardrobeReadiness({ count, onOpenWardrobe }: { count: number; onOpenWardrobe: () => void }) {
  const enough = count >= 8;
  return (
    <div className={`rounded-2xl border p-5 ${enough ? "border-[#E2E0D8] bg-white" : "border-amber-200 bg-amber-50"}`}>
      <p className="text-sm font-semibold text-[#1C1C1C]">
        {count} piece{count === 1 ? "" : "s"} in your wardrobe
      </p>
      <p className="mt-1 text-xs text-[#8C8A82]">
        {enough
          ? "The pack list is built only from these clothes."
          : "With only a few pieces the list will be short. Add more clothes for better results."}
      </p>
      <button type="button" onClick={onOpenWardrobe} className="mt-3 text-xs font-semibold text-[#556B2F] hover:underline">
        {enough ? "View my wardrobe" : "Add clothes"} {"→"}
      </button>
    </div>
  );
}

export function HowItWorks() {
  const steps = [
    ["Tell us the trip", "Where, when and what you will do."],
    ["We check the weather", "Real forecasts for each day of the trip."],
    ["You get a plan", "What to pack from your own clothes, and a look for every day."],
  ];
  return (
    <div className="rounded-2xl border border-[#E2E0D8] bg-white p-5">
      <p className="text-xs font-semibold uppercase tracking-widest text-[#8C8A82]">How it works</p>
      <ol className="mt-3 space-y-3">
        {steps.map(([title, detail], index) => (
          <li key={title} className="flex gap-3">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[#E8EDE0] text-xs font-semibold text-[#556B2F]">
              {index + 1}
            </span>
            <div>
              <p className="text-sm font-medium text-[#1C1C1C]">{title}</p>
              <p className="text-xs text-[#8C8A82]">{detail}</p>
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}
