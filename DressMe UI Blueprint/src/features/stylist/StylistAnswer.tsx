import type { ReactNode } from "react"
import { asset } from "../../lib/api"
import { cap } from "../../lib/taxonomy"
import type { AdviceSource, StylistSections, WardrobeItem } from "../../lib/types"

// A line of advice with its [S1]-style markers drawn as small badges; hovering one names the book and page.
function Cited({ text, sources }: { text: string; sources: AdviceSource[] }) {
  const parts = text.split(/(\[S\d+\])/g)
  return (
    <>
      {parts.map((part, index) => {
        const source = sources.find((entry) => entry.marker === part)
        if (!/^\[S\d+\]$/.test(part)) return <span key={index}>{part}</span>
        const title = source ? `${source.title}${source.page ? `, p. ${source.page}` : ""}` : "Fashion book"
        return (
          <span
            key={index}
            title={title}
            className="mx-0.5 rounded bg-[#E8EDE0] px-1 py-px align-baseline text-[10px] font-semibold text-[#556B2F]"
          >
            {part.slice(1, -1)}
          </span>
        )
      })}
    </>
  )
}

function Zone({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="rounded-xl border border-[#E2E0D8] bg-[#FAF9F6] p-3">
      <p className="text-xs font-bold text-[#1C1C1C]">{title}</p>
      <div className="mt-2">{children}</div>
    </div>
  )
}

function Bullets({ lines, sources }: { lines: string[]; sources: AdviceSource[] }) {
  return (
    <ul className="space-y-1.5">
      {lines.map((line, index) => (
        <li key={index} className="flex items-start gap-2 text-[13px] leading-relaxed text-[#1C1C1C]">
          <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-[#556B2F]" />
          <span>
            <Cited text={line} sources={sources} />
          </span>
        </li>
      ))}
    </ul>
  )
}

function Tiles({ items }: { items: WardrobeItem[] }) {
  return (
    <div className="flex flex-wrap gap-3">
      {items.map((item) => (
        <div key={item.id} className="w-20 text-center">
          <div className="flex aspect-[4/5] items-center justify-center overflow-hidden rounded-lg border border-[#E2E0D8] bg-white">
            {item.cutout_url ? (
              <img src={asset(item.cutout_url)} alt={item.name} loading="lazy" className="h-full w-full object-contain p-1" />
            ) : (
              <span className="px-1 text-[10px] text-[#8C8A82]">{cap(item.category)}</span>
            )}
          </div>
          <p className="mt-1 line-clamp-2 text-[11px] leading-tight text-[#1C1C1C]">{item.name}</p>
        </div>
      ))}
    </div>
  )
}

// The stylist's reply: the answer, then one zone per section (title in bold), the outfit as pictures, and the
// fashion books it relied on. A reply without sections (a plain search) is the text and the pieces found.
export default function StylistAnswer({
  text,
  sections,
  items,
  sources,
}: {
  text: string
  sections?: StylistSections | null
  items: WardrobeItem[]
  sources: AdviceSource[]
}) {
  const outfit = sections?.outfit ?? []
  const why = sections?.why ?? []
  const tips = sections?.tips ?? []
  const hasOutfit = outfit.length > 0

  return (
    <div className="space-y-3">
      <p className="whitespace-pre-line">
        <Cited text={text} sources={sources} />
      </p>

      {hasOutfit && (
        <Zone title="Outfit idea">
          {items.length > 0 && (
            <div className="mb-2">
              <Tiles items={items.slice(0, 6)} />
            </div>
          )}
          <Bullets lines={outfit} sources={sources} />
        </Zone>
      )}
      {!hasOutfit && items.length > 0 && <Tiles items={items.slice(0, 8)} />}
      {why.length > 0 && (
        <Zone title="Why it works">
          <Bullets lines={why} sources={sources} />
        </Zone>
      )}
      {tips.length > 0 && (
        <Zone title="Tips">
          <Bullets lines={tips} sources={sources} />
        </Zone>
      )}
      {sources.length > 0 && (
        <Zone title="From fashion books">
          <ul className="space-y-1">
            {[...sources].sort((a, b) => Number(a.marker.slice(2, -1)) - Number(b.marker.slice(2, -1))).map((source) => (
              <li key={source.marker} className="flex gap-2 text-[11px] leading-snug text-[#1C1C1C]">
                <span className="shrink-0 font-semibold text-[#556B2F]">{source.marker.slice(1, -1)}</span>
                <span>
                  {source.title}
                  {source.page ? <span className="text-[#8C8A82]"> - p. {source.page}</span> : null}
                </span>
              </li>
            ))}
          </ul>
        </Zone>
      )}
    </div>
  )
}
