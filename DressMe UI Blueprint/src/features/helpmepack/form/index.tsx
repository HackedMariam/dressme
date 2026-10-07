import { IMG, type Trip } from "../data"
import { PrimaryButton } from "../ui"

export default function TripContext({
  trip,
  setTrip,
  onNext,
}: {
  trip: Trip
  setTrip: (t: Trip) => void
  onNext: () => void
}) {
  const fields: { label: keyof Trip, placeholder?: string, opts?: string[] }[] = [
    { label: "dest", placeholder: "City or country" },
    { label: "dates", placeholder: "e.g. Oct 14–21" },
    {
      label: "tripType",
      opts: [
        "Leisure",
        "Business",
        "Business + Leisure",
        "Adventure",
        "Beach",
        "Formal Event",
      ],
    },
    {
      label: "dresscode",
      opts: [
        "Casual",
        "Smart Casual",
        "Business Casual",
        "Formal",
        "Black Tie",
        "Mixed",
      ],
    },
    {
      label: "bags",
      opts: [
        "Personal Item Only",
        "1 Carry-On",
        "1 Checked Bag",
        "2 Checked Bags",
        "No Limit",
      ],
    },
  ]

  const labels: Record<keyof Trip, string> = {
    dest: "Destination",
    dates: "Dates",
    tripType: "Trip Type",
    dresscode: "Dress Code",
    bags: "Luggage Limit",
  }

  return (
    <div className="grid grid-cols-[1fr_360px] gap-6">
      <div className="bg-[#F0EFEA] rounded-xl p-8 space-y-5">
        <h2 className="font-display text-xl font-medium text-[#1C1C1C]">
          Trip Details
        </h2>

        {fields.map((f) => (
          <div key={f.label}>
            <label className="text-xs font-semibold text-[#8C8A82] uppercase tracking-widest block mb-2">
              {labels[f.label]}
            </label>
            {f.opts ? (
              <select
                value={trip[f.label]}
                onChange={(e) =>
                  setTrip({ ...trip, [f.label]: e.target.value })
                }
                className="w-full px-4 py-3 bg-white border border-[#E2E0D8] rounded-lg text-sm text-[#1C1C1C] outline-none focus:border-[#556B2F] transition-colors"
              >
                {f.opts.map((o) => (
                  <option key={o}>{o}</option>
                ))}
              </select>
            ) : (
              <input
                value={trip[f.label]}
                onChange={(e) =>
                  setTrip({ ...trip, [f.label]: e.target.value })
                }
                placeholder={f.placeholder}
                className="w-full px-4 py-3 bg-white border border-[#E2E0D8] rounded-lg text-sm text-[#1C1C1C] outline-none focus:border-[#556B2F] transition-colors"
              />
            )}
          </div>
        ))}

        <div className="pt-1">
          <PrimaryButton onClick={onNext} full>
            Analyze My Trip
          </PrimaryButton>
        </div>
      </div>

      <div className="space-y-4">
        <div className="bg-[#1C1C1C] rounded-xl overflow-hidden h-48">
          <img
            src={IMG.editorial}
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
          ].map((f) => (
            <div
              key={f}
              className="flex items-center gap-2 py-2 border-b border-[#E2E0D8] last:border-0"
            >
              <span className="text-[#556B2F] text-sm">✓</span>
              <span className="text-sm text-[#1C1C1C]">{f}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
