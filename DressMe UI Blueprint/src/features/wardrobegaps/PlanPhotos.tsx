import { useEffect, useState } from "react";
import { fetchPlanPhotos, type WebPhoto } from "./api";

// Photos of Tunisian shops for one planned piece. Loaded only when the user asks (each web search takes about a second
// and the free search engine throttles bursts).
export default function PlanPhotos({ category, subcategory }: { category: string; subcategory: string }) {
  const [state, setState] = useState<{ photos: WebPhoto[]; message: string | null } | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchPlanPhotos(category, subcategory)
      .then((reply) => !cancelled && setState({ photos: reply.images, message: reply.message }))
      .catch(() => !cancelled && setState({ photos: [], message: "Shop photos are unavailable right now." }));
    return () => {
      cancelled = true;
    };
  }, [category, subcategory]);

  if (!state) {
    return (
      <div className="mt-3 grid grid-cols-3 gap-2" aria-label="Loading shop photos">
        {[0, 1, 2].map((i) => (
          <div key={i} className="aspect-[4/3] animate-pulse rounded-lg bg-[#F0EFEA]" />
        ))}
      </div>
    );
  }
  if (state.photos.length === 0) {
    return <p className="mt-3 rounded-lg bg-[#FAF9F6] px-3 py-2 text-[11.5px] text-[#8C8A82]">{state.message ?? "No photo found."}</p>;
  }
  return (
    <div className="mt-3">
      <div className="grid grid-cols-3 gap-2">
        {state.photos.map((photo) => (
          <a
            key={photo.page_url}
            href={photo.page_url}
            target="_blank"
            rel="noopener noreferrer"
            title={photo.title}
            className="group relative block aspect-[4/3] overflow-hidden rounded-lg bg-[#F0EFEA]"
          >
            <img
              src={photo.thumbnail}
              alt={photo.title}
              loading="lazy"
              referrerPolicy="no-referrer"
              onError={(event) => (event.currentTarget.style.visibility = "hidden")}
              className="h-full w-full object-cover transition-transform duration-200 group-hover:scale-[1.03]"
            />
            <span className="absolute inset-x-0 bottom-0 flex justify-between bg-gradient-to-t from-black/60 to-transparent px-1.5 pb-1 pt-5 text-[10px] font-semibold text-white">
              <span className="truncate">{photo.source}</span>
              <span aria-hidden="true">↗</span>
            </span>
          </a>
        ))}
      </div>
      <p className="mt-1 text-[10.5px] text-[#8C8A82]">Tunisian shops, for inspiration. Click to open the shop.</p>
    </div>
  );
}
