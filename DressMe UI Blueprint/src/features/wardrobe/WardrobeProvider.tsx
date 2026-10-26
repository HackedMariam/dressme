import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react"
import { api } from "../../lib/api"
import type { Health, WardrobeItem } from "../../lib/types"

interface WardrobeContextValue {
  items: WardrobeItem[]
  health: Health | null
  loading: boolean
  error: string | null
  reload: () => Promise<void>
  addItems: (items: WardrobeItem[]) => void
  updateItem: (id: string, fields: Record<string, unknown>, confirm?: boolean) => Promise<WardrobeItem>
  reclassifyItem: (id: string) => Promise<WardrobeItem>
  deleteItem: (id: string) => Promise<void>
}

const WardrobeContext = createContext<WardrobeContextValue | null>(null)

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : "Something went wrong."
}

export function WardrobeProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<WardrobeItem[]>([])
  const [health, setHealth] = useState<Health | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const reload = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [nextHealth, nextItems] = await Promise.all([api.health(), api.list()])
      setHealth(nextHealth)
      setItems(nextItems)
    } catch (loadError) {
      setError(errorMessage(loadError))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void reload()
  }, [reload])

  const addItems = useCallback((incoming: WardrobeItem[]) => {
    if (!incoming.length) return
    setItems((previous) => {
      const next = [...previous]
      for (const item of incoming) {
        const index = next.findIndex((entry) => entry.id === item.id)
        if (index >= 0) next[index] = item
        else next.unshift(item)
      }
      return next
    })
  }, [])

  const updateItem = useCallback(
    async (id: string, fields: Record<string, unknown>, confirm = true) => {
      const updated = await api.update(id, fields, confirm)
      setItems((previous) =>
        previous.map((item) => (item.id === id ? { ...item, ...updated } : item)),
      )
      return updated
    },
    [],
  )

  const reclassifyItem = useCallback(async (id: string) => {
    const updated = await api.reclassify(id)
    setItems((previous) =>
      previous.map((item) => (item.id === id ? { ...item, ...updated } : item)),
    )
    return updated
  }, [])

  const deleteItem = useCallback(async (id: string) => {
    await api.remove(id)
    setItems((previous) => previous.filter((item) => item.id !== id))
  }, [])

  const value = useMemo(
    () => ({
      items,
      health,
      loading,
      error,
      reload,
      addItems,
      updateItem,
      reclassifyItem,
      deleteItem,
    }),
    [items, health, loading, error, reload, addItems, updateItem, reclassifyItem, deleteItem],
  )

  return <WardrobeContext.Provider value={value}>{children}</WardrobeContext.Provider>
}

export function useWardrobe(): WardrobeContextValue {
  const context = useContext(WardrobeContext)
  if (!context) throw new Error("useWardrobe must be used inside WardrobeProvider")
  return context
}
