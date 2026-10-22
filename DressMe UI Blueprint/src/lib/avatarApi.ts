import type { BodyMetrics, MetricReliability, Proportions } from "./pose"
import type { GarmentId } from "./garments"

export type { GarmentId }

export const API_BASE = "http://127.0.0.1:8000"

export type MpbParam =
  | "gender"
  | "age"
  | "muscle"
  | "weight"
  | "height"
  | "proportions"
  | "cupsize"
  | "firmness"

export type BodyParam = MpbParam | "legLength"

export type MpbTargets = Partial<Record<MpbParam, number>> & { legLength?: number }

export type BodyTargets = Record<BodyParam, number>

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

export const DEFAULT_DRESSED_URL = "/models/dressed_avatar.glb"

export type DetailTargets = Partial<Record<string, number>>

export type GenerateResult = {
  jobId: string
  url: string
  params: Record<string, number>
  details: DetailTargets
  outfit: GarmentId[]
  bytes: number
  elapsedSeconds: number
  metrics: Record<string, number>
}

export type Health = {
  ok: boolean
  blenderExists: boolean
  blendExists: boolean
  dressedScriptExists: boolean
  allowedGarments: string[]
  slots?: string[]
  bodyScanConfigured?: boolean
  visionConfigured?: boolean
}

export type BodyScanResult = {
  ok: boolean
  source: string
  measurements: Record<string, number>
  targets: Partial<Record<BodyParam, number>>
  ratios: {
    shoulderToHip?: number
    legFraction?: number
    torsoToLeg?: number
    waistToHip?: number
  }
  notes: string[]
}

export type QuestionnairePayload = {
  height_cm: number
  mass_kg: number
  gender: "female" | "male"
  body_shape: "hourglass" | "rectangle" | "inverted_triangle" | "pear" | "apple"
  belly: number
  build: number
  legs: number
  arms: number
  cupsize?: string
  ancestry?: string
}

export type VisionObservation = {
  relative: string
  confidence: number
}

export type VisionAnalysis = {
  ok: boolean
  model: string
  analysis: {
    body_shape: string
    confidence: number
    targets: Partial<Record<MpbParam | "legLength", number>>
    detail_values: Record<string, number>
    suggested_details?: Record<string, number>
    photo_quality: { front: number; side: number; notes: string[] }
    posture: Record<string, string>
    observations: Record<string, VisionObservation>
    notes: string[]
  }
  createdAt: number
}

export type MeasurementsPayload = {
  height_cm: number
  mass_kg?: number
  bmi?: number
  bust_cm?: number
  underbust_cm?: number
  waist_cm?: number
  hip_cm?: number
  shoulder_width_cm?: number
  inseam_cm?: number
  thigh_cm?: number
  upperarm_cm?: number
  neck_cm?: number
  calf_cm?: number
  wrist_cm?: number
}

export type MappingPreview = {
  targets: MpbTargets
  notes: string[]
}

const SHOULDER_HIP_MID = 1.3
const SHOULDER_HIP_GAIN = 0.6

const TORSO_LEG_MID = 0.75
const TORSO_LEG_GAIN = 1.25

const LEG_HEIGHT_MID = 0.53
const LEG_HEIGHT_GAIN = 4

const WIDTH_HEIGHT_MID = 0.35
const WIDTH_HEIGHT_GAIN = 5

const HEIGHT_CM_MID = 170
const HEIGHT_CM_RANGE = 60

function clamp01(n: number): number {
  return Math.min(1, Math.max(0, n))
}

function round2(n: number): number {
  return Math.round(n * 100) / 100
}

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

export function defaultBodyTargets(): BodyTargets {
  return { ...defaultMpbTargets(), legLength: MPFB_NEUTRAL }
}

export function muscleFromShoulderToHip(ratio: number): number {
  return round2(clamp01(0.5 + (ratio - SHOULDER_HIP_MID) * SHOULDER_HIP_GAIN))
}

export function legLengthFromTorsoToLeg(ratio: number): number {
  return round2(clamp01(0.5 + (TORSO_LEG_MID - ratio) * TORSO_LEG_GAIN))
}

export function heightFromCm(cm: number): number {
  return round2(clamp01(0.5 + (cm - HEIGHT_CM_MID) / HEIGHT_CM_RANGE))
}

export function cmFromHeightParam(value: number): number {
  return Math.round(HEIGHT_CM_MID + (value - 0.5) * HEIGHT_CM_RANGE)
}

export const PHOTO_ESTIMATED_PARAMS: MpbParam[] = ["muscle", "height", "weight"]
export const MANUAL_ONLY_PARAMS: MpbParam[] = ["gender", "age", "proportions", "cupsize", "firmness"]

