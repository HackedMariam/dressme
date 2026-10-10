import { useEffect, useRef, useState } from "react"
import { AvatarCanvas } from "./AvatarViewer"
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

export default function CustomizeAvatar() {
  const [fileUrl, setFileUrl] = useState<string | null>(null)
  const [fileName, setFileName] = useState<string | null>(null)
  const [modelStatus, setModelStatus] = useState<ModelStatus>("idle")
  const [analyzing, setAnalyzing] = useState(false)
  const [analysis, setAnalysis] = useState<Extract<PoseAnalysis, { ok: true }> | null>(null)
  const [adjusted, setAdjusted] = useState<Proportions>(defaultProportions())
  const [error, setError] = useState<string | null>(null)
  const imgRef = useRef<HTMLImageElement | null>(null)
  const prevUrlRef = useRef<string | null>(null)

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
    }
  }, [])

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
    setAnalysis(null)
    setAdjusted(defaultProportions())
    setError(null)
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
    try {
      if (img.decode) {
        await img.decode().catch(() => undefined)
      }
      const result = await analyzePhoto(img)
      if (result.ok) {
        setAnalysis(result)
        setAdjusted(result.proportions)
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
          onChange={(e) => setAdjusted((prev) => ({ ...prev, [key]: Number(e.target.value) }))}
          className="w-full accent-[#556B2F]"
        />
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
            <div className="flex items-center justify-between">
              <h3 className="font-display text-lg font-medium text-[#1C1C1C]">Estimated proportions</h3>
              {analysis && (
                <span className={`text-xs font-semibold px-3 py-1 rounded-full ${qualityBadgeStyle(analysis.qualityLabel)}`}>
                  {analysis.qualityLabel} confidence · {analysis.quality}/100
                </span>
              )}
            </div>

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
          </div>
        </div>

        <div className="space-y-4">
          <AvatarCanvas />
          <div className="bg-[#F0EFEA] rounded-xl p-6 space-y-3">
            <h3 className="font-display text-lg font-medium text-[#1C1C1C]">Current targets</h3>
            <div className="grid grid-cols-2 gap-3">
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
            </div>
            <p className="text-xs text-[#8C8A82]">
              The avatar GLB is not modified yet. In the next step these targets will be mapped to MPFB body
              parameters in Blender.
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
