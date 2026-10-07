import type { ReactNode } from "react"
import type { Status, Step } from "./data"

export const STEP_FLOW: Step[] = [
  "form",
  "trip",
  "wardrobe",
  "processing",
  "outfits",
  "optimize",
  "list",
  "coverage",
]

export const STEP_LABELS: Record<Step, string> = {
  form: "Trip",
  trip: "Weather",
  wardrobe: "Wardrobe",
  processing: "Plan",
  outfits: "Looks",
  optimize: "Optimize",
  list: "Pack List",
  coverage: "Coverage",
  feedback: "Feedback",
}

export function Eyebrow({
  children,
  tone = "muted",
}: {
  children: ReactNode
  tone?: "muted" | "olive" | "dark"
}) {
  const color =
    tone === "olive"
      ? "text-[#556B2F]"
      : tone === "dark"
        ? "text-white/40"
        : "text-[#8C8A82]"
  return (
    <p className={`text-xs font-semibold uppercase tracking-widest ${color}`}>
      {children}
    </p>
  )
}

export function PrimaryButton({
  children,
  onClick,
  full,
  disabled,
}: {
  children: ReactNode
  onClick?: () => void
  full?: boolean
  disabled?: boolean
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`${
        full ? "w-full" : ""
      } bg-[#1C1C1C] hover:bg-[#333] disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-semibold px-7 py-3.5 rounded-lg transition-colors`}
    >
      {children}
    </button>
  )
}

export function SecondaryButton({
  children,
  onClick,
  full,
}: {
  children: ReactNode
  onClick?: () => void
  full?: boolean
}) {
  return (
    <button
      onClick={onClick}
      className={`${
        full ? "w-full" : ""
      } bg-white border border-[#E2E0D8] text-[#1C1C1C] text-sm font-semibold px-6 py-3.5 rounded-lg hover:border-[#556B2F] hover:text-[#556B2F] transition-colors`}
    >
      {children}
    </button>
  )
}

export function FlowFooter({
  onBack,
  backLabel = "Back",
  onNext,
  nextLabel,
  nextDisabled,
}: {
  onBack?: () => void
  backLabel?: string
  onNext?: () => void
  nextLabel: string
  nextDisabled?: boolean
}) {
  return (
    <div className="flex items-center justify-between gap-4 pt-1">
      {onBack ? (
        <button
          onClick={onBack}
          className="text-sm text-[#8C8A82] hover:text-[#1C1C1C] transition-colors"
        >
          ← {backLabel}
        </button>
      ) : (
        <span />
      )}
      <PrimaryButton onClick={onNext} disabled={nextDisabled}>
        {nextLabel} →
      </PrimaryButton>
    </div>
  )
}

const STATUS_MAP: Record<Status, { label: string, icon: string, cls: string }> = {
  own: { label: "Already Own", icon: "✓", cls: "text-[#556B2F] bg-[#E8EDE0]" },
  buy: {
    label: "Recommended Purchase",
    icon: "◆",
    cls: "text-amber-700 bg-amber-50",
  },
  optional: {
    label: "Optional",
    icon: "○",
    cls: "text-[#8C8A82] bg-[#F0EFEA] border border-[#E2E0D8]",
  },
}

export function StatusBadge({
  status,
  dark,
}: {
  status: Status
  dark?: boolean
}) {
  const s = STATUS_MAP[status]
  const cls = dark
    ? status === "own"
      ? "text-[#8FA968] bg-[#556B2F]/25"
      : status === "buy"
        ? "text-amber-300 bg-amber-400/15"
        : "text-white/50 bg-white/10 border border-white/15"
    : s.cls
  return (
    <span
      className={`inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full whitespace-nowrap ${cls}`}
    >
      <span aria-hidden>{s.icon}</span>
      {s.label}
    </span>
  )
}

export function PackedToggle({
  packed,
  onToggle,
}: {
  packed: boolean
  onToggle: () => void
}) {
  return (
    <button
      onClick={onToggle}
      className={`shrink-0 min-w-[104px] text-center text-[11px] font-semibold px-3 py-1.5 rounded-lg border transition-colors ${
        packed
          ? "bg-[#556B2F] border-[#556B2F] text-white"
          : "bg-white border-[#E2E0D8] text-[#8C8A82] hover:border-[#556B2F] hover:text-[#556B2F]"
      }`}
    >
      {packed ? "✓ Packed" : "Mark packed"}
    </button>
  )
}

export function Stars({ value }: { value: number }) {
  return (
    <span className="text-[#556B2F] text-sm tracking-wide">
      {"★".repeat(value)}
      <span className="text-[#E2E0D8]">{"★".repeat(5 - value)}</span>
    </span>
  )
}

export function DownArrow({ label }: { label?: string }) {
  return (
    <div className="flex items-center gap-3 my-2">
      <span className="text-[#8C8A82] text-lg leading-none">↓</span>
      {label && <span className="text-xs text-[#8C8A82]">{label}</span>}
      <span className="h-px flex-1 bg-[#E2E0D8]" />
    </div>
  )
}

export function Stepper({
  step,
  onGo,
  onOpenAgents,
}: {
  step: Step
  onGo: (s: Step) => void
  onOpenAgents: () => void
}) {
  const idx = STEP_FLOW.indexOf(step)
  const current = idx === -1 ? STEP_FLOW.length : idx
  return (
    <div className="flex items-center gap-1.5 bg-[#F0EFEA] border border-[#E2E0D8] rounded-xl px-4 py-3">
      {STEP_FLOW.map((s, i) => {
        const done = current > -1 && i < current
        const active = i === current
        return (
          <div key={s} className="flex items-center gap-1.5 flex-1 min-w-0">
            {i > 0 && <span className="h-px flex-1 bg-[#D9D7CE] min-w-2" />}
            <button
              onClick={() => done && onGo(s)}
              disabled={!done}
              className={`flex items-center gap-1.5 shrink-0 rounded px-1 py-0.5 transition-colors ${
                active
                  ? "text-[#1C1C1C]"
                  : done
                    ? "text-[#556B2F] hover:text-[#1C1C1C] cursor-pointer"
                    : "text-[#8C8A82]/60 cursor-default"
              }`}
            >
              <span
                className={`w-4 h-4 rounded-full flex items-center justify-center text-[9px] font-bold ${
                  active
                    ? "bg-[#556B2F] text-white"
                    : done
                      ? "bg-[#556B2F]/15 text-[#556B2F]"
                      : "bg-[#E2E0D8] text-[#8C8A82]"
                }`}
              >
                {done ? "✓" : i + 1}
              </span>
              <span className="text-[11px] font-semibold uppercase tracking-wide whitespace-nowrap">
                {STEP_LABELS[s]}
              </span>
            </button>
          </div>
        )
      })}
      <button
        onClick={onOpenAgents}
        className="ml-3 shrink-0 text-[11px] font-semibold text-[#8C8A82] hover:text-[#556B2F] border border-[#E2E0D8] hover:border-[#556B2F] rounded-lg px-3 py-1.5 transition-colors"
        title="Technical view of the agent exchange"
      >
        ◇ Agent Activity
      </button>
    </div>
  )
}
