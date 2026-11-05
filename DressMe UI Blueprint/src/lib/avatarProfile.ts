import { analyzeBodyPhotos } from "./bodyPhotos"
import { analyzePhoto, type PosePoint } from "./pose"

export type Hairstyle = "long" | "bob" | "short" | "bun" | "curly" | "bald"
export type FaceShape = "oval" | "round" | "square" | "heart"

export type AvatarBody = {
  heightCm: number
  shoulderCm: number
  bustCm: number
  waistCm: number
  hipCm: number
  inseamCm: number
  thighCm: number
  calfCm: number
  neckCm: number
  upperArmCm: number
  wristCm: number
  chestDepthCm: number
  waistDepthCm: number
  hipDepthCm: number
}

export type AvatarAppearance = {
  skinColor: string
  hairColor: string
  eyeColor: string
  lipColor: string
  hairstyle: Hairstyle
  faceShape: FaceShape
}

export type AvatarProfile = {
  version: 1
  body: AvatarBody
  appearance: AvatarAppearance
  confidence: number
  notes: string[]
  source: "photos" | "manual"
  createdAt: number
}

export type AvatarDimensions = {
  height: number
  headHeight: number
  headWidth: number
  headDepth: number
  headBottomY: number
  headCenterY: number
  neckHeight: number
  shoulderY: number
  chestY: number
  waistY: number
  hipY: number
  kneeY: number
  ankleY: number
  shoulderHalf: number
  chestHalf: number
  waistHalf: number
  hipHalf: number
  chestDepthHalf: number
  waistDepthHalf: number
  hipDepthHalf: number
  thighHalf: number
  calfHalf: number
  ankleHalf: number
  neckHalf: number
  upperArmHalf: number
  wristHalf: number
  hipJointX: number
  upperArmLength: number
  foreArmLength: number
  handLength: number
  footLength: number
  footWidth: number
}

export const HAIRSTYLES: { value: Hairstyle; label: string }[] = [
  { value: "long", label: "Long" },
  { value: "bob", label: "Bob" },
  { value: "short", label: "Short" },
  { value: "bun", label: "Bun" },
  { value: "curly", label: "Curly" },
  { value: "bald", label: "Bald" },
]

export const FACE_SHAPES: { value: FaceShape; label: string }[] = [
  { value: "oval", label: "Oval" },
  { value: "round", label: "Round" },
  { value: "square", label: "Square" },
  { value: "heart", label: "Heart" },
]

export const SKIN_PRESETS = ["#F2D3BC", "#E3B894", "#C98F65", "#A96A43", "#7A4A2E", "#4E3020"]
export const HAIR_PRESETS = ["#1F1B18", "#3B2A21", "#6A4A32", "#A8763E", "#C9A15C", "#8C2F2F", "#D9D2C5"]

const DEFAULT_BODY: AvatarBody = {
  heightCm: 170,
  shoulderCm: 40,
  bustCm: 88,
  waistCm: 72,
  hipCm: 96,
  inseamCm: 79,
  thighCm: 54,
  calfCm: 35,
  neckCm: 34,
  upperArmCm: 28,
  wristCm: 16,
  chestDepthCm: 22,
  waistDepthCm: 18,
  hipDepthCm: 24,
}

const DEFAULT_APPEARANCE: AvatarAppearance = {
  skinColor: "#C98F65",
  hairColor: "#3B2A21",
  eyeColor: "#4A3828",
  lipColor: "#A25C52",
  hairstyle: "long",
  faceShape: "oval",
}

const PROFILE_STORAGE_KEY = "dressme.avatarStudio.v1"

function profileKey(userId: string | null | undefined): string {
  return `${PROFILE_STORAGE_KEY}.${userId || "guest"}`
}

