import { useEffect, useMemo, useRef, useState } from "react"
import { AvatarCanvas } from "./AvatarViewer"
import {
  AGE_PRESETS,
  analyzeBodyVision,
  defaultMpbTargets,
  fitScore,
  fitTargets,
  GENDER_PRESETS,
  generateAvatar,
  getAvatarOptimization,
  heightFromCm,
  legLengthFromTorsoToLeg,
  MPFB_NEUTRAL,
  MPFB_PARAMS,
  muscleFromShoulderToHip,
  scanBodyMeasurements,
  scanBodyQuestionnaire,
  startAvatarOptimization,
  type BodyScanResult,
  type BodyTargets,
  type DetailTargets,
  type GenerateResult,
  type MpbParam,
  type MpbParamMeta,
  type OptimizeResult,
  type QuestionnairePayload,
  type VisionAnalysis,
  versionedUrl,
} from "../lib/avatarApi"
import { analyzeBodyPhotos, type PhotoPairAnalysis } from "../lib/bodyPhotos"
import { preloadPoseModel } from "../lib/pose"
import { preloadSilhouetteModel } from "../lib/silhouette"
import { BODY_SHAPES, CUP_SIZES, GENDERS, measurementRows } from "../lib/questionnaire"
import {
  countActiveDetails,
  DETAIL_CONTROLS,
  detailTargetsToValues,
  detailValuesToTargets,
  type DetailValues,
} from "../lib/bodyDetails"

type Proportions = {
  shoulderToHip: number
  torsoToLeg: number
}

const DEFAULT_PROPORTIONS: Proportions = { shoulderToHip: 1.3, torsoToLeg: 0.75 }
const PROPORTION_LIMITS: Record<keyof Proportions, { min: number; max: number; step: number }> = {
  shoulderToHip: { min: 0.9, max: 1.8, step: 0.01 },
  torsoToLeg: { min: 0.5, max: 1.1, step: 0.01 },
}

const RATIO_LABELS: Record<keyof Proportions, string> = {
  shoulderToHip: "Shoulder-to-hip",
  torsoToLeg: "Torso-to-leg",
}

function loadImage(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image()
    image.onload = () => resolve(image)
    image.onerror = () => reject(new Error("Could not load that photo."))
    image.src = url
  })
}

