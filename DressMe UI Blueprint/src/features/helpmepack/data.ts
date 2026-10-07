export type Step = "form" | "trip" | "wardrobe" | "processing" | "outfits" | "optimize" | "list" | "coverage" | "feedback"

export type Status = "own" | "buy" | "optional"

export type Category = "TOPS" | "BOTTOMS" | "OUTERWEAR" | "SHOES" | "ACCESSORIES"

export interface PackItem {
  id: string
  name: string
  category: Category
  meta: string
  season: string
  outfits: number
  status: Status
  img: string
  weather: string
  style: string
  tripValue: "High" | "Medium" | "Low"
  why: string
  stars: { versatility: number, weather: number, compatibility: number }
}

const img = (id: string) =>
  `https://images.unsplash.com/photo-${id}?w=440&h=560&fit=crop&auto=format`

export const IMG = {
  blazer: img("1551232864-3f0890e580d9"),
  turtleneck: img("1603805752838-aa579d77da72"),
  trousers: img("1558769132-cb1aea458c5e"),
  oxford: img("1521572163474-6864f9cf17ab"),
  jeans: img("1617178388553-a9d022974a5c"),
  boots: img("1614676471928-2ed0ad1061a4"),
  trench: img("1599643478518-a784e5dc4c8f"),
  bag: img("1467043237213-65f2da53396f"),
  slipdress: img("1644094751419-cc8ae49dd26d"),
  earrings: img("1598033129183-c4f50c736f10"),
  flats: img("1618354691373-d851c5c3a990"),
  knit: img("1516762689617-e1cffcef479d"),
  sneakers: img("1560343090-f0409e92791a"),
  editorial: img("1683392969197-17547ac3e06e"),
  rack: img("1532453288672-3a27e9be9efd"),
  flatlay: img("1556905055-8f358a7a47b2"),
}

export interface Trip {
  dest: string
  dates: string
  tripType: string
  dresscode: string
  bags: string
}

export const DEFAULT_TRIP: Trip = {
  dest: "Paris",
  dates: "Oct 14–21",
  tripType: "Adventure",
  dresscode: "Smart Casual",
  bags: "1 Carry-On",
}

export const TRIP_META = {
  duration: "7 days",
  activity: "Adventure",
  style: "Smart Casual",
  luggage: "1 Carry-On",
}

export const WEATHER = {
  range: "12–19°C",
  condition: "Partly Cloudy",
  rain: "Medium rain probability",
  icon: "⛅",
}

export const FORECAST = [
  { day: "14", week: "Tue", icon: "⛅", hi: 17, lo: 12 },
  { day: "15", week: "Wed", icon: "🌦️", hi: 16, lo: 11 },
  { day: "16", week: "Thu", icon: "🌧️", hi: 15, lo: 10 },
  { day: "17", week: "Fri", icon: "🌥️", hi: 14, lo: 9 },
  { day: "18", week: "Sat", icon: "⛅", hi: 16, lo: 11 },
  { day: "19", week: "Sun", icon: "☀️", hi: 18, lo: 12 },
  { day: "20", week: "Mon", icon: "☀️", hi: 19, lo: 13 },
]

export const CONDITIONS = [
  "Layering recommended",
  "Light outerwear",
  "Closed shoes",
  "Rain-compatible option",
  "Smart-casual dinner option",
]

export const WARDROBE_STATS = { total: 47, matched: 18 }

