import { useEffect, useState } from "react"
import { useAuth } from "../auth/AuthProvider"
import {
  deleteGalleryPhoto,
  galleryPhotoUrl,
  listGalleryPhotos,
  type GalleryPhoto,
} from "../../lib/photoGallery"

const FEATURE_LABELS: Record<string, string> = {
  avatar: "Avatar customization",
  wardrobe: "Wardrobe",
  "find-similar": "Find similar",
  "should-i-buy": "Should I buy?",
}

export default function GalleryPage() {
  const { user } = useAuth()
  const [photos, setPhotos] = useState<GalleryPhoto[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!user?.id) return
    let active = true
    setLoading(true)
    listGalleryPhotos(user.id)
      .then((next) => {
        if (active) setPhotos(next)
      })
      .catch((reason) => {
        if (active) setError(reason instanceof Error ? reason.message : "Could not load your gallery.")
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [user?.id])

  const remove = async (id: string) => {
    try {
      await deleteGalleryPhoto(id)
      setPhotos((current) => current.filter((photo) => photo.id !== id))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not delete that photo.")
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-3xl font-semibold text-[#1C1C1C]">My photo gallery</h1>
        <p className="mt-1 text-sm text-[#8C8A82]">
          Photos you add to DressMe are kept here so you can return to them between features.
        </p>
      </div>
      {error && <p className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>}
      {loading ? (
        <p className="text-sm text-[#8C8A82]">Loading your gallery...</p>
      ) : photos.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-[#E2E0D8] bg-white p-12 text-center text-sm text-[#8C8A82]">
          Photos added for avatar analysis, wardrobe items, or shopping tools will appear here.
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-5 md:grid-cols-3 lg:grid-cols-4">
          {photos.map((photo) => {
            const url = galleryPhotoUrl(photo)
            return (
              <article key={photo.id} className="overflow-hidden rounded-xl border border-[#E2E0D8] bg-white">
                <img src={url} alt={photo.name} className="aspect-square w-full object-cover" onLoad={() => URL.revokeObjectURL(url)} />
                <div className="space-y-2 p-3">
                  <p className="truncate text-xs font-semibold text-[#1C1C1C]">{photo.name}</p>
                  <p className="text-[11px] text-[#8C8A82]">
                    {FEATURE_LABELS[photo.feature] ?? photo.feature} · {new Date(photo.createdAt).toLocaleDateString()}
                  </p>
                  <button type="button" onClick={() => void remove(photo.id)} className="text-[11px] font-semibold text-red-600 hover:text-red-800">
                    Remove
                  </button>
                </div>
              </article>
            )
          })}
        </div>
      )}
    </div>
  )
}