export function defaultAvatarProfile(): AvatarProfile {
  return {
    version: 1,
    body: { ...DEFAULT_BODY },
    appearance: { ...DEFAULT_APPEARANCE },
    confidence: 0,
    notes: ["Neutral studio body. Upload photos or move the sliders to match your silhouette."],
    source: "manual",
    createdAt: Date.now(),
  }
}

export function loadAvatarProfile(userId: string | null | undefined): AvatarProfile | null {
  if (typeof window === "undefined") return null
  try {
    const raw = window.localStorage.getItem(profileKey(userId))
    if (!raw) return null
    const parsed = JSON.parse(raw) as AvatarProfile
    if (!parsed || parsed.version !== 1 || !parsed.body || !parsed.appearance) return null
    return {
      ...parsed,
      body: { ...DEFAULT_BODY, ...parsed.body },
      appearance: { ...DEFAULT_APPEARANCE, ...parsed.appearance },
    }
  } catch {
    return null
  }
}

export function saveAvatarProfile(userId: string | null | undefined, profile: AvatarProfile): void {
  if (typeof window === "undefined") return
  try {
    window.localStorage.setItem(profileKey(userId), JSON.stringify(profile))
  } catch {
    // Storage can be unavailable in private mode; the in-memory profile still works.
  }
}

export function clearAvatarProfile(userId: string | null | undefined): void {
  if (typeof window === "undefined") return
  try {
    window.localStorage.removeItem(profileKey(userId))
  } catch {
    // ignore
  }
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}

function num(value: unknown, fallback: number): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback
}

export function deriveAvatarDimensions(body: AvatarBody): AvatarDimensions {
  const H = clamp(body.heightCm, 120, 230) / 100
  const headHeight = H * 0.13
  const headWidth = H * 0.085
  const headDepth = H * 0.1
  const neckHeight = H * 0.035
  const headBottomY = H - headHeight
  const shoulderY = headBottomY - neckHeight
  const hipY = clamp(H - body.inseamCm / 100, H * 0.38, H * 0.62)
  const ankleY = H * 0.055
  const kneeY = ankleY + (hipY - ankleY) * 0.48
  const chestY = hipY + (shoulderY - hipY) * 0.62
  const waistY = hipY + (shoulderY - hipY) * 0.3

  const shoulderHalf = clamp(body.shoulderCm, 24, 60) / 200
  const chestHalf = clamp(body.bustCm, 55, 160) / 600
  const waistHalf = clamp(body.waistCm, 45, 150) / 600
  const hipHalf = clamp(body.hipCm, 60, 170) / 600

  return {
    height: H,
    headHeight,
    headWidth,
    headDepth,
    headBottomY,
    headCenterY: headBottomY + headHeight / 2,
    neckHeight,
    shoulderY,
    chestY,
    waistY,
    hipY,
    kneeY,
    ankleY,
    shoulderHalf,
    chestHalf,
    waistHalf,
    hipHalf,
    chestDepthHalf: clamp(body.chestDepthCm, 12, 45) / 200,
    waistDepthHalf: clamp(body.waistDepthCm, 10, 40) / 200,
    hipDepthHalf: clamp(body.hipDepthCm, 14, 48) / 200,
    thighHalf: clamp(body.thighCm, 30, 95) / 100 / (Math.PI * 2),
    calfHalf: clamp(body.calfCm, 20, 70) / 100 / (Math.PI * 2),
    ankleHalf: H * 0.023,
    neckHalf: clamp(body.neckCm, 24, 55) / 100 / (Math.PI * 2),
    upperArmHalf: clamp(body.upperArmCm, 18, 50) / 100 / (Math.PI * 2),
    wristHalf: clamp(body.wristCm, 11, 26) / 100 / (Math.PI * 2),
    hipJointX: hipHalf * 0.52,
    upperArmLength: H * 0.185,
    foreArmLength: H * 0.155,
    handLength: H * 0.09,
    footLength: H * 0.145,
    footWidth: H * 0.055,
  }
}

