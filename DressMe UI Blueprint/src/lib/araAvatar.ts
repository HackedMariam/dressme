import { AssetLibrary, fetchSource } from "@ara/core/assets"
import { buildHuman, type Character } from "@ara/core/human"
import { DEFAULT_PARAMS, type HumanParams } from "@ara/core/params"
import type { BodyTargets, DetailTargets } from "./avatarApi"
import type { TryOnItem } from "./tryon"

let libraryPromise: Promise<AssetLibrary> | null = null

function library(): Promise<AssetLibrary> {
  if (!libraryPromise) libraryPromise = new AssetLibrary(fetchSource("/ara-assets/")).init()
  return libraryPromise
}

function clamp(value: number): number {
  return Math.min(1, Math.max(0, value))
}

function detailModifier(details: DetailTargets, key: string): number {
  const controls: Record<string, [string, string]> = {
    shoulders: ["measure-shoulder-dist-incr", "measure-shoulder-dist-decr"],
    waist: ["measure-waist-circ-incr", "measure-waist-circ-decr"],
    hips: ["measure-hips-circ-incr", "measure-hips-circ-decr"],
    hipWidth: ["hip-scale-horiz-incr", "hip-scale-horiz-decr"],
    chestDepth: ["measure-frontchest-dist-incr", "measure-frontchest-dist-decr"],
    torsoDepth: ["torso-scale-depth-incr", "torso-scale-depth-decr"],
    belly: ["stomach-navel-out", "stomach-navel-in"],
    buttocks: ["buttocks-volume-incr", "buttocks-volume-decr"],
    upperArm: ["measure-upperarm-circ-incr", "measure-upperarm-circ-decr"],
    thigh: ["measure-thigh-circ-incr", "measure-thigh-circ-decr"],
    calf: ["measure-calf-circ-incr", "measure-calf-circ-decr"],
    armLength: ["measure-upperarm-length-incr", "measure-upperarm-length-decr"],
    upperLegHeight: ["measure-upperleg-height-incr", "measure-upperleg-height-decr"],
    lowerLegHeight: ["measure-lowerleg-height-incr", "measure-lowerleg-height-decr"],
  }
  const control = controls[key]
  if (!control) return 0
  const increase = Number(details[control[0]] ?? 0)
  const decrease = Number(details[control[1]] ?? 0)
  return (Number.isFinite(increase) ? increase : 0) - (Number.isFinite(decrease) ? decrease : 0)
}

function araGarmentId(template: string, slot: TryOnItem["slot"]): string {
  if (slot === "shoes") return "shoes01"
  if (slot === "outerwear") return "techwear_jacket"
  if (slot === "bottom") return template === "shorts" ? "cargo_shorts" : "trousers"
  if (slot === "dress") return "long_tunic"
  return template === "turtleneck" ? "tunic" : template === "oxford" ? "uniform_shirt" : "fatigue_shirt"
}

function araParams(
  targets: BodyTargets,
  details: DetailTargets,
  heightCm: number,
  selection: TryOnItem[],
): HumanParams {
  const top = selection.find((item) => item.slot === "top")
  const jacket = selection.find((item) => item.slot === "outerwear")
  const bottom = selection.find((item) => item.slot === "bottom")
  const shoes = selection.find((item) => item.slot === "shoes")
  const gender = clamp(targets.gender)
  const legLength = clamp(targets.legLength)
  const proportions = clamp(targets.proportions * 0.7 + legLength * 0.3)
  const detailModifiers: Record<string, number> = {}
  const modifierMap: Record<string, string> = {
    shoulders: "shoulder/shoulder-scale-horiz",
    waist: "torso/waist-scale-horiz",
    hips: "hip/hip-scale-horiz",
    hipWidth: "hip/hip-scale-horiz",
    chestDepth: "torso/torso-scale-depth",
    torsoDepth: "torso/torso-scale-depth",
    belly: "stomach/stomach-navel-out",
    buttocks: "buttocks/buttocks-volume",
    upperArm: "upperarm/upperarm-scale",
    thigh: "thigh/thigh-scale",
    calf: "calf/calf-scale",
    armLength: "upperarm/upperarm-length",
    upperLegHeight: "upperleg/upperleg-height",
    lowerLegHeight: "lowerleg/lowerleg-height",
  }
  for (const [source, target] of Object.entries(modifierMap)) {
    const value = detailModifier(details, source)
    if (Math.abs(value) > 0.01) detailModifiers[target] = value
  }
  const topId = top ? araGarmentId(top.templateId, top.slot) : "none"
  const bottomId = bottom ? araGarmentId(bottom.templateId, bottom.slot) : "none"
  const jacketId = jacket ? araGarmentId(jacket.templateId, jacket.slot) : "none"
  const dress = selection.find((item) => item.slot === "dress")
  return {
    ...DEFAULT_PARAMS,
    name: "dressme-avatar",
    seed: 1,
    gender,
    age: clamp(targets.age),
    muscle: clamp(targets.muscle),
    weight: clamp(targets.weight),
    height: clamp(0.5 + (heightCm - 170) / 60),
    proportions,
    breastSize: clamp(targets.cupsize),
    breastFirmness: clamp(targets.firmness),
    african: 0.1,
    asian: 0.1,
    caucasian: 0.8,
    skin: "auto",
    hair: gender >= 0.5 ? "short04" : "short02",
    outfit: dress ? "none" : "none",
    top: dress ? "none" : topId,
    jacket: jacketId,
    bottom: dress ? "wrapper_long" : bottomId,
    shoes: shoes?.templateId ?? "none",
    detail: "medium",
    animations: false,
    modifiers: detailModifiers,
    garmentStyles: Object.fromEntries(
      selection.map((item) => [araGarmentId(item.templateId, item.slot), { color: item.colorHex }]),
    ),
  }
}

export async function buildAraAvatar(
  targets: BodyTargets,
  details: DetailTargets,
  heightCm: number,
  selection: TryOnItem[],
): Promise<Character> {
  return buildHuman(await library(), araParams(targets, details, heightCm, selection))
}
