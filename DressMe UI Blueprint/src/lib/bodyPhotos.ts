import { analyzePhoto, type PoseAnalysis, type PosePoint } from "./pose"
import { extractSilhouette, measureRow, silhouetteToPngDataUrl, type Silhouette } from "./silhouette"
import type { MeasurementsPayload } from "./avatarApi"

const L_SHOULDER = 11
const R_SHOULDER = 12
const L_HIP = 23
const R_HIP = 24
const L_KNEE = 25
const R_KNEE = 26
const L_ANKLE = 27
const R_ANKLE = 28

export type PhotoPairAnalysis =
  | {
      ok: true
      measurements: MeasurementsPayload
      detailSuggestions: Record<string, number>
      confidence: number
      frontQuality: number
      sideQuality: number
      frontWidthsCm: Record<string, number>
      sideDepths: Record<string, number>
      silhouettes: { front: string; side: string }
      notes: string[]
    }
  | { ok: false; reason: string }

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}

function midY(a: PosePoint, b: PosePoint): number {
  return (a.y + b.y) / 2
}

function toBoxFraction(yNormalized: number, silhouette: Silhouette): number {
  const y = yNormalized * silhouette.height
  return clamp((y - silhouette.box.minY) / silhouette.box.height, 0, 1)
}

function bodyFractions(landmarks: PosePoint[], silhouette: Silhouette) {
  const shoulderY = midY(landmarks[L_SHOULDER], landmarks[R_SHOULDER])
  const hipY = midY(landmarks[L_HIP], landmarks[R_HIP])
  const kneeY = midY(landmarks[L_KNEE], landmarks[R_KNEE])
  const ankleY = midY(landmarks[L_ANKLE], landmarks[R_ANKLE])

  return {
    shoulder: toBoxFraction(shoulderY, silhouette),
    chest: toBoxFraction(shoulderY + (hipY - shoulderY) * 0.25, silhouette),
    waist: toBoxFraction(shoulderY + (hipY - shoulderY) * 0.65, silhouette),
    hip: toBoxFraction(hipY, silhouette),
    thigh: toBoxFraction(hipY + (ankleY - hipY) * 0.28, silhouette),
    knee: toBoxFraction(kneeY, silhouette),
    calf: toBoxFraction(hipY + (ankleY - hipY) * 0.72, silhouette),
    ankle: toBoxFraction(ankleY, silhouette),
    legFraction: clamp((ankleY - hipY) / Math.max(1e-6, silhouette.box.height / silhouette.height), 0, 1),
  }
}

function rowWidthCm(silhouette: Silhouette, fraction: number, heightCm: number): number {
  const row = measureRow(silhouette, fraction)
  return (row.width * heightCm) / Math.max(1, silhouette.box.height)
}

export async function analyzeBodyPhotos(
  frontImage: HTMLImageElement,
  sideImage: HTMLImageElement,
  heightCm: number,
): Promise<PhotoPairAnalysis> {
  const front = await analyzePhoto(frontImage, "front")
  if (!front.ok) return { ok: false, reason: `Front photo: ${front.reason}` }

  const side = await analyzePhoto(sideImage, "side")
  if (!side.ok) return { ok: false, reason: `Side photo: ${side.reason}` }

  let frontSilhouette: Silhouette
  let sideSilhouette: Silhouette
  try {
    frontSilhouette = await extractSilhouette(frontImage)
    sideSilhouette = await extractSilhouette(sideImage)
  } catch (error) {
    return {
      ok: false,
      reason: error instanceof Error ? error.message : "Could not extract the body silhouettes.",
    }
  }

  const frontFractions = bodyFractions(front.landmarks, frontSilhouette)
  const sideFractions = bodyFractions(side.landmarks, sideSilhouette)

  const frontWidthsCm = {
    shoulder: rowWidthCm(frontSilhouette, frontFractions.shoulder, heightCm),
    chest: rowWidthCm(frontSilhouette, frontFractions.chest, heightCm),
    waist: rowWidthCm(frontSilhouette, frontFractions.waist, heightCm),
    hip: rowWidthCm(frontSilhouette, frontFractions.hip, heightCm),
    thigh: rowWidthCm(frontSilhouette, frontFractions.thigh, heightCm),
    calf: rowWidthCm(frontSilhouette, frontFractions.calf, heightCm),
  }

  const sideDepths = {
    shoulder: rowWidthCm(sideSilhouette, sideFractions.shoulder, heightCm),
    chest: rowWidthCm(sideSilhouette, sideFractions.chest, heightCm),
    waist: rowWidthCm(sideSilhouette, sideFractions.waist, heightCm),
    hip: rowWidthCm(sideSilhouette, sideFractions.hip, heightCm),
    thigh: rowWidthCm(sideSilhouette, sideFractions.thigh, heightCm),
    calf: rowWidthCm(sideSilhouette, sideFractions.calf, heightCm),
  }

  const widthRatio =
    (frontWidthsCm.shoulder / heightCm + frontWidthsCm.hip / heightCm) / 2
  const bmi = clamp(22 + (widthRatio - 0.24) * 80, 16, 40)
  const massKg = bmi * (heightCm / 100) ** 2

  const legFraction = frontFractions.legFraction
  const inseam = legFraction * heightCm * 0.89

  const measurements: MeasurementsPayload = {
    height_cm: Math.round(heightCm * 10) / 10,
    mass_kg: Math.round(massKg * 10) / 10,
    bmi: Math.round(bmi * 10) / 10,
    shoulder_width_cm: Math.round(frontWidthsCm.shoulder * 10) / 10,
    bust_cm: Math.round(frontWidthsCm.chest * 3 * 10) / 10,
    underbust_cm: Math.round(frontWidthsCm.chest * 2.85 * 10) / 10,
    waist_cm: Math.round(frontWidthsCm.waist * 3 * 10) / 10,
    hip_cm: Math.round(frontWidthsCm.hip * 3 * 10) / 10,
    inseam_cm: Math.round(inseam * 10) / 10,
    thigh_cm: Math.round(frontWidthsCm.thigh * 0.55 * Math.PI * 10) / 10,
    calf_cm: Math.round(frontWidthsCm.calf * 0.55 * Math.PI * 10) / 10,
    neck_cm: Math.round(heightCm * 0.19 * 10) / 10,
    upperarm_cm: Math.round(heightCm * 0.17 * 10) / 10,
  }

  const chestDepthRatio = sideDepths.chest / heightCm
  const hipDepthRatio = sideDepths.hip / heightCm
  const detailSuggestions = {
    torsoDepth: clamp((chestDepthRatio / 0.18 - 1) * 3, -1, 1),
    hipDepth: clamp((hipDepthRatio / 0.19 - 1) * 3, -1, 1),
  }

  const confidence = Math.round(front.quality * 0.55 + side.quality * 0.45)
  const notes = [
    "Measurements come from MediaPipe pose landmarks, body silhouettes and the height you entered. They are estimates, not tape measurements.",
    "Mass and BMI are inferred from the silhouette width-to-height ratio; edit them in the questionnaire if you know the real values.",
    "The side silhouette only nudges torso and hip depth; every value remains editable before generation.",
    "Photos stay in the browser. Nothing is uploaded or sent to an external service.",
  ]

  return {
    ok: true,
    measurements,
    detailSuggestions,
    confidence,
    frontQuality: front.quality,
    sideQuality: side.quality,
    frontWidthsCm,
    sideDepths,
    silhouettes: {
      front: silhouetteToPngDataUrl(frontSilhouette),
      side: silhouetteToPngDataUrl(sideSilhouette),
    },
    notes,
  }
}
