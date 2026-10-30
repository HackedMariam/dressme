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

export interface PurchaseEvaluation {
  user_query: string
  candidate_item: {
    detected_category: string
    detected_color: string
    inferred_occasion: string
    price: number
    budget: number
  }
  tool_evidence: {
    redundancy_score: number
    closest_wardrobe_match: string | null
    compatible_outfits_count: number
    wardrobe_gap_score: number
    budget_penalty: number
    matching_outfits?: {
      outfit_id: string
      compatibility_score: number
      paired_items: { name: string; category: string; color: string }[]
    }[]
  }
  agent_verdict: { decision: string; score: number; reasons: string[] }
  stylist_interpretation?: string
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
