import { SHOP_PAGES, type Page } from "./navigation"

// One tab bar for the three shopping tools, with one sentence on when to use each.
export default function ShopTabs({ current, onNav }: { current: Page; onNav: (page: Page) => void }) {
  const active = SHOP_PAGES.find((entry) => entry.page === current)
  return (
    <div className="mb-8">
      <div className="flex flex-wrap items-center gap-2" role="tablist" aria-label="Shopping tools">
        {SHOP_PAGES.map((entry) => (
          <button
            key={entry.page}
            type="button"
            role="tab"
            aria-selected={entry.page === current}
            onClick={() => onNav(entry.page)}
            className={`rounded-full px-4 py-2 text-sm font-medium transition-colors ${
              entry.page === current
                ? "bg-[#1C1C1C] text-white"
                : "border border-[#E2E0D8] bg-white text-[#1C1C1C] hover:bg-[#F0EFEA]"
            }`}
          >
            {entry.label}
          </button>
        ))}
      </div>
      {active && <p className="mt-2.5 text-xs text-[#8C8A82]">{active.blurb}</p>}
    </div>
  )
}
