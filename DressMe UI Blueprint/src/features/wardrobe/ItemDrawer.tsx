import { useEffect, useMemo, useState } from "react"
import { api, asset } from "../../lib/api"
import { COLORS, TAXONOMY, cap } from "../../lib/taxonomy"
import type { Health, ItemMeshStatus, WardrobeItem } from "../../lib/types"
import Item3DPreview from "./Item3DPreview"

interface ItemDrawerProps {
  item: WardrobeItem
  health: Health | null
  onClose: () => void
  onSave: (id: string, fields: Record<string, unknown>, confirm?: boolean) => Promise<unknown>
  onReclassify: (id: string) => Promise<unknown>
  onDelete: (id: string) => Promise<void>
  onMeshUpdated?: () => void
  onItemUpdated?: () => void
}

interface FormState {
  name: string
  category: string
  color_name: string
  color_hex: string
  color_family: string
  pattern: string
  seasons: string[]
  style: string
  occasions: string[]
  material: string
  description: string
  warmth: string
  formality: string
  tags: string
}

const emptyForm = (item: WardrobeItem): FormState => ({
  name: item.name ?? "",
  category: item.category ?? "top",
  color_name: item.color_name ?? "",
  color_hex: item.color_hex ?? "#8a8a8a",
  color_family: item.color_family ?? "neutral",
  pattern: item.pattern ?? "solid",
  seasons: item.seasons ?? [],
  style: item.style ?? "casual",
  occasions: item.occasions ?? [],
  material: item.material ?? "",
  description: item.description ?? "",
  warmth: item.warmth == null ? "" : String(item.warmth),
  formality: item.formality == null ? "" : String(item.formality),
  tags: (item.tags ?? []).join(", "),
})

