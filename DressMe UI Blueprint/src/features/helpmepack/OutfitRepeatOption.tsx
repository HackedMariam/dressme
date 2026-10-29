type Props = {
  allowed: boolean;
  confirmed: boolean;
  legacyService: boolean;
  otherRequirements: boolean;
  loading: boolean;
  onAllow: () => void;
};

export default function OutfitRepeatOption({ allowed, confirmed, legacyService, otherRequirements, loading, onAllow }: Props) {
  return (
    <div className="mt-5 rounded-xl border border-[#D4DBC9] bg-[#F2F6EC] p-4">
      <h4 className="text-sm font-semibold text-[#1C1C1C]">Want to wear the same outfit again?</h4>
      <p className="mt-1 text-xs leading-relaxed text-[#4C5C3A]">
        {allowed
          ? "Outfit repeats are already allowed for this trip."
          : confirmed
            ? "A plan was found when full outfits were allowed to repeat."
            : "You can try allowing a complete outfit to be worn on more than one day."}
        {" "}Rain protection, other weather needs and your luggage limit still apply.
        {otherRequirements && " You will still need to address the items listed above."}
      </p>
      <button
        onClick={onAllow}
        disabled={loading || legacyService || allowed}
        className="mt-3 rounded-lg bg-[#556B2F] px-4 py-2.5 text-xs font-semibold text-white hover:bg-[#6B8A3A] disabled:cursor-not-allowed disabled:opacity-50"
      >
        {allowed ? "Outfit repeats allowed" : "Allow outfit repeats & retry"}
      </button>
      {legacyService && (
        <p className="mt-2 text-xs leading-relaxed text-amber-900">
          The running packing service is using an older version. Restart it to enable outfit repeats and the latest explanations, then start the trip again.
        </p>
      )}
    </div>
  );
}
