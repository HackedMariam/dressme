import { useCallback, useEffect, useRef, useState } from "react"
import {
  getLatestAvatar,
  type AvatarSnapshot,
} from "../../lib/avatarApi"

export function useLatestAvatar(userId: string | null | undefined) {
  const [snapshot, setSnapshot] = useState<AvatarSnapshot | null>(null)
  const [loading, setLoading] = useState(Boolean(userId))
  const requestId = useRef(0)

  const load = useCallback(
    async (signal?: AbortSignal) => {
      const current = ++requestId.current
      if (!userId) {
        setSnapshot(null)
        setLoading(false)
        return
      }

      setLoading(true)
      try {
        const result = await getLatestAvatar(signal)
        if (current !== requestId.current) return
        setSnapshot(result)
      } catch {
        if (current !== requestId.current) return
        setSnapshot(null)
      } finally {
        if (current === requestId.current) setLoading(false)
      }
    },
    [userId],
  )

  useEffect(() => {
    const controller = new AbortController()
    void load(controller.signal)
    return () => {
      controller.abort()
      requestId.current += 1
    }
  }, [load])

  return { snapshot, loading, refresh: () => load() }
}
