import { useEffect, useState } from "react";
import { fetchGapImages, type WebPhoto } from "./api";

// Photos of Tunisian shops for the selected missing piece. They load after the piece is shown, and only for
// the selected piece: each web search takes about a second, and the free search engine throttles bursts.
export default function GapPhotos({
  goal,
  candidateId,
  onLoaded,
}: {
  goal: string;
  candidateId: string;
  onLoaded?: (photos: WebPhoto[]) => void;
}) {
  const [state, setState] = useState<{ photos: WebPhoto[]; message: string | null } | null>(null);

  useEffect(() => {
    let cancelled = false; // ignore a late answer if the selection changed meanwhile
    setState(null);
    fetchGapImages(goal, candidateId)
      .then((reply) => {
        if (cancelled) return;
        setState({ photos: reply.images, message: reply.message });
        onLoaded?.(reply.images);
      })
      .catch(() => !cancelled && setState({ photos: [], message: null })); // photos are a bonus: fail quietly
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- onLoaded is a callback that must not restart the search
  }, [goal, candidateId]);

  if (!state) {
    return (
      <div className="mt-4 grid grid-cols-3 gap-2.5" aria-label="Loading photos">
        {[0, 1, 2].map((i) => (
          <div key={i} className="aspect-square xl:aspect-[4/3] animate-pulse rounded-xl bg-[#F0EFEA]" />
        ))}
      </div>
    );
  }
  if (state.photos.length === 0) {
    return state.message ? <p className="mt-4 rounded-xl bg-[#FAF9F6] px-3 py-3 text-xs text-[#8C8A82]">{state.message}</p> : null;
  }
  return (
    <div className="mt-4">
      <div className="grid grid-cols-3 gap-2.5">
        {state.photos.map((photo) => (
          <a
            key={photo.page_url}
            href={photo.page_url}
            target="_blank"
            rel="noopener noreferrer"
            title={photo.title}
            className="group relative block aspect-square xl:aspect-[4/3] overflow-hidden rounded-xl bg-[#F0EFEA]"
          >
            <img
              src={photo.thumbnail}
              alt={photo.title}
              loading="lazy"
              referrerPolicy="no-referrer"
              onError={(event) => (event.currentTarget.style.visibility = "hidden")}
              className="h-full w-full object-cover transition-transform duration-200 group-hover:scale-[1.03]"
            />
            <span className="absolute inset-x-0 bottom-0 flex justify-between bg-gradient-to-t from-black/60 to-transparent px-2 pb-1.5 pt-6 text-[11px] font-semibold text-white">
              <span className="truncate">{photo.source}</span>
              <span aria-hidden="true">↗</span>
            </span>
          </a>
        ))}
      </div>
      <p className="mt-1.5 text-[10.5px] text-[#8C8A82]">Photos from Tunisian shops, for inspiration. Click to open the shop.</p>
    </div>
  );
}
