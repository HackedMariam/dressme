import { useEffect, useState } from "react"
import { api } from "../../lib/api"

// The photo the user's 3D avatar was made from (kept privately by the backend), or null when there is none.
// Fetched once per page and shown as a blob URL because the file needs the session token.
export function useAvatarPhoto(): string | null {
  const [url, setUrl] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    let created = ""
    api
      .avatarStatus()
      .then((status) => (status.exists ? api.avatarPhoto() : null))
      .then((blob) => {
        if (cancelled || !blob) return
        created = URL.createObjectURL(blob)
        setUrl(created)
      })
      .catch(() => {}) // no avatar, or the avatar service is off: the initial is shown instead
    return () => {
      cancelled = true
      if (created) URL.revokeObjectURL(created)
    }
  }, [])

  return url
}

// A round picture: the avatar photo when there is one, otherwise the initial.
export default function UserAvatar({
  initial,
  size = 40,
  photo,
  className = "",
}: {
  initial: string
  size?: number
  photo?: string | null
  className?: string
}) {
  return (
    <div
      className={`flex shrink-0 items-center justify-center overflow-hidden rounded-full bg-[#556B2F]/30 font-semibold text-[#8FAE5A] ${className}`}
      style={{ width: size, height: size, fontSize: Math.round(size * 0.4) }}
    >
      {photo ? <img src={photo} alt="Your avatar" className="h-full w-full object-cover object-top" /> : initial}
    </div>
  )
}

// The signed-in user's own picture; it loads the avatar photo itself.
export function OwnAvatar(props: { initial: string; size?: number; className?: string }) {
  return <UserAvatar {...props} photo={useAvatarPhoto()} />
}
