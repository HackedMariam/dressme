export type Option = {
  value: string
  label: string
}

export type ColorOption = Option & {
  hex: string
}

export const STYLE_OPTIONS: Option[] = [
  { value: "Minimalist", label: "Minimalist" },
  { value: "Classic / Timeless", label: "Classic / Timeless" },
  { value: "Smart Casual", label: "Smart Casual" },
  {
    value: "Editorial / Fashion-Forward",
    label: "Editorial / Fashion-Forward",
  },
  { value: "Boho / Relaxed", label: "Boho / Relaxed" },
  { value: "Elegant", label: "Elegant" },
  { value: "Sporty", label: "Sporty" },
  { value: "Streetwear", label: "Streetwear" },
]

export const COLOR_OPTIONS: ColorOption[] = [
  { value: "Ivory", label: "Ivory", hex: "#FFFFF0" },
  { value: "White", label: "White", hex: "#FFFFFF" },
  { value: "Camel", label: "Camel", hex: "#C19A6B" },
  { value: "Beige", label: "Beige", hex: "#D8C8B4" },
  { value: "Charcoal", label: "Charcoal", hex: "#36454F" },
  { value: "Black", label: "Black", hex: "#1C1C1C" },
  { value: "Olive", label: "Olive", hex: "#556B2F" },
  { value: "Sage", label: "Sage", hex: "#9CAF88" },
  { value: "Indigo", label: "Indigo", hex: "#4B0082" },
  { value: "Navy", label: "Navy", hex: "#1F2A44" },
  { value: "Blush", label: "Blush", hex: "#FFB7C5" },
  { value: "Red", label: "Red", hex: "#B3261E" },
  { value: "Burgundy", label: "Burgundy", hex: "#6D1A2F" },
  { value: "Brown", label: "Brown", hex: "#6B4A2F" },
  { value: "Grey", label: "Grey", hex: "#9A9A9A" },
  { value: "Metallic", label: "Metallic", hex: "#C0C0C0" },
]

export const OCCASION_OPTIONS: Option[] = [
  { value: "Work / Office", label: "Work / Office" },
  { value: "Smart Casual", label: "Smart Casual" },
  { value: "Weekend Leisure", label: "Weekend Leisure" },
  { value: "Evening / Dinner", label: "Evening / Dinner" },
  { value: "Travel", label: "Travel" },
  { value: "Formal Event", label: "Formal Event" },
  { value: "Wedding / Ceremony", label: "Wedding / Ceremony" },
  { value: "Sport / Active", label: "Sport / Active" },
  { value: "Everyday Casual", label: "Everyday Casual" },
]

export const CATEGORY_OPTIONS: Option[] = [
  { value: "Tops", label: "Tops" },
  { value: "Bottoms", label: "Bottoms" },
  { value: "Dresses", label: "Dresses" },
  { value: "Outerwear", label: "Outerwear" },
  { value: "Shoes", label: "Shoes" },
  { value: "Accessories", label: "Accessories" },
  { value: "Activewear", label: "Activewear" },
  { value: "Swimwear", label: "Swimwear" },
]

export const FIT_OPTIONS: Option[] = [
  { value: "fitted", label: "Fitted" },
  { value: "regular", label: "Regular" },
  { value: "relaxed", label: "Relaxed" },
]

export const LANGUAGE_OPTIONS: Option[] = [
  { value: "en", label: "English" },
  { value: "fr", label: "Français" },
  { value: "ar", label: "العربية" },
]

export const CURRENCY_OPTIONS: Option[] = [
  { value: "TND", label: "TND — Tunisian Dinar" },
  { value: "EUR", label: "EUR — Euro" },
  { value: "USD", label: "USD — US Dollar" },
  { value: "GBP", label: "GBP — British Pound" },
]

export const TEMPERATURE_OPTIONS: Option[] = [
  { value: "Celsius", label: "Celsius" },
  { value: "Fahrenheit", label: "Fahrenheit" },
]

export const SIZE_SYSTEM_OPTIONS: Option[] = [
  { value: "EU", label: "EU" },
  { value: "US", label: "US" },
  { value: "UK", label: "UK" },
]

export const COUNTRY_OPTIONS: Option[] = [
  { value: "Tunisia", label: "Tunisia" },
  { value: "France", label: "France" },
  { value: "Italy", label: "Italy" },
  { value: "Spain", label: "Spain" },
  { value: "Germany", label: "Germany" },
  { value: "United Kingdom", label: "United Kingdom" },
  { value: "United States", label: "United States" },
  { value: "Canada", label: "Canada" },
  { value: "Morocco", label: "Morocco" },
  { value: "Algeria", label: "Algeria" },
  { value: "Egypt", label: "Egypt" },
  { value: "Turkey", label: "Turkey" },
  { value: "United Arab Emirates", label: "United Arab Emirates" },
  { value: "Saudi Arabia", label: "Saudi Arabia" },
  { value: "Other", label: "Other" },
]

export const CLOTHING_SIZE_FIELDS = [
  { key: "top", label: "Top" },
  { key: "bottom", label: "Bottom" },
  { key: "dress", label: "Dress" },
  { key: "shoes", label: "Shoes" },
] as const

export type ClothingSizeKey = typeof CLOTHING_SIZE_FIELDS[number]["key"]

export const ONBOARDING_STEPS = [
  { title: "About you", description: "The basics we use across DressMe." },
  { title: "Fit & sizes", description: "Help us recommend the right cut." },
  { title: "Your style", description: "The looks and colours you love." },
] as const

export const MAX_ONBOARDING_STEP = ONBOARDING_STEPS.length - 1
