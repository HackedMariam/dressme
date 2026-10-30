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

export interface QuickDetection {
  category: string
  group: string
  confidence: number
  box: number[]
  color_name?: string | null
}

export interface OutfitScore {
  complete: boolean
  message: string
  score: number | null
  color_score?: number
  style_score?: number
  occasion_score?: number
  season_score?: number
  explanations?: string[]
  suggested_item_ids: string[]
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
}
