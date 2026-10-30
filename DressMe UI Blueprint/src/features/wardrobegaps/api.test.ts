import { afterEach, describe, expect, it, vi } from "vitest"

const { getSession } = vi.hoisted(() => ({ getSession: vi.fn() }))
vi.mock("../../lib/supabase", () => ({ supabase: { auth: { getSession } } }))

import { fetchGaps, sendFeedback } from "./api"

describe("Wardrobe Gaps API authentication", () => {
  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
    getSession.mockReset()
  })

  it("forwards the current session token for reads and feedback", async () => {
    getSession.mockResolvedValue({ data: { session: { access_token: "user-token" } }, error: null })
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) })
    vi.stubGlobal("fetch", fetchMock)
    await fetchGaps("winter_work")
    await sendFeedback("winter_work", "coat", 3)
    expect(fetchMock).toHaveBeenCalledTimes(2)
    for (const [, init] of fetchMock.mock.calls) {
      expect(init.headers.get("Authorization")).toBe("Bearer user-token")
    }
    expect(fetchMock.mock.calls[1][1].headers.get("Content-Type")).toBe("application/json")
  })

  it("does not send a request when no session exists", async () => {
    getSession.mockResolvedValue({ data: { session: null }, error: null })
    const fetchMock = vi.fn()
    vi.stubGlobal("fetch", fetchMock)
    await expect(fetchGaps("winter_work")).rejects.toThrow("Please sign in")
    expect(fetchMock).not.toHaveBeenCalled()
  })
})