export const ITEMS: PackItem[] = [
  {
    id: "turtleneck",
    name: "Ivory Turtleneck",
    category: "TOPS",
    meta: "Top · Layering",
    season: "Autumn/Winter",
    outfits: 5,
    status: "own",
    img: IMG.turtleneck,
    weather: "Suitable for 12–19°C",
    style: "Smart Casual",
    tripValue: "High",
    why: "Your most reused layer. It pairs with every bottom you are taking and adds warmth without adding bulk to a carry-on.",
    stars: { versatility: 5, weather: 5, compatibility: 5 },
  },
  {
    id: "oxford",
    name: "White Oxford Shirt",
    category: "TOPS",
    meta: "Top · Smart Casual",
    season: "All Season",
    outfits: 4,
    status: "own",
    img: IMG.oxford,
    weather: "Suitable for 12–19°C",
    style: "Smart Casual",
    tripValue: "High",
    why: "Covers the smart-casual side of your trip: it dresses up the jeans for dinner and works alone on the warmer days.",
    stars: { versatility: 5, weather: 4, compatibility: 5 },
  },
  {
    id: "trousers",
    name: "Charcoal Wide-Leg Trousers",
    category: "BOTTOMS",
    meta: "Bottom · Smart Casual",
    season: "All Season",
    outfits: 3,
    status: "own",
    img: IMG.trousers,
    weather: "Suitable for 12–19°C",
    style: "Smart Casual",
    tripValue: "High",
    why: "The only bottom that carries both your city days and your smart-casual dinners, so you do not need a second pair of tailored trousers.",
    stars: { versatility: 4, weather: 5, compatibility: 5 },
  },
  {
    id: "jeans",
    name: "High-Rise Jeans",
    category: "BOTTOMS",
    meta: "Bottom · Adventure",
    season: "All Season",
    outfits: 4,
    status: "own",
    img: IMG.jeans,
    weather: "Suitable for 12–19°C",
    style: "Casual",
    tripValue: "High",
    why: "Your adventure days need a durable bottom. It mixes with both tops you are packing, so it replaces two casual pairs.",
    stars: { versatility: 5, weather: 4, compatibility: 4 },
  },
  {
    id: "blazer",
    name: "Camel Blazer",
    category: "OUTERWEAR",
    meta: "Outerwear · Smart Casual",
    season: "Autumn",
    outfits: 4,
    status: "own",
    img: IMG.blazer,
    weather: "Suitable for 12–19°C",
    style: "Smart Casual",
    tripValue: "High",
    why: "This item works with 4 different outfit combinations and provides an additional warm layer without requiring another outerwear piece.",
    stars: { versatility: 5, weather: 4, compatibility: 5 },
  },
  {
    id: "trench",
    name: "Trench Coat",
    category: "OUTERWEAR",
    meta: "Outerwear · Rain-friendly",
    season: "Autumn",
    outfits: 5,
    status: "buy",
    img: IMG.trench,
    weather: "Covers the medium rain forecast",
    style: "Smart Casual",
    tripValue: "High",
    why: "You have no rain-friendly outer layer. It is the single purchase that raises your coverage the most for this forecast.",
    stars: { versatility: 5, weather: 5, compatibility: 4 },
  },
  {
    id: "boots",
    name: "Chelsea Boots",
    category: "SHOES",
    meta: "Shoes · Smart Casual",
    season: "Fall/Winter",
    outfits: 6,
    status: "own",
    img: IMG.boots,
    weather: "Suitable for 12–19°C and light rain",
    style: "Smart Casual",
    tripValue: "High",
    why: "One pair of shoes that walks all day and still looks right at dinner — the highest-utility item in this pack.",
    stars: { versatility: 5, weather: 5, compatibility: 5 },
  },
  {
    id: "bag",
    name: "Crossbody Bag",
    category: "ACCESSORIES",
    meta: "Accessory · Everyday",
    season: "All Season",
    outfits: 2,
    status: "optional",
    img: IMG.bag,
    weather: "Rain-compatible",
    style: "Any",
    tripValue: "Medium",
    why: "Hands-free for adventure days. Optional because it does not change your outfit coverage — take it if your carry-on has room.",
    stars: { versatility: 4, weather: 4, compatibility: 4 },
  },
  {
    id: "slipdress",
    name: "Silk Slip Dress",
    category: "BOTTOMS",
    meta: "Dress · Evening",
    season: "Spring/Summer",
    outfits: 2,
    status: "optional",
    img: IMG.slipdress,
    weather: "Wear with the trench on cooler evenings",
    style: "Dinner",
    tripValue: "Medium",
    why: "Optional: it covers one dinner look. Packed only if you want a dedicated evening option.",
    stars: { versatility: 3, weather: 3, compatibility: 4 },
  },
  {
    id: "earrings",
    name: "Statement Earrings",
    category: "ACCESSORIES",
    meta: "Accessory · Evening",
    season: "All Season",
    outfits: 2,
    status: "optional",
    img: IMG.earrings,
    weather: "No weather constraint",
    style: "Dinner",
    tripValue: "Low",
    why: "Zero luggage weight, instant evening upgrade. Optional because it never affects coverage.",
    stars: { versatility: 3, weather: 5, compatibility: 4 },
  },
  {
    id: "flats",
    name: "Pointed-Toe Flats",
    category: "SHOES",
    meta: "Shoes · Formal",
    season: "All Season",
    outfits: 3,
    status: "buy",
    img: IMG.flats,
    weather: "Suitable for 12–19°C",
    style: "Formal",
    tripValue: "Medium",
    why: "No suitable formal footwear was found in your current wardrobe, so one dinner-ready option is missing.",
    stars: { versatility: 4, weather: 4, compatibility: 4 },
  },
  {
    id: "knit",
    name: "Cream Ribbed Knit",
    category: "TOPS",
    meta: "Top · Layering",
    season: "Autumn/Winter",
    outfits: 3,
    status: "own",
    img: IMG.knit,
    weather: "Suitable for 12–19°C",
    style: "Casual",
    tripValue: "Low",
    why: "Almost identical role to your Ivory Turtleneck — packing both would add weight without adding a single new combination.",
    stars: { versatility: 3, weather: 4, compatibility: 3 },
  },
  {
    id: "sneakers",
    name: "White Leather Sneakers",
    category: "SHOES",
    meta: "Shoes · Casual",
    season: "All Season",
    outfits: 3,
    status: "own",
    img: IMG.sneakers,
    weather: "Not rain-safe",
    style: "Casual",
    tripValue: "Low",
    why: "Overlaps with your Chelsea Boots for this forecast and fails the rain check, so it was dropped to save luggage weight.",
    stars: { versatility: 4, weather: 2, compatibility: 3 },
  },
]

