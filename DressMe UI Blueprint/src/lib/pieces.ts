import { TAXONOMY } from "./taxonomy"

// Everyday words for garments -> the detector's classes. Shared by Find Similar and the shop suggestions.
export const CATEGORY_WORDS: Record<string, string> = {
  tee: "top", tshirt: "top", "t-shirt": "top", shirt: "top", blouse: "top", tank: "top",
  sweatshirt: "sweater", hoodie: "sweater", cardigan: "sweater", jumper: "sweater", pullover: "sweater",
  coat: "jacket", blazer: "jacket", parka: "jacket", puffer: "jacket", bomber: "jacket",
  jeans: "pants", trousers: "pants", chinos: "pants", leggings: "pants",
  sneakers: "shoe", shoes: "shoe", boots: "shoe", heels: "shoe", loafers: "shoe", sandals: "shoe",
  handbag: "bag", backpack: "bag", tote: "bag", purse: "bag",
  gown: "dress", jumpsuit: "dress", cap: "hat", beanie: "hat", sunglasses: "glasses", tie: "scarf",
}

/** The garment class named in a text ("camel wool coat" -> "jacket"), or undefined. */
export function inferCategory(text: string): string | undefined {
  const words = text.toLowerCase().match(/[a-z-]+/g) ?? []
  const lookup = (word: string) => (TAXONOMY.classes.includes(word) ? word : CATEGORY_WORDS[word])
  return words.map(lookup).find(Boolean) ?? words.map((word) => lookup(word.replace(/s$/, ""))).find(Boolean)
}

// The virtual try-on dresses the body: shoes, bags and accessories are not supported.
const TRYON_GROUPS = ["Tops", "Outerwear", "Bottoms", "Dresses"]

/** The wardrobe group to send to the try-on, or null when this kind of piece cannot be tried on. */
export function tryOnGroup(category: string | undefined): string | null {
  const group = category ? TAXONOMY.class_to_group[category] : undefined
  return group && TRYON_GROUPS.includes(group) ? group : null
}
