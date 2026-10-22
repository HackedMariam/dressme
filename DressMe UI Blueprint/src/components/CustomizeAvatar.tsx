import { useEffect, useMemo, useRef, useState } from "react"
import { AvatarCanvas } from "./AvatarViewer"
import {
  AGE_PRESETS,
  cmFromHeightParam,
  defaultMpbTargets,
  estimatesFromMetrics,
  fitScore,
  fitTargets,
  generateAvatar,
  GENDER_PRESETS,
  checkBodyScanStatus,
  heightFromCm,
  legLengthFromTorsoToLeg,
  MPFB_NEUTRAL,
  MPFB_PARAMS,
  muscleFromShoulderToHip,
  PHOTO_ESTIMATED_PARAMS,
  scanBodyPhoto,
  scanBodyQuestionnaire,
  type BodyScanResult,
  type BodyTargets,
  type GenerateResult,
  type MpbParam,
  type MpbParamMeta,
  type QuestionnairePayload,
} from "../lib/avatarApi"
import { BODY_SHAPES, CUP_SIZES, GENDERS, measurementRows, quotaRemaining } from "../lib/clad"
import {
  analyzePhoto,
  defaultProportions,
  preloadPoseModel,
  PROPORTION_LIMITS,
  type PoseAnalysis,
  type Proportions,
} from "../lib/pose"

type ModelStatus = "idle" | "loading" | "ready" | "error"

const RATIO_LABELS: Record<keyof Proportions, string> = {
  shoulderToHip: "Shoulder-to-hip",
  torsoToLeg: "Torso-to-leg",
}

function qualityBadgeStyle(label: "Good" | "Fair" | "Low"): string {
  if (label === "Good") return "bg-[#E8EED6] text-[#3F4E1F]"
  if (label === "Fair") return "bg-[#F5EDDC] text-[#7A5B1E]"
  return "bg-[#F5E0E0] text-[#8A2E2E]"
}