function MultiChips({
  options,
  value,
  onChange,
}: {
  options: string[]
  value: string[]
  onChange: (next: string[]) => void
}) {
  const toggle = (option: string) => {
    onChange(value.includes(option) ? value.filter((entry) => entry !== option) : [...value, option])
  }
  return (
    <div className="flex flex-wrap gap-2">
      {options.map((option) => {
        const active = value.includes(option)
        return (
          <button
            key={option}
            type="button"
            onClick={() => toggle(option)}
            className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
              active
                ? "border-[#556B2F] bg-[#556B2F] text-white"
                : "border-[#E2E0D8] bg-white text-[#1C1C1C] hover:border-[#556B2F]"
            }`}
          >
            {cap(option)}
          </button>
        )
      })}
    </div>
  )
}

export default function ItemDrawer({
  item,
  health,
  onClose,
  onSave,
  onReclassify,
  onDelete,
  onMeshUpdated,
  onItemUpdated,
}: ItemDrawerProps) {
  const [form, setForm] = useState<FormState>(() => emptyForm(item))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const [backPhoto, setBackPhoto] = useState<File | null>(null)
  const [backPreview, setBackPreview] = useState<string | null>(item.back_photo_url ? asset(item.back_photo_url) : null)
  const [pendingProvider, setPendingProvider] = useState<string | null>(null)
  const [mesh, setMesh] = useState<ItemMeshStatus>({
    mesh_url: item.mesh_url ?? null,
    mesh_status: (item.mesh_status as ItemMeshStatus["mesh_status"]) ?? (item.mesh_url ? "ready" : "none"),
    mesh_source: item.mesh_source ?? null,
    mesh_version: item.mesh_version ?? 0,
    mesh_meta: item.mesh_meta ?? null,
    mesh_error: item.mesh_error ?? null,
  })

  useEffect(() => {
    setForm(emptyForm(item))
    setMesh({
      mesh_url: item.mesh_url ?? null,
      mesh_status: (item.mesh_status as ItemMeshStatus["mesh_status"]) ?? (item.mesh_url ? "ready" : "none"),
      mesh_source: item.mesh_source ?? null,
      mesh_version: item.mesh_version ?? 0,
      mesh_meta: item.mesh_meta ?? null,
      mesh_error: item.mesh_error ?? null,
    })
    setBackPhoto(null)
    setBackPreview(item.back_photo_url ? asset(item.back_photo_url) : null)
  }, [item])

  useEffect(() => {
    if (mesh.mesh_status !== "queued" && mesh.mesh_status !== "building") return
    let active = true
    const timer = window.setInterval(() => {
      api
        .itemMesh(item.id)
        .then((next) => {
          if (!active) return
          setMesh((previous) => {
            if (next.mesh_status === "ready" && previous.mesh_status !== "ready") {
              onMeshUpdated?.()
            }
            return next
          })
        })
        .catch(() => {
          // keep polling; the backend may still be starting
        })
    }, 1800)
    return () => {
      active = false
      window.clearInterval(timer)
    }
  }, [item.id, mesh.mesh_status, onMeshUpdated])

  const original = useMemo(() => emptyForm(item), [item])
  const changed = useMemo(() => {
    const entries: [string, unknown][] = []
    for (const key of Object.keys(form) as (keyof FormState)[]) {
      if (JSON.stringify(form[key]) !== JSON.stringify(original[key])) {
        entries.push([key, form[key]])
      }
    }
    return entries
  }, [form, original])

  const update = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setForm((previous) => ({ ...previous, [key]: value }))
  }

  const run = async (action: () => Promise<unknown>) => {
    setBusy(true)
    setError("")
    try {
      await action()
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : "Something went wrong.")
    } finally {
      setBusy(false)
    }
  }

  const save = (fields: Record<string, unknown>) => run(() => onSave(item.id, fields))

  const uploadBackPhoto = () => {
    if (!backPhoto) return
    return run(async () => {
      await api.uploadBackPhoto(item.id, backPhoto)
      setBackPhoto(null)
      onItemUpdated?.()
    })
  }

  const buildMesh = (provider?: string) => {
    setPendingProvider(provider || health?.mesh_provider || "cutout-2.5d")
    return run(async () => {
      const next = await api.generateItemMesh(item.id, true, provider)
      setMesh(next)
      if (next.mesh_status === "ready") onMeshUpdated?.()
    }).finally(() => setPendingProvider(null))
  }

  const aiAvailable = health?.mesh_providers?.includes("hunyuan3d") ?? false
  const isBuilding = mesh.mesh_status === "queued" || mesh.mesh_status === "building"

  const remove = async () => {
    if (!window.confirm("Delete this item?")) return
    setBusy(true)
    setError("")
    try {
      await onDelete(item.id)
      onClose()
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : "Could not delete this item.")
    } finally {
      setBusy(false)
    }
  }

  const serialize = (entries: [string, unknown][]) =>
    Object.fromEntries(
      entries.map(([key, value]) => {
        if (key === "tags") {
          return [
            key,
            String(value)
              .split(",")
              .map((tag) => tag.trim())
              .filter(Boolean),
          ]
        }
        if (key === "warmth" || key === "formality") {
          return [key, value === "" ? null : Number(value)]
        }
        return [key, value]
      }),
    )

  const confidence = item.field_confidence ?? {}
  const primaryConfidence = item.confidence

  return (
    <div className="fixed inset-0 z-[70] flex justify-end bg-black/30" onClick={onClose}>
      <aside
        className="h-full w-full max-w-md overflow-y-auto bg-[#FAF9F6] shadow-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-[#E2E0D8] bg-[#FAF9F6]/95 px-5 py-4 backdrop-blur">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-widest text-[#8C8A82]">
              Item details
            </p>
            <p className="text-sm font-medium text-[#1C1C1C]">
              {item.category_group}
              {primaryConfidence != null ? ` - ${Math.round(primaryConfidence * 100)}% sure` : ""}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-[#E2E0D8] px-3 py-1.5 text-xs font-semibold text-[#1C1C1C] hover:bg-[#F0EFEA]"
          >
            Close
          </button>
        </div>

        <div className="space-y-5 p-5">
          {item.cutout_url ? (
            <div className="flex aspect-[4/5] items-center justify-center overflow-hidden rounded-xl bg-[#F0EFEA]">
              <img src={asset(item.cutout_url)} alt={item.name} className="h-full w-full object-contain" />
            </div>
          ) : (
            <div className="flex aspect-[4/5] items-center justify-center rounded-xl bg-[#F0EFEA] text-sm text-[#8C8A82]">
              No image
            </div>
          )}
          <div className="space-y-2 rounded-xl border border-[#E2E0D8] bg-white p-3">
            <div>
              <p className="text-xs font-semibold text-[#1C1C1C]">Back photo for Try-On</p>
              <p className="mt-1 text-[11px] text-[#8C8A82]">
                Optional. The photo is applied to the back of this garment on the avatar.
              </p>
            </div>
            {backPreview && (
              <img src={backPreview} alt={`${item.name} back`} className="h-40 w-full rounded-lg bg-[#F0EFEA] object-contain" />
            )}
            <input
              type="file"
              accept="image/*"
              onChange={(event) => {
                const file = event.target.files?.[0] ?? null
                setBackPhoto(file)
                if (file) setBackPreview(URL.createObjectURL(file))
                event.target.value = ""
              }}
              className="block w-full text-xs text-[#8C8A82] file:mr-2 file:rounded-lg file:border-0 file:bg-[#E8EDE0] file:px-3 file:py-2 file:text-xs file:font-semibold file:text-[#556B2F]"
            />
            {backPhoto && (
              <button
                type="button"
                onClick={() => void uploadBackPhoto()}
                disabled={busy}
                className="w-full rounded-lg bg-[#556B2F] px-3 py-2 text-xs font-semibold text-white hover:bg-[#6B8A3A] disabled:opacity-50"
              >
                {busy ? "Uploading..." : "Save back photo"}
              </button>
            )}
          </div>

          {mesh.mesh_status === "ready" && mesh.mesh_url ? (
            <div className="space-y-2">
              <Item3DPreview
                url={`${mesh.mesh_url}${mesh.mesh_url.includes("?") ? "&" : "?"}v=${mesh.mesh_version}`}
              />
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="flex items-center gap-1.5 text-[11px] text-[#8C8A82]">
                  <span className="rounded-full bg-[#E8EDE0] px-2 py-0.5 font-semibold uppercase tracking-wide text-[#556B2F]">
                    {mesh.mesh_source?.startsWith("hunyuan3d") ? "Hunyuan3D" : "2.5D"}
                  </span>
                  Generated from this item’s cutout.
                </span>
                <span className="flex gap-2">
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void buildMesh()}
                    className="text-[11px] font-semibold text-[#556B2F] hover:underline disabled:opacity-40"
                  >
                    Rebuild
                  </button>
                  {aiAvailable && (
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => void buildMesh("hunyuan3d")}
                      className="text-[11px] font-semibold text-[#7A5B1E] hover:underline disabled:opacity-40"
                    >
                      AI rebuild
                    </button>
                  )}
                </span>
              </div>
              {typeof mesh.mesh_meta?.fallback_reason === "string" && (
                <p className="text-[10px] text-[#7A5B1E]">
                  AI 3D failed, so this uses the fast mesh:{" "}
                  {String(mesh.mesh_meta.fallback_reason).slice(0, 180)}
                </p>
              )}
            </div>
          ) : (
            <div className="rounded-xl border border-dashed border-[#E2E0D8] bg-white/60 px-4 py-4">
              <p className="text-xs font-semibold text-[#1C1C1C]">3D model</p>
              <p className="mt-1 text-[11px] text-[#8C8A82]">
                {isBuilding
                  ? pendingProvider === "hunyuan3d"
                    ? "Hunyuan3D is reconstructing the mesh from the cutout… (~1–2 minutes)"
                    : "Building a 3D version of this item from its cutout…"
                  : mesh.mesh_status === "failed"
                    ? mesh.mesh_error || "The 3D model could not be built."
                    : "Turn this cutout into a 3D item for the wardrobe view."}
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                <button
                  type="button"
                  disabled={busy || isBuilding}
                  onClick={() => void buildMesh()}
                  className="rounded-lg bg-[#556B2F] px-3 py-2 text-xs font-semibold text-white transition-colors hover:bg-[#6B8A3A] disabled:cursor-not-allowed disabled:opacity-40"
                >
                  {isBuilding ? "Building 3D…" : "Create 3D model"}
                </button>
                {aiAvailable && (
                  <button
                    type="button"
                    disabled={busy || isBuilding}
                    onClick={() => void buildMesh("hunyuan3d")}
                    className="rounded-lg border border-[#D8C9A8] bg-[#F5EDDC] px-3 py-2 text-xs font-semibold text-[#7A5B1E] transition-colors hover:bg-[#EFE3C8] disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    {isBuilding && pendingProvider === "hunyuan3d"
                      ? "Hunyuan3D working…"
                      : "Generate AI 3D"}
                  </button>
                )}
              </div>
              {aiAvailable && (
                <p className="mt-2 text-[10px] text-[#8C8A82]">
                  AI 3D uses Hunyuan3D-2.1 through Hugging Face and takes about 1–2 minutes per item.
                </p>
              )}
            </div>
          )}

          {item.needs_review && (
            <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
              The detector is not fully sure about this item. Check the category, then confirm or
              correct it.
            </div>
          )}
          {item.status === "confirmed" && (
            <div className="rounded-xl border border-[#556B2F]/20 bg-[#E8EDE0] px-4 py-3 text-sm text-[#556B2F]">
              Confirmed by you
            </div>
          )}

          <label className="block">
            <span className="mb-1.5 block text-xs font-semibold uppercase tracking-widest text-[#8C8A82]">
              Name
            </span>
            <input
              value={form.name}
              onChange={(event) => update("name", event.target.value)}
              className="w-full rounded-lg border border-[#E2E0D8] bg-white px-3 py-2.5 text-sm text-[#1C1C1C] outline-none focus:border-[#556B2F]"
            />
          </label>

          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className="mb-1.5 block text-xs font-semibold uppercase tracking-widest text-[#8C8A82]">
                Category
              </span>
              <select
                value={form.category}
                onChange={(event) => update("category", event.target.value)}
                className="w-full rounded-lg border border-[#E2E0D8] bg-white px-3 py-2.5 text-sm capitalize text-[#1C1C1C] outline-none focus:border-[#556B2F]"
              >
                {TAXONOMY.groups.map((group) => (
                  <optgroup key={group} label={group}>
                    {TAXONOMY.classes
                      .filter((entry) => TAXONOMY.class_to_group[entry] === group)
                      .map((entry) => (
                        <option key={entry} value={entry}>
                          {cap(entry)}
                        </option>
                      ))}
                  </optgroup>
                ))}
              </select>
            </label>

            <label className="block">
              <span className="mb-1.5 block text-xs font-semibold uppercase tracking-widest text-[#8C8A82]">
                Pattern
              </span>
              <select
                value={form.pattern}
                onChange={(event) => update("pattern", event.target.value)}
                className="w-full rounded-lg border border-[#E2E0D8] bg-white px-3 py-2.5 text-sm text-[#1C1C1C] outline-none focus:border-[#556B2F]"
              >
                {TAXONOMY.patterns.map((option) => (
                  <option key={option} value={option}>
                    {cap(option)}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className="mb-1.5 block text-xs font-semibold uppercase tracking-widest text-[#8C8A82]">
                Colour
                {confidence.color != null ? ` - ${Math.round(confidence.color * 100)}%` : ""}
              </span>
              <div className="flex items-center gap-2">
                <span
                  className="h-8 w-8 shrink-0 rounded-full border border-[#E2E0D8]"
                  style={{ backgroundColor: form.color_hex }}
                />
                <select
                  value={form.color_name}
                  onChange={(event) => {
                    const name = event.target.value
                    setForm((previous) => ({
                      ...previous,
                      color_name: name,
                      color_hex: COLORS[name] ?? previous.color_hex,
                    }))
                  }}
                  className="w-full rounded-lg border border-[#E2E0D8] bg-white px-3 py-2.5 text-sm text-[#1C1C1C] outline-none focus:border-[#556B2F]"
                >
                  {!COLORS[form.color_name] && (
                    <option value={form.color_name}>{cap(form.color_name)}</option>
                  )}
                  {Object.keys(COLORS).map((name) => (
                    <option key={name} value={name}>
                      {cap(name)}
                    </option>
                  ))}
                </select>
              </div>
            </label>

            <label className="block">
              <span className="mb-1.5 block text-xs font-semibold uppercase tracking-widest text-[#8C8A82]">
                Colour family
              </span>
              <select
                value={form.color_family}
                onChange={(event) => update("color_family", event.target.value)}
                className="w-full rounded-lg border border-[#E2E0D8] bg-white px-3 py-2.5 text-sm text-[#1C1C1C] outline-none focus:border-[#556B2F]"
              >
                {TAXONOMY.colorFamilies.map((option) => (
                  <option key={option} value={option}>
                    {cap(option)}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className="mb-1.5 block text-xs font-semibold uppercase tracking-widest text-[#8C8A82]">
                Style
              </span>
              <select
                value={form.style}
                onChange={(event) => update("style", event.target.value)}
                className="w-full rounded-lg border border-[#E2E0D8] bg-white px-3 py-2.5 text-sm text-[#1C1C1C] outline-none focus:border-[#556B2F]"
              >
                {TAXONOMY.styles.map((option) => (
                  <option key={option} value={option}>
                    {cap(option)}
                  </option>
                ))}
              </select>
            </label>

            <label className="block">
              <span className="mb-1.5 block text-xs font-semibold uppercase tracking-widest text-[#8C8A82]">
                Material
              </span>
              <input
                value={form.material}
                onChange={(event) => update("material", event.target.value)}
                className="w-full rounded-lg border border-[#E2E0D8] bg-white px-3 py-2.5 text-sm text-[#1C1C1C] outline-none focus:border-[#556B2F]"
              />
            </label>
          </div>

          <div>
            <span className="mb-2 block text-xs font-semibold uppercase tracking-widest text-[#8C8A82]">
              Seasons
            </span>
            <MultiChips
              options={TAXONOMY.seasons}
              value={form.seasons}
              onChange={(next) => update("seasons", next)}
            />
          </div>

          <div>
            <span className="mb-2 block text-xs font-semibold uppercase tracking-widest text-[#8C8A82]">
              Occasions
            </span>
            <MultiChips
              options={TAXONOMY.occasions}
              value={form.occasions}
              onChange={(next) => update("occasions", next)}
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className="mb-1.5 block text-xs font-semibold uppercase tracking-widest text-[#8C8A82]">
                Warmth (1-5)
              </span>
              <input
                type="number"
                min={1}
                max={5}
                value={form.warmth}
                onChange={(event) => update("warmth", event.target.value)}
                className="w-full rounded-lg border border-[#E2E0D8] bg-white px-3 py-2.5 text-sm text-[#1C1C1C] outline-none focus:border-[#556B2F]"
              />
            </label>
            <label className="block">
              <span className="mb-1.5 block text-xs font-semibold uppercase tracking-widest text-[#8C8A82]">
                Formality (1-5)
              </span>
              <input
                type="number"
                min={1}
                max={5}
                value={form.formality}
                onChange={(event) => update("formality", event.target.value)}
                className="w-full rounded-lg border border-[#E2E0D8] bg-white px-3 py-2.5 text-sm text-[#1C1C1C] outline-none focus:border-[#556B2F]"
              />
            </label>
          </div>

          <label className="block">
            <span className="mb-1.5 block text-xs font-semibold uppercase tracking-widest text-[#8C8A82]">
              Description
            </span>
            <textarea
              rows={3}
              value={form.description}
              onChange={(event) => update("description", event.target.value)}
              className="w-full resize-y rounded-lg border border-[#E2E0D8] bg-white px-3 py-2.5 text-sm text-[#1C1C1C] outline-none focus:border-[#556B2F]"
            />
          </label>

          <label className="block">
            <span className="mb-1.5 block text-xs font-semibold uppercase tracking-widest text-[#8C8A82]">
              Tags (comma separated)
            </span>
            <input
              value={form.tags}
              onChange={(event) => update("tags", event.target.value)}
              className="w-full rounded-lg border border-[#E2E0D8] bg-white px-3 py-2.5 text-sm text-[#1C1C1C] outline-none focus:border-[#556B2F]"
            />
          </label>

          {(item.styling_tips ?? []).length > 0 && (
            <div className="rounded-xl bg-[#F0EFEA] p-4">
              <p className="text-xs font-semibold uppercase tracking-widest text-[#8C8A82]">
                Styling tips
              </p>
              <ul className="mt-2 list-disc space-y-1 pl-4 text-sm text-[#1C1C1C]">
                {(item.styling_tips ?? []).map((tip) => (
                  <li key={tip}>{tip}</li>
                ))}
              </ul>
            </div>
          )}

          {error && (
            <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>
          )}

          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              disabled={busy || changed.length === 0}
              onClick={() => save(serialize(changed))}
              className="rounded-lg bg-[#556B2F] px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-[#6B8A3A] disabled:cursor-not-allowed disabled:opacity-40"
            >
              Save correction
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => save({})}
              className="rounded-lg border border-[#E2E0D8] bg-white px-4 py-2.5 text-sm font-semibold text-[#1C1C1C] transition-colors hover:bg-[#F0EFEA] disabled:opacity-40"
            >
              Looks right
            </button>
          </div>

          <div className="flex items-center justify-between border-t border-[#E2E0D8] pt-4 text-xs text-[#8C8A82]">
            <span>
              {item.enrichment_source
                ? `Classified by ${item.enrichment_source.replace(/^llm[-:]?/, "")}`
                : "Classification source unknown"}
            </span>
            <div className="flex gap-3">
              {health?.llm && (
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => run(() => onReclassify(item.id))}
                  className="font-semibold text-[#556B2F] hover:underline disabled:opacity-40"
                >
                  {busy ? "Working..." : "Re-run AI"}
                </button>
              )}
              <button
                type="button"
                disabled={busy}
                onClick={() => void remove()}
                className="font-semibold text-red-600 hover:underline disabled:opacity-40"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      </aside>
    </div>
  )
}
