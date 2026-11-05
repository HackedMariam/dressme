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
  avatar?: boolean
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

/** A fashion-book passage the stylist's advice is based on; `marker` is the [S1] tag used in the reply. */
export interface AdviceSource {
  marker: string
  title: string
  page?: number | null
  source?: string | null
}

/** The sections of a stylist answer; the page writes their titles. */
export interface StylistSections {
  outfit: string[]
  why: string[]
  tips: string[]
}

export interface AgentReply {
  reply: string
  items: WardrobeItem[]
  sources?: AdviceSource[]
  sections?: StylistSections | null
  /** Search filters the agent chose, e.g. { category: "jacket", min_warmth: 4 } */
  filters?: Record<string, string | number>[]
}

export interface AvatarJob {
  id: string
  kind: "avatar" | "tryon"
  status: "running" | "done" | "failed"
  error?: string | null
}

export interface AvatarStatus {
  configured: boolean
  exists: boolean
  created_at?: string | null
  /** pieces already tried on; has_3d is false when only the 2D photo step worked */
  tryons: { item_id: string; has_3d: boolean }[]
  /** a generation still running (it survives a page reload) */
  job?: AvatarJob | null
}

export interface DuplicateResult {
  duplicate: boolean
  similar_item_id: string | null
  note: string
}

/** A detection that was NOT saved: a poor photo, or it looks like an item already owned. `note` says why. */
export interface SkippedItem {
  index: number
  category: string
  reason: "duplicate" | "quality"
  similar_item: WardrobeItem | null
  note: string
}

export interface AnalyzeResponse {
  items: WardrobeItem[]
  skipped?: SkippedItem | null
  skipped_items?: SkippedItem[]
}

export interface QuickDetection {
  category: string
  group: string
  confidence: number
  box: number[]
  color_name?: string | null
  /** Advice when this frame will not be saved as is (item cut off, too far, not sure what it is). */
  problem?: string | null
}


export interface PurchaseEvaluationResult {
  status: string
  user_query?: string
  candidate_item?: {
    image_source?: string
    detected_category?: string
    detected_color?: string
    inferred_occasion?: string
    inferred_style?: string[]
    price?: number
    budget?: number
  }
  tool_evidence?: {
    redundancy_score?: number
    closest_wardrobe_match?: string | null
    compatible_outfits_count?: number
    matching_wardrobe_item_ids?: string[]
    matching_outfits?: Array<{
      outfit_id?: string
      description?: string
      compatibility_score?: number
      paired_items?: Array<{
        item_id: string
        name: string
        category: string
        color: string
      }>
    }>
    wardrobe_gap_score?: number
    xgboost_prediction?: string
    xgboost_confidence?: number
    deterministic_score?: number
    budget_penalty?: number
  }
  agent_verdict?: {
    decision?: string
    score?: number
    matching_item_ids?: string[]
    reasons?: string[]
    uncertainties?: string[]
  }
  stylist_interpretation?: string
  /** The stylist's answer, one list of short plain-text lines per section (the page writes the titles). */
  stylist_sections?: {
    verdict?: string[]
    why_it_works?: string[]
    ready_to_wear?: string[]
    final_advice?: string[]
  }
}
