import type { DetailTargets } from "./avatarApi"

export type DetailControl = {
  key: string
  label: string
  hint: string
  incr: string
  decr: string
}

export const DETAIL_CONTROLS: DetailControl[] = [
  {
    key: "shoulders",
    label: "Shoulder width",
    hint: "Narrower ↔ broader shoulders",
    incr: "measure-shoulder-dist-incr",
    decr: "measure-shoulder-dist-decr",
  },
  {
    key: "bust",
    label: "Bust",
    hint: "Smaller ↔ larger bust",
    incr: "measure-bust-circ-incr",
    decr: "measure-bust-circ-decr",
  },
  {
    key: "underbust",
    label: "Underbust",
    hint: "Tighter ↔ wider ribcage",
    incr: "measure-underbust-circ-incr",
    decr: "measure-underbust-circ-decr",
  },
  {
    key: "waist",
    label: "Waist",
    hint: "Narrower ↔ wider waist",
    incr: "measure-waist-circ-incr",
    decr: "measure-waist-circ-decr",
  },
  {
    key: "hips",
    label: "Hips",
    hint: "Narrower ↔ wider hips",
    incr: "measure-hips-circ-incr",
    decr: "measure-hips-circ-decr",
  },
  {
    key: "waistToHip",
    label: "Waist-to-hip",
    hint: "Lower ↔ higher waist-to-hip distance",
    incr: "measure-waisttohip-dist-incr",
    decr: "measure-waisttohip-dist-decr",
  },
  {
    key: "chestDepth",
    label: "Chest depth",
    hint: "Shallower ↔ deeper chest",
    incr: "measure-frontchest-dist-incr",
    decr: "measure-frontchest-dist-decr",
  },
  {
    key: "torsoDepth",
    label: "Torso depth",
    hint: "Thinner ↔ thicker front-to-back torso",
    incr: "torso-scale-depth-incr",
    decr: "torso-scale-depth-decr",
  },
  {
    key: "vShape",
    label: "Torso V-shape",
    hint: "Straighter ↔ stronger V-taper",
    incr: "torso-vshape-incr",
    decr: "torso-vshape-decr",
  },
  {
    key: "hipWidth",
    label: "Hip width",
    hint: "Narrower ↔ wider hip bones",
    incr: "hip-scale-horiz-incr",
    decr: "hip-scale-horiz-decr",
  },
  {
    key: "hipDepth",
    label: "Hip depth",
    hint: "Shallower ↔ deeper hips",
    incr: "hip-scale-depth-incr",
    decr: "hip-scale-depth-decr",
  },
  {
    key: "belly",
    label: "Belly",
    hint: "Flatter ↔ more projected belly",
    incr: "stomach-navel-out",
    decr: "stomach-navel-in",
  },
  {
    key: "buttocks",
    label: "Buttocks",
    hint: "Flatter ↔ fuller buttocks",
    incr: "buttocks-volume-incr",
    decr: "buttocks-volume-decr",
  },
  {
    key: "upperArm",
    label: "Upper arm",
    hint: "Thinner ↔ thicker upper arms",
    incr: "measure-upperarm-circ-incr",
    decr: "measure-upperarm-circ-decr",
  },
  {
    key: "armLength",
    label: "Arm length",
    hint: "Shorter ↔ longer upper arms",
    incr: "measure-upperarm-length-incr",
    decr: "measure-upperarm-length-decr",
  },
  {
    key: "thigh",
    label: "Thigh",
    hint: "Thinner ↔ thicker thighs",
    incr: "measure-thigh-circ-incr",
    decr: "measure-thigh-circ-decr",
  },
  {
    key: "calf",
    label: "Calf",
    hint: "Thinner ↔ thicker calves",
    incr: "measure-calf-circ-incr",
    decr: "measure-calf-circ-decr",
  },
  {
    key: "upperLegHeight",
    label: "Upper leg length",
    hint: "Shorter ↔ longer upper legs",
    incr: "measure-upperleg-height-incr",
    decr: "measure-upperleg-height-decr",
  },
  {
    key: "lowerLegHeight",
    label: "Lower leg length",
    hint: "Shorter ↔ longer lower legs",
    incr: "measure-lowerleg-height-incr",
    decr: "measure-lowerleg-height-decr",
  },
]

export type DetailValues = Record<string, number>

export function detailValuesToTargets(values: DetailValues): DetailTargets {
  const targets: DetailTargets = {}
  for (const control of DETAIL_CONTROLS) {
    const raw = values[control.key] ?? 0
    const magnitude = Math.min(1, Math.abs(raw))
    if (magnitude < 0.01) continue
    targets[raw > 0 ? control.incr : control.decr] = Math.round(magnitude * 100) / 100
  }
  return targets
}

export function detailTargetsToValues(targets: DetailTargets): DetailValues {
  const values: DetailValues = {}
  for (const control of DETAIL_CONTROLS) {
    const incr = targets[control.incr] ?? 0
    const decr = targets[control.decr] ?? 0
    const value = Math.max(-1, Math.min(1, incr - decr))
    if (Math.abs(value) >= 0.01) values[control.key] = Math.round(value * 100) / 100
  }
  return values
}

export function countActiveDetails(values: DetailValues): number {
  return Object.values(values).filter((value) => Math.abs(value) >= 0.01).length
}
