import { useCallback, useEffect, useRef, useState } from "react"
import type { WardrobeItemRow } from "../../lib/database.types"
import { fetchWardrobeItems } from "./api"

type WardrobeState = {
  items: WardrobeItemRow[]
  loading: boolean
  error: string | null
}

export function useWardrobeItems(userId: string | null | undefined) {
  const [state, setState] = useState<WardrobeState>({
    items: [],
    loading: Boolean(userId),
    error: null,
  })
  const requestId = useRef(0)

  const load = useCallback(async () => {
    const current = ++requestId.current
    if (!userId) {
      setState({ items: [], loading: false, error: null })
      return
    }

    setState((previous) => ({ ...previous, loading: true, error: null }))
    try {
      const items = await fetchWardrobeItems(userId)
      if (current !== requestId.current) return
      setState({ items, loading: false, error: null })
    } catch (error) {
      if (current !== requestId.current) return
      setState({
        items: [],
        loading: false,
        error:
          error instanceof Error
            ? error.message
            : "Could not load your wardrobe.",
      })
    }
  }, [userId])

  useEffect(() => {
    void load()
    return () => {
      requestId.current += 1
    }
  }, [load])

  return { ...state, refresh: load }
}