export const byId = (id: string) => ITEMS.find((i) => i.id === id)!

export const CORE_IDS = [
  "turtleneck",
  "oxford",
  "trousers",
  "jeans",
  "blazer",
  "trench",
  "boots",
  "bag",
]
export const OPTIONAL_IDS = ["slipdress", "earrings"]
export const REMOVED = [
  {
    id: "knit",
    reason: "Similar neutral top",
    detail: "87% overlap with Ivory Turtleneck",
  },
  {
    id: "sneakers",
    reason: "Duplicate casual shoe",
    detail: "Same role as Chelsea Boots, fails rain check",
  },
]

export interface Look {
  id: string
  day: string
  occasion: string
  itemIds: string[]
  compat: number
  weatherOk: boolean
  note?: string
}

export const LOOKS: Look[] = [
  {
    id: "mon",
    day: "MON",
    occasion: "CITY",
    itemIds: ["blazer", "turtleneck", "trousers"],
    compat: 94,
    weatherOk: true,
  },
  {
    id: "tue",
    day: "TUE",
    occasion: "ADVENTURE",
    itemIds: ["oxford", "jeans", "boots"],
    compat: 91,
    weatherOk: true,
  },
  {
    id: "wed",
    day: "WED",
    occasion: "DINNER",
    itemIds: ["slipdress", "trench"],
    compat: 89,
    weatherOk: true,
    note: "Uses an optional item",
  },
  {
    id: "thu",
    day: "THU",
    occasion: "CITY",
    itemIds: ["blazer", "oxford", "trousers"],
    compat: 96,
    weatherOk: true,
  },
  {
    id: "fri",
    day: "FRI",
    occasion: "TRAVEL",
    itemIds: ["turtleneck", "jeans", "boots", "bag"],
    compat: 93,
    weatherOk: true,
  },
  {
    id: "sat",
    day: "SAT",
    occasion: "ADVENTURE",
    itemIds: ["oxford", "jeans", "trench", "boots"],
    compat: 90,
    weatherOk: true,
  },
]

