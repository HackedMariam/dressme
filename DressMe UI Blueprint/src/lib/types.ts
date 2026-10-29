export interface WardrobeItem {
  id: string
  name: string
  category: string
  category_group: string
  subcategory?: string | null
  color_name?: string | null
  color_hex?: string | null
  color_family?: string | null
  colors?: { name: string; hex: string; share: number }[]
  pattern?: string | null
  material?: string | null
  seasons?: string[]
  style?: string | null
  occasions?: string[]
  formality?: string | null
  warmth?: number | null
  description?: string | null
  tags?: string[]
  styling_tips?: string[]
  confidence?: number | null
  field_confidence?: Record<string, number>
  needs_review?: boolean
  status?: string | null
  enrichment_source?: string | null
  image_url?: string | null
  cutout_url?: string | null
  back_photo_url?: string | null
  mesh_url?: string | null
  mesh_status?: string | null
  mesh_source?: string | null
  mesh_version?: number | null
  mesh_meta?: Record<string, unknown> | null
  mesh_error?: string | null
  created_at?: string | null
  updated_at?: string | null
}

export interface Health {
  ok: boolean
  model_loaded: boolean
  model: string
  store: string
  auth: boolean
  llm: boolean
  llm_model?: string
  mesh_builder?: boolean
  mesh_provider?: string
  mesh_providers?: string[]
  hf_3d?: boolean
}

export interface AccuracyRow {
  field: string
  reviewed: number
  corrected: number
  accuracy: number | null
}

export interface PhotoMatch {
  category: string
  group: string
  color_name: string | null
  match: WardrobeItem | null
}

export interface AgentReply {
  reply: string
  items: WardrobeItem[]
}

export interface DuplicateResult {
  duplicate: boolean
  similar_item_id: string | null
  note: string
}

export interface AnalyzeResponse {
  items: WardrobeItem[]
}

export interface ItemMeshStatus {
  mesh_url: string | null
  mesh_status: "none" | "queued" | "building" | "ready" | "failed"
  mesh_source: string | null
  mesh_version: number
  mesh_meta: Record<string, unknown> | null
  mesh_error: string | null
  queued?: boolean
}

export interface QuickDetection {
  category: string
  group: string
  confidence: number
  box: number[]
  color_name?: string | null
}
