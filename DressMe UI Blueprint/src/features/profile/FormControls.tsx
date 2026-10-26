import type {
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
} from "react"
import type { ColorOption, Option } from "./options"

export function Spinner({ size = 18 }: { size?: number }) {
  return (
    <span
      className="inline-block animate-spin rounded-full border-2 border-current border-t-transparent"
      style={{ width: size, height: size }}
      aria-hidden="true"
    />
  )
}

export function FullScreenLoader({
  label = "Loading your profile…",
}: {
  label?: string
}) {
  return (
    <div className="flex h-screen items-center justify-center bg-[#FAF9F6]">
      <div className="flex flex-col items-center gap-4 text-[#556B2F]">
        <Spinner size={28} />
        <p className="text-sm text-[#8C8A82]">{label}</p>
      </div>
    </div>
  )
}

export function Alert({
  tone = "error",
  children,
}: {
  tone?: "error" | "success" | "info"
  children: ReactNode
}) {
  const palette = {
    error: "border-red-200 bg-red-50 text-red-700",
    success: "border-[#556B2F]/20 bg-[#E8EDE0] text-[#3F5122]",
    info: "border-[#E2E0D8] bg-[#F0EFEA] text-[#6E6C64]",
  }[tone]

  return (
    <div
      className={`rounded-lg border px-4 py-3 text-sm leading-relaxed ${palette}`}
      role={tone === "error" ? "alert" : "status"}
    >
      {children}
    </div>
  )
}

export function Field({
  label,
  hint,
  error,
  children,
}: {
  label: string
  hint?: string
  error?: string
  children: ReactNode
}) {
  return (
    <label className="block">
      <span className="mb-2 block text-[11px] font-semibold uppercase tracking-widest text-[#8C8A82]">
        {label}
      </span>
      {children}
      {error ? (
        <span className="mt-1 block text-xs text-red-600">{error}</span>
      ) : hint ? (
        <span className="mt-1 block text-xs text-[#8C8A82]">{hint}</span>
      ) : null}
    </label>
  )
}

export function TextInput(props: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={`w-full rounded-lg border border-[#E2E0D8] bg-white px-4 py-3 text-sm text-[#1C1C1C] outline-none transition-colors placeholder:text-[#8C8A82]/70 focus:border-[#556B2F] disabled:bg-[#F0EFEA] disabled:text-[#8C8A82] ${props.className ?? ""}`}
    />
  )
}

export function SelectInput({
  options,
  ...props
}: SelectHTMLAttributes<HTMLSelectElement> & { options: Option[] }) {
  return (
    <select
      {...props}
      className={`w-full rounded-lg border border-[#E2E0D8] bg-white px-4 py-3 text-sm text-[#1C1C1C] outline-none transition-colors focus:border-[#556B2F] disabled:bg-[#F0EFEA] disabled:text-[#8C8A82] ${props.className ?? ""}`}
    >
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  )
}

export function MultiSelectChips({
  options,
  value,
  onChange,
  disabled,
}: {
  options: Option[]
  value: string[]
  onChange: (next: string[]) => void
  disabled?: boolean
}) {
  const toggle = (optionValue: string) => {
    if (disabled) return
    onChange(
      value.includes(optionValue)
        ? value.filter((item) => item !== optionValue)
        : [...value, optionValue],
    )
  }

  return (
    <div className="flex flex-wrap gap-2">
      {options.map((option) => {
        const selected = value.includes(option.value)
        return (
          <button
            key={option.value}
            type="button"
            aria-pressed={selected}
            disabled={disabled}
            onClick={() => toggle(option.value)}
            className={`rounded-full border px-3.5 py-2 text-xs font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
              selected
                ? "border-[#556B2F] bg-[#556B2F] text-white"
                : "border-[#E2E0D8] bg-white text-[#1C1C1C] hover:border-[#556B2F]"
            }`}
          >
            {option.label}
          </button>
        )
      })}
    </div>
  )
}

export function ColorMultiSelect({
  options,
  value,
  onChange,
  disabled,
}: {
  options: ColorOption[]
  value: string[]
  onChange: (next: string[]) => void
  disabled?: boolean
}) {
  const toggle = (optionValue: string) => {
    if (disabled) return
    onChange(
      value.includes(optionValue)
        ? value.filter((item) => item !== optionValue)
        : [...value, optionValue],
    )
  }

  return (
    <div className="flex flex-wrap gap-3">
      {options.map((option) => {
        const selected = value.includes(option.value)
        return (
          <button
            key={option.value}
            type="button"
            aria-pressed={selected}
            disabled={disabled}
            onClick={() => toggle(option.value)}
            className={`flex flex-col items-center gap-1 rounded-lg p-1.5 transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
              selected ? "bg-[#E8EDE0]" : "hover:bg-[#F0EFEA]"
            }`}
          >
            <span
              className={`h-8 w-8 rounded-full border ${
                selected
                  ? "border-[#556B2F] ring-2 ring-[#556B2F]/30"
                  : "border-[#E2E0D8]"
              }`}
              style={{ backgroundColor: option.hex }}
            />
            <span
              className={`text-[10px] ${
                selected ? "font-semibold text-[#556B2F]" : "text-[#8C8A82]"
              }`}
            >
              {option.label}
            </span>
          </button>
        )
      })}
    </div>
  )
}

export function SegmentedChoice({
  options,
  value,
  onChange,
  disabled,
}: {
  options: Option[]
  value: string
  onChange: (next: string) => void
  disabled?: boolean
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {options.map((option) => {
        const selected = value === option.value
        return (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={selected}
            disabled={disabled}
            onClick={() => onChange(option.value)}
            className={`rounded-lg border px-4 py-2.5 text-xs font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
              selected
                ? "border-[#1C1C1C] bg-[#1C1C1C] text-white"
                : "border-[#E2E0D8] bg-white text-[#1C1C1C] hover:border-[#556B2F]"
            }`}
          >
            {option.label}
          </button>
        )
      })}
    </div>
  )
}

export function SectionCard({
  title,
  description,
  children,
}: {
  title: string
  description?: string
  children: ReactNode
}) {
  return (
    <section className="rounded-xl bg-[#F0EFEA] p-6">
      <h3 className="font-display text-lg font-medium text-[#1C1C1C]">
        {title}
      </h3>
      {description && (
        <p className="mt-1 text-xs text-[#8C8A82]">{description}</p>
      )}
      <div className="mt-5 space-y-5">{children}</div>
    </section>
  )
}
