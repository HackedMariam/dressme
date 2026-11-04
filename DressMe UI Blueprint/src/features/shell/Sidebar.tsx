import { useAuth } from "../auth/AuthProvider"
import { userInitial } from "../profile/types"
import { OwnAvatar } from "../profile/UserAvatar"
import { useUserData } from "../profile/UserDataProvider"
import { NAV_GROUPS, type Page } from "./navigation"

export default function Sidebar({
  current,
  onNav,
  onAddItem,
}: {
  current: Page
  onNav: (page: Page) => void
  onAddItem: () => void
}) {
  const { profile } = useUserData()
  const { user, signOut } = useAuth()
  const displayName = profile?.display_name?.trim() || "Your profile"

  return (
    <aside className="fixed left-0 top-0 z-50 flex h-screen w-[260px] flex-col bg-[#1C1C1C]">
      <div className="border-b border-white/10 px-7 py-7">
        <div className="flex items-baseline gap-1">
          <span className="font-display text-2xl font-semibold italic text-[#FAF9F6]">Dress</span>
          <span className="font-display text-2xl font-semibold text-[#556B2F]">Me</span>
        </div>
        <p className="mt-0.5 text-[11px] font-light uppercase tracking-widest text-white/30">AI Style Intelligence</p>
      </div>

      <div className="px-5 pt-5">
        <button
          type="button"
          onClick={onAddItem}
          className="w-full rounded-lg bg-[#556B2F] py-2.5 text-sm font-semibold text-white transition-colors hover:bg-[#6B8A3A]"
        >
          + Add clothing
        </button>
      </div>

      <nav className="flex-1 overflow-y-auto py-4" aria-label="Main">
        {NAV_GROUPS.map((group, index) => (
          <div key={group.title ?? index} className={index === 0 ? "" : "mt-4"}>
            {group.title && (
              <p className="px-7 pb-1.5 text-[10px] font-semibold uppercase tracking-[0.18em] text-white/25">
                {group.title}
              </p>
            )}
            {group.entries.map((entry) => {
              const active = current === entry.page || Boolean(entry.also?.includes(current))
              return (
                <button
                  key={entry.page}
                  type="button"
                  onClick={() => onNav(entry.page)}
                  aria-current={active ? "page" : undefined}
                  className={`flex w-full items-center gap-3 px-7 py-2.5 text-left text-sm transition-all duration-150 ${
                    active
                      ? "border-r-2 border-[#556B2F] bg-[#556B2F]/20 text-[#FAF9F6]"
                      : "text-white/50 hover:bg-white/5 hover:text-white/80"
                  }`}
                >
                  <span className="text-base opacity-70">{entry.icon}</span>
                  <span className="font-medium">{entry.label}</span>
                </button>
              )
            })}
          </div>
        ))}
      </nav>

      <div className="flex items-center gap-3 border-t border-white/10 px-7 py-5">
        <OwnAvatar initial={userInitial(profile?.display_name, user?.email)} size={36} />
        <div className="min-w-0 flex-1">
          <p className="truncate text-xs font-medium text-white/80">{displayName}</p>
          <button
            type="button"
            onClick={() => void signOut()}
            className="text-[10px] text-white/35 hover:text-white/70"
          >
            Sign out
          </button>
        </div>
      </div>
    </aside>
  )
}
