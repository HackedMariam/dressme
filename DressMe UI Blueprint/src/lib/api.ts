import { isSupabaseConfigured, supabase } from "./supabase"
import type {
  AccuracyRow,
  AgentReply,
  AnalyzeResponse,
  DuplicateResult,
  Health,
  ItemMeshStatus,
  PhotoMatch,
  QuickDetection,
  WardrobeItem,
} from "./types"

const configuredBase = import.meta.env.VITE_API_URL?.trim() || ""
export const API_BASE = configuredBase.replace(/\/$/, "")

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = "ApiError"
    this.status = status
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json")
  }

  if (isSupabaseConfigured) {
    const { data } = await supabase.auth.getSession()
    const token = data.session?.access_token
    if (token) headers.set("Authorization", `Bearer ${token}`)
  }

  let response: Response
  try {
    response = await fetch(`${API_BASE}${path}`, { ...init, headers })
  } catch {
    throw new ApiError(
      `Cannot reach the API server${API_BASE ? ` at ${API_BASE}` : ""}. Make sure the backend is running.`,
      0,
    )
  }

  if (response.status === 401 && isSupabaseConfigured) {
    await supabase.auth.signOut()
  }

  if (!response.ok) {
    let message = response.statusText || "Request failed"
    try {
      const data = (await response.json()) as { detail?: unknown }
      if (typeof data.detail === "string") message = data.detail
      else if (Array.isArray(data.detail)) {
        message = data.detail
          .map((entry) => (typeof entry === "object" && entry && "msg" in entry ? String(entry.msg) : String(entry)))
          .join(", ")
      }
    } catch {
      // The body was not JSON; keep the HTTP status text.
    }
    throw new ApiError(message, response.status)
  }

  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

function fileBody(file: File | Blob, name = "file") {
  const form = new FormData()
  form.append("file", file, file instanceof File ? file.name : "frame.jpg")
  return form
}

export function asset(url?: string | null) {
  if (!url) return ""
  if (url.startsWith("http") || url.startsWith("data:") || url.startsWith("blob:")) return url
  if (url.startsWith("/")) return `${API_BASE}${url}`
  return url
}

export const api = {
  health: () => request<Health>("/api/health"),

  list: () => request<WardrobeItem[]>("/api/items"),

  analyze: (
    file: File | Blob,
    options: { allItems?: boolean; save?: boolean; fast?: boolean } = {},
  ) => {
    const query = new URLSearchParams({
      all_items: String(options.allItems ?? false),
      save: String(options.save ?? true),
      fast: String(options.fast ?? false),
    })
    return request<AnalyzeResponse>(`/api/items/analyze?${query}`, {
      method: "POST",
      body: fileBody(file),
    })
  },

  quickDetect: (frame: Blob) =>
    request<{ detections: QuickDetection[] }>("/api/items/quick-detect", {
      method: "POST",
      body: fileBody(frame, "frame.jpg"),
    }),

  update: (id: string, fields: Record<string, unknown>, confirm = true) =>
    request<WardrobeItem>(`/api/items/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ fields, confirm }),
    }),

  reclassify: (id: string) =>
    request<WardrobeItem>(`/api/items/${id}/reclassify`, { method: "POST" }),

  itemMesh: (id: string) => request<ItemMeshStatus>(`/api/items/${id}/mesh`),

  generateItemMesh: (id: string, force = false, provider?: string) => {
    const query = new URLSearchParams({ force: String(force) })
    if (provider) query.set("provider", provider)
    return request<ItemMeshStatus>(`/api/items/${id}/mesh?${query}`, { method: "POST" })
  },

  searchByPhoto: (file: File | Blob) =>
    request<PhotoMatch>("/api/search/photo", { method: "POST", body: fileBody(file) }),

  agentSearch: (message: string) =>
    request<AgentReply>("/api/agent/search", {
      method: "POST",
      body: JSON.stringify({ message }),
    }),

  checkDuplicate: (item: Pick<WardrobeItem, "category" | "color_name" | "pattern" | "material">) =>
    request<DuplicateResult>("/api/agent/check-duplicate", {
      method: "POST",
      body: JSON.stringify({
        category: item.category,
        color_name: item.color_name ?? null,
        pattern: item.pattern ?? null,
        material: item.material ?? null,
      }),
    }),

  remove: (id: string) => request<{ deleted: string }>(`/api/items/${id}`, { method: "DELETE" }),

  accuracy: () => request<AccuracyRow[]>("/api/stats/accuracy"),
}
