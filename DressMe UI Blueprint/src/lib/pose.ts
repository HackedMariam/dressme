import { FilesetResolver, PoseLandmarker } from "@mediapipe/tasks-vision"

export type Proportions = {
  shoulderToHip: number
  torsoToLeg: number
}

export type RatioReport = {
  key: keyof Proportions
  label: string
  value: number | null
  reliable: boolean
  note: string
}

export type PoseAnalysis =
  | {
      ok: true
      proportions: Proportions
      quality: number
      qualityLabel: "Good" | "Fair" | "Low"
      reports: RatioReport[]
      personHeight: number
    }
  | {
      ok: false
      reason: string
    }

const L_SHOULDER = 11
const R_SHOULDER = 12
const L_HIP = 23
const R_HIP = 24
const L_ANKLE = 27
const R_ANKLE = 28

const MIN_VISIBILITY = 0.5
const DEFAULT_PROPORTIONS: Proportions = { shoulderToHip: 1.3, torsoToLeg: 0.75 }
export const PROPORTION_LIMITS: Record<keyof Proportions, { min: number; max: number; step: number }> = {
  shoulderToHip: { min: 0.6, max: 2.4, step: 0.01 },
  torsoToLeg: { min: 0.3, max: 1.4, step: 0.01 },
}

export function defaultProportions(): Proportions {
  return { ...DEFAULT_PROPORTIONS }
}

let landmarkerPromise: Promise<PoseLandmarker> | null = null

function getLandmarker(): Promise<PoseLandmarker> {
  if (!landmarkerPromise) {
    landmarkerPromise = (async () => {
      const fileset = await FilesetResolver.forVisionTasks("/mediapipe/wasm")
      const base = {
        modelAssetPath: "/mediapipe/pose_landmarker_lite.task",
        delegate: "GPU" as const,
      }
      const options = {
        baseOptions: base,
        runningMode: "IMAGE" as const,
        numPoses: 1,
        minPoseDetectionConfidence: 0.4,
        minPosePresenceConfidence: 0.4,
        minPoseLandmarksConfidence: 0.4,
      }
      try {
        return await PoseLandmarker.createFromOptions(fileset, options)
      } catch {
        return await PoseLandmarker.createFromOptions(fileset, {
          ...options,
          baseOptions: { ...base, delegate: "CPU" as const },
        })
      }
    })()
  }
  return landmarkerPromise
}

export function preloadPoseModel(): Promise<unknown> {
  return getLandmarker()
}

function dist3(
  a: { x: number; y: number; z: number },
  b: { x: number; y: number; z: number },
): number {
  return Math.hypot(a.x - b.x, a.y - b.y, a.z - b.z)
}

function mid(a: { x: number; y: number; z: number }, b: { x: number; y: number; z: number }) {
  return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2, z: (a.z + b.z) / 2 }
}

function clamp01(n: number): number {
  return Math.min(1, Math.max(0, n))
}

export async function analyzePhoto(image: HTMLImageElement): Promise<PoseAnalysis> {
  const landmarker = await getLandmarker()
  const result = landmarker.detect(image)

  const world = result.worldLandmarks?.[0]
  if (!world || world.length < 29) {
    return {
      ok: false,
      reason:
        "No person was detected in this photo. Try a full-body shot with the whole body visible, good lighting, and a plain background.",
    }
  }

  const vis = (i: number) => (world[i]?.visibility ?? 0)
  const allVisible = [L_SHOULDER, R_SHOULDER, L_HIP, R_HIP, L_ANKLE, R_ANKLE].every((i) => vis(i) >= MIN_VISIBILITY)

  const shoulderMid = mid(world[L_SHOULDER], world[R_SHOULDER])
  const hipMid = mid(world[L_HIP], world[R_HIP])
  const ankleMid = mid(world[L_ANKLE], world[R_ANKLE])

  const shoulderWidth = dist3(world[L_SHOULDER], world[R_SHOULDER])
  const hipWidth = dist3(world[L_HIP], world[R_HIP])
  const torsoLength = dist3(shoulderMid, hipMid)
  const legLength = dist3(hipMid, ankleMid)
  const personHeight = torsoLength + legLength

  const shoulderVisOk = vis(L_SHOULDER) >= MIN_VISIBILITY && vis(R_SHOULDER) >= MIN_VISIBILITY
  const hipVisOk = vis(L_HIP) >= MIN_VISIBILITY && vis(R_HIP) >= MIN_VISIBILITY
  const ankleVisOk = vis(L_ANKLE) >= MIN_VISIBILITY && vis(R_ANKLE) >= MIN_VISIBILITY

  const shoulderToHip =
    shoulderVisOk && hipVisOk && shoulderWidth > 1e-4 && hipWidth > 1e-4
      ? shoulderWidth / hipWidth
      : null
  const torsoToLeg =
    shoulderVisOk && hipVisOk && ankleVisOk && torsoLength > 1e-4 && legLength > 1e-4
      ? torsoLength / legLength
      : null

  const shoulderToHipOk =
    shoulderToHip !== null && shoulderToHip >= 0.5 && shoulderToHip <= 2.8
  const torsoToLegOk = torsoToLeg !== null && torsoToLeg >= 0.2 && torsoToLeg <= 1.8

  if (shoulderToHip === null && torsoToLeg === null) {
    return {
      ok: false,
      reason:
        "A pose was found, but key body parts (shoulders, hips or ankles) are not reliably visible. Make sure the full body is in frame and not cropped or occluded.",
    }
  }

  const used = [L_SHOULDER, R_SHOULDER, L_HIP, R_HIP, L_ANKLE, R_ANKLE]
  const avgVis = used.reduce((sum, i) => sum + vis(i), 0) / used.length
  const minVis = Math.min(...used.map(vis))
  const completeness = personHeight >= 1.0 && personHeight <= 2.4 ? 1 : clamp01(personHeight / 1.0) * 0.6
  const geo = (shoulderToHipOk ? 0.5 : 0) + (torsoToLegOk ? 0.5 : 0)
  let quality = Math.round(100 * (0.5 * clamp01(avgVis) + 0.2 * clamp01(minVis) + 0.2 * completeness + 0.1 * geo))
  if (!allVisible) {
    quality = Math.min(quality, 60)
  }
  const qualityLabel: "Good" | "Fair" | "Low" = quality >= 75 ? "Good" : quality >= 50 ? "Fair" : "Low"

  const reports: RatioReport[] = [
    {
      key: "shoulderToHip",
      label: "Shoulder-to-hip width",
      value: shoulderToHip,
      reliable: shoulderToHipOk,
      note: shoulderToHipOk
        ? "Shoulders and hips clearly visible"
        : shoulderToHip === null
          ? "Shoulders or hips not reliably visible"
          : "Value looks implausible for this photo",
    },
    {
      key: "torsoToLeg",
      label: "Torso-to-leg length",
      value: torsoToLeg,
      reliable: torsoToLegOk,
      note: torsoToLegOk
        ? "Shoulders, hips and ankles clearly visible"
        : torsoToLeg === null
          ? "Legs or ankles cropped / occluded - ratio skipped"
          : "Value looks implausible for this photo",
    },
  ]

  return {
    ok: true,
    proportions: {
      shoulderToHip: shoulderToHipOk && shoulderToHip !== null ? shoulderToHip : DEFAULT_PROPORTIONS.shoulderToHip,
      torsoToLeg: torsoToLegOk && torsoToLeg !== null ? torsoToLeg : DEFAULT_PROPORTIONS.torsoToLeg,
    },
    quality,
    qualityLabel,
    reports,
    personHeight,
  }
}