export default function CustomizeAvatar({
  initialUrl,
  onUseParams,
  onGoToTryOn,
}: {
  initialUrl?: string
  onUseParams?: (p: BodyTargets, details: DetailTargets, heightCm: number) => void
  onGoToTryOn?: () => void
} = {}) {
  const [mpfb, setMpb] = useState<Record<MpbParam, number>>(defaultMpbTargets)
  const [adjusted, setAdjusted] = useState<Proportions>(DEFAULT_PROPORTIONS)
  const [legLengthOverride, setLegLengthOverride] = useState<number | null>(null)
  const [linkMuscle, setLinkMuscle] = useState(true)
  const [heightCm, setHeightCm] = useState(170)
  const [detailValues, setDetailValues] = useState<DetailValues>({})
  const [captureMode, setCaptureMode] = useState<"photos" | "questionnaire">("photos")
  const [frontFile, setFrontFile] = useState<File | null>(null)
  const [sideFile, setSideFile] = useState<File | null>(null)
  const [frontUrl, setFrontUrl] = useState<string | null>(null)
  const [sideUrl, setSideUrl] = useState<string | null>(null)
  const [photoAnalysis, setPhotoAnalysis] = useState<Extract<PhotoPairAnalysis, { ok: true }> | null>(null)
  const [photoState, setPhotoState] = useState<"idle" | "running" | "success" | "error">("idle")
  const [photoError, setPhotoError] = useState<string | null>(null)
  const [visionConsent, setVisionConsent] = useState(false)
  const [visionState, setVisionState] = useState<"idle" | "running" | "success" | "error">("idle")
  const [visionResult, setVisionResult] = useState<VisionAnalysis | null>(null)
  const [createError, setCreateError] = useState<string | null>(null)
  const [optState, setOptState] = useState<"idle" | "running" | "success" | "error">("idle")
  const [optError, setOptError] = useState<string | null>(null)
  const [optProgress, setOptProgress] = useState<{
    evaluations: number
    maxEvaluations: number
    bestScore: number | null
  }>({ evaluations: 0, maxEvaluations: 36, bestScore: null })
  const [optResult, setOptResult] = useState<OptimizeResult | null>(null)

  const [qMass, setQMass] = useState(65)
  const [qGender, setQGender] = useState<"female" | "male">("female")
  const [qShape, setQShape] = useState<QuestionnairePayload["body_shape"]>("hourglass")
  const [qBelly, setQBelly] = useState(2)
  const [qBuild, setQBuild] = useState(2)
  const [qLegs, setQLegs] = useState(2)
  const [qArms, setQArms] = useState(2)
  const [qCup, setQCup] = useState("")

  const [scanState, setScanState] = useState<"idle" | "running" | "success" | "error">("idle")
  const [scanError, setScanError] = useState<string | null>(null)
  const [scanResult, setScanResult] = useState<BodyScanResult | null>(null)

  const [genState, setGenState] = useState<"idle" | "running" | "success" | "error">("idle")
  const [genError, setGenError] = useState<string | null>(null)
  const [generatedUrl, setGeneratedUrl] = useState<string | null>(initialUrl ?? null)
  const [lastJob, setLastJob] = useState<string | null>(null)
  const [lastResult, setLastResult] = useState<GenerateResult | null>(null)
  const [genIteration, setGenIteration] = useState(0)
  const [fitInfo, setFitInfo] = useState<{ score: number; achieved: Record<string, number> } | null>(null)
  const genAbortRef = useRef<AbortController | null>(null)
  const optAbortRef = useRef<AbortController | null>(null)
  const optTimerRef = useRef<number | null>(null)
  const frontUrlRef = useRef<string | null>(null)
  const sideUrlRef = useRef<string | null>(null)

  useEffect(() => {
    return () => {
      genAbortRef.current?.abort()
      optAbortRef.current?.abort()
      if (optTimerRef.current !== null) window.clearTimeout(optTimerRef.current)
      if (frontUrlRef.current) URL.revokeObjectURL(frontUrlRef.current)
      if (sideUrlRef.current) URL.revokeObjectURL(sideUrlRef.current)
    }
  }, [])

  useEffect(() => {
    if (initialUrl) setGeneratedUrl(initialUrl)
  }, [initialUrl])

  useEffect(() => {
    preloadPoseModel().catch(() => undefined)
    preloadSilhouetteModel().catch(() => undefined)
  }, [])

  const cancelOptimization = () => {
    optAbortRef.current?.abort()
    if (optTimerRef.current !== null) {
      window.clearTimeout(optTimerRef.current)
      optTimerRef.current = null
    }
    setOptResult(null)
    setOptState("idle")
    setOptError(null)
  }

  useEffect(() => {
    if (!linkMuscle) return
    const linked = muscleFromShoulderToHip(adjusted.shoulderToHip)
    setMpb((prev) => (prev.muscle === linked ? prev : { ...prev, muscle: linked }))
  }, [adjusted.shoulderToHip, linkMuscle])

  const derivedLegLength = useMemo(() => legLengthFromTorsoToLeg(adjusted.torsoToLeg), [adjusted.torsoToLeg])
  const legLength = legLengthOverride ?? derivedLegLength

  const activeTargets = useMemo(
    () => (Object.entries(mpfb) as [MpbParam, number][]).filter(([, v]) => Math.abs(v - MPFB_NEUTRAL) > 0.001),
    [mpfb],
  )
  const activeDetails = countActiveDetails(detailValues)
  const detailTargets = useMemo(() => detailValuesToTargets(detailValues), [detailValues])

  const rows = scanResult ? measurementRows(scanResult.measurements) : []
  const captureState =
    captureMode === "photos"
      ? visionState !== "idle"
        ? visionState
        : photoState !== "idle"
          ? photoState
          : scanState
      : scanState

  const onHeightCmChange = (value: number) => {
    setHeightCm(value)
    setCreateError(null)
    setPhotoAnalysis(null)
    setPhotoState("idle")
    setVisionResult(null)
    setVisionState("idle")
    cancelOptimization()
    if (!Number.isFinite(value) || value < 140 || value > 220) return
    setMpb((prev) => ({ ...prev, height: heightFromCm(value) }))
  }

  const onPhotoFile = (slot: "front" | "side", file: File | undefined) => {
    if (!file) return
    if (!file.type.startsWith("image/")) {
      setPhotoError("Choose a JPG, PNG, or WebP image.")
      return
    }
    if (file.size > 20 * 1024 * 1024) {
      setPhotoError("That photo is larger than 20 MB. Pick a smaller one.")
      return
    }

    const url = URL.createObjectURL(file)
    if (slot === "front") {
      if (frontUrlRef.current) URL.revokeObjectURL(frontUrlRef.current)
      frontUrlRef.current = url
      setFrontUrl(url)
      setFrontFile(file)
    } else {
      if (sideUrlRef.current) URL.revokeObjectURL(sideUrlRef.current)
      sideUrlRef.current = url
      setSideUrl(url)
      setSideFile(file)
    }
    setPhotoAnalysis(null)
    setPhotoState("idle")
    setCreateError(null)
    setPhotoError(null)
    setVisionResult(null)
    setVisionState("idle")
    cancelOptimization()
  }

  const onAnalyzePhotos = async () => {
    if (!frontFile || !sideFile || !frontUrl || !sideUrl) {
      setPhotoError("Add both a front and a side photo.")
      return
    }
    if (!Number.isFinite(heightCm) || heightCm < 140 || heightCm > 220) {
      setPhotoError("Enter a height between 140 and 220 cm.")
      return
    }

    setPhotoState("running")
    setCreateError(null)
    setPhotoError(null)
    cancelOptimization()
    try {
      const [frontImage, sideImage] = await Promise.all([loadImage(frontUrl), loadImage(sideUrl)])
      const analysis = await analyzeBodyPhotos(frontImage, sideImage, heightCm)
      if (!analysis.ok) {
        setPhotoState("error")
        setPhotoError(analysis.reason)
        return
      }

      const result = await scanBodyMeasurements(analysis.measurements)
      setPhotoAnalysis(analysis)
      applyBodyScan({ ...result, notes: [...analysis.notes, ...result.notes] })
      setDetailValues(analysis.detailSuggestions)
      setPhotoState("success")
    } catch (e) {
      setPhotoState("error")
      setPhotoError(e instanceof Error ? e.message : "Photo analysis failed.")
    }
  }

  const applyBodyScan = (result: BodyScanResult) => {
    setScanResult(result)
    setScanState("success")
    setScanError(null)

    setMpb((prev) => {
      const next = { ...prev }
      for (const meta of MPFB_PARAMS) {
        const value = result.targets[meta.key]
        if (value !== undefined) next[meta.key] = value
      }
      return next
    })

    if (result.ratios.shoulderToHip !== undefined) {
      setAdjusted((prev) => ({ ...prev, shoulderToHip: result.ratios.shoulderToHip as number }))
    }
    if (result.ratios.torsoToLeg !== undefined) {
      setAdjusted((prev) => ({ ...prev, torsoToLeg: result.ratios.torsoToLeg as number }))
    }
    if (result.targets.legLength !== undefined) {
      setLegLengthOverride(result.targets.legLength)
    }
    if (result.measurements.height_cm) {
      setHeightCm(Math.round(result.measurements.height_cm))
    }
    setLinkMuscle(false)
    setDetailValues({})
    setFitInfo(null)
  }

  const applyQuestionnaire = (result: BodyScanResult) => {
    setCreateError(null)
    setPhotoAnalysis(null)
    setPhotoState("idle")
    setVisionResult(null)
    setVisionState("idle")
    cancelOptimization()
    applyBodyScan(result)
  }

  const onQuestionnaire = async () => {
    setScanState("running")
    setScanError(null)
    const payload: QuestionnairePayload = {
      height_cm: heightCm,
      mass_kg: qMass,
      gender: qGender,
      body_shape: qShape,
      belly: qBelly,
      build: qBuild,
      legs: qLegs,
      arms: qArms,
      ...(qCup ? { cupsize: qCup } : {}),
    }
    try {
      const result = await scanBodyQuestionnaire(payload)
      applyQuestionnaire(result)
    } catch (e) {
      setScanState("error")
      setScanError(e instanceof Error ? e.message : "Questionnaire measurement failed.")
    }
  }

  const onGenerate = async () => {
    if (genState === "running") return
    genAbortRef.current?.abort()
    const controller = new AbortController()
    genAbortRef.current = controller
    const timer = window.setTimeout(() => controller.abort(), 320_000)
    setGenState("running")
    setGenError(null)
    setFitInfo(null)
    setGenIteration(0)
    try {
      let current: BodyTargets = { ...mpfb, legLength }
      let last: GenerateResult | null = null
      const desired = scanResult ? { ...adjusted } : undefined
      const maxPasses = desired ? 2 : 1

      for (let pass = 0; pass < maxPasses; pass++) {
        setGenIteration(pass + 1)
        last = await generateAvatar(current, [], controller.signal, detailTargets, { heightCm })
        if (!desired) break
        const next = fitTargets(current, last.metrics, desired)
        if (!next) break
        if (!linkMuscle) {
          next.targets.muscle = current.muscle
          if (next.targets.legLength === current.legLength) break
        }
        current = next.targets
      }

      if (!last) throw new Error("Generation produced no result")
      setGeneratedUrl(versionedUrl(last.url, last.jobId))
      setLastJob(last.jobId)
      setLastResult(last)
      setGenState("success")
      setLegLengthOverride(current.legLength)
      if (desired && last.metrics) {
        setFitInfo({ score: fitScore(last.metrics, desired), achieved: last.metrics })
      }
      onUseParams?.(current, detailTargets, heightCm)
    } catch (e) {
      const aborted = controller.signal.aborted
      setGenState("error")
      setGenError(
        aborted
          ? "Generation timed out after ~5 minutes. Check the backend console for the Blender log."
          : e instanceof Error
            ? e.message
            : "Generation failed for an unknown reason.",
      )
    } finally {
      window.clearTimeout(timer)
    }
  }

  const applyOptimized = (result: OptimizeResult) => {
    setMpb((prev) => {
      const next = { ...prev }
      for (const meta of MPFB_PARAMS) {
        const value = result.targets[meta.key]
        if (value !== undefined) next[meta.key] = value
      }
      return next
    })
    if (result.targets.legLength !== undefined) {
      setLegLengthOverride(result.targets.legLength)
    }
    setDetailValues(detailTargetsToValues(result.details))
    setGeneratedUrl(versionedUrl(result.url, result.jobId))
    setLastJob(result.jobId)
    setLastResult({
      jobId: result.jobId,
      url: result.url,
      params: result.targets,
      details: result.details,
      outfit: [],
      bytes: result.bytes,
      elapsedSeconds: result.elapsedSeconds,
      metrics: result.metrics,
    })
    setGenState("success")
    setGenError(null)
    const match = Math.round(100 * (0.5 * result.fit.iouFront + 0.5 * result.fit.iouSide))
    setFitInfo({ score: match, achieved: result.metrics })
    onUseParams?.(
      {
        ...defaultMpbTargets(),
        ...(result.targets as Partial<Record<MpbParam, number>>),
        legLength: result.targets.legLength ?? legLength,
      } as BodyTargets,
      result.details,
      heightCm,
    )
  }

  const onCreateAvatar = async () => {
    if (!frontFile || !sideFile) {
      setCreateError("Add both a front and a side photo.")
      return
    }
    if (!visionConsent) {
      setCreateError("Agree to send both photos to OpenAI before creating the avatar.")
      return
    }
    if (!Number.isFinite(heightCm) || heightCm < 140 || heightCm > 220) {
      setCreateError("Enter a height between 140 and 220 cm.")
      return
    }

    genAbortRef.current?.abort()
    const controller = new AbortController()
    genAbortRef.current = controller
    const timer = window.setTimeout(() => controller.abort(), 420_000)
    setCreateError(null)
    setVisionState("running")
    setGenState("idle")
    setGenError(null)
    setScanResult(null)
    cancelOptimization()

    try {
      const vision = await analyzeBodyVision(frontFile, sideFile, heightCm, controller.signal)
      setVisionResult(vision)

      const rawTargets = vision.analysis.targets ?? {}
      const nextMpb = defaultMpbTargets()
      for (const meta of MPFB_PARAMS) {
        const value = rawTargets[meta.key]
        if (value !== undefined) nextMpb[meta.key] = Math.max(0, Math.min(1, value))
      }
      nextMpb.height = heightFromCm(heightCm)
      const nextLegLength =
        rawTargets.legLength !== undefined ? Math.max(0, Math.min(1, rawTargets.legLength)) : MPFB_NEUTRAL
      const targets: BodyTargets = { ...nextMpb, legLength: nextLegLength }

      const allowed = new Set(DETAIL_CONTROLS.map((control) => control.key))
      const rawDetails = vision.analysis.detail_values ?? vision.analysis.suggested_details ?? {}
      const nextDetails: DetailValues = {}
      for (const [key, value] of Object.entries(rawDetails)) {
        if (allowed.has(key)) nextDetails[key] = Math.max(-1, Math.min(1, value))
      }
      const nextDetailTargets = detailValuesToTargets(nextDetails)

      setMpb(nextMpb)
      setLegLengthOverride(nextLegLength)
      setDetailValues(nextDetails)
      setLinkMuscle(false)
      setVisionState("success")
      setGenState("running")

      const result = await generateAvatar(targets, [], controller.signal, nextDetailTargets, { heightCm })
      setGeneratedUrl(versionedUrl(result.url, result.jobId))
      setLastJob(result.jobId)
      setLastResult(result)
      setGenState("success")
      setFitInfo({
        score: Math.round(Math.max(0, Math.min(1, vision.analysis.confidence)) * 100),
        achieved: result.metrics,
      })
      onUseParams?.(targets, nextDetailTargets, heightCm)
    } catch (e) {
      const aborted = controller.signal.aborted
      setGenState("error")
      setVisionState("error")
      setCreateError(
        aborted
          ? "Creating the avatar timed out. Check the backend console and try again."
          : e instanceof Error
            ? e.message
            : "Could not create the avatar.",
      )
    } finally {
      window.clearTimeout(timer)
    }
  }

  const onOptimize = async () => {
    if (!photoAnalysis) {
      setOptError("Run the front + side analysis first.")
      return
    }
    if (optState === "running") return

    optAbortRef.current?.abort()
    if (optTimerRef.current !== null) window.clearTimeout(optTimerRef.current)
    const controller = new AbortController()
    optAbortRef.current = controller
    setOptState("running")
    setOptError(null)
    setOptResult(null)
    setOptProgress({ evaluations: 0, maxEvaluations: 36, bestScore: null })

    try {
      const started = await startAvatarOptimization(
        { ...mpfb, legLength },
        detailTargets,
        photoAnalysis.silhouettes,
        36,
        controller.signal,
        heightCm,
      )
      const jobId = started.jobId
      const poll = async () => {
        if (controller.signal.aborted) return
        try {
          const job = await getAvatarOptimization(jobId, controller.signal)
          if (job.progress) {
            setOptProgress({
              evaluations: job.progress.evaluations ?? 0,
              maxEvaluations: job.progress.maxEvaluations ?? 36,
              bestScore: job.progress.bestScore ?? null,
            })
          }
          if (job.status === "done" && job.result) {
            setOptResult(job.result)
            applyOptimized(job.result)
            setOptState("success")
            return
          }
          if (job.status === "error") {
            setOptState("error")
            setOptError(job.error || "Silhouette optimization failed.")
            return
          }
          optTimerRef.current = window.setTimeout(poll, 2000)
        } catch (e) {
          if (controller.signal.aborted) return
          setOptState("error")
          setOptError(e instanceof Error ? e.message : "Could not read the optimization status.")
        }
      }
      optTimerRef.current = window.setTimeout(poll, 2000)
    } catch (e) {
      setOptState("error")
      setOptError(e instanceof Error ? e.message : "Could not start silhouette optimization.")
    }
  }

  const slider = (key: keyof Proportions) => {
    const limits = PROPORTION_LIMITS[key]
    return (
      <div key={key} className="space-y-1.5">
        <div className="flex items-center justify-between">
          <label htmlFor={`slider-${key}`} className="text-sm font-medium text-[#1C1C1C]">
            {RATIO_LABELS[key]}
          </label>
          <span className="text-sm font-semibold text-[#556B2F] tabular-nums">{adjusted[key].toFixed(2)}</span>
        </div>
        <input
          id={`slider-${key}`}
          type="range"
          min={limits.min}
          max={limits.max}
          step={limits.step}
          value={adjusted[key]}
          onChange={(e) => {
            setAdjusted((prev) => ({ ...prev, [key]: Number(e.target.value) }))
            if (key === "torsoToLeg") setLegLengthOverride(null)
          }}
          className="w-full accent-[#556B2F]"
        />
        {key === "torsoToLeg" && (
          <p className="text-[11px] text-[#8C8A82]">
            Blender leg-length target: <span className="font-semibold text-[#556B2F] tabular-nums">{legLength.toFixed(2)}</span>
          </p>
        )}
      </div>
    )
  }

  const detailSlider = (control: (typeof DETAIL_CONTROLS)[number]) => {
    const value = detailValues[control.key] ?? 0
    return (
      <div key={control.key} className="space-y-1.5">
        <div className="flex items-center justify-between gap-2">
          <label htmlFor={`detail-${control.key}`} className="text-sm font-medium text-[#1C1C1C]">
            {control.label}
          </label>
          <span className="text-sm font-semibold text-[#556B2F] tabular-nums">{value.toFixed(2)}</span>
        </div>
        <input
          id={`detail-${control.key}`}
          type="range"
          min={-1}
          max={1}
          step={0.05}
          value={value}
          onChange={(e) =>
            setDetailValues((prev) => {
              const next = { ...prev, [control.key]: Number(e.target.value) }
              if (Math.abs(next[control.key]) < 0.01) delete next[control.key]
              return next
            })
          }
          className="w-full accent-[#556B2F]"
        />
        <p className="text-xs text-[#8C8A82]">{control.hint}</p>
      </div>
    )
  }

  const mpfbSlider = (meta: MpbParamMeta) => {
    const presets = meta.key === "gender" ? GENDER_PRESETS : meta.key === "age" ? AGE_PRESETS : null
    return (
      <div key={meta.key} className="space-y-1.5">
        <div className="flex items-center justify-between gap-2">
          <label htmlFor={`mpfb-${meta.key}`} className="text-sm font-medium text-[#1C1C1C]">
            {meta.label}
          </label>
          <span className="text-sm font-semibold text-[#556B2F] tabular-nums">{mpfb[meta.key].toFixed(2)}</span>
        </div>
        <input
          id={`mpfb-${meta.key}`}
          type="range"
          min={0}
          max={1}
          step={0.01}
          value={mpfb[meta.key]}
          onChange={(e) => {
            setMpb((prev) => ({ ...prev, [meta.key]: Number(e.target.value) }))
            if (meta.key === "muscle") setLinkMuscle(false)
          }}
          className="w-full accent-[#556B2F]"
        />
        {meta.key === "muscle" && (
          <button
            type="button"
            onClick={() => setLinkMuscle((value) => !value)}
            className={`text-xs px-2.5 py-1 rounded-full border transition-colors ${
              linkMuscle
                ? "bg-[#E8EDE0] text-[#556B2F] border-[#556B2F]/30"
                : "bg-white text-[#8C8A82] border-[#E2E0D8] hover:bg-[#E2E0D8]"
            }`}
          >
            {linkMuscle ? "Linked to shoulder-to-hip" : "Manual (unlinked)"}
          </button>
        )}
        {presets && (
          <div className="flex flex-wrap gap-1.5 pt-0.5">
            {presets.map((p) => (
              <button
                key={p.label}
                type="button"
                onClick={() => setMpb((prev) => ({ ...prev, [meta.key]: p.value }))}
                className={`text-xs px-2.5 py-1 rounded-full border transition-colors ${
                  mpfb[meta.key] === p.value
                    ? "bg-[#556B2F] text-white border-[#556B2F]"
                    : "bg-white text-[#1C1C1C] border-[#E2E0D8] hover:bg-[#E2E0D8]"
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>
        )}
        <p className="text-xs text-[#8C8A82]">{meta.hint}</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-3xl font-semibold text-[#1C1C1C]">Customize My Avatar</h1>
        <p className="text-[#8C8A82] text-sm mt-1">
          Use a front and side photo, or fall back to the sizing questionnaire, then generate a matching body
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-start">
        <div className="space-y-6">
          <div className="bg-[#F0EFEA] rounded-xl p-6 space-y-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h3 className="font-display text-lg font-medium text-[#1C1C1C]">Body capture</h3>
                <p className="text-xs text-[#8C8A82] mt-0.5">
                  Two photos are the primary path. The questionnaire stays available as a fallback.
                </p>
              </div>
              <span
                className={`text-[10px] font-semibold px-2.5 py-1 rounded-full ${
                  captureState === "success"
                    ? "bg-[#E8EDE0] text-[#556B2F]"
                    : captureState === "error"
                      ? "bg-[#F5E0E0] text-[#8A2E2E]"
                      : "bg-[#E2E0D8] text-[#8C8A82]"
                }`}
              >
                {captureState === "running"
                  ? "Analyzing…"
                  : captureState === "success"
                    ? "Applied"
                    : captureState === "error"
                      ? "Failed"
                      : "Not applied"}
              </span>
            </div>

            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => setCaptureMode("photos")}
                className={`text-sm font-semibold py-2 rounded-lg border transition-colors ${
                  captureMode === "photos"
                    ? "bg-[#556B2F] text-white border-[#556B2F]"
                    : "bg-white text-[#1C1C1C] border-[#E2E0D8] hover:bg-[#E2E0D8]"
                }`}
              >
                Front + side photos
              </button>
              <button
                type="button"
                onClick={() => setCaptureMode("questionnaire")}
                className={`text-sm font-semibold py-2 rounded-lg border transition-colors ${
                  captureMode === "questionnaire"
                    ? "bg-[#556B2F] text-white border-[#556B2F]"
                    : "bg-white text-[#1C1C1C] border-[#E2E0D8] hover:bg-[#E2E0D8]"
                }`}
              >
                Questionnaire
              </button>
            </div>

            {captureMode === "photos" && (
              <div className="space-y-3">
                <div className="grid grid-cols-2 gap-3">
                  <label className="block cursor-pointer">
                    <span className="text-[10px] text-[#8C8A82] uppercase tracking-wide">Front photo</span>
                    <div className="mt-1 h-48 rounded-lg overflow-hidden bg-white border border-dashed border-[#C9C6BB] flex items-center justify-center">
                      {frontUrl ? (
                        <img src={frontUrl} alt="Front body" className="w-full h-full object-cover" />
                      ) : (
                        <span className="text-[#B5B3AA] text-xs px-3 text-center">Choose a straight-on photo</span>
                      )}
                    </div>
                    <input
                      type="file"
                      accept="image/*"
                      className="hidden"
                      onChange={(e) => {
                        onPhotoFile("front", e.target.files?.[0])
                        e.target.value = ""
                      }}
                    />
                  </label>
                  <label className="block cursor-pointer">
                    <span className="text-[10px] text-[#8C8A82] uppercase tracking-wide">Side photo</span>
                    <div className="mt-1 h-48 rounded-lg overflow-hidden bg-white border border-dashed border-[#C9C6BB] flex items-center justify-center">
                      {sideUrl ? (
                        <img src={sideUrl} alt="Side body" className="w-full h-full object-cover" />
                      ) : (
                        <span className="text-[#B5B3AA] text-xs px-3 text-center">Choose a profile photo</span>
                      )}
                    </div>
                    <input
                      type="file"
                      accept="image/*"
                      className="hidden"
                      onChange={(e) => {
                        onPhotoFile("side", e.target.files?.[0])
                        e.target.value = ""
                      }}
                    />
                  </label>
                </div>
                <div className="flex items-center gap-2">
                  <label htmlFor="photo-height" className="text-xs font-semibold text-[#8C8A82]">
                    Your height
                  </label>
                  <input
                    id="photo-height"
                    type="number"
                    min={140}
                    max={220}
                    step={1}
                    value={heightCm}
                    onChange={(e) => onHeightCmChange(Number(e.target.value))}
                    className="w-20 bg-white border border-[#E2E0D8] rounded-lg text-sm text-[#1C1C1C] px-2.5 py-1.5 outline-none focus:border-[#556B2F]"
                  />
                  <span className="text-xs text-[#8C8A82]">cm</span>
                </div>
                <p className="text-[11px] text-[#8C8A82]">
                  Full body in frame, plain background, arms slightly away from the body. Keep the same stance in both
                  shots.
                </p>
                <label className="flex items-start gap-2 text-[11px] text-[#8C8A82]">
                  <input
                    type="checkbox"
                    checked={visionConsent}
                    onChange={(e) => setVisionConsent(e.target.checked)}
                    className="mt-0.5 accent-[#556B2F]"
                  />
                  <span>I agree to send these two photos to OpenAI for avatar estimation.</span>
                </label>
                <button
                  type="button"
                  onClick={onCreateAvatar}
                  disabled={
                    !frontFile || !sideFile || !visionConsent || visionState === "running" || genState === "running"
                  }
                  className="w-full bg-[#556B2F] hover:bg-[#6B8A3A] text-white text-sm font-semibold py-2.5 rounded-lg transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {visionState === "running"
                    ? "Reading your photos…"
                    : genState === "running"
                      ? "Building your avatar…"
                      : "Create my avatar"}
                </button>
                {createError && (
                  <div className="bg-[#F5E0E0] text-[#8A2E2E] text-xs rounded-lg px-3 py-2.5">{createError}</div>
                )}
                {visionResult && (
                  <div className="bg-white rounded-lg px-3 py-2.5 text-xs text-[#8C8A82] space-y-1">
                    <p>
                      <span className="font-semibold text-[#1C1C1C]">
                        {visionResult.analysis.body_shape.replace("_", " ")}
                      </span>
                      {" · "}confidence{" "}
                      <span className="font-semibold text-[#1C1C1C] tabular-nums">
                        {Math.round(visionResult.analysis.confidence * 100)}%
                      </span>
                    </p>
                    {Object.entries(visionResult.analysis.observations).length > 0 && (
                      <p className="text-[11px]">
                        {Object.entries(visionResult.analysis.observations)
                          .map(([key, observation]) => `${key}: ${observation.relative}`)
                          .join(" · ")}
                      </p>
                    )}
                    {visionResult.analysis.notes.length > 0 && (
                      <p className="text-[11px]">{visionResult.analysis.notes[0]}</p>
                    )}
                    <p className="text-[11px]">
                      GPT-4 Vision chose the body parameters. Expand Advanced customization to tweak anything.
                    </p>
                  </div>
                )}

                <details className="border-t border-[#E2E0D8] pt-3">
                  <summary className="text-xs font-semibold text-[#1C1C1C] cursor-pointer">
                    Advanced photo tools (optional)
                  </summary>
                  <div className="space-y-3 pt-3">
                    <p className="text-[11px] text-[#8C8A82]">
                      Run local MediaPipe measurements or use silhouette fitting if the LLM result needs a second pass.
                    </p>
                    <button
                      type="button"
                      onClick={onAnalyzePhotos}
                      disabled={!frontFile || !sideFile || photoState === "running"}
                      className="w-full bg-white border border-[#E2E0D8] hover:bg-[#E2E0D8] text-[#1C1C1C] text-sm font-semibold py-2.5 rounded-lg transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                      {photoState === "running" ? "Analyzing photos…" : "Analyze with MediaPipe"}
                    </button>
                    {photoError && (
                      <div className="bg-[#F5E0E0] text-[#8A2E2E] text-xs rounded-lg px-3 py-2.5">{photoError}</div>
                    )}
                    {photoAnalysis && (
                      <div className="bg-white rounded-lg px-3 py-2.5 text-xs text-[#8C8A82] space-y-1">
                        <p>
                          Confidence <span className="font-semibold text-[#1C1C1C]">{photoAnalysis.confidence}/100</span>
                          {" · "}front {photoAnalysis.frontQuality}/100
                          {" · "}side {photoAnalysis.sideQuality}/100
                        </p>
                        <p>
                          Side-depth hints: torso{" "}
                          <span className="font-semibold text-[#1C1C1C] tabular-nums">
                            {photoAnalysis.detailSuggestions.torsoDepth.toFixed(2)}
                          </span>
                          {" · "}hips{" "}
                          <span className="font-semibold text-[#1C1C1C] tabular-nums">
                            {photoAnalysis.detailSuggestions.hipDepth.toFixed(2)}
                          </span>
                        </p>
                      </div>
                    )}
                    {photoAnalysis && (
                      <div className="space-y-2">
                        <button
                          type="button"
                          onClick={onOptimize}
                          disabled={optState === "running"}
                          className="w-full bg-[#1C1C1C] hover:bg-[#333] text-white text-sm font-semibold py-2.5 rounded-lg transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                        >
                          {optState === "running" ? "Fitting silhouettes…" : "Refine with silhouette fitting"}
                        </button>
                        {optState === "running" && (
                          <div className="space-y-1">
                            <div className="h-2 rounded-full bg-[#E2E0D8] overflow-hidden">
                              <div
                                className="h-full bg-[#556B2F] transition-all"
                                style={{
                                  width: `${Math.min(100, (optProgress.evaluations / Math.max(1, optProgress.maxEvaluations)) * 100)}%`,
                                }}
                              />
                            </div>
                            <p className="text-[11px] text-[#8C8A82] tabular-nums">
                              Evaluation {optProgress.evaluations} / {optProgress.maxEvaluations}
                              {optProgress.bestScore !== null
                                ? ` · best error ${optProgress.bestScore.toFixed(4)}`
                                : ""}
                            </p>
                          </div>
                        )}
                        {optError && (
                          <div className="bg-[#F5E0E0] text-[#8A2E2E] text-xs rounded-lg px-3 py-2.5">{optError}</div>
                        )}
                        {optState === "success" && optResult && (
                          <div className="bg-white rounded-lg px-3 py-2.5 text-xs text-[#8C8A82] space-y-1">
                            <p>
                              Silhouette match{" "}
                              <span className="font-semibold text-[#1C1C1C]">
                                {Math.round(100 * (0.5 * optResult.fit.iouFront + 0.5 * optResult.fit.iouSide))}/100
                              </span>
                            </p>
                            <p>
                              {optResult.evaluations} evaluations in {optResult.elapsedSeconds.toFixed(0)}s.
                            </p>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </details>
              </div>
            )}

            {captureMode === "questionnaire" && (
              <>
              <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-[10px] text-[#8C8A82] uppercase tracking-wide" htmlFor="q-height">
                  Height (cm)
                </label>
                <input
                  id="q-height"
                  type="number"
                  min={140}
                  max={220}
                  step={1}
                  value={heightCm}
                  onChange={(e) => onHeightCmChange(Number(e.target.value))}
                  className="w-full mt-1 bg-white border border-[#E2E0D8] rounded-lg text-sm px-2.5 py-2 outline-none focus:border-[#556B2F]"
                />
              </div>
              <div>
                <label className="text-[10px] text-[#8C8A82] uppercase tracking-wide" htmlFor="q-mass">
                  Mass (kg)
                </label>
                <input
                  id="q-mass"
                  type="number"
                  min={30}
                  max={200}
                  value={qMass}
                  onChange={(e) => setQMass(Number(e.target.value))}
                  className="w-full mt-1 bg-white border border-[#E2E0D8] rounded-lg text-sm px-2.5 py-2 outline-none focus:border-[#556B2F]"
                />
              </div>
              <div>
                <label className="text-[10px] text-[#8C8A82] uppercase tracking-wide" htmlFor="q-gender">
                  Gender
                </label>
                <select
                  id="q-gender"
                  value={qGender}
                  onChange={(e) => setQGender(e.target.value as "female" | "male")}
                  className="w-full mt-1 bg-white border border-[#E2E0D8] rounded-lg text-sm px-2.5 py-2 outline-none focus:border-[#556B2F]"
                >
                  {GENDERS.map((g) => (
                    <option key={g.value} value={g.value}>
                      {g.label}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="text-[10px] text-[#8C8A82] uppercase tracking-wide" htmlFor="q-shape">
                  Body shape
                </label>
                <select
                  id="q-shape"
                  value={qShape}
                  onChange={(e) => setQShape(e.target.value as QuestionnairePayload["body_shape"])}
                  className="w-full mt-1 bg-white border border-[#E2E0D8] rounded-lg text-sm px-2.5 py-2 outline-none focus:border-[#556B2F]"
                >
                  {BODY_SHAPES.map((s) => (
                    <option key={s.value} value={s.value}>
                      {s.label}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="text-[10px] text-[#8C8A82] uppercase tracking-wide" htmlFor="q-cup">
                  Cup size (optional)
                </label>
                <select
                  id="q-cup"
                  value={qCup}
                  onChange={(e) => setQCup(e.target.value)}
                  className="w-full mt-1 bg-white border border-[#E2E0D8] rounded-lg text-sm px-2.5 py-2 outline-none focus:border-[#556B2F]"
                >
                  <option value="">—</option>
                  {CUP_SIZES.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              </div>
              {[
                { label: "Belly", value: qBelly, set: setQBelly, id: "q-belly" },
                { label: "Build", value: qBuild, set: setQBuild, id: "q-build" },
                { label: "Legs", value: qLegs, set: setQLegs, id: "q-legs" },
                { label: "Arms", value: qArms, set: setQArms, id: "q-arms" },
              ].map((field) => (
                <div key={field.id}>
                  <label className="text-[10px] text-[#8C8A82] uppercase tracking-wide" htmlFor={field.id}>
                    {field.label}
                  </label>
                  <select
                    id={field.id}
                    value={field.value}
                    onChange={(e) => field.set(Number(e.target.value))}
                    className="w-full mt-1 bg-white border border-[#E2E0D8] rounded-lg text-sm px-2.5 py-2 outline-none focus:border-[#556B2F]"
                  >
                    {[1, 2, 3].map((n) => (
                      <option key={n} value={n}>
                        {n === 1 ? "Low" : n === 2 ? "Average" : "High"}
                      </option>
                    ))}
                  </select>
                </div>
              ))}
            </div>

            <button
              type="button"
              onClick={onQuestionnaire}
              disabled={scanState === "running"}
              className="w-full bg-[#1C1C1C] hover:bg-[#333] text-white text-sm font-semibold py-2.5 rounded-lg transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {scanState === "running" ? "Measuring…" : "Apply questionnaire to avatar"}
            </button>

            {scanError && (
              <div className="bg-[#F5E0E0] text-[#8A2E2E] text-xs rounded-lg px-3 py-2.5">{scanError}</div>
            )}
              </>
            )}
          </div>

          {scanResult && (
            <div className="bg-[#F0EFEA] rounded-xl p-6 space-y-3">
              <h3 className="font-display text-lg font-medium text-[#1C1C1C]">Estimated measurements</h3>
              {photoAnalysis && (
                <p className="text-xs text-[#556B2F]">
                  From the front + side photos · confidence {photoAnalysis.confidence}/100. Edit any value below before
                  generating.
                </p>
              )}
              <div className="grid grid-cols-2 gap-2">
                {rows.map((row) => (
                  <div key={row.key} className="bg-white rounded-lg px-3 py-2">
                    <p className="text-[10px] text-[#8C8A82] uppercase tracking-wide">{row.label}</p>
                    <p className="text-sm font-semibold text-[#1C1C1C] tabular-nums">
                      {row.value.toFixed(1)}
                      {row.unit ? (
                        <span className="ml-1 text-[10px] font-normal text-[#8C8A82]">{row.unit}</span>
                      ) : null}
                    </p>
                  </div>
                ))}
              </div>
              <p className="text-xs text-[#556B2F]">
                Applied to the avatar: height, leg length, muscle, weight, proportions
                {scanResult.targets.cupsize !== undefined ? ", cup size" : ""}.
              </p>
              {scanResult.notes.length > 0 && (
                <ul className="text-[11px] text-[#8C8A82] list-disc pl-4 space-y-1">
                  {scanResult.notes.map((note) => (
                    <li key={note}>{note}</li>
                  ))}
                </ul>
              )}
            </div>
          )}

          <details className="rounded-xl border border-[#E2E0D8] bg-white/40 p-2">
            <summary className="cursor-pointer px-3 py-2 text-sm font-semibold text-[#1C1C1C]">
              Advanced customization (optional)
            </summary>
            <div className="space-y-6 pt-2">
          <div className="bg-[#F0EFEA] rounded-xl p-6 space-y-4">
            <div>
              <h3 className="font-display text-lg font-medium text-[#1C1C1C]">Body shape parameters</h3>
              <p className="text-xs text-[#8C8A82] mt-0.5">
                Direct MPFB2 controls sent to Blender. 0.50 is neutral. The photo or questionnaire capture pre-fills
                the ones it can estimate; you can still refine every value by hand.
              </p>
            </div>
            {MPFB_PARAMS.map((meta) => mpfbSlider(meta))}
          </div>

          <div className="bg-[#F0EFEA] rounded-xl p-6 space-y-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h3 className="font-display text-lg font-medium text-[#1C1C1C]">Advanced body details</h3>
                <p className="text-xs text-[#8C8A82] mt-0.5">
                  19 local MPFB targets that the macros cannot isolate. 0.00 is the current body; move left or right
                  to shrink or grow that region. Values are limited to ±1.00.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setDetailValues({})}
                disabled={activeDetails === 0}
                className="text-xs font-semibold text-[#556B2F] hover:underline disabled:opacity-40 disabled:no-underline shrink-0"
              >
                Reset
              </button>
            </div>
            {DETAIL_CONTROLS.map((control) => detailSlider(control))}
          </div>

          <div className="bg-[#F0EFEA] rounded-xl p-6 space-y-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h3 className="font-display text-lg font-medium text-[#1C1C1C]">Adjust manually</h3>
                <p className="text-xs text-[#8C8A82] mt-0.5">
                  These two ratios drive MPFB muscle and the Blender leg-length post-process.
                </p>
              </div>
              <button
                type="button"
                onClick={() => {
                  if (!scanResult) return
                  const next = {
                    shoulderToHip: scanResult.ratios.shoulderToHip ?? DEFAULT_PROPORTIONS.shoulderToHip,
                    torsoToLeg: scanResult.ratios.torsoToLeg ?? DEFAULT_PROPORTIONS.torsoToLeg,
                  }
                  setAdjusted(next)
                  setLegLengthOverride(scanResult.targets.legLength ?? null)
                }}
                disabled={!scanResult}
                className="text-xs font-semibold text-[#556B2F] hover:underline disabled:opacity-40 disabled:no-underline shrink-0"
              >
                Reset to questionnaire
              </button>
            </div>
            {slider("shoulderToHip")}
            {slider("torsoToLeg")}
          </div>

          <div className="bg-white rounded-lg px-4 py-4 space-y-3 border border-[#E2E0D8]">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-sm font-semibold text-[#1C1C1C]">Generate Avatar</p>
                <p className="text-xs text-[#8C8A82]">Runs Blender + MPFB2 locally (~5 s per job)</p>
              </div>
              <button
                onClick={onGenerate}
                disabled={genState === "running"}
                className="bg-[#556B2F] hover:bg-[#6B8A3A] text-white text-sm font-semibold px-6 py-2.5 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed shrink-0"
              >
                {genState === "running" ? "Generating…" : "Generate Avatar"}
              </button>
            </div>
            <div className="text-xs text-[#8C8A82] space-y-1">
              <p className="font-medium text-[#1C1C1C]">
                Will apply:{" "}
                {activeTargets.length
                  ? activeTargets.map(([k, v]) => `${k} ${v.toFixed(2)}`).join(", ")
                  : "default body (all parameters neutral)"}
                {activeDetails > 0 ? ` + ${activeDetails} detail target${activeDetails === 1 ? "" : "s"}` : ""}
              </p>
              <p>· Leg length {legLength.toFixed(2)} from torso-to-leg — applied in Blender after MPFB shaping</p>
              <p>· Muscle {linkMuscle ? "is linked to the shoulder-to-hip slider" : "is unlinked and set manually"}</p>
              <p>· Every value is 0.00–1.00 with 0.50 as the neutral default</p>
            </div>
            {genState === "running" && (
              <p className="text-xs text-[#556B2F]">
                Blender is regenerating your avatar
                {scanResult ? ` — proportion pass ${genIteration} of 2` : ""}… the original file is never overwritten.
              </p>
            )}
            {genState === "success" && (
              <div className="space-y-1">
                <p className="text-xs text-[#556B2F]">
                  Done — the viewer now shows your generated avatar (job {lastJob}). The original avatar.glb is unchanged.
                </p>
                {fitInfo && (
                  <p className="text-xs text-[#556B2F]">
                    Proportion match: <span className="font-semibold">{fitInfo.score}/100</span>
                    {lastResult?.metrics?.heightMeters
                      ? ` · generated height ${Number(lastResult.metrics.heightMeters).toFixed(2)} m`
                      : ""}
                  </p>
                )}
              </div>
            )}
            {genState === "success" && generatedUrl && (
              <a
                href={generatedUrl}
                download
                className="block text-center w-full bg-white border border-[#E2E0D8] hover:bg-[#E2E0D8] text-[#1C1C1C] text-sm font-semibold py-2.5 rounded-lg transition-colors"
              >
                Download customized GLB
              </a>
            )}
            {genState === "success" && onGoToTryOn && (
              <button
                onClick={onGoToTryOn}
                className="w-full bg-[#1C1C1C] hover:bg-[#333] text-white text-sm font-semibold py-2.5 rounded-lg transition-colors"
              >
                Try on outfits →
              </button>
            )}
            {genState === "error" && genError && (
              <div className="bg-[#F5E0E0] text-[#8A2E2E] text-xs rounded-lg px-3 py-2.5">{genError}</div>
            )}
          </div>
            </div>
          </details>
        </div>

        <div className="space-y-4">
          <AvatarCanvas url={generatedUrl ?? undefined} />
          {genState === "success" && (
            <div className="grid grid-cols-2 gap-2">
              {onGoToTryOn && (
                <button
                  onClick={onGoToTryOn}
                  className="bg-[#1C1C1C] hover:bg-[#333] text-white text-sm font-semibold py-2.5 rounded-lg transition-colors"
                >
                  Try on outfits →
                </button>
              )}
              {generatedUrl && (
                <a
                  href={generatedUrl}
                  download
                  className="text-center bg-white border border-[#E2E0D8] hover:bg-[#E2E0D8] text-[#1C1C1C] text-sm font-semibold py-2.5 rounded-lg transition-colors"
                >
                  Download GLB
                </a>
              )}
            </div>
          )}
          <div className="bg-[#F0EFEA] rounded-xl p-6 space-y-3">
            <h3 className="font-display text-lg font-medium text-[#1C1C1C]">Current targets</h3>
            <div className="grid grid-cols-3 gap-3">
              {(["shoulderToHip", "torsoToLeg"] as const).map((key) => (
                <div key={key} className="bg-white rounded-lg px-4 py-3">
                  <p className="text-xs text-[#8C8A82]">{RATIO_LABELS[key]}</p>
                  <p className="text-lg font-semibold text-[#1C1C1C] tabular-nums">{adjusted[key].toFixed(2)}</p>
                  <p className={`text-[10px] ${scanResult ? "text-[#556B2F]" : "text-[#B5B3AA]"}`}>
                    {scanResult ? "from questionnaire" : "default — set manually"}
                  </p>
                </div>
              ))}
              <div className="bg-white rounded-lg px-4 py-3">
                <p className="text-xs text-[#8C8A82]">Leg length</p>
                <p className="text-lg font-semibold text-[#1C1C1C] tabular-nums">{legLength.toFixed(2)}</p>
                <p className="text-[10px] text-[#556B2F]">Blender post-process</p>
              </div>
            </div>
            {fitInfo && (
              <div className="bg-white rounded-lg px-4 py-3 text-xs text-[#8C8A82]">
                <p className="font-semibold text-[#1C1C1C]">Last generated body</p>
                <p>
                  Shoulder-to-hip{" "}
                  <span className="font-semibold text-[#1C1C1C] tabular-nums">
                    {Number(fitInfo.achieved.shoulderToHip ?? 0).toFixed(2)}
                  </span>
                  {" · "}Torso-to-leg{" "}
                  <span className="font-semibold text-[#1C1C1C] tabular-nums">
                    {Number(fitInfo.achieved.torsoToLeg ?? 0).toFixed(2)}
                  </span>
                </p>
              </div>
            )}
            <p className="text-xs text-[#8C8A82]">
              Generate Avatar applies these targets via local Blender + MPFB2 into a new file under
              public/models/generated/ — your original avatar.glb is never overwritten.
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
