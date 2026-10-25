import { useState, type FormEvent } from "react"
import { Alert, Field, Spinner, TextInput } from "../profile/FormControls"
import {
  describeError,
  validateEmail,
  validatePassword,
} from "../profile/validation"
import { useAuth } from "./AuthProvider"

type Mode = "signin" | "signup"

export default function AuthScreen() {
  const { signIn, signUp } = useAuth()
  const [mode, setMode] = useState<Mode>("signin")
  const [fullName, setFullName] = useState("")
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const switchMode = (next: Mode) => {
    setMode(next)
    setError(null)
    setNotice(null)
  }

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (submitting) return

    setError(null)
    setNotice(null)

    try {
      const cleanEmail = validateEmail(email)
      const cleanPassword = validatePassword(password)

      if (mode === "signup" && !fullName.trim()) {
        throw new Error("Please enter your name.")
      }

      setSubmitting(true)

      if (mode === "signin") {
        await signIn(cleanEmail, cleanPassword)
      } else {
        const result = await signUp(cleanEmail, cleanPassword, fullName)
        if (result.needsEmailConfirmation) {
          setNotice("Check your inbox to confirm your email, then sign in.")
          setMode("signin")
          setPassword("")
        }
      }
    } catch (submitError) {
      setError(describeError(submitError))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="grid min-h-screen bg-[#FAF9F6] lg:grid-cols-[1.05fr_1fr]">
      <section className="relative hidden overflow-hidden bg-[#1C1C1C] px-12 py-14 lg:flex lg:flex-col lg:justify-between">
        <div className="absolute -right-24 top-24 h-72 w-72 rounded-full bg-[#556B2F]/30 blur-3xl" />
        <div className="absolute -bottom-20 left-10 h-64 w-64 rounded-full bg-[#C19A6B]/20 blur-3xl" />

        <div className="relative">
          <div className="flex items-baseline gap-1">
            <span className="font-display text-3xl font-semibold italic text-[#FAF9F6]">
              Dress
            </span>
            <span className="font-display text-3xl font-semibold text-[#8FA45C]">
              Me
            </span>
          </div>
          <p className="mt-1 text-[11px] uppercase tracking-[0.28em] text-white/30">
            AI Style Intelligence
          </p>
        </div>

        <div className="relative max-w-md">
          <p className="text-xs font-semibold uppercase tracking-widest text-[#8FA45C]">
            Your wardrobe, understood
          </p>
          <h1 className="mt-4 font-display text-4xl font-medium leading-tight text-white">
            Style decisions that start from what you already own.
          </h1>
          <p className="mt-4 text-sm leading-relaxed text-white/50">
            Save your fit, colours and occasions once. DressMe uses them to
            build outfits, packing lists and purchase advice that actually fit
            your life.
          </p>
        </div>

        <div className="relative grid grid-cols-3 gap-3 text-white/60">
          {[
            "Wardrobe intelligence",
            "Personal preferences",
            "Private by design",
          ].map((item) => (
            <div
              key={item}
              className="rounded-lg border border-white/10 bg-white/5 px-3 py-3 text-[11px]"
            >
              {item}
            </div>
          ))}
        </div>
      </section>

      <section className="flex items-center justify-center px-6 py-12 sm:px-10">
        <div className="w-full max-w-md">
          <div className="mb-8 lg:hidden">
            <div className="flex items-baseline gap-1">
              <span className="font-display text-2xl font-semibold italic text-[#1C1C1C]">
                Dress
              </span>
              <span className="font-display text-2xl font-semibold text-[#556B2F]">
                Me
              </span>
            </div>
          </div>

          <p className="text-xs font-semibold uppercase tracking-widest text-[#8C8A82]">
            {mode === "signin" ? "Welcome back" : "Create your account"}
          </p>
          <h2 className="mt-2 font-display text-3xl font-semibold text-[#1C1C1C]">
            {mode === "signin"
              ? "Sign in to DressMe"
              : "Start your style profile"}
          </h2>
          <p className="mt-2 text-sm text-[#8C8A82]">
            {mode === "signin"
              ? "Your saved profile and preferences will be restored."
              : "A few details now, better recommendations every day."}
          </p>

          <div className="mt-7 flex rounded-lg bg-[#F0EFEA] p-1">
            {([
              { value: "signin", label: "Sign in" },
              { value: "signup", label: "Sign up" },
            ] as const).map((tab) => (
              <button
                key={tab.value}
                type="button"
                onClick={() => switchMode(tab.value)}
                className={`flex-1 rounded-md px-4 py-2 text-sm font-semibold transition-colors ${
                  mode === tab.value
                    ? "bg-white text-[#1C1C1C] shadow-sm"
                    : "text-[#8C8A82] hover:text-[#1C1C1C]"
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          <form className="mt-6 space-y-5" onSubmit={onSubmit} noValidate>
            {mode === "signup" && (
              <Field label="Full name">
                <TextInput
                  value={fullName}
                  onChange={(event) => setFullName(event.target.value)}
                  autoComplete="name"
                  placeholder="Your name"
                  disabled={submitting}
                />
              </Field>
            )}

            <Field label="Email">
              <TextInput
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                autoComplete="email"
                placeholder="you@example.com"
                disabled={submitting}
              />
            </Field>

            <Field
              label="Password"
              hint={mode === "signup" ? "At least 8 characters." : undefined}
            >
              <TextInput
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                autoComplete={
                  mode === "signin" ? "current-password" : "new-password"
                }
                placeholder="••••••••"
                disabled={submitting}
              />
            </Field>

            {error && <Alert>{error}</Alert>}
            {notice && <Alert tone="success">{notice}</Alert>}

            <button
              type="submit"
              disabled={submitting}
              className="flex w-full items-center justify-center gap-2 rounded-lg bg-[#556B2F] px-5 py-3.5 text-sm font-semibold text-white transition-colors hover:bg-[#6B8A3A] disabled:cursor-not-allowed disabled:opacity-60"
            >
              {submitting && <Spinner size={16} />}
              {submitting
                ? mode === "signin"
                  ? "Signing in…"
                  : "Creating account…"
                : mode === "signin"
                  ? "Sign in"
                  : "Create account"}
            </button>
          </form>

          <p className="mt-6 text-center text-xs leading-relaxed text-[#8C8A82]">
            Your profile is stored privately in your DressMe account and
            protected by row-level security.
          </p>
        </div>
      </section>
    </div>
  )
}
