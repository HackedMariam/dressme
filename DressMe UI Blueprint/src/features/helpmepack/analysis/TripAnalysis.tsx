import { CONDITIONS, FORECAST, TRIP_META, WEATHER, type Trip } from "../data"
import { Eyebrow, FlowFooter, StatusBadge } from "../ui"

export default function TripAnalysis({
  trip,
  onBack,
  onNext,
}: {
  trip: Trip
  onBack: () => void
  onNext: () => void
}) {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-6">
        {/* Trip overview */}
        <div className="bg-[#1C1C1C] rounded-xl p-6">
          <Eyebrow tone="olive">Trip Overview</Eyebrow>
          <h2 className="font-display text-3xl font-medium text-white mt-2">
            {trip.dest}
          </h2>
          <p className="text-white/50 text-sm mt-1">
            {trip.dates} · {TRIP_META.duration}
          </p>

          <div className="flex flex-wrap gap-2 mt-4">
            <span className="text-[11px] font-semibold bg-white/10 text-white/75 px-3 py-1 rounded-full">
              {trip.tripType}
            </span>
            <span className="text-[11px] font-semibold bg-white/10 text-white/75 px-3 py-1 rounded-full">
              {trip.dresscode}
            </span>
            <span className="text-[11px] font-semibold bg-[#556B2F]/30 text-[#A8C078] px-3 py-1 rounded-full">
              {trip.bags}
            </span>
          </div>

          <div className="mt-5 pt-4 border-t border-white/10 space-y-2.5">
            {[
              { l: "Activity", v: trip.tripType },
              { l: "Dress code", v: trip.dresscode },
              { l: "Luggage limit", v: trip.bags },
            ].map((r) => (
              <div key={r.l} className="flex items-center justify-between">
                <span className="text-white/40 text-xs">{r.l}</span>
                <span className="text-white/85 text-xs font-medium">{r.v}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Weather */}
        <div className="bg-[#F0EFEA] rounded-xl p-6">
          <Eyebrow>Weather</Eyebrow>
          <div className="flex items-center gap-4 mt-3">
            <span className="text-5xl leading-none">{WEATHER.icon}</span>
            <div>
              <p className="font-display text-4xl font-medium text-[#1C1C1C] leading-none">
                {WEATHER.range}
              </p>
              <p className="text-sm text-[#8C8A82] mt-2">
                {WEATHER.condition} · {WEATHER.rain}
              </p>
            </div>
          </div>

          <div className="mt-5 pt-4 border-t border-[#E2E0D8]">
            <div className="grid grid-cols-7 gap-1.5">
              {FORECAST.map((f) => (
                <div
                  key={f.day}
                  className="bg-white rounded-lg py-2 px-1 text-center border border-[#E2E0D8]"
                >
                  <p className="text-[10px] font-semibold text-[#8C8A82]">
                    {f.week}
                  </p>
                  <span className="text-base block my-1">{f.icon}</span>
                  <p className="text-[11px] font-semibold text-[#1C1C1C]">
                    {f.hi}°
                  </p>
                  <p className="text-[10px] text-[#8C8A82]">{f.lo}°</p>
                </div>
              ))}
            </div>
            <p className="text-[11px] text-[#8C8A82] mt-2.5">
              Paris · Oct 14–20 · forecast for your trip window
            </p>
          </div>
        </div>
      </div>

      {/* Packing conditions */}
      <div className="bg-[#F0EFEA] rounded-xl p-6">
        <div className="flex items-center justify-between">
          <Eyebrow>Packing Conditions</Eyebrow>
          <span className="text-[11px] text-[#8C8A82]">
            Derived from weather + activity + dress code
          </span>
        </div>
        <div className="grid grid-cols-5 gap-3 mt-4">
          {CONDITIONS.map((c) => (
            <div
              key={c}
              className="bg-white border border-[#E2E0D8] rounded-lg p-4"
            >
              <span className="w-5 h-5 rounded-full bg-[#E8EDE0] text-[#556B2F] text-[11px] font-bold flex items-center justify-center">
                ✓
              </span>
              <p className="text-xs font-medium text-[#1C1C1C] mt-2.5 leading-snug">
                {c}
              </p>
            </div>
          ))}
        </div>
      </div>

      {/* Status */}
      <div className="flex items-center justify-between gap-4 bg-[#E8EDE0] border border-[#556B2F]/20 rounded-xl px-6 py-4">
        <div className="flex items-center gap-3">
          <span className="w-4 h-4 rounded-full border-2 border-[#556B2F] border-t-transparent animate-spin" />
          <p className="text-sm text-[#1C1C1C]">
            DressMe is checking your wardrobe against these conditions…
          </p>
        </div>
        <span className="text-[11px] font-semibold text-[#556B2F] uppercase tracking-widest">
          Weather-aware
        </span>
      </div>

      <FlowFooter
        onBack={onBack}
        backLabel="Edit trip"
        onNext={onNext}
        nextLabel="Analyze My Wardrobe"
      />
    </div>
  )
}
