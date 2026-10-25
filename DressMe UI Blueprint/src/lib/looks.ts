import type { GarmentId } from "./garments"
import type { TryOnItemSnapshot } from "./tryon"

export type SavedLook = {
  id: string
  label: string
  garmentIds: GarmentId[]
  wardrobeIds: string[]
  items?: TryOnItemSnapshot[]
  createdAt: number
}

const STORAGE_KEY = "dressme.savedLooks.v1"
const MAX_LOOKS = 24

function makeId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID()
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`
}

export function loadLooks(): SavedLook[] {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed
      .filter(
        (look): look is SavedLook =>
          typeof look?.id === "string" &&
          typeof look?.label === "string" &&
          Array.isArray(look?.garmentIds) &&
          Array.isArray(look?.wardrobeIds),
      )
      .map((look) => ({
        ...look,
        wardrobeIds: look.wardrobeIds.map((id) => String(id)),
      }))
  } catch {
    return []
  }
}

export function saveLook(look: Omit<SavedLook, "id" | "createdAt">): SavedLook[] {
  const next: SavedLook[] = [
    { ...look, id: makeId(), createdAt: Date.now() },
    ...loadLooks(),
  ].slice(0, MAX_LOOKS)
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
  } catch {
    // localStorage may be unavailable (private mode); keep the in-memory list.
  }
  return next
}

export function removeLook(id: string): SavedLook[] {
  const next = loadLooks().filter((look) => look.id !== id)
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
  } catch {
    // ignore
  }
  return next
}
