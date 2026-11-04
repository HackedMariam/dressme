export type Page =
  | "dashboard"
  | "wardrobe"
  | "avatar"
  | "ai-stylist"
  | "help-me-pack"
  | "wardrobe-gaps"
  | "should-i-buy"
  | "find-similar"
  | "style-profile"
  | "settings"

export type NavEntry = { label: string; page: Page; icon: string; also?: Page[] }
export type NavGroup = { title?: string; entries: NavEntry[] }

// The three shopping tools share one sidebar entry and one tab bar (see ShopTabs).
export const SHOP_PAGES: { page: Page; label: string; blurb: string }[] = [
  {
    page: "wardrobe-gaps",
    label: "Wardrobe Gaps",
    blurb: "What is missing from your wardrobe, and what to buy first.",
  },
  {
    page: "find-similar",
    label: "Find Similar",
    blurb: "Show a look you like and see how much of it you can already recreate.",
  },
  {
    page: "should-i-buy",
    label: "Should I Buy?",
    blurb: "Check one piece against your wardrobe and budget before you pay.",
  },
]

export const NAV_GROUPS: NavGroup[] = [
  { entries: [{ label: "Dashboard", page: "dashboard", icon: "⊞" }] },
  {
    title: "My closet",
    entries: [
      { label: "My Wardrobe", page: "wardrobe", icon: "◫" },
      { label: "My 3D Avatar", page: "avatar", icon: "☺" },
    ],
  },
  {
    title: "Style",
    entries: [
      { label: "AI Stylist", page: "ai-stylist", icon: "◆" },
      { label: "Help Me Pack", page: "help-me-pack", icon: "◈" },
    ],
  },
  {
    title: "Shop",
    entries: [
      {
        label: "Shop smart",
        page: "wardrobe-gaps",
        icon: "◇",
        also: SHOP_PAGES.map((entry) => entry.page),
      },
    ],
  },
  {
    title: "Account",
    entries: [
      { label: "Style Profile", page: "style-profile", icon: "◉" },
      { label: "Settings", page: "settings", icon: "⊙" },
    ],
  },
]

export const isShopPage = (page: Page) => SHOP_PAGES.some((entry) => entry.page === page)