export type PhotoEstimates = Partial<Record<MpbParam, number>>

export type PhotoEstimateResult = {
  values: PhotoEstimates
  keys: MpbParam[]
}

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
// Only metrics that passed the reliability checks are applied.
export function estimatesFromMetrics(
  m: BodyMetrics,
  reliability?: MetricReliability,
): PhotoEstimateResult {
  const values: PhotoEstimates = {}
  const keys: MpbParam[] = []
  const trusted: MetricReliability = reliability ?? {
    shoulderToHip: true,
    torsoToLeg: true,
    shoulderToHeight: true,
    hipToHeight: true,
    legToHeight: true,
  }

  if (trusted.shoulderToHip) {
    values.muscle = muscleFromShoulderToHip(m.shoulderToHip)
    keys.push("muscle")
  }
  if (trusted.legToHeight) {
    values.height = round2(clamp01(0.5 + (m.legToHeight - LEG_HEIGHT_MID) * LEG_HEIGHT_GAIN))
    keys.push("height")
  }
  if (trusted.shoulderToHeight && trusted.hipToHeight) {
    const widthRatio = (m.shoulderToHeight + m.hipToHeight) / 2
    values.weight = round2(clamp01(0.5 + (widthRatio - WIDTH_HEIGHT_MID) * WIDTH_HEIGHT_GAIN))
    keys.push("weight")
  }

  return { values, keys }
}

export function mapRatiosToMpbTargets(ratios: Proportions): MappingPreview {
  return {
    targets: {
      muscle: muscleFromShoulderToHip(ratios.shoulderToHip),
      legLength: legLengthFromTorsoToLeg(ratios.torsoToLeg),
    },
    notes: [
      "Shoulder-to-hip maps to MPFB muscle (broader shoulders relative to hips = higher muscle)",
      "Torso-to-leg maps to a dedicated leg-length post-process in Blender (not an MPFB macro parameter)",
      "These are rough shape hints from a photo, not measurements",
    ],
  }
}

export type OptimizeFit = {
  iouFront: number
  iouSide: number
  profileRmseFront: number
  profileRmseSide: number
}

export type OptimizeResult = {
  ok: boolean
  jobId: string
  url: string
  bytes: number
  score: number
  fit: OptimizeFit
  targets: Record<string, number>
  details: DetailTargets
  metrics: Record<string, number>
  evaluations: number
  maxEvaluations: number
  elapsedSeconds: number
  scipy: {
    success: boolean
    message: string
    iterations: number
    functionEvaluations: number
  }
}

export type OptimizeJob = {
  jobId: string
  status: "running" | "done" | "error"
  progress?: {
    evaluations?: number
    maxEvaluations?: number
    bestScore?: number | null
    latest?: OptimizeFit
  }
  result?: OptimizeResult
  error?: string
  createdAt?: number
}

export type FitOutcome = {
  targets: BodyTargets
  error: number
  adjustments: string[]
}

// Closed-loop correction: compare the ratios the generated body actually achieved
// with the photo targets, then nudge the two controls that drive those ratios.
export function fitTargets(
  current: BodyTargets,
  achieved: Record<string, number>,
  desired: Proportions,
): FitOutcome | null {
  const achievedShoulder = achieved.shoulderToHip
  const achievedTorso = achieved.torsoToLeg
  if (!Number.isFinite(achievedShoulder) || !Number.isFinite(achievedTorso)) return null
  if (desired.shoulderToHip <= 0 || desired.torsoToLeg <= 0) return null

  const shoulderError = (desired.shoulderToHip - achievedShoulder) / desired.shoulderToHip
  const torsoError = (achievedTorso - desired.torsoToLeg) / desired.torsoToLeg
  const next: BodyTargets = { ...current }
  const adjustments: string[] = []

  if (Math.abs(shoulderError) > 0.04) {
    const muscle = round2(clamp01(current.muscle + shoulderError * 0.8))
    if (muscle !== current.muscle) {
      next.muscle = muscle
      adjustments.push(`muscle ${current.muscle.toFixed(2)} → ${muscle.toFixed(2)}`)
    }
  }

  if (Math.abs(torsoError) > 0.04) {
    const legLength = round2(clamp01(current.legLength + torsoError * 0.9))
    if (legLength !== current.legLength) {
      next.legLength = legLength
      adjustments.push(`leg length ${current.legLength.toFixed(2)} → ${legLength.toFixed(2)}`)
    }
  }

  if (adjustments.length === 0) return null
  return { targets: next, error: (Math.abs(shoulderError) + Math.abs(torsoError)) / 2, adjustments }
}