export default function CustomizeAvatar({
  onUseParams,
  onGoToTryOn,
}: {
  onUseParams?: (p: BodyTargets) => void
  onGoToTryOn?: () => void
} = {}) {
  const [fileUrl, setFileUrl] = useState<string | null>(null)
  const [fileName, setFileName] = useState<string | null>(null)
  const [modelStatus, setModelStatus] = useState<ModelStatus>("idle")
  const [analyzing, setAnalyzing] = useState(false)
  const [analysis, setAnalysis] = useState<Extract<PoseAnalysis, { ok: true }> | null>(null)
  const [adjusted, setAdjusted] = useState<Proportions>(defaultProportions())
  const [mpfb, setMpb] = useState<Record<MpbParam, number>>(defaultMpbTargets)
  const [photoKeys, setPhotoKeys] = useState<MpbParam[]>([])
  const [error, setError] = useState<string | null>(null)
  const [genState, setGenState] = useState<"idle" | "running" | "success" | "error">("idle")
  const [genError, setGenError] = useState<string | null>(null)
  const [generatedUrl, setGeneratedUrl] = useState<string | null>(null)
  const [lastJob, setLastJob] = useState<string | null>(null)
  const [lastResult, setLastResult] = useState<GenerateResult | null>(null)
  const [linkMuscle, setLinkMuscle] = useState(true)
  const [heightCm, setHeightCm] = useState(170)
  const [genIteration, setGenIteration] = useState(0)
  const [fitInfo, setFitInfo] = useState<{ score: number; achieved: Record<string, number> } | null>(null)
  const [photoFile, setPhotoFile] = useState<File | null>(null)
  const [legLengthOverride, setLegLengthOverride] = useState<number | null>(null)
  const [cladConsent, setCladConsent] = useState(false)
  const [cladState, setCladState] = useState<"idle" | "running" | "success" | "error">("idle")
  const [cladError, setCladError] = useState<string | null>(null)
  const [cladResult, setCladResult] = useState<BodyScanResult | null>(null)
  const [cladConfigured, setCladConfigured] = useState<boolean | null>(null)
  const [qMass, setQMass] = useState(65)
  const [qGender, setQGender] = useState<"female" | "male">("female")
  const [qShape, setQShape] = useState<QuestionnairePayload["body_shape"]>("hourglass")
  const [qBelly, setQBelly] = useState(2)
  const [qBuild, setQBuild] = useState(2)
  const [qLegs, setQLegs] = useState(2)
  const [qArms, setQArms] = useState(2)
  const [qCup, setQCup] = useState("")
  const imgRef = useRef<HTMLImageElement | null>(null)
  const prevUrlRef = useRef<string | null>(null)
  const genAbortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    if (modelStatus !== "idle") return
    setModelStatus("loading")
    preloadPoseModel()
      .then(() => setModelStatus("ready"))
      .catch(() => setModelStatus("error"))
  }, [modelStatus])

  useEffect(() => {
    return () => {
      if (prevUrlRef.current) URL.revokeObjectURL(prevUrlRef.current)
      genAbortRef.current?.abort()
    }
  }, [])

  useEffect(() => {
    let active = true
    checkBodyScanStatus()
      .then((status) => {
        if (active) setCladConfigured(status.configured)
      })
      .catch(() => {
        if (active) setCladConfigured(false)
      })
    return () => {
      active = false
    }
  }, [])

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

  const cladRows = cladResult ? measurementRows(cladResult.measurements) : []
  const photoScanRemaining = cladResult ? quotaRemaining(cladResult.quota, "photo") : null
  const questionnaireRemaining = cladResult ? quotaRemaining(cladResult.quota, "questionnaire") : null

  const onFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    if (!file.type.startsWith("image/")) {
      setError("Please choose an image file (JPG, PNG, WebP...).")
      return
    }
    if (file.size > 20 * 1024 * 1024) {
      setError("That image is larger than 20 MB. Please pick a smaller photo.")
      return
    }
    if (prevUrlRef.current) URL.revokeObjectURL(prevUrlRef.current)
    const url = URL.createObjectURL(file)
    prevUrlRef.current = url
    setFileUrl(url)
    setFileName(file.name)
    setPhotoFile(file)
    setAnalysis(null)
    setAdjusted(defaultProportions())
    setLegLengthOverride(null)
    setCladResult(null)
    setCladState("idle")
    setCladError(null)
    setCladConsent(false)
    setMpb((prev) => {
      const next = { ...prev }
      for (const k of PHOTO_ESTIMATED_PARAMS) next[k] = MPFB_NEUTRAL
      return next
    })
    setPhotoKeys([])
    setError(null)
    setHeightCm(170)
    setLinkMuscle(true)
    setGeneratedUrl(null)
    setLastResult(null)
    setFitInfo(null)
    if (modelStatus === "idle") setModelStatus("loading")
    preloadPoseModel()
      .then(() => setModelStatus("ready"))
      .catch(() => setModelStatus("error"))
    e.target.value = ""
  }

  const onAnalyze = async () => {
    const img = imgRef.current
    if (!img || !fileUrl) {
      setError("Upload a full-body photo first.")
      return
    }
    if (modelStatus === "error") {
      setError("The pose engine failed to load. Check your connection once (to fetch it), then reload the page.")
      return
    }
    setAnalyzing(true)
    setError(null)
    setCladResult(null)
    setCladError(null)
    setCladState("idle")
    setLegLengthOverride(null)
    try {
      if (img.decode) {
        await img.decode().catch(() => undefined)
      }
      const result = await analyzePhoto(img)
      if (result.ok) {
        setAnalysis(result)
        setAdjusted(result.proportions)
        const estimates = estimatesFromMetrics(result.metrics, result.reliability)
        setMpb((prev) => {
          const next = { ...prev }
          for (const key of PHOTO_ESTIMATED_PARAMS) next[key] = MPFB_NEUTRAL
          return { ...next, ...estimates.values }
        })
        setPhotoKeys(estimates.keys)
        if (estimates.values.height !== undefined) {
          setHeightCm(cmFromHeightParam(estimates.values.height))
        }
        setFitInfo(null)
      } else {
        setAnalysis(null)
        setError(result.reason)
      }
    } catch {
      setAnalysis(null)
      setError("Something went wrong while analyzing the photo. Try another image or reload the page.")
    } finally {
      setAnalyzing(false)
    }
  }

  const onReset = () => {
    setAdjusted(analysis ? { ...analysis.proportions } : defaultProportions())
    setLegLengthOverride(null)
    setFitInfo(null)
  }

  const onHeightCmChange = (value: number) => {
    setHeightCm(value)
    if (!Number.isFinite(value) || value < 140 || value > 220) return
    setMpb((prev) => ({ ...prev, height: heightFromCm(value) }))
    setPhotoKeys((prev) => prev.filter((k) => k !== "height"))
  }

  const applyBodyScan = (result: BodyScanResult) => {
    const targets = result.targets
    setCladResult(result)
    setCladState("success")
    setCladError(null)

    setMpb((prev) => {
      const next = { ...prev }
      if (targets.height !== undefined) next.height = targets.height
      if (targets.muscle !== undefined) next.muscle = targets.muscle
      if (targets.weight !== undefined) next.weight = targets.weight
      if (targets.proportions !== undefined) next.proportions = targets.proportions
      if (targets.cupsize !== undefined) next.cupsize = targets.cupsize
      return next
    })

    if (result.ratios.shoulderToHip !== undefined) {
      const ratio = result.ratios.shoulderToHip
      setAdjusted((prev) => ({ ...prev, shoulderToHip: ratio }))
    }
    if (targets.legLength !== undefined) {
      setLegLengthOverride(targets.legLength)
    }

    setLinkMuscle(false)
    const keys: MpbParam[] = []
    if (targets.height !== undefined) keys.push("height")
    if (targets.muscle !== undefined) keys.push("muscle")
    if (targets.weight !== undefined) keys.push("weight")
    if (targets.proportions !== undefined) keys.push("proportions")
    if (targets.cupsize !== undefined) keys.push("cupsize")
    setPhotoKeys(keys)
    setAnalysis(null)
    setFitInfo(null)
    if (result.measurements.height_cm) {
      setHeightCm(Math.round(result.measurements.height_cm))
    }
  }

  const onCladScan = async () => {
    if (!photoFile) {
      setCladError("Upload a full-body photo first.")
      return
    }
    if (!cladConsent) {
      setCladError("Please agree to send this photo to Clad before scanning.")
      return
    }
    setCladState("running")
    setCladError(null)
    try {
      const result = await scanBodyPhoto(photoFile, heightCm)
      applyBodyScan(result)
    } catch (e) {
      setCladState("error")
      setCladError(e instanceof Error ? e.message : "Body scan failed.")
    }
  }

  const onCladQuestionnaire = async () => {
    setCladState("running")
    setCladError(null)
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
      applyBodyScan(result)
    } catch (e) {
      setCladState("error")
      setCladError(e instanceof Error ? e.message : "Questionnaire measurement failed.")
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
      // Fit against the sliders the user actually sees, so manual adjustments win.
      const desired = analysis ? { ...adjusted } : undefined
      const maxPasses = desired ? 2 : 1

      for (let pass = 0; pass < maxPasses; pass++) {
        setGenIteration(pass + 1)
        last = await generateAvatar(current, [], controller.signal)
        if (!desired) break
        const next = fitTargets(current, last.metrics, desired)
        if (!next) break
        // Respect an explicitly unlinked muscle slider.
        if (!linkMuscle) {
          next.targets.muscle = current.muscle
          if (next.targets.legLength === current.legLength) break
        }
        current = next.targets
      }

      if (!last) throw new Error("Generation produced no result")
      setGeneratedUrl(`${last.url}?v=${last.jobId}`)
      setLastJob(last.jobId)
      setLastResult(last)
      setGenState("success")
      setLegLengthOverride(current.legLength)
      if (desired && last.metrics) {
        setFitInfo({ score: fitScore(last.metrics, desired), achieved: last.metrics })
      }
      onUseParams?.(current)
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

  const mpfbSlider = (meta: MpbParamMeta) => {
    const fromPhoto = photoKeys.includes(meta.key)
    const presets = meta.key === "gender" ? GENDER_PRESETS : meta.key === "age" ? AGE_PRESETS : null
    return (
      <div key={meta.key} className="space-y-1.5">
        <div className="flex items-center justify-between gap-2">
          <label htmlFor={`mpfb-${meta.key}`} className="text-sm font-medium text-[#1C1C1C]">
            {meta.label}
            {fromPhoto && <span className="ml-2 text-[10px] font-semibold text-[#556B2F]">from photo</span>}
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
            const value = Number(e.target.value)
            setMpb((prev) => ({ ...prev, [meta.key]: value }))
            setPhotoKeys((prev) => prev.filter((k) => k !== meta.key))
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
                onClick={() => {
                  setMpb((prev) => ({ ...prev, [meta.key]: p.value }))
                  setPhotoKeys((prev) => prev.filter((k) => k !== meta.key))
                }}
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
          Upload a full-body photo to estimate your body proportions — step one of your personalized avatar
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-start">
        <div className="space-y-6">
          <div className="bg-[#F0EFEA] rounded-xl p-6 space-y-4">
            <h3 className="font-display text-lg font-medium text-[#1C1C1C]">Your photo</h3>
            <div className="flex items-start gap-4">
              <div className="w-40 h-56 rounded-lg overflow-hidden bg-white border border-[#E2E0D8] flex items-center justify-center shrink-0">
                {fileUrl ? (
                  <img ref={imgRef} src={fileUrl} alt="Uploaded full-body photo" className="w-full h-full object-cover" />
                ) : (
                  <span className="text-[#B5B3AA] text-xs px-3 text-center">No photo yet</span>
                )}
              </div>
              <div className="space-y-3 min-w-0">
                <label className="inline-block bg-white hover:bg-[#E2E0D8] border border-[#E2E0D8] text-[#1C1C1C] text-sm font-semibold px-5 py-2.5 rounded-lg cursor-pointer transition-colors">
                  Choose photo
                  <input type="file" accept="image/*" className="hidden" onChange={onFileChange} />
                </label>
                <p className="text-xs text-[#8C8A82] break-all">{fileName ?? "Stand fully in frame, arms slightly apart, plain background works best."}</p>
                <button
                  onClick={onAnalyze}
                  disabled={!fileUrl || analyzing}
                  className="block bg-[#556B2F] hover:bg-[#6B8A3A] text-white text-sm font-semibold px-5 py-2.5 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {analyzing ? "Analyzing…" : "Estimate proportions"}
                </button>
                <div className="flex items-center gap-2 pt-1">
                  <label htmlFor="height-cm" className="text-xs font-semibold text-[#8C8A82]">
                    Your height
                  </label>
                  <input
                    id="height-cm"
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
                  Calibrates the MPFB height parameter. Edit it after the photo estimate if you know your height.
                </p>
                {modelStatus === "loading" && <p className="text-xs text-[#8C8A82]">Preparing pose engine (one-time)…</p>}
                {modelStatus === "error" && (
                  <p className="text-xs text-[#8A2E2E]">Pose engine failed to load — reload the page to retry.</p>
                )}
              </div>
            </div>
            {error && (
              <div className="bg-[#F5E0E0] text-[#8A2E2E] text-sm rounded-lg px-4 py-3">{error}</div>
            )}
          </div>

          <div className="bg-[#F0EFEA] rounded-xl p-6 space-y-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h3 className="font-display text-lg font-medium text-[#1C1C1C]">Body scan (Clad)</h3>
                <p className="text-xs text-[#8C8A82] mt-0.5">
                  Photo + height → 24 ISO 8559-1 measurements. This sends the photo to Clad.
                </p>
              </div>
              <span
                className={`text-[10px] font-semibold px-2.5 py-1 rounded-full ${
                  cladState === "success"
                    ? "bg-[#E8EDE0] text-[#556B2F]"
                    : cladState === "error"
                      ? "bg-[#F5E0E0] text-[#8A2E2E]"
                      : "bg-[#E2E0D8] text-[#8C8A82]"
                }`}
              >
                {cladState === "running"
                  ? "Scanning…"
                  : cladState === "success"
                    ? "Measurements ready"
                    : cladState === "error"
                      ? "Scan failed"
                      : "Optional"}
              </span>
            </div>

            {cladConfigured === false && (
              <div className="bg-[#F5EDDC] text-[#7A5B1E] text-xs rounded-lg px-3 py-2.5">
                Clad is not configured. Add <code className="font-mono">CLAD_API_KEY</code> to the repo-root{" "}
                <code className="font-mono">.env</code> and restart the backend.
              </div>
            )}

            <label className="flex items-start gap-2 text-xs text-[#8C8A82]">
              <input
                type="checkbox"
                checked={cladConsent}
                onChange={(e) => setCladConsent(e.target.checked)}
                className="mt-0.5 accent-[#556B2F]"
              />
              <span>
                I agree to send this photo to Clad for body measurement. DressMe does not store the original image.
              </span>
            </label>

            <button
              onClick={onCladScan}
              disabled={!photoFile || !cladConsent || cladState === "running" || cladConfigured === false}
              className="w-full bg-[#1C1C1C] hover:bg-[#333] text-white text-sm font-semibold py-2.5 rounded-lg transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {cladState === "running" ? "Measuring…" : "Measure with Clad"}
            </button>

            {cladError && (
              <div className="bg-[#F5E0E0] text-[#8A2E2E] text-xs rounded-lg px-3 py-2.5">{cladError}</div>
            )}

            {cladResult && (
              <div className="space-y-3">
                <div className="grid grid-cols-2 gap-2">
                  {cladRows.map((row) => (
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
                  Applied to the sliders: height, leg length, muscle, weight, proportions
                  {cladResult.targets.cupsize !== undefined ? ", cup size" : ""}.
                </p>
                {cladResult.cached && (
                  <p className="text-[11px] text-[#8C8A82]">Cached result — no new API call was used.</p>
                )}
                {(photoScanRemaining !== null || questionnaireRemaining !== null) && (
                  <p className="text-[11px] text-[#8C8A82]">
                    {photoScanRemaining !== null
                      ? `Photo scans left this week: ${photoScanRemaining}. `
                      : ""}
                    {questionnaireRemaining !== null
                      ? `Questionnaire calls left: ${questionnaireRemaining}.`
                      : ""}
                  </p>
                )}
                {cladResult.notes.length > 0 && (
                  <ul className="text-[11px] text-[#8C8A82] list-disc pl-4 space-y-1">
                    {cladResult.notes.map((note) => (
                      <li key={note}>{note}</li>
                    ))}
                  </ul>
                )}
              </div>
            )}

            <details className="border-t border-[#E2E0D8] pt-3">
              <summary className="text-xs font-semibold text-[#1C1C1C] cursor-pointer">
                No photo? Use the 8-question sizing flow
              </summary>
              <div className="grid grid-cols-2 gap-3 pt-3">
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
                onClick={onCladQuestionnaire}
                disabled={cladState === "running" || cladConfigured === false}
                className="mt-3 w-full bg-white border border-[#E2E0D8] hover:bg-[#E2E0D8] text-[#1C1C1C] text-sm font-semibold py-2.5 rounded-lg transition-colors disabled:opacity-40"
              >
                {cladState === "running" ? "Measuring…" : "Measure from questionnaire"}
              </button>
            </details>
          </div>

          <div className="bg-[#F0EFEA] rounded-xl p-6 space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="font-display text-lg font-medium text-[#1C1C1C]">Estimated proportions</h3>
              {analysis && (
                <span className={`text-xs font-semibold px-3 py-1 rounded-full ${qualityBadgeStyle(analysis.qualityLabel)}`}>
                  {analysis.qualityLabel} confidence · {analysis.quality}/100
                </span>
              )}
            </div>

            {cladResult && (
              <p className="text-xs text-[#556B2F]">
                Clad scan applied. Running “Estimate proportions” will replace these values with local pose estimates.
              </p>
            )}

            {!analysis && !error && (
              <p className="text-sm text-[#8C8A82]">
                Upload a photo and run the estimate. You can still set the proportions by hand with the sliders below.
              </p>
            )}

            {analysis && (
              <div className="space-y-3">
                {analysis.reports.map((report) => (
                  <div key={report.label} className="bg-white rounded-lg px-4 py-3 flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-[#1C1C1C]">{report.label}</p>
                      <p className="text-xs text-[#8C8A82]">{report.note}</p>
                    </div>
                    <div className="text-right shrink-0">
                      <p className="text-sm font-semibold text-[#1C1C1C] tabular-nums">
                        {report.value !== null && report.reliable ? report.value.toFixed(2) : "—"}
                      </p>
                      <p className={`text-xs ${report.reliable ? "text-[#556B2F]" : "text-[#8A2E2E]"}`}>
                        {report.reliable ? "estimate" : "unreliable"}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            )}

            <div className="bg-white rounded-lg px-4 py-3 text-xs text-[#8C8A82] leading-relaxed">
              A single photo cannot reveal exact body measurements or depth. These ratios come from 2D landmark
              positions: posture, camera angle, lens distortion and clothing all shift them. Treat them as rough
              shape hints for styling — not centimeters, and not an exact likeness of you.
            </div>

            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h4 className="text-sm font-semibold text-[#1C1C1C]">Adjust manually</h4>
                <button
                  onClick={onReset}
                  disabled={!analysis}
                  className="text-xs font-semibold text-[#556B2F] hover:underline disabled:opacity-40 disabled:no-underline"
                >
                  Reset to detected values
                </button>
              </div>
              {slider("shoulderToHip")}
              {slider("torsoToLeg")}
            </div>

            <div className="space-y-4 border-t border-[#E2E0D8] pt-4">
              <div>
                <h4 className="text-sm font-semibold text-[#1C1C1C]">Body shape parameters</h4>
                <p className="text-xs text-[#8C8A82]">
                  Direct MPFB2 controls sent to Blender. 0.50 is the neutral default. Weight, muscle and height are
                  pre-filled from your photo when reliable; torso-to-leg drives the Blender leg-length post-process.
                  Gender and age are self-reported, and cup size / firmness are manual — a pose photo cannot reveal
                  those.
                </p>
              </div>
              {MPFB_PARAMS.map((meta) => mpfbSlider(meta))}
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
                </p>
                <p>· Leg length {legLength.toFixed(2)} from torso-to-leg — applied in Blender after MPFB shaping</p>
                <p>· Muscle {linkMuscle ? "is linked to the shoulder-to-hip slider" : "is unlinked and set manually"}</p>
                <p>· Every value is 0.00–1.00 with 0.50 as the neutral default</p>
              </div>
              {genState === "running" && (
                <p className="text-xs text-[#556B2F]">
                  Blender is regenerating your avatar
                  {analysis ? ` — proportion pass ${genIteration} of 2` : ""}… the original file is never overwritten.
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
        </div>

        <div className="space-y-4">
          <AvatarCanvas url={generatedUrl ?? undefined} />
          <div className="bg-[#F0EFEA] rounded-xl p-6 space-y-3">
            <h3 className="font-display text-lg font-medium text-[#1C1C1C]">Current targets</h3>
            <div className="grid grid-cols-3 gap-3">
              {(["shoulderToHip", "torsoToLeg"] as const).map((key) => {
                const report = analysis?.reports.find((r) => r.key === key)
                const fromPhoto = report?.reliable === true
                return (
                  <div key={key} className="bg-white rounded-lg px-4 py-3">
                    <p className="text-xs text-[#8C8A82]">{RATIO_LABELS[key]}</p>
                    <p className="text-lg font-semibold text-[#1C1C1C] tabular-nums">{adjusted[key].toFixed(2)}</p>
                    <p className={`text-[10px] ${fromPhoto ? "text-[#556B2F]" : "text-[#B5B3AA]"}`}>
                      {fromPhoto ? "from photo estimate" : "default — set manually"}
                    </p>
                  </div>
                )
              })}
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
