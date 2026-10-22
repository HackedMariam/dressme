import { useEffect, useRef, useState } from 'react'
import { api, cap } from '../api'

const POLL_MS = 600       // how often we ask the server "what's in frame right now"
const STABLE_MS = 1400    // how long the same item must hold steady before we save it
const COOLDOWN_MS = 2200  // after a capture, ignore detections for this long (lets you swap items)
const MIN_CONFIDENCE = 0.35

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

  const [status, setStatus] = useState('starting') // starting | scanning | holding | captured | error
  const [error, setError] = useState('')
  const [label, setLabel] = useState(null)          // { category, color_name }
  const [box, setBox] = useState(null)               // { x1,y1,x2,y2, frameW, frameH }
  const [progress, setProgress] = useState(0)
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
        setStatus('scanning')
        return
      }
      setBox({ ...boxOf(det), frameW, frameH })
      setLabel(det)
      const key = `${det.category}|${det.color_name}`
      if (trackRef.current?.key !== key) trackRef.current = { key, since: now }
      const held = now - trackRef.current.since
      setProgress(Math.min(1, held / STABLE_MS))
      setStatus('holding')
      if (held >= STABLE_MS) {
        trackRef.current = null
        cooldownUntilRef.current = now + COOLDOWN_MS
        capture()
      }
    }

    async function capture() {
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
        const { items: added } = await api.analyze(file, false, true)
        if (cancelled) return
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
      } catch (e) {
        setSession((s) => [{ id: `err-${Date.now()}`, error: e.message }, ...s])
      } finally {
        if (!cancelled) setTimeout(() => setStatus('scanning'), 1100)
      }
    }

    return () => {
      cancelled = true
      clearInterval(pollRef.current)
      streamRef.current?.getTracks().forEach((t) => t.stop())
    }
  }, [])

  function boxOf(det) {
    const [x1, y1, x2, y2] = det.box
    return { x1, y1, x2, y2 }
  }

  const boxStyle = box && {
    left: `${(box.x1 / box.frameW) * 100}%`, top: `${(box.y1 / box.frameH) * 100}%`,
    width: `${((box.x2 - box.x1) / box.frameW) * 100}%`, height: `${((box.y2 - box.y1) / box.frameH) * 100}%`,
  }

  return (
    <div className="scan-overlay" onClick={onClose}>
      <div className="scan-panel" onClick={(e) => e.stopPropagation()}>
        <div className="scan-head">
          <h2>Live scan</h2>
          <button className="icon-btn" title="Close" onClick={onClose}>
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M5 5l14 14M19 5L5 19" />
            </svg>
          </button>
        </div>

        <div className="scan-video-wrap">
          {status === 'error' ? (
            <div className="scan-error">
              <p>Can't reach the camera.</p>
              <p className="muted">{error}</p>
            </div>
          ) : (
            <>
              <video ref={videoRef} muted playsInline className="scan-video" />
              {box && status !== 'captured' && (
                <div className={`scan-box ${status === 'holding' ? 'holding' : ''}`} style={boxStyle}>
                  <span className="scan-bar" style={{ width: `${progress * 100}%` }} />
                </div>
              )}
              <div className={`scan-status ${status}`}>
                {status === 'starting' && 'Starting camera…'}
                {status === 'scanning' && 'Point the camera at one clothing item'}
                {status === 'holding' && `Hold still — ${cap(label?.color_name || '')} ${cap(label?.category || '')}…`}
                {status === 'captured' && '✓ Added!'}
              </div>
            </>
          )}
        </div>

        <canvas ref={previewCanvasRef} hidden />
        <canvas ref={captureCanvasRef} hidden />

        <div className="scan-session">
          <h3>Added this session {session.length ? `(${session.length})` : ''}</h3>
          {!session.length ? (
            <p className="muted">Nothing yet — hold an item steady in frame.</p>
          ) : (
            <div className="scan-session-list">
              {session.map((i) => (
                <div key={i.id} className={`scan-chip ${i.error ? 'failed' : ''} ${i.dup ? 'dup' : ''}`}>
                  {i.error ? <span>Couldn't add: {i.error}</span> : (
                    <>
                      {i.cutout_url && <img src={i.cutout_url} alt="" />}
                      <div className="scan-chip-body">
                        <span>{i.name}{i.pending ? '…' : ''}</span>
                        {i.dup && <small>⚠ {i.dup}</small>}
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
