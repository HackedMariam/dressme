import { useCallback, useEffect, useRef, useState } from "react"

// The Web Speech API is not in the TypeScript DOM lib, and only some browsers ship it (Chrome, Edge, Safari).
interface Recognition {
  lang: string
  interimResults: boolean
  continuous: boolean
  onresult: ((event: { results: ArrayLike<ArrayLike<{ transcript: string }> & { isFinal: boolean }> }) => void) | null
  onerror: ((event: { error: string }) => void) | null
  onend: (() => void) | null
  start: () => void
  stop: () => void
  abort: () => void
}

function recognitionClass(): (new () => Recognition) | null {
  if (typeof window === "undefined") return null
  const w = window as unknown as Record<string, new () => Recognition>
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null
}

const MESSAGES: Record<string, string> = {
  "not-allowed": "Microphone access was blocked. Allow it in the browser address bar.",
  "service-not-allowed": "Microphone access was blocked. Allow it in the browser address bar.",
  "no-speech": "I did not hear anything. Try again.",
  "audio-capture": "No microphone found.",
  network: "Speech recognition needs an internet connection.",
}

/** Dictation: `onText` receives the live transcript, with `final` true once the sentence is done. */
export function useSpeech(onText: (text: string, final: boolean) => void, lang?: string) {
  const supported = recognitionClass() !== null
  const [listening, setListening] = useState(false)
  const [error, setError] = useState("")
  const recognition = useRef<Recognition | null>(null)
  const callback = useRef(onText)
  callback.current = onText

  const stop = useCallback(() => recognition.current?.stop(), [])

  const start = useCallback(() => {
    const Recognizer = recognitionClass()
    if (!Recognizer) return
    recognition.current?.abort()
    const next = new Recognizer()
    next.lang = lang || (typeof navigator !== "undefined" ? navigator.language : "") || "en-US"
    next.interimResults = true
    next.continuous = false
    next.onresult = (event) => {
      let text = ""
      let final = false
      for (let i = 0; i < event.results.length; i++) {
        text += event.results[i][0].transcript
        final = event.results[i].isFinal
      }
      callback.current(text.trim(), final)
    }
    next.onerror = (event) => setError(MESSAGES[event.error] ?? "Voice input failed.")
    next.onend = () => setListening(false)
    recognition.current = next
    setError("")
    setListening(true)
    try {
      next.start()
    } catch {
      setListening(false)
    }
  }, [lang])

  useEffect(() => () => recognition.current?.abort(), [])

  return { supported, listening, error, start, stop, toggle: () => (listening ? stop() : start()) }
}
