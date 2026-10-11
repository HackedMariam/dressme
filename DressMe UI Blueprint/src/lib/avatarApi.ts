import type { BodyMetrics, Proportions } from "./pose"

const API_BASE = "http://127.0.0.1:8000"

export type MpbTargets = {
  gender?: number
  age?: number
  muscle?: number
  weight?: number
  height?: number
  proportions?: number
  cupsize?: number
  firmness?: number
}

export type MpbParam = "gender" | "age" | "muscle" | "weight" | "height" | "proportions" | "cupsize" | "firmness"

export type MpbParamMeta = {
  key: MpbParam
  label: string
  hint: string
}

export const MPFB_PARAMS: MpbParamMeta[] = [
  { key: "gender", label: "Gender", hint: "0.00 = feminine, 1.00 = masculine" },
  { key: "age", label: "Age", hint: "younger → older" },
  { key: "height", label: "Height", hint: "shorter → taller" },
  { key: "weight", label: "Weight", hint: "lighter → heavier build" },
  { key: "muscle", label: "Muscle", hint: "leaner → more muscular" },
  { key: "proportions", label: "Proportions", hint: "stockier ↔ more slender" },
  { key: "cupsize", label: "Cup size", hint: "flatter → fuller chest" },
  { key: "firmness", label: "Firmness", hint: "chest firmness" },
]

export const MPFB_NEUTRAL = 0.5

export type GarmentId = "tshirt" | "trousers" | "jacket"

export type GarmentMeta = {
  id: GarmentId
  label: string
  swatch: string
  hint: string
}

export const GARMENTS: GarmentMeta[] = [
  { id: "tshirt", label: "T-Shirt", swatch: "#34538C", hint: "Short-sleeve top, neckline to hip" },
  { id: "trousers", label: "Trousers", swatch: "#29292B", hint: "Waist to ankle, split legs" },
  { id: "jacket", label: "Jacket", swatch: "#8C5733", hint: "Long sleeves, layered over the top" },
]

export const DEFAULT_DRESSED_URL = "/models/dressed_avatar.glb"

export function defaultMpbTargets(): Record<MpbParam, number> {
  return {
    gender: MPFB_NEUTRAL,
    age: MPFB_NEUTRAL,
    muscle: MPFB_NEUTRAL,
    weight: MPFB_NEUTRAL,
    height: MPFB_NEUTRAL,
    proportions: MPFB_NEUTRAL,
    cupsize: MPFB_NEUTRAL,
    firmness: MPFB_NEUTRAL,
  }
}

export type GenerateResult = {
  jobId: string
  url: string
  params: Record<string, number>
  outfit: string[]
  bytes: number
  elapsedSeconds: number
}

export type MappingPreview = {
  targets: MpbTargets
  notes: string[]
}

const SHOULDER_HIP_MID = 1.3
const SHOULDER_HIP_GAIN = 0.6

const TORSO_LEG_MID = 0.75
const TORSO_LEG_GAIN = 1.2

const LEG_HEIGHT_MID = 0.53
const LEG_HEIGHT_GAIN = 4

const WIDTH_HEIGHT_MID = 0.35
const WIDTH_HEIGHT_GAIN = 5

function clamp01(n: number): number {
  return Math.min(1, Math.max(0, n))
}

function round2(n: number): number {
  return Math.round(n * 100) / 100
}

export function muscleFromShoulderToHip(ratio: number): number {
  return round2(clamp01(0.5 + (ratio - SHOULDER_HIP_MID) * SHOULDER_HIP_GAIN))
}

export const PHOTO_ESTIMATED_PARAMS: MpbParam[] = ["weight", "muscle", "height", "proportions"]
export const MANUAL_ONLY_PARAMS: MpbParam[] = ["gender", "age", "cupsize", "firmness"]

export type PhotoEstimates = Partial<Record<MpbParam, number>>

export const GENDER_PRESETS: { label: string; value: number }[] = [
  { label: "Feminine", value: 0.2 },
  { label: "Neutral", value: 0.5 },
  { label: "Masculine", value: 0.8 },
]

export const AGE_PRESETS: { label: string; value: number }[] = [
  { label: "Under 25", value: 0.15 },
  { label: "25–39", value: 0.4 },
  { label: "40–54", value: 0.65 },
  { label: "55+", value: 0.85 },
]

// Rough, uncalibrated heuristics. A single uncalibrated photo cannot measure a body,
// so these only nudge the neutral 0.50 toward "broader/heavier/leggier" or the reverse.
// They are shape hints, not measurements, and should be labelled as low confidence.
export function estimatesFromMetrics(m: BodyMetrics): PhotoEstimates {
  const widthRatio = (m.shoulderToHeight + m.hipToHeight) / 2
  return {
    muscle: muscleFromShoulderToHip(m.shoulderToHip),
    proportions: round2(clamp01(0.5 + (TORSO_LEG_MID - m.torsoToLeg) * TORSO_LEG_GAIN)),
    height: round2(clamp01(0.5 + (m.legToHeight - LEG_HEIGHT_MID) * LEG_HEIGHT_GAIN)),
    weight: round2(clamp01(0.5 + (widthRatio - WIDTH_HEIGHT_MID) * WIDTH_HEIGHT_GAIN)),
  }
}

export function mapRatiosToMpbTargets(ratios: Proportions): MappingPreview {
  return {
    targets: { muscle: muscleFromShoulderToHip(ratios.shoulderToHip) },
    notes: [
      "Shoulder-to-hip ratio maps to MPFB muscle (heuristic: broader shoulders relative to hips = higher muscle)",
      "Torso-to-leg has no matching MPFB macro parameter — not applied in this version",
      "These are rough shape hints from a photo, not measurements",
    ],
  }
}

export async function generateAvatar(
  targets: MpbTargets,
  outfit: GarmentId[] = [],
  signal?: AbortSignal,
): Promise<GenerateResult> {
  let res: Response
  try {
    res = await fetch(`${API_BASE}/api/avatar/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ targets, outfit }),
      signal,
    })
  } catch {
    throw new Error(
      "Cannot reach the local avatar backend. Start it with: cd backend && venv\\Scripts\\activate && uvicorn main:app --host 127.0.0.1 --port 8000",
    )
  }
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const body = await res.json()
      if (typeof body?.detail === "string") detail = body.detail
    } catch {
      // keep default detail
    }
    throw new Error(detail)
  }
  return (await res.json()) as GenerateResult
}