export type ArmJoints = {
  side: 1 | -1
  pivot: { x: number; y: number; z: number }
  elbow: { x: number; y: number; z: number }
  wrist: { x: number; y: number; z: number }
  direction: { x: number; y: number; z: number }
}

export function deriveArmJoints(dims: AvatarDimensions): ArmJoints[] {
  return ([1, -1] as const).map((side) => {
    const spread = 0.2
    const pivot = {
      x: side * dims.shoulderHalf * 0.87,
      y: dims.shoulderY - dims.height * 0.015,
      z: 0,
    }
    const direction = { x: side * Math.sin(spread), y: -Math.cos(spread), z: 0 }
    const elbow = {
      x: pivot.x + direction.x * dims.upperArmLength,
      y: pivot.y + direction.y * dims.upperArmLength,
      z: 0,
    }
    const foreDirection = { x: side * Math.sin(spread + 0.04), y: -Math.cos(spread + 0.04), z: 0 }
    const wrist = {
      x: elbow.x + foreDirection.x * dims.foreArmLength,
      y: elbow.y + foreDirection.y * dims.foreArmLength,
      z: 0,
    }
    return { side, pivot, elbow, wrist, direction }
  })
}

export type AvatarPhotoResult =
  | {
      ok: true
      profile: AvatarProfile
      frontWidthsCm: Record<string, number>
      sideDepths: Record<string, number>
      quality: number
    }
  | { ok: false; reason: string }

export async function createAvatarFromPhotos(
  front: HTMLImageElement,
  side: HTMLImageElement,
  heightCm: number,
): Promise<AvatarPhotoResult> {
  const analysis = await analyzeBodyPhotos(front, side, heightCm)
  if (!analysis.ok) return { ok: false, reason: analysis.reason }

  const m = analysis.measurements
  const widths = analysis.frontWidthsCm
  const depths = analysis.sideDepths

  const shoulderCm = clamp(num(m.shoulder_width_cm, widths.shoulder), 28, 56)
  const bustCm = clamp(num(m.bust_cm, widths.chest * 3), 65, 155)
  const waistCm = clamp(num(m.waist_cm, widths.waist * 3), 50, 145)
  const hipCm = clamp(num(m.hip_cm, widths.hip * 3), 70, 165)

  const chestWidthCm = bustCm / 3
  const waistWidthCm = waistCm / 3
  const hipWidthCm = hipCm / 3
  const chestDepth = clamp(num(depths.chest, chestWidthCm * 0.72), chestWidthCm * 0.55, chestWidthCm * 1.2)
  const waistDepth = clamp(num(depths.waist, waistWidthCm * 0.68), waistWidthCm * 0.5, waistWidthCm * 1.15)
  const hipDepth = clamp(num(depths.hip, hipWidthCm * 0.76), hipWidthCm * 0.55, hipWidthCm * 1.2)

  const body: AvatarBody = {
    heightCm: clamp(num(m.height_cm, heightCm), 140, 220),
    shoulderCm,
    bustCm,
    waistCm,
    hipCm,
    inseamCm: clamp(num(m.inseam_cm, heightCm * 0.46), 55, 105),
    thighCm: clamp(num(m.thigh_cm, hipCm * 0.58), 32, 90),
    calfCm: clamp(num(m.calf_cm, shoulderCm * 0.85), 22, 65),
    neckCm: clamp(num(m.neck_cm, heightCm * 0.19), 26, 52),
    upperArmCm: clamp(num(m.upperarm_cm, heightCm * 0.16), 18, 48),
    wristCm: clamp(num(m.wrist_cm, heightCm * 0.098), 12, 25),
    chestDepthCm: chestDepth,
    waistDepthCm: waistDepth,
    hipDepthCm: hipDepth,
  }

  const pose = await analyzePhoto(front, "front")
  const appearance = pose.ok
    ? extractAppearance(front, pose.landmarks)
    : { ...DEFAULT_APPEARANCE }

  const notes = [...analysis.notes]
  notes.unshift(
    "Your silhouette was rebuilt as a live 3D mesh in the browser from the front and side photos. No mesh files are uploaded.",
  )

  return {
    ok: true,
    profile: {
      version: 1,
      body,
      appearance,
      confidence: clamp(analysis.confidence, 0, 100),
      notes,
      source: "photos",
      createdAt: Date.now(),
    },
    frontWidthsCm: widths,
    sideDepths: depths,
    quality: analysis.confidence,
  }
}

