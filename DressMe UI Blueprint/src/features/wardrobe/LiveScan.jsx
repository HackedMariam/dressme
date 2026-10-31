import { useEffect, useRef, useState } from 'react'
import { api, asset } from '../../lib/api'
import { cap } from '../../lib/taxonomy'

const POLL_MS = 600       // how often we ask the server "what's in frame right now"
const STABLE_MS = 1400    // how long the same item must hold steady before we save it
const COOLDOWN_MS = 2200  // after a capture, ignore detections for this long (lets you swap items)
const MIN_CONFIDENCE = 0.35  // below this it is background noise; between this and the server's bar you get a question

// Live camera scan: polls /api/items/quick-detect (fast, YOLO-only) to track whatever is
// in frame, and once the same item has been held steady for STABLE_MS, saves it instantly
// via /api/items/analyze?fast=true (rule-based classification) so there's no multi-second
// wait. The full GPT-4 classification is then requested in the background per item via
// /reclassify, and the card updates itself whenever that resolves.
export default function LiveScan({ onAdded, onClose }) {
  const videoRef = useRef()
  const previewCanvasRef = useRef()
  const captureCanvasRef = useRef()
  const streamRef = useRef()
  const pollRef = useRef()
  const busyRef = useRef(false)
  const trackRef = useRef(null)       // { key, since }
  const cooldownUntilRef = useRef(0)
  const lastKeyRef = useRef(null)     // item just captured; it must leave the frame before the next capture
  const armedRef = useRef(true)
  const addRef = useRef(null)         // addFromFile, reachable from the "Add anyway" button

  const [status, setStatus] = useState('starting') // starting | scanning | holding | captured | error
  const [error, setError] = useState('')
  const [label, setLabel] = useState(null)          // { category, color_name }
  const [box, setBox] = useState(null)               // { x1,y1,x2,y2, frameW, frameH }
  const [progress, setProgress] = useState(0)
  const [hint, setHint] = useState('')                // live advice: show the whole item, move closer...
  const [session, setSession] = useState([])          // this session's captures, newest first

  useEffect(() => {
    let cancelled = false
    navigator.mediaDevices?.getUserMedia({ video: { facingMode: 'environment', width: { ideal: 1280 } }, audio: false })
      .then((stream) => {
        if (cancelled) { stream.getTracks().forEach((t) => t.stop()); return }
        streamRef.current = stream
        if (videoRef.current) {
          videoRef.current.srcObject = stream
          videoRef.current.play().catch(() => {})
        }
        setStatus('scanning')
        pollRef.current = setInterval(tick, POLL_MS)
      })
      .catch((e) => { setStatus('error'); setError(e.message || "Can't access the camera") })

    async function tick() {
      if (busyRef.current) return
      const video = videoRef.current
      if (!video || video.readyState < 2) return
      busyRef.current = true
      try {
        const scale = Math.min(1, 640 / video.videoWidth)
        const canvas = previewCanvasRef.current
        canvas.width = Math.round(video.videoWidth * scale)
        canvas.height = Math.round(video.videoHeight * scale)
        canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height)
        const blob = await new Promise((res) => canvas.toBlob(res, 'image/jpeg', 0.7))
        if (!blob || cancelled) return
        const { detections } = await api.quickDetect(blob)
        if (!cancelled) handleDetection(detections[0] || null, canvas.width, canvas.height)
      } catch {
        // transient network hiccup — just keep scanning
      } finally {
        busyRef.current = false
      }
    }

    function handleDetection(det, frameW, frameH) {
      const now = Date.now()
      if (now < cooldownUntilRef.current) return
      if (!det || det.confidence < MIN_CONFIDENCE) {
        trackRef.current = null
        setBox(null)
        setProgress(0)
        setHint('')
        setStatus('scanning')
        armedRef.current = true   // nothing usable in frame: the last item was taken away
        return
      }
      const key = `${det.category}|${det.color_name}`
      if (key !== lastKeyRef.current) armedRef.current = true
      if (!armedRef.current) {    // same item still in front of the camera: do not save it again
        trackRef.current = null
        setBox(null)
        setProgress(0)
        setHint('Already scanned. Remove it, or show another item.')
        setStatus('scanning')
        return
      }
      setHint(det.problem || '')
      setBox({ ...boxOf(det), frameW, frameH })
      setLabel(det)
      if (trackRef.current?.key !== key) trackRef.current = { key, since: now }
      const held = now - trackRef.current.since
      setProgress(Math.min(1, held / STABLE_MS))
      setStatus('holding')
      if (held >= STABLE_MS) {
        trackRef.current = null
        cooldownUntilRef.current = now + COOLDOWN_MS
        capture(key)
      }
    }

    async function capture(key) {
      setStatus('captured')
      try {
        const video = videoRef.current
        const canvas = captureCanvasRef.current
        canvas.width = video.videoWidth
        canvas.height = video.videoHeight
        canvas.getContext('2d').drawImage(video, 0, 0)
        const blob = await new Promise((res) => canvas.toBlob(res, 'image/jpeg', 0.92))
        if (!blob) throw new Error('Could not capture the frame')
        const file = new File([blob], 'capture.jpg', { type: 'image/jpeg' })
        lastKeyRef.current = key
        armedRef.current = false
        await addFromFile(file, false)
      } catch (e) {
        if (e.status === 422) {
          // The server refused a bad frame (low confidence, item cut off, too far): advice, not an error card.
          setHint(e.message)
          armedRef.current = true
        } else {
          setSession((s) => [{ id: `err-${Date.now()}`, error: e.message }, ...s])
        }
      } finally {
        if (!cancelled) setTimeout(() => setStatus('scanning'), 1100)
      }
    }

    // Saves one frame. The server skips it (nothing saved) when it looks like an item you already own.
    async function addFromFile(file, force) {
      {
        const { items: added, skipped } = await api.analyze(file, { fast: true, force })
        if (cancelled) return
        if (skipped) {
          // Nothing was saved. The card says why and lets the user confirm or dismiss.
          setSession((s) => [{ id: `skip-${Date.now()}`, skipped, file, preview: URL.createObjectURL(file) }, ...s])
          return
        }
        onAdded(added)
        setSession((s) => [...added.map((i) => ({ ...i, pending: true })), ...s])
        added.forEach((item) => {
          api.reclassify(item.id).then((updated) => {
            if (cancelled) return
            onAdded([updated])
            setSession((s) => s.map((x) => (x.id === item.id ? { ...updated, pending: false, dup: x.dup } : x)))
          }).catch(() => {
            setSession((s) => s.map((x) => (x.id === item.id ? { ...x, pending: false } : x)))
          })
          // The duplicate check is itself an agent: it decides whether to search the wardrobe
          // for a near-duplicate of this item and only flags a genuinely confident match.
          api.checkDuplicate(item).then((res) => {
            if (cancelled || !res.duplicate) return
            setSession((s) => s.map((x) => (x.id === item.id ? { ...x, dup: res.note || 'Looks like one you already have' } : x)))
          }).catch(() => {})
        })
      }
    }
    addRef.current = addFromFile

    return () => {
      cancelled = true
      clearInterval(pollRef.current)
      streamRef.current?.getTracks().forEach((t) => t.stop())
    }
  }, [])

  function dismiss(entry) {
    if (entry.preview) URL.revokeObjectURL(entry.preview)
    setSession((s) => s.filter((x) => x.id !== entry.id))
  }

  async function addAnyway(entry) {
    dismiss(entry)
    try {
      await addRef.current(entry.file, true)
    } catch (e) {
      setSession((s) => [{ id: `err-${Date.now()}`, error: e.message }, ...s])
    }
  }

  function boxOf(det) {
    const [x1, y1, x2, y2] = det.box
    return { x1, y1, x2, y2 }
  }

  const boxStyle = box && {
    left: `${(box.x1 / box.frameW) * 100}%`, top: `${(box.y1 / box.frameH) * 100}%`,
    width: `${((box.x2 - box.x1) / box.frameW) * 100}%`, height: `${((box.y2 - box.y1) / box.frameH) * 100}%`,
  }

  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div className="flex max-h-[90vh] w-full max-w-2xl flex-col overflow-y-auto rounded-2xl bg-[#FAF9F6] p-5 shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between">
          <h2 className="font-display text-xl font-semibold text-[#1C1C1C]">Live scan</h2>
          <button type="button" className="rounded-lg border border-[#E2E0D8] bg-white p-2 text-[#1C1C1C] hover:bg-[#F0EFEA]" title="Close" onClick={onClose}>
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M5 5l14 14M19 5L5 19" />
            </svg>
          </button>
        </div>

        <div className="relative mt-4 aspect-video overflow-hidden rounded-xl bg-black">
          {status === 'error' ? (
            <div className="flex h-full flex-col items-center justify-center gap-2 px-6 text-center text-sm text-white">
              <p>Can't reach the camera.</p>
              <p className="text-white/60">{error}</p>
            </div>
          ) : (
            <>
              <video ref={videoRef} muted playsInline className="h-full w-full object-cover" />
              {box && status !== 'captured' && (
                <div
                  className={`absolute rounded border-2 transition-colors ${status === 'holding' ? 'border-amber-400' : 'border-[#8FAE5A]'}`}
                  style={boxStyle}
                >
                  <span className="absolute bottom-0 left-0 h-1 rounded-full bg-amber-400" style={{ width: `${progress * 100}%` }} />
                </div>
              )}
              <div className={`absolute inset-x-0 bottom-0 px-4 py-2 text-center text-sm font-medium text-white ${status === 'captured' ? 'bg-[#556B2F]' : 'bg-black/50'}`}>
                {status === 'starting' && 'Starting camera...'}
                {status === 'scanning' && (hint || 'Point the camera at one clothing item')}
                {status === 'holding' && `Hold still - ${cap(label?.color_name || '')} ${cap(label?.category || '')}...${hint ? ` (${hint})` : ''}`}
                {status === 'captured' && 'Added!'}
              </div>
            </>
          )}
        </div>

        <canvas ref={previewCanvasRef} hidden />
        <canvas ref={captureCanvasRef} hidden />

        <div className="mt-4 space-y-2">
          <h3 className="text-xs font-semibold uppercase tracking-widest text-[#8C8A82]">
            Added this session {session.length ? `(${session.length})` : ''}
          </h3>
          {!session.length ? (
            <p className="text-sm text-[#8C8A82]">Nothing yet - hold an item steady in frame.</p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {session.map((i) => (
                <div
                  key={i.id}
                  className={`flex max-w-full items-center gap-2 rounded-lg border p-2 text-xs ${
                    i.error
                      ? 'border-red-200 bg-red-50 text-red-700'
                      : i.dup || i.skipped
                        ? 'border-amber-200 bg-amber-50'
                        : 'border-[#E2E0D8] bg-white'
                  }`}
                >
                  {i.error ? <span>Could not add: {i.error}</span> : i.skipped ? (
                    <>
                      {i.preview && <img src={i.preview} alt="" className="h-12 w-10 rounded bg-[#F0EFEA] object-cover" />}
                      <div className="min-w-0">
                        <span className="block font-medium text-[#1C1C1C]">Not added yet</span>
                        <span className="block text-amber-800">{i.skipped.note}</span>
                        <div className="mt-1 flex gap-3">
                          <button type="button" className="font-semibold text-[#556B2F] underline" onClick={() => addAnyway(i)}>Add anyway</button>
                          <button type="button" className="text-[#8C8A82] underline" onClick={() => dismiss(i)}>Dismiss</button>
                        </div>
                      </div>
                    </>
                  ) : (
                    <>
                      {i.cutout_url && <img src={asset(i.cutout_url)} alt="" className="h-10 w-8 rounded bg-[#F0EFEA] object-contain" />}
                      <div className="min-w-0">
                        <span className="block truncate text-[#1C1C1C]">{i.name}{i.pending ? '...' : ''}</span>
                        {i.dup && <small className="block text-amber-700">{i.dup}</small>}
                      </div>
                    </>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