export function fitScore(achieved: Record<string, number>, desired: Proportions): number {
  const errors: number[] = []
  if (Number.isFinite(achieved.shoulderToHip) && desired.shoulderToHip > 0) {
    errors.push(Math.abs(achieved.shoulderToHip - desired.shoulderToHip) / desired.shoulderToHip)
  }
  if (Number.isFinite(achieved.torsoToLeg) && desired.torsoToLeg > 0) {
    errors.push(Math.abs(achieved.torsoToLeg - desired.torsoToLeg) / desired.torsoToLeg)
  }
  if (errors.length === 0) return 0
  const average = errors.reduce((sum, value) => sum + value, 0) / errors.length
  return Math.round(100 * Math.max(0, 1 - average))
}

export async function generateAvatar(
  targets: BodyTargets | MpbTargets,
  outfit: GarmentId[] = [],
  signal?: AbortSignal,
  details: DetailTargets = {},
): Promise<GenerateResult> {
  let res: Response
  try {
    res = await fetch(`${API_BASE}/api/avatar/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ targets, details, outfit }),
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
  const data = (await res.json()) as GenerateResult
  return { ...data, details: data.details ?? {}, metrics: data.metrics ?? {} }
}

export async function startAvatarOptimization(
  targets: BodyTargets | MpbTargets,
  details: DetailTargets,
  silhouettes: { front: string; side: string },
  maxEvaluations = 36,
  signal?: AbortSignal,
): Promise<{ jobId: string; status: string; progress: OptimizeJob["progress"] }> {
  let res: Response
  try {
    res = await fetch(`${API_BASE}/api/avatar/optimize`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ targets, details, silhouettes, maxEvaluations }),
      signal,
    })
  } catch {
    throw new Error(
      "Cannot reach the local avatar backend. Start it with: cd backend && uvicorn main:app --host 127.0.0.1 --port 8000",
    )
  }
  if (!res.ok) throw new Error(await readApiError(res))
  return (await res.json()) as { jobId: string; status: string; progress: OptimizeJob["progress"] }
}

export async function getAvatarOptimization(jobId: string, signal?: AbortSignal): Promise<OptimizeJob> {
  let res: Response
  try {
    res = await fetch(`${API_BASE}/api/avatar/optimize/${jobId}`, { signal })
  } catch {
    throw new Error("Cannot reach the local optimization backend.")
  }
  if (!res.ok) throw new Error(await readApiError(res))
  return (await res.json()) as OptimizeJob
}

export async function checkAvatarBackend(): Promise<Health> {
  const res = await fetch(`${API_BASE}/api/health`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return (await res.json()) as Health
}

async function readApiError(res: Response): Promise<string> {
  let detail = `HTTP ${res.status}`
  try {
    const body = await res.json()
    if (typeof body?.detail === "string") detail = body.detail
  } catch {
    // keep the HTTP status
  }
  return detail
}

export async function scanBodyQuestionnaire(
  payload: QuestionnairePayload,
  signal?: AbortSignal,
): Promise<BodyScanResult> {
  let res: Response
  try {
    res = await fetch(`${API_BASE}/api/body/questionnaire`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal,
    })
  } catch {
    throw new Error(
      "Cannot reach the local body-scan backend. Start it with: cd backend && uvicorn main:app --host 127.0.0.1 --port 8000",
    )
  }
  if (!res.ok) throw new Error(await readApiError(res))
  return (await res.json()) as BodyScanResult
}

export async function analyzeBodyVision(
  front: File,
  side: File,
  heightCm: number,
  signal?: AbortSignal,
): Promise<VisionAnalysis> {
  const form = new FormData()
  form.append("front", front)
  form.append("side", side)
  form.append("height_cm", String(heightCm))

  let res: Response
  try {
    res = await fetch(`${API_BASE}/api/body/vision`, {
      method: "POST",
      body: form,
      signal,
    })
  } catch {
    throw new Error(
      "Cannot reach the local body-scan backend. Start it with: cd backend && uvicorn main:app --host 127.0.0.1 --port 8000",
    )
  }
  if (!res.ok) throw new Error(await readApiError(res))
  return (await res.json()) as VisionAnalysis
}

export async function scanBodyMeasurements(
  payload: MeasurementsPayload,
  signal?: AbortSignal,
): Promise<BodyScanResult> {
  let res: Response
  try {
    res = await fetch(`${API_BASE}/api/body/measurements`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal,
    })
  } catch {
    throw new Error(
      "Cannot reach the local body-scan backend. Start it with: cd backend && uvicorn main:app --host 127.0.0.1 --port 8000",
    )
  }
  if (!res.ok) throw new Error(await readApiError(res))
  return (await res.json()) as BodyScanResult
}