export const OPTIMIZER = {
  candidates: 10,
  removed: 2,
  essential: 8,
  saved: "0.8 kg",
  combos: 18,
  baseCoverage: 92,
}

export const COVERAGE_CHECKS = [
  { label: "Days covered", value: "7 / 7 days" },
  { label: "Weather requirements", value: "Covered" },
  { label: "Adventure requirements", value: "Covered" },
  { label: "Smart-casual outfits", value: "Covered" },
  { label: "Valid outfit combinations", value: "18" },
]

export const PROCESS_TASKS = [
  "Understanding your trip",
  "Checking destination weather",
  "Analyzing your wardrobe",
  "Finding compatible outfits",
  "Removing redundant items",
  "Optimizing your packing set",
  "Checking trip coverage",
]

export const AGENT_FLOW = [
  {
    from: "STYLIST AGENT",
    request: "Create a packing plan for Paris, Oct 14–21.",
    response: "Plan draft requested",
    bo: "Orchestrator",
  },
  {
    from: "WARDROBE AGENT",
    request: "Retrieve garments suitable for the trip.",
    response: "18 candidate garments",
    bo: "BO1",
  },
  {
    from: "OUTFIT AGENT",
    request: "Generate compatible combinations.",
    response: "24 candidate outfits",
    bo: "BO4",
  },
  {
    from: "GAP AGENT",
    request: "Check missing requirements.",
    response: "Formal footwear missing",
    bo: "BO3",
  },
  {
    from: "PACKING AGENT",
    request: "Minimize items while maintaining coverage.",
    response: "8 selected items · 18 combinations · 92% coverage",
    bo: "BO7",
  },
  {
    from: "STYLIST AGENT",
    request: "Assemble the final draft.",
    response: "Final draft generated",
    bo: "Orchestrator",
  },
  {
    from: "TRUST AGENT",
    request: "Validate the recommendation and its reasoning.",
    response: "Confidence: 91% · Recommendation validated",
    bo: "BO5",
  },
]

export const CHANGE_OPTIONS = [
  "Fewer items",
  "More outfit variety",
  "Remove an item",
  "Different style",
  "I don't want to buy anything",
  "Other",
]

export interface Revision {
  removedIds: string[]
  combos: number
  coverage: number
  summary: string
}

export const revisionFor = (reason: string): Revision => {
  switch (reason) {
    case "Fewer items":
      return {
        removedIds: ["bag"],
        combos: 16,
        coverage: 89,
        summary: "Dropped the optional Crossbody Bag for a lighter carry-on.",
      }
    case "Remove an item":
      return {
        removedIds: ["trousers"],
        combos: 15,
        coverage: 87,
        summary: "Removed the Charcoal Wide-Leg Trousers from the plan.",
      }
    case "I don't want to buy anything":
      return {
        removedIds: ["trench"],
        combos: 14,
        coverage: 85,
        summary:
          "Trench Coat removed — plan rebuilt with pieces you already own.",
      }
    case "More outfit variety":
      return {
        removedIds: [],
        combos: 21,
        coverage: 94,
        summary: "Rebalanced the set for 3 additional combinations.",
      }
    case "Different style":
      return {
        removedIds: ["blazer"],
        combos: 17,
        coverage: 90,
        summary: "Shifted the balance away from tailored pieces.",
      }
    default:
      return {
        removedIds: [],
        combos: 19,
        coverage: 93,
        summary: "Plan re-optimized from your feedback.",
      }
  }
}
