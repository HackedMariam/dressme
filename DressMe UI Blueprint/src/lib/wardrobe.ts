import type { GarmentId } from "./garments"

export type WardrobeItem = {
  id: number
  name: string
  category: string
  color: string
  season: string
  img: string
  tags: string[]
  wear: number
  cost: number
  garmentId: GarmentId
}

export const wardrobeItems: WardrobeItem[] = [
  {
    id: 1,
    name: "Merino Wool Turtleneck",
    category: "Tops",
    color: "Ivory",
    season: "Winter",
    img: "https://images.unsplash.com/photo-1603805752838-aa579d77da72?w=300&h=380&fit=crop&auto=format",
    tags: ["Casual", "Layering"],
    wear: 12,
    cost: 89,
    garmentId: "turtleneck",
  },
  {
    id: 2,
    name: "High-Rise Straight Jeans",
    category: "Bottoms",
    color: "Indigo",
    season: "All Season",
    img: "https://images.unsplash.com/photo-1617178388553-a9d022974a5c?w=300&h=380&fit=crop&auto=format",
    tags: ["Casual", "Versatile"],
    wear: 28,
    cost: 120,
    garmentId: "jeans",
  },
  {
    id: 3,
    name: "Camel Blazer",
    category: "Outerwear",
    color: "Camel",
    season: "Fall",
    img: "https://images.unsplash.com/photo-1551232864-3f0890e580d9?w=300&h=380&fit=crop&auto=format",
    tags: ["Work", "Smart Casual"],
    wear: 9,
    cost: 245,
    garmentId: "blazer",
  },
  {
    id: 4,
    name: "Silk Slip Dress",
    category: "Dresses",
    color: "Champagne",
    season: "Spring/Summer",
    img: "https://images.unsplash.com/photo-1644094751419-cc8ae49dd26d?w=300&h=380&fit=crop&auto=format",
    tags: ["Evening", "Date Night"],
    wear: 4,
    cost: 195,
    garmentId: "dress",
  },
  {
    id: 5,
    name: "White Oxford Shirt",
    category: "Tops",
    color: "White",
    season: "All Season",
    img: "https://images.unsplash.com/photo-1558769132-cb1aea458c5e?w=300&h=380&fit=crop&auto=format",
    tags: ["Work", "Versatile"],
    wear: 22,
    cost: 68,
    garmentId: "oxford",
  },
  {
    id: 6,
    name: "Suede Chelsea Boots",
    category: "Shoes",
    color: "Tan",
    season: "Fall/Winter",
    img: "https://images.unsplash.com/photo-1614676471928-2ed0ad1061a4?w=300&h=380&fit=crop&auto=format",
    tags: ["Versatile", "Smart Casual"],
    wear: 31,
    cost: 310,
    garmentId: "boots",
  },
  {
    id: 7,
    name: "Cashmere Cardigan",
    category: "Tops",
    color: "Oatmeal",
    season: "Fall/Winter",
    img: "https://images.unsplash.com/photo-1516762689617-e1cffcef479d?w=300&h=380&fit=crop&auto=format",
    tags: ["Cozy", "Layering"],
    wear: 17,
    cost: 185,
    garmentId: "cardigan",
  },
  {
    id: 8,
    name: "Wide-Leg Trousers",
    category: "Bottoms",
    color: "Charcoal",
    season: "All Season",
    img: "https://images.unsplash.com/photo-1479064555552-3ef4979f8908?w=300&h=380&fit=crop&auto=format",
    tags: ["Work", "Evening"],
    wear: 14,
    cost: 145,
    garmentId: "trousers",
  },
]
