import { renderToStaticMarkup } from "react-dom/server"
import { beforeEach, describe, expect, it, vi } from "vitest"
import type { WardrobeItem } from "../../lib/types"

const state = vi.hoisted(() => ({ items: [] as WardrobeItem[], loading: false, error: null as string | null }))
vi.mock("../wardrobe/WardrobeProvider", () => ({
  useWardrobe: () => ({ ...state, reload: vi.fn() }),
}))
vi.mock("../../lib/api", () => ({ api: { scoreOutfit: vi.fn() }, asset: (url: string | null) => url || "" }))

import OutfitStudioPage from "./OutfitStudioPage"

describe("Outfit Studio", () => {
  beforeEach(() => { state.items = []; state.loading = false; state.error = null })

  it("renders the actual wardrobe rather than the old example garments", () => {
    state.items = [{ id: "real-1", name: "My blue shirt", category: "top", category_group: "Tops", color_name: "blue" }]
    const html = renderToStaticMarkup(<OutfitStudioPage onOpenWardrobe={() => {}} />)
    expect(html).toContain("My blue shirt")
    expect(html).toContain("1 item")
    expect(html).not.toContain("Camel Blazer")
    expect(html).not.toContain("Style Synergy Score")
  })

  it("explains an empty wardrobe without displaying a fabricated score", () => {
    const html = renderToStaticMarkup(<OutfitStudioPage onOpenWardrobe={() => {}} />)
    expect(html).toContain("Your wardrobe is empty")
    expect(html).toContain("Open My Wardrobe")
    expect(html).not.toContain("Strong combination")
  })

  it("shows a wardrobe failure rather than treating it as an empty wardrobe", () => {
    state.error = "Wardrobe unavailable"
    const html = renderToStaticMarkup(<OutfitStudioPage onOpenWardrobe={() => {}} />)
    expect(html).toContain("Wardrobe unavailable")
    expect(html).toContain("Retry wardrobe")
    expect(html).not.toContain("Your wardrobe is empty")
  })
})
