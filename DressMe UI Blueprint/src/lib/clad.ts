import type { CladQuota } from "./avatarApi"

export type CladMeasurementRow = {
  key: string
  label: string
  unit: string
}

export const CLAD_MEASUREMENT_ROWS: CladMeasurementRow[] = [
  { key: "height_cm", label: "Height", unit: "cm" },
  { key: "bust_cm", label: "Bust", unit: "cm" },
  { key: "underbust_cm", label: "Underbust", unit: "cm" },
  { key: "waist_cm", label: "Waist", unit: "cm" },
  { key: "hip_cm", label: "Hip", unit: "cm" },
  { key: "shoulder_width_cm", label: "Shoulder width", unit: "cm" },
  { key: "inseam_cm", label: "Inseam", unit: "cm" },
  { key: "thigh_cm", label: "Thigh", unit: "cm" },
  { key: "upperarm_cm", label: "Upper arm", unit: "cm" },
  { key: "neck_cm", label: "Neck", unit: "cm" },
  { key: "calf_cm", label: "Calf", unit: "cm" },
  { key: "wrist_cm", label: "Wrist", unit: "cm" },
  { key: "mass_kg", label: "Mass", unit: "kg" },
  { key: "bmi", label: "BMI", unit: "" },
]

export function measurementRows(measurements: Record<string, number>) {
  return CLAD_MEASUREMENT_ROWS.filter((row) => Number.isFinite(measurements[row.key])).map(
    (row) => ({ ...row, value: measurements[row.key] }),
  )
}

export function quotaRemaining(quota: CladQuota | undefined, bucket: "photo" | "questionnaire"): number | null {
  const entry = quota?.[bucket]
  if (!entry) return null
  return Math.max(0, entry.limit - entry.used_this_week)
}

export const BODY_SHAPES = [
  { value: "hourglass", label: "Hourglass" },
  { value: "rectangle", label: "Rectangle" },
  { value: "inverted_triangle", label: "Inverted triangle" },
  { value: "pear", label: "Pear" },
  { value: "apple", label: "Apple" },
] as const

export const GENDERS = [
  { value: "female", label: "Female" },
  { value: "male", label: "Male" },
] as const

export const CUP_SIZES = ["A", "B", "C", "D", "E", "F"] as const