const L_EYE = 2
const R_EYE = 5
const L_EAR = 7
const R_EAR = 8
const MOUTH_L = 9
const MOUTH_R = 10
const NOSE = 0

type Rgb = { r: number; g: number; b: number }

function midPoint(a: PosePoint, b: PosePoint): { x: number; y: number } {
  return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 }
}

function distance(a: PosePoint, b: PosePoint): number {
  return Math.hypot(a.x - b.x, a.y - b.y)
}

function hexToRgb(hex: string): Rgb {
  const match = /^#?([0-9a-f]{6})$/i.exec(hex)
  if (!match) return { r: 201, g: 143, b: 101 }
  const value = parseInt(match[1], 16)
  return { r: (value >> 16) & 255, g: (value >> 8) & 255, b: value & 255 }
}

function rgbToHex(c: Rgb): string {
  const to = (v: number) => clamp(Math.round(v), 0, 255).toString(16).padStart(2, "0")
  return `#${to(c.r)}${to(c.g)}${to(c.b)}`
}

function colorDistance(a: Rgb, b: Rgb): number {
  return Math.hypot(a.r - b.r, a.g - b.g, a.b - b.b)
}

function dominantColor(pixels: Rgb[]): Rgb | null {
  if (pixels.length === 0) return null
  const buckets = new Map<number, { count: number; r: number; g: number; b: number }>()
  for (const pixel of pixels) {
    const key = ((pixel.r >> 4) << 8) | ((pixel.g >> 4) << 4) | (pixel.b >> 4)
    const bucket = buckets.get(key) ?? { count: 0, r: 0, g: 0, b: 0 }
    bucket.count += 1
    bucket.r += pixel.r
    bucket.g += pixel.g
    bucket.b += pixel.b
    buckets.set(key, bucket)
  }
  let best: { count: number; r: number; g: number; b: number } | null = null
  for (const bucket of buckets.values()) {
    if (!best || bucket.count > best.count) best = bucket
  }
  if (!best) return null
  return { r: best.r / best.count, g: best.g / best.count, b: best.b / best.count }
}

function canvasFromImage(image: HTMLImageElement): { canvas: HTMLCanvasElement; ctx: CanvasRenderingContext2D } | null {
  const maxSide = 900
  const scale = Math.min(1, maxSide / Math.max(image.naturalWidth || image.width, image.naturalHeight || image.height))
  const canvas = document.createElement("canvas")
  canvas.width = Math.max(1, Math.round((image.naturalWidth || image.width) * scale))
  canvas.height = Math.max(1, Math.round((image.naturalHeight || image.height) * scale))
  const ctx = canvas.getContext("2d", { willReadFrequently: true })
  if (!ctx) return null
  ctx.drawImage(image, 0, 0, canvas.width, canvas.height)
  return { canvas, ctx }
}

function patchPixels(
  ctx: CanvasRenderingContext2D,
  cx: number,
  cy: number,
  rx: number,
  ry: number,
): Rgb[] {
  const { width, height } = ctx.canvas
  const x0 = clamp(Math.round(cx - rx), 0, width - 1)
  const x1 = clamp(Math.round(cx + rx), 0, width - 1)
  const y0 = clamp(Math.round(cy - ry), 0, height - 1)
  const y1 = clamp(Math.round(cy + ry), 0, height - 1)
  if (x1 <= x0 || y1 <= y0) return []
  try {
    const data = ctx.getImageData(x0, y0, x1 - x0, y1 - y0).data
    const pixels: Rgb[] = []
    for (let i = 0; i < data.length; i += 4) {
      if (data[i + 3] < 30) continue
      pixels.push({ r: data[i], g: data[i + 1], b: data[i + 2] })
    }
    return pixels
  } catch {
    return []
  }
}

