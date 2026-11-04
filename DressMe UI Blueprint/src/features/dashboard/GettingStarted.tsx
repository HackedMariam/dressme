import { useEffect, useState } from "react"
import { api } from "../../lib/api"
import { useUserData } from "../profile/UserDataProvider"
import type { Page } from "../shell/navigation"
import { useWardrobe } from "../wardrobe/WardrobeProvider"

const DISMISS_KEY = "dressme.gettingStartedDismissed"
const MIN_ITEMS = 5

function dismissedBefore() {
  try {
    return localStorage.getItem(DISMISS_KEY) === "1"
  } catch {
    return false
  }
}

type Step = { id: string; title: string; detail: string; done: boolean; page: Page; action: string }

// First-visit checklist: what to do to get the most out of DressMe. It disappears once everything is done.
export default function GettingStarted({ onNavigate }: { onNavigate: (page: Page) => void }) {
  const { items, health } = useWardrobe()
  const { profile } = useUserData()
  const [hasAvatar, setHasAvatar] = useState<boolean | null>(null)
  const [dismissed, setDismissed] = useState(dismissedBefore)

  useEffect(() => {
    if (!health?.avatar) return
    api
      .avatarStatus()
      .then((status) => setHasAvatar(status.exists))
      .catch(() => setHasAvatar(null))
  }, [health?.avatar])

  const steps: Step[] = [
    {
      id: "items",
      title: "Add your clothes",
      detail: `Photograph at least ${MIN_ITEMS} pieces so DressMe can analyse your wardrobe (${Math.min(items.length, MIN_ITEMS)}/${MIN_ITEMS}).`,
      done: items.length >= MIN_ITEMS,
      page: "wardrobe",
      action: "Add clothes",
    },
    {
      id: "profile",
      title: "Complete your style profile",
      detail: "Tell us your style, sizes and budget so suggestions fit you.",
      done: Boolean(profile?.onboarding_completed),
      page: "style-profile",
      action: "Open profile",
    },
    ...(health?.avatar
      ? [
          {
            id: "avatar",
            title: "Create your 3D avatar",
            detail: "Optional. Lets you try on pieces before you buy them.",
            done: hasAvatar === true,
            page: "avatar" as Page,
            action: "Create avatar",
          },
        ]
      : []),
  ]

  const remaining = steps.filter((step) => !step.done)
  if (dismissed || remaining.length === 0) return null

  const dismiss = () => {
    setDismissed(true)
    try {
      localStorage.setItem(DISMISS_KEY, "1")
    } catch {
      // the checklist simply comes back next time
    }
  }

  return (
    <section className="rounded-xl border border-[#556B2F]/25 bg-[#E8EDE0] p-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="font-display text-lg font-medium text-[#1C1C1C]">Get started</h2>
          <p className="mt-1 text-xs text-[#556B2F]">
            {steps.length - remaining.length} of {steps.length} steps done
          </p>
        </div>
        <button type="button" onClick={dismiss} className="text-xs text-[#556B2F] underline hover:text-[#1C1C1C]">
          Hide
        </button>
      </div>
      <div className="mt-4 grid gap-3 md:grid-cols-3">
        {steps.map((step) => (
          <div
            key={step.id}
            className={`flex flex-col rounded-lg bg-white p-4 ${step.done ? "opacity-60" : ""}`}
          >
            <p className="flex items-center gap-2 text-sm font-semibold text-[#1C1C1C]">
              <span
                className={`flex h-5 w-5 items-center justify-center rounded-full text-[11px] ${
                  step.done ? "bg-[#556B2F] text-white" : "border border-[#C9C6BA] text-transparent"
                }`}
              >
                {"✓"}
              </span>
              {step.title}
            </p>
            <p className="mt-1 flex-1 text-xs text-[#8C8A82]">{step.detail}</p>
            {!step.done && (
              <button
                type="button"
                onClick={() => onNavigate(step.page)}
                className="mt-3 self-start rounded-lg bg-[#556B2F] px-3 py-1.5 text-xs font-semibold text-white hover:bg-[#6B8A3A]"
              >
                {step.action}
              </button>
            )}
          </div>
        ))}
      </div>
    </section>
  )
}