function areaPixels(
  ctx: CanvasRenderingContext2D,
  nx0: number,
  ny0: number,
  nx1: number,
  ny1: number,
  reject?: (pixel: Rgb) => boolean,
): Rgb[] {
  const { width, height } = ctx.canvas
  const x0 = clamp(Math.round(nx0 * width), 0, width - 1)
  const x1 = clamp(Math.round(nx1 * width), 0, width - 1)
  const y0 = clamp(Math.round(ny0 * height), 0, height - 1)
  const y1 = clamp(Math.round(ny1 * height), 0, height - 1)
  if (x1 <= x0 || y1 <= y0) return []
  try {
    const data = ctx.getImageData(x0, y0, x1 - x0, y1 - y0).data
    const pixels: Rgb[] = []
    const step = Math.max(1, Math.floor(Math.hypot(x1 - x0, y1 - y0) / 120))
    for (let y = 0; y < y1 - y0; y += step) {
      for (let x = 0; x < x1 - x0; x += step) {
        const i = (y * (x1 - x0) + x) * 4
        if (data[i + 3] < 30) continue
        const pixel = { r: data[i], g: data[i + 1], b: data[i + 2] }
        if (reject?.(pixel)) continue
        pixels.push(pixel)
      }
    }
    return pixels
  } catch {
    return []
  }
}

function luminance(pixel: Rgb): number {
  return 0.2126 * pixel.r + 0.7152 * pixel.g + 0.0722 * pixel.b
}

function extractAppearance(image: HTMLImageElement, landmarks: PosePoint[]): AvatarAppearance {
  const appearance: AvatarAppearance = { ...DEFAULT_APPEARANCE }
  if (landmarks.length < 29) return appearance
  const source = canvasFromImage(image)
  if (!source) return appearance
  const { ctx } = source
  const W = ctx.canvas.width
  const H = ctx.canvas.height

  const nose = landmarks[NOSE]
  const eyeL = landmarks[L_EYE]
  const eyeR = landmarks[R_EYE]
  const earL = landmarks[L_EAR]
  const earR = landmarks[R_EAR]
  const mouth = midPoint(landmarks[MOUTH_L], landmarks[MOUTH_R])
  const eyeMid = midPoint(eyeL, eyeR)
  const eyeDistance = Math.max(0.008, distance(eyeL, eyeR))
  const earDistance = Math.max(eyeDistance, distance(earL, earR))
  const faceHeight = eyeDistance * 3.05

  const toX = (value: number) => value * W
  const toY = (value: number) => value * H
  const radius = (fraction: number) => Math.max(2, fraction * W)

  const borderSamples = [
    patchPixels(ctx, 2, 2, 4, 4),
    patchPixels(ctx, W - 3, 2, 4, 4),
    patchPixels(ctx, 2, H - 3, 4, 4),
    patchPixels(ctx, W - 3, H - 3, 4, 4),
  ].flat()
  const background = dominantColor(borderSamples) ?? { r: 240, g: 240, b: 240 }

  const skinSamples = [
    patchPixels(ctx, toX(nose.x), toY(eyeMid.y - eyeDistance * 0.62), radius(eyeDistance * 0.22), radius(eyeDistance * 0.14)),
    patchPixels(ctx, toX(nose.x - eyeDistance * 0.55), toY(nose.y + eyeDistance * 0.08), radius(eyeDistance * 0.16), radius(eyeDistance * 0.18)),
    patchPixels(ctx, toX(nose.x + eyeDistance * 0.55), toY(nose.y + eyeDistance * 0.08), radius(eyeDistance * 0.16), radius(eyeDistance * 0.18)),
    patchPixels(ctx, toX(nose.x), toY(nose.y), radius(eyeDistance * 0.13), radius(eyeDistance * 0.14)),
  ].flat()

  const plausibleSkin = skinSamples.filter(
    (pixel) =>
      luminance(pixel) > 45 &&
      colorDistance(pixel, background) > 28 &&
      pixel.r >= pixel.b - 8,
  )
  const skin = dominantColor(plausibleSkin)
  if (skin) appearance.skinColor = rgbToHex(skin)

  const hairBand:
    | { r: number; g: number; b: number }
    | null = dominantColor(
    areaPixels(
      ctx,
      nose.x - eyeDistance * 1.05,
      eyeMid.y - eyeDistance * 1.35,
      nose.x + eyeDistance * 1.05,
      eyeMid.y - eyeDistance * 0.32,
      (pixel) => {
        if (colorDistance(pixel, background) < 40) return true
        if (skin && colorDistance(pixel, skin) < 38) return true
        return luminance(pixel) > 238
      },
    ),
  )
  if (hairBand) {
    const darker = { r: hairBand.r * 0.92, g: hairBand.g * 0.92, b: hairBand.b * 0.92 }
    appearance.hairColor = rgbToHex(darker)
  }

  const lipPixels = patchPixels(
    ctx,
    toX(mouth.x),
    toY(mouth.y),
    radius(eyeDistance * 0.3),
    radius(eyeDistance * 0.12),
  )
  const lip = dominantColor(lipPixels)
  if (lip) {
    const blended = {
      r: lip.r * 0.72 + hexToRgb(appearance.skinColor).r * 0.28,
      g: lip.g * 0.55 + hexToRgb(appearance.skinColor).g * 0.45,
      b: lip.b * 0.55 + hexToRgb(appearance.skinColor).b * 0.45,
    }
    appearance.lipColor = rgbToHex(blended)
  }

  const eyePixels = [
    patchPixels(ctx, toX(eyeL.x), toY(eyeL.y), radius(eyeDistance * 0.16), radius(eyeDistance * 0.09)),
    patchPixels(ctx, toX(eyeR.x), toY(eyeR.y), radius(eyeDistance * 0.16), radius(eyeDistance * 0.09)),
  ].flat()
  const iris = dominantColor(
    eyePixels.filter((pixel) => luminance(pixel) > 25 && luminance(pixel) < 190),
  )
  if (iris) appearance.eyeColor = rgbToHex(iris)

  const faceRatio = earDistance / Math.max(0.001, faceHeight)
  appearance.faceShape =
    faceRatio > 0.72 ? "round" : faceRatio > 0.68 ? "square" : faceRatio < 0.6 ? "heart" : "oval"

  const hairBelow = areaPixels(
    ctx,
    nose.x - eyeDistance * 1.3,
    mouth.y + eyeDistance * 0.45,
    nose.x + eyeDistance * 1.3,
    mouth.y + eyeDistance * 2.6,
    (pixel) => {
      if (colorDistance(pixel, background) < 45) return true
      if (skin && colorDistance(pixel, skin) < 45) return true
      if (hairBand && colorDistance(pixel, hairBand) > 70) return true
      return false
    },
  )
  const hairRatio = hairBelow.length / Math.max(1, Math.round(W * H * 0.01))
  appearance.hairstyle = hairRatio > 0.55 ? "long" : hairRatio > 0.22 ? "bob" : "short"

  return appearance
}

export function describeBody(body: AvatarBody): string {
  return `${Math.round(body.heightCm)} cm · shoulders ${Math.round(body.shoulderCm)} cm · waist ${Math.round(
    body.waistCm,
  )} cm · hips ${Math.round(body.hipCm)} cm`
}

export function appearanceSwatch(hex: string): string {
  const rgb = hexToRgb(hex)
  return rgbToHex(rgb)
}
