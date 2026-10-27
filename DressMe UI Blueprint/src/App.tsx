import { useState } from "react";
import GapsCard from "@/features/wardrobegaps/GapsCard";
import WardrobeGapsPage from "@/features/wardrobegaps/WardrobeGapsPage";

type Page =
  | "dashboard"
  | "wardrobe"
  | "wardrobe-gaps"
  | "outfit-studio"
  | "help-me-pack"
  | "style-profile"
  | "should-i-buy"
  | "find-similar"
  | "ai-stylist"
  | "weather"
  | "settings";

const OUTFIT_IMG = "https://images.unsplash.com/photo-1556905055-8f358a7a47b2?w=600&h=800&fit=crop&auto=format";
const WARDROBE_IMG = "https://images.unsplash.com/photo-1490481651871-ab68de25d43d?w=800&h=500&fit=crop&auto=format";
const EDITORIAL_IMG = "https://images.unsplash.com/photo-1683392969197-17547ac3e06e?w=600&h=800&fit=crop&auto=format";
const FLATLAY_IMG = "https://images.unsplash.com/photo-1467043237213-65f2da53396f?w=400&h=500&fit=crop&auto=format";
const RACK_IMG = "https://images.unsplash.com/photo-1532453288672-3a27e9be9efd?w=400&h=500&fit=crop&auto=format";

const wardrobeItems = [
  { id: 1, name: "Merino Wool Turtleneck", category: "Tops", color: "Ivory", season: "Winter", img: "https://images.unsplash.com/photo-1603805752838-aa579d77da72?w=300&h=380&fit=crop&auto=format", tags: ["Casual", "Layering"], wear: 12, cost: 89 },
  { id: 2, name: "High-Rise Straight Jeans", category: "Bottoms", color: "Indigo", season: "All Season", img: "https://images.unsplash.com/photo-1617178388553-a9d022974a5c?w=300&h=380&fit=crop&auto=format", tags: ["Casual", "Versatile"], wear: 28, cost: 120 },
  { id: 3, name: "Camel Blazer", category: "Outerwear", color: "Camel", season: "Fall", img: "https://images.unsplash.com/photo-1551232864-3f0890e580d9?w=300&h=380&fit=crop&auto=format", tags: ["Work", "Smart Casual"], wear: 9, cost: 245 },
  { id: 4, name: "Silk Slip Dress", category: "Dresses", color: "Champagne", season: "Spring/Summer", img: "https://images.unsplash.com/photo-1644094751419-cc8ae49dd26d?w=300&h=380&fit=crop&auto=format", tags: ["Evening", "Date Night"], wear: 4, cost: 195 },
  { id: 5, name: "White Oxford Shirt", category: "Tops", color: "White", season: "All Season", img: "https://images.unsplash.com/photo-1558769132-cb1aea458c5e?w=300&h=380&fit=crop&auto=format", tags: ["Work", "Versatile"], wear: 22, cost: 68 },
  { id: 6, name: "Suede Chelsea Boots", category: "Shoes", color: "Tan", season: "Fall/Winter", img: "https://images.unsplash.com/photo-1614676471928-2ed0ad1061a4?w=300&h=380&fit=crop&auto=format", tags: ["Versatile", "Smart Casual"], wear: 31, cost: 310 },
  { id: 7, name: "Cashmere Cardigan", category: "Tops", color: "Oatmeal", season: "Fall/Winter", img: "https://images.unsplash.com/photo-1516762689617-e1cffcef479d?w=300&h=380&fit=crop&auto=format", tags: ["Cozy", "Layering"], wear: 17, cost: 185 },
  { id: 8, name: "Wide-Leg Trousers", category: "Bottoms", color: "Charcoal", season: "All Season", img: "https://images.unsplash.com/photo-1479064555552-3ef4979f8908?w=300&h=380&fit=crop&auto=format", tags: ["Work", "Evening"], wear: 14, cost: 145 },
];

const navItems: { label: string; page: Page; icon: string }[] = [
  { label: "Dashboard", page: "dashboard", icon: "⊞" },
  { label: "My Wardrobe", page: "wardrobe", icon: "◫" },
  { label: "Wardrobe Gaps", page: "wardrobe-gaps", icon: "◐" },
  { label: "Outfit Studio", page: "outfit-studio", icon: "✦" },
  { label: "Help Me Pack", page: "help-me-pack", icon: "◈" },
  { label: "Style Profile", page: "style-profile", icon: "◉" },
  { label: "Should I Buy?", page: "should-i-buy", icon: "◇" },
  { label: "Find Similar", page: "find-similar", icon: "◎" },
  { label: "AI Stylist", page: "ai-stylist", icon: "◆" },
  { label: "Weather", page: "weather", icon: "◌" },
  { label: "Settings", page: "settings", icon: "⊙" },
];

function Sidebar({ current, onNav }: { current: Page; onNav: (p: Page) => void }) {
  return (
    <aside className="fixed left-0 top-0 h-screen w-[260px] bg-[#1C1C1C] flex flex-col z-50">
      <div className="px-7 py-8 border-b border-white/10">
        <div className="flex items-baseline gap-1">
          <span className="font-display text-2xl font-semibold text-[#FAF9F6] italic">Dress</span>
          <span className="font-display text-2xl font-semibold text-[#556B2F]">Me</span>
        </div>
        <p className="text-[11px] text-white/30 mt-0.5 tracking-widest uppercase font-light">AI Style Intelligence</p>
      </div>

      <nav className="flex-1 py-5 overflow-y-auto">
        {navItems.map((item) => {
          const active = current === item.page;
          return (
            <button
              key={item.page}
              onClick={() => onNav(item.page)}
              className={`w-full flex items-center gap-3 px-7 py-3 text-sm transition-all duration-150 text-left ${
                active
                  ? "bg-[#556B2F]/20 text-[#FAF9F6] border-r-2 border-[#556B2F]"
                  : "text-white/50 hover:text-white/80 hover:bg-white/5"
              }`}
            >
              <span className="text-base opacity-70">{item.icon}</span>
              <span className="font-medium">{item.label}</span>
            </button>
          );
        })}
      </nav>

      <div className="px-7 py-6 border-t border-white/10">
        <button className="w-full bg-[#556B2F] hover:bg-[#6B8A3A] text-white text-sm font-semibold py-3 rounded-lg transition-colors">
          + Add Item
        </button>
        <div className="flex items-center gap-3 mt-5">
          <div className="w-8 h-8 rounded-full bg-[#556B2F]/30 flex items-center justify-center text-xs text-[#556B2F] font-semibold">S</div>
          <div>
            <p className="text-white/80 text-xs font-medium">Sophia L.</p>
            <p className="text-white/30 text-[10px]">Style Enthusiast</p>
          </div>
        </div>
      </div>
    </aside>
  );
}

function ScoreRing({ score, size = 80 }: { score: number; size?: number }) {
  const r = (size - 8) / 2;
  const circ = 2 * Math.PI * r;
  const dash = (score / 100) * circ;
  return (
    <svg width={size} height={size} className="-rotate-90">
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#E2E0D8" strokeWidth="4" />
      <circle
        cx={size / 2} cy={size / 2} r={r} fill="none"
        stroke="#556B2F" strokeWidth="4"
        strokeDasharray={`${dash} ${circ}`}
        strokeLinecap="round"
      />
    </svg>
  );
}

function Dashboard({ onNav }: { onNav: (p: Page) => void }) {
  return (
    <div className="space-y-8">
      <div>
        <h1 className="font-display text-3xl font-semibold text-[#1C1C1C]">Good morning, Sophia.</h1>
        <p className="text-[#8C8A82] text-sm mt-1">Thursday, September 11 · 18°C, Partly Cloudy in New York</p>
      </div>

      {/* Hero AI Recommendation */}
      <div className="bg-[#1C1C1C] rounded-2xl overflow-hidden flex min-h-[360px]">
        <div className="flex-1 p-8 flex flex-col justify-between">
          <div>
            <span className="text-[#556B2F] text-xs font-semibold tracking-widest uppercase">AI Daily Recommendation</span>
            <h2 className="font-display text-2xl font-medium text-white mt-3 leading-snug">
              The Effortless<br />Autumn Transition
            </h2>
            <p className="text-white/50 text-sm mt-3 leading-relaxed max-w-sm">
              Your camel blazer over the ivory turtleneck creates a tonal warmth ideal for today's 18°C. Wide-leg trousers anchor the silhouette; Chelsea boots tie it to the season.
            </p>
          </div>
          <div className="space-y-4">
            <div className="grid grid-cols-3 gap-3">
              {["Camel Blazer", "Ivory Turtleneck", "Charcoal Trousers"].map((item) => (
                <div key={item} className="bg-white/5 rounded-lg px-3 py-2">
                  <p className="text-white/40 text-[10px] uppercase tracking-wide">Piece</p>
                  <p className="text-white/80 text-xs font-medium mt-0.5">{item}</p>
                </div>
              ))}
            </div>
            <div className="flex items-center gap-3">
              <div className="relative">
                <ScoreRing score={92} size={64} />
                <span className="absolute inset-0 flex items-center justify-center text-white font-bold text-sm">92</span>
              </div>
              <div>
                <p className="text-white font-semibold">Compatibility Score</p>
                <p className="text-white/40 text-xs">Excellent · Weather + Occasion matched</p>
              </div>
            </div>
          </div>
        </div>
        <div className="w-[280px] relative bg-[#2A2A2A]">
          <img src={OUTFIT_IMG} alt="AI recommended outfit flat lay" className="w-full h-full object-cover opacity-80" />
          <div className="absolute bottom-0 inset-x-0 bg-gradient-to-t from-black/60 to-transparent p-4">
            <p className="text-white/60 text-xs">Why it works</p>
            <p className="text-white text-xs mt-1">Warm tones mirror autumn light · Layering handles temperature swings · Proportions balance relaxed + structured</p>
          </div>
        </div>
      </div>

      {/* Insights Row */}
      <div className="grid grid-cols-4 gap-4">
        {[
          { label: "Total Items", value: "84", sub: "across 8 categories" },
          { label: "Avg Cost-Per-Wear", value: "$4.20", sub: "down 12% this month" },
          { label: "Outfits Created", value: "31", sub: "this season" },
          { label: "Wardrobe Value", value: "$6,840", sub: "est. retail" },
        ].map((s) => (
          <div key={s.label} className="bg-[#F0EFEA] rounded-xl p-5">
            <p className="text-[#8C8A82] text-xs uppercase tracking-widest">{s.label}</p>
            <p className="font-display text-3xl font-semibold text-[#1C1C1C] mt-2">{s.value}</p>
            <p className="text-[#8C8A82] text-xs mt-1">{s.sub}</p>
          </div>
        ))}
      </div>

      {/* Analytics */}
      <div className="grid grid-cols-2 gap-6">
        <GapsCard onOpen={() => onNav("wardrobe-gaps")} />
        <div className="bg-[#F0EFEA] rounded-xl p-6">
          <h3 className="font-display text-lg font-medium text-[#1C1C1C]">Potential Duplicates</h3>
          <p className="text-[#8C8A82] text-xs mt-1 mb-4">Similar items that may overlap in function</p>
          {[
            { a: "Ivory Turtleneck", b: "Cream Ribbed Knit", sim: 87 },
            { a: "Camel Blazer", b: "Tan Longline Coat", sim: 74 },
            { a: "Indigo Jeans #1", b: "Indigo Jeans #2", sim: 91 },
          ].map((d) => (
            <div key={d.a} className="flex items-center justify-between py-3 border-b border-[#E2E0D8] last:border-0">
              <div>
                <p className="text-xs font-medium text-[#1C1C1C]">{d.a}</p>
                <p className="text-[10px] text-[#8C8A82] mt-0.5">vs. {d.b}</p>
              </div>
              <span className="text-xs font-semibold text-[#556B2F] bg-[#E8EDE0] px-2 py-0.5 rounded-full">{d.sim}% similar</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function MyWardrobe() {
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("All");
  const [sort, setSort] = useState("Recent");
  const categories = ["All", "Tops", "Bottoms", "Dresses", "Outerwear", "Shoes"];

  const filtered = wardrobeItems.filter(
    (i) =>
      (category === "All" || i.category === category) &&
      i.name.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="font-display text-3xl font-semibold text-[#1C1C1C]">My Wardrobe</h1>
          <p className="text-[#8C8A82] text-sm mt-1">{wardrobeItems.length} items · Last updated today</p>
        </div>
        <button className="bg-[#556B2F] hover:bg-[#6B8A3A] text-white text-sm font-semibold px-5 py-2.5 rounded-lg transition-colors">
          + Add Clothing
        </button>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-4">
        <div className="relative flex-1 max-w-sm">
          <span className="absolute left-3 top-1/2 -translate-y-1/2 text-[#8C8A82] text-sm">⌕</span>
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search your wardrobe…"
            className="w-full pl-8 pr-4 py-2.5 bg-[#F0EFEA] border border-[#E2E0D8] rounded-lg text-sm text-[#1C1C1C] placeholder-[#8C8A82] outline-none focus:border-[#556B2F] transition-colors"
          />
        </div>
        <div className="flex gap-2">
          {categories.map((c) => (
            <button
              key={c}
              onClick={() => setCategory(c)}
              className={`px-4 py-2 rounded-lg text-xs font-semibold transition-all ${
                category === c
                  ? "bg-[#1C1C1C] text-white"
                  : "bg-[#F0EFEA] text-[#8C8A82] hover:text-[#1C1C1C]"
              }`}
            >
              {c}
            </button>
          ))}
        </div>
        <select
          value={sort}
          onChange={(e) => setSort(e.target.value)}
          className="ml-auto bg-[#F0EFEA] border border-[#E2E0D8] rounded-lg text-xs font-medium text-[#1C1C1C] px-3 py-2.5 outline-none"
        >
          {["Recent", "Most Worn", "Cost-Per-Wear", "Category"].map((o) => (
            <option key={o}>{o}</option>
          ))}
        </select>
      </div>

      {/* Grid */}
      <div className="grid grid-cols-4 gap-4">
        {filtered.map((item) => (
          <div key={item.id} className="bg-[#F0EFEA] rounded-xl overflow-hidden group cursor-pointer hover:shadow-md transition-shadow">
            <div className="h-48 bg-[#E2E0D8] overflow-hidden relative">
              <img src={item.img} alt={item.name} className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500" />
              <div className="absolute top-2 right-2 flex gap-1">
                {item.tags.slice(0, 1).map((t) => (
                  <span key={t} className="text-[9px] font-semibold bg-[#1C1C1C]/70 text-white px-2 py-0.5 rounded-full">{t}</span>
                ))}
              </div>
            </div>
            <div className="p-3">
              <p className="text-xs text-[#8C8A82] font-medium uppercase tracking-wide">{item.category}</p>
              <p className="text-sm font-semibold text-[#1C1C1C] mt-0.5 leading-tight">{item.name}</p>
              <div className="flex items-center justify-between mt-2">
                <span className="text-xs text-[#8C8A82]">{item.color} · {item.season}</span>
              </div>
              <div className="flex items-center justify-between mt-2 pt-2 border-t border-[#E2E0D8]">
                <span className="text-xs text-[#8C8A82]">Worn {item.wear}×</span>
                <span className="text-xs font-semibold text-[#556B2F]">${(item.cost / item.wear).toFixed(2)}/wear</span>
              </div>
            </div>
          </div>
        ))}

        {/* Add Item Card */}
        <div className="bg-[#F0EFEA] rounded-xl border-2 border-dashed border-[#E2E0D8] flex flex-col items-center justify-center h-[282px] cursor-pointer hover:border-[#556B2F] hover:bg-[#E8EDE0] transition-all group">
          <span className="text-3xl text-[#E2E0D8] group-hover:text-[#556B2F] transition-colors">+</span>
          <p className="text-sm text-[#8C8A82] font-medium mt-2">Add clothing</p>
          <p className="text-xs text-[#8C8A82]/60 mt-0.5">Drag & drop or browse</p>
        </div>
      </div>
    </div>
  );
}

function OutfitStudio() {
  const [canvas, setCanvas] = useState<typeof wardrobeItems>([]);
  const [score, setScore] = useState(0);

  const addToCanvas = (item: (typeof wardrobeItems)[0]) => {
    if (!canvas.find((c) => c.id === item.id)) {
      const next = [...canvas, item];
      setCanvas(next);
      setScore(Math.min(98, 40 + next.length * 15 + Math.floor(Math.random() * 10)));
    }
  };

  const removeFromCanvas = (id: number) => {
    const next = canvas.filter((c) => c.id !== id);
    setCanvas(next);
    setScore(next.length === 0 ? 0 : Math.max(0, score - 15));
  };

  return (
    <div className="space-y-6 h-full">
      <div>
        <h1 className="font-display text-3xl font-semibold text-[#1C1C1C]">Outfit Studio</h1>
        <p className="text-[#8C8A82] text-sm mt-1">Assemble looks and get AI feedback</p>
      </div>

      <div className="grid grid-cols-[280px_1fr] gap-6 h-[calc(100vh-220px)]">
        {/* Wardrobe Panel */}
        <div className="bg-[#F0EFEA] rounded-xl p-4 flex flex-col overflow-hidden">
          <p className="text-xs font-semibold text-[#8C8A82] uppercase tracking-widest mb-3">Your Wardrobe</p>
          <div className="space-y-2 overflow-y-auto flex-1">
            {wardrobeItems.map((item) => {
              const inCanvas = !!canvas.find((c) => c.id === item.id);
              return (
                <button
                  key={item.id}
                  onClick={() => addToCanvas(item)}
                  disabled={inCanvas}
                  className={`w-full flex items-center gap-3 p-2.5 rounded-lg text-left transition-all ${
                    inCanvas
                      ? "opacity-40 cursor-not-allowed bg-[#E2E0D8]"
                      : "hover:bg-[#E2E0D8] cursor-pointer"
                  }`}
                >
                  <div className="w-10 h-12 rounded bg-[#E2E0D8] overflow-hidden shrink-0">
                    <img src={item.img} alt={item.name} className="w-full h-full object-cover" />
                  </div>
                  <div className="min-w-0">
                    <p className="text-xs font-semibold text-[#1C1C1C] truncate">{item.name}</p>
                    <p className="text-[10px] text-[#8C8A82]">{item.category} · {item.color}</p>
                  </div>
                  {!inCanvas && <span className="ml-auto text-[#556B2F] text-sm">+</span>}
                </button>
              );
            })}
          </div>
        </div>

        {/* Canvas */}
        <div className="flex flex-col gap-4">
          <div className="bg-[#F0EFEA] rounded-xl p-6 flex-1 overflow-hidden">
            <div className="flex items-center justify-between mb-4">
              <p className="text-xs font-semibold text-[#8C8A82] uppercase tracking-widest">Outfit Canvas</p>
              <button
                onClick={() => { setCanvas([]); setScore(0); }}
                className="text-xs text-[#8C8A82] hover:text-[#1C1C1C] transition-colors"
              >
                Clear all
              </button>
            </div>

            {canvas.length === 0 ? (
              <div className="h-full flex flex-col items-center justify-center text-center">
                <div className="w-16 h-16 rounded-full bg-[#E2E0D8] flex items-center justify-center mb-3">
                  <span className="text-2xl text-[#8C8A82]">✦</span>
                </div>
                <p className="text-sm font-medium text-[#8C8A82]">Select items from your wardrobe</p>
                <p className="text-xs text-[#8C8A82]/60 mt-1">Click pieces to add them to your outfit</p>
              </div>
            ) : (
              <div className="flex flex-wrap gap-3">
                {canvas.map((item) => (
                  <div key={item.id} className="relative group">
                    <div className="w-28 h-36 rounded-xl overflow-hidden bg-[#E2E0D8]">
                      <img src={item.img} alt={item.name} className="w-full h-full object-cover" />
                    </div>
                    <div className="mt-1.5 text-center">
                      <p className="text-xs font-medium text-[#1C1C1C] truncate w-28">{item.name}</p>
                    </div>
                    <button
                      onClick={() => removeFromCanvas(item.id)}
                      className="absolute -top-1.5 -right-1.5 w-5 h-5 bg-[#1C1C1C] text-white rounded-full text-xs hidden group-hover:flex items-center justify-center"
                    >
                      ×
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Score Panel */}
          {canvas.length > 0 && (
            <div className="bg-[#1C1C1C] rounded-xl p-5 flex items-center gap-6">
              <div className="relative">
                <ScoreRing score={score} size={72} />
                <span className="absolute inset-0 flex items-center justify-center text-white font-bold text-lg">{score}</span>
              </div>
              <div className="flex-1">
                <p className="text-[#556B2F] text-xs font-semibold uppercase tracking-widest">Style Synergy Score</p>
                <p className="text-white font-display text-xl font-medium mt-0.5">
                  {score >= 85 ? "Excellent combination" : score >= 65 ? "Good pairing" : "Building potential"}
                </p>
                <p className="text-white/50 text-xs mt-1">
                  {canvas.length < 3
                    ? "Add shoes or an outer layer to complete the look"
                    : "Well-balanced silhouette · Seasonal cohesion · Try adding an accessory"}
                </p>
              </div>
              <div className="space-y-1.5">
                <p className="text-white/40 text-[10px] uppercase tracking-widest">Suggested additions</p>
                {["Leather Belt", "Silk Scarf", "Watch"].map((s) => (
                  <div key={s} className="text-xs text-white/70 bg-white/10 px-3 py-1.5 rounded-lg">{s}</div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function HelpMePack() {
  const [step, setStep] = useState<"form" | "result">("form");
  const [dest, setDest] = useState("Paris");
  const [dates, setDates] = useState("Oct 14–21");
  const [tripType, setTripType] = useState("Business + Leisure");
  const [dresscode, setDresscode] = useState("Smart Casual");
  const [bags, setBags] = useState("1 Carry-On");

  const checklist = [
    { item: "Camel Blazer", status: "own", outfits: 4 },
    { item: "Ivory Turtleneck", status: "own", outfits: 5 },
    { item: "Charcoal Wide-Leg Trousers", status: "own", outfits: 3 },
    { item: "Silk Slip Dress", status: "own", outfits: 2 },
    { item: "White Oxford Shirt", status: "own", outfits: 4 },
    { item: "Chelsea Boots", status: "own", outfits: 6 },
    { item: "Trench Coat", status: "buy", outfits: 5 },
    { item: "Pointed-Toe Flats", status: "buy", outfits: 3 },
    { item: "Crossbody Bag", status: "optional", outfits: 2 },
    { item: "Statement Earrings", status: "optional", outfits: 0 },
  ];

  const statusColor = { own: "text-[#556B2F] bg-[#E8EDE0]", buy: "text-amber-700 bg-amber-50", optional: "text-[#8C8A82] bg-[#F0EFEA]" };
  const statusLabel = { own: "Already Own", buy: "Rec. Purchase", optional: "Optional" };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-3xl font-semibold text-[#1C1C1C]">Help Me Pack</h1>
        <p className="text-[#8C8A82] text-sm mt-1">Smart packing optimized for your trip and wardrobe</p>
      </div>

      {step === "form" ? (
        <div className="grid grid-cols-[1fr_360px] gap-6">
          <div className="bg-[#F0EFEA] rounded-xl p-8 space-y-5">
            <h2 className="font-display text-xl font-medium text-[#1C1C1C]">Trip Details</h2>

            {[
              { label: "Destination", value: dest, set: setDest, placeholder: "City or country" },
              { label: "Dates", value: dates, set: setDates, placeholder: "e.g. Oct 14–21" },
            ].map((f) => (
              <div key={f.label}>
                <label className="text-xs font-semibold text-[#8C8A82] uppercase tracking-widest block mb-2">{f.label}</label>
                <input
                  value={f.value}
                  onChange={(e) => f.set(e.target.value)}
                  placeholder={f.placeholder}
                  className="w-full px-4 py-3 bg-white border border-[#E2E0D8] rounded-lg text-sm text-[#1C1C1C] outline-none focus:border-[#556B2F] transition-colors"
                />
              </div>
            ))}

            {[
              { label: "Trip Type", value: tripType, set: setTripType, opts: ["Leisure", "Business", "Business + Leisure", "Adventure", "Beach", "Formal Event"] },
              { label: "Dress Code", value: dresscode, set: setDresscode, opts: ["Casual", "Smart Casual", "Business Casual", "Formal", "Black Tie", "Mixed"] },
              { label: "Luggage Limit", value: bags, set: setBags, opts: ["Personal Item Only", "1 Carry-On", "1 Checked Bag", "2 Checked Bags", "No Limit"] },
            ].map((f) => (
              <div key={f.label}>
                <label className="text-xs font-semibold text-[#8C8A82] uppercase tracking-widest block mb-2">{f.label}</label>
                <select
                  value={f.value}
                  onChange={(e) => f.set(e.target.value)}
                  className="w-full px-4 py-3 bg-white border border-[#E2E0D8] rounded-lg text-sm text-[#1C1C1C] outline-none focus:border-[#556B2F] transition-colors"
                >
                  {f.opts.map((o) => <option key={o}>{o}</option>)}
                </select>
              </div>
            ))}

            <button
              onClick={() => setStep("result")}
              className="w-full bg-[#1C1C1C] hover:bg-[#333] text-white font-semibold py-3.5 rounded-lg transition-colors mt-2"
            >
              Generate Pack List
            </button>
          </div>

          <div className="space-y-4">
            <div className="bg-[#1C1C1C] rounded-xl overflow-hidden h-48">
              <img src={EDITORIAL_IMG} alt="Travel fashion" className="w-full h-full object-cover opacity-60" />
            </div>
            <div className="bg-[#F0EFEA] rounded-xl p-5">
              <p className="text-xs font-semibold text-[#8C8A82] uppercase tracking-widest mb-3">Packing Intelligence</p>
              {["Removes redundant items", "Maximizes outfit combinations", "Weather-aware selection", "Daily look generator"].map((f) => (
                <div key={f} className="flex items-center gap-2 py-2 border-b border-[#E2E0D8] last:border-0">
                  <span className="text-[#556B2F] text-sm">✓</span>
                  <span className="text-sm text-[#1C1C1C]">{f}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      ) : (
        <div className="space-y-6">
          <div className="bg-[#1C1C1C] rounded-xl p-6 flex items-center justify-between">
            <div>
              <p className="text-[#556B2F] text-xs font-semibold uppercase tracking-widest">Pack List Ready</p>
              <h2 className="font-display text-2xl font-medium text-white mt-1">{dest} · {dates}</h2>
              <p className="text-white/50 text-sm mt-0.5">{tripType} · {dresscode} · {bags}</p>
            </div>
            <div className="text-right">
              <p className="text-white/40 text-xs uppercase tracking-widest">Outfit combinations</p>
              <p className="font-display text-4xl font-semibold text-white">18</p>
              <p className="text-white/50 text-xs">from 10 items</p>
            </div>
            <button
              onClick={() => setStep("form")}
              className="text-white/50 hover:text-white text-xs border border-white/20 rounded-lg px-4 py-2 transition-colors"
            >
              Edit Trip
            </button>
          </div>

          <div className="grid grid-cols-[1fr_280px] gap-6">
            <div className="bg-[#F0EFEA] rounded-xl overflow-hidden">
              <div className="px-6 py-4 border-b border-[#E2E0D8] flex items-center justify-between">
                <p className="font-medium text-[#1C1C1C] text-sm">Smart Checklist</p>
                <div className="flex gap-2 text-[10px] font-semibold">
                  {(["own", "buy", "optional"] as const).map((s) => (
                    <span key={s} className={`px-2 py-0.5 rounded-full ${statusColor[s]}`}>{statusLabel[s]}</span>
                  ))}
                </div>
              </div>
              {checklist.map((c, i) => (
                <div key={i} className="flex items-center gap-4 px-6 py-3.5 border-b border-[#E2E0D8] last:border-0 hover:bg-[#E2E0D8]/50 transition-colors">
                  <input type="checkbox" defaultChecked={c.status === "own"} className="rounded accent-[#556B2F]" />
                  <span className="text-sm font-medium text-[#1C1C1C] flex-1">{c.item}</span>
                  {c.outfits > 0 && <span className="text-xs text-[#8C8A82]">{c.outfits} outfits</span>}
                  <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${statusColor[c.status as keyof typeof statusColor]}`}>
                    {statusLabel[c.status as keyof typeof statusLabel]}
                  </span>
                </div>
              ))}
            </div>

            <div className="space-y-4">
              <div className="bg-[#F0EFEA] rounded-xl p-5">
                <p className="text-xs font-semibold text-[#8C8A82] uppercase tracking-widest mb-3">Daily Looks</p>
                {["Mon: Blazer + Turtleneck + Trousers", "Tue: Shirt + Jeans + Boots", "Wed: Slip Dress + Trench", "Thu: Blazer + Shirt + Trousers"].map((l) => (
                  <div key={l} className="text-xs text-[#1C1C1C] py-2 border-b border-[#E2E0D8] last:border-0">{l}</div>
                ))}
              </div>
              <div className="bg-[#E8EDE0] rounded-xl p-5">
                <p className="text-xs font-semibold text-[#556B2F] uppercase tracking-widest mb-2">Optimizer Result</p>
                <p className="text-sm text-[#1C1C1C]">2 redundant items removed · Saved 0.8kg luggage weight</p>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function WeatherPage() {
  const forecast = [
    { day: "Thu", icon: "⛅", high: 18, low: 11, desc: "Partly Cloudy", wind: 12, humid: 65 },
    { day: "Fri", icon: "☀️", high: 22, low: 14, desc: "Sunny", wind: 8, humid: 50 },
    { day: "Sat", icon: "🌧️", high: 15, low: 10, desc: "Rainy", wind: 20, humid: 85 },
    { day: "Sun", icon: "🌥️", high: 16, low: 10, desc: "Overcast", wind: 15, humid: 72 },
    { day: "Mon", icon: "☀️", high: 21, low: 13, desc: "Sunny", wind: 6, humid: 45 },
    { day: "Tue", icon: "⛅", high: 19, low: 12, desc: "Partly Cloudy", wind: 10, humid: 58 },
    { day: "Wed", icon: "🌧️", high: 13, low: 8, desc: "Heavy Rain", wind: 25, humid: 90 },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-3xl font-semibold text-[#1C1C1C]">Weather & Style</h1>
        <p className="text-[#8C8A82] text-sm mt-1">New York, NY · What to wear based on conditions</p>
      </div>

      {/* Today Hero */}
      <div className="bg-[#1C1C1C] rounded-2xl p-8 flex gap-8">
        <div>
          <p className="text-white/40 text-xs uppercase tracking-widest">Today · Thursday</p>
          <div className="flex items-center gap-4 mt-2">
            <span className="text-6xl">⛅</span>
            <div>
              <p className="font-display text-6xl font-light text-white">18°</p>
              <p className="text-white/50 text-sm">Partly Cloudy · Feels like 15°</p>
            </div>
          </div>
          <div className="flex gap-6 mt-4">
            {[{ l: "Wind", v: "12 km/h" }, { l: "Humidity", v: "65%" }, { l: "UV Index", v: "3 Low" }].map((s) => (
              <div key={s.l}>
                <p className="text-white/30 text-xs">{s.l}</p>
                <p className="text-white/80 text-sm font-medium">{s.v}</p>
              </div>
            ))}
          </div>
        </div>
        <div className="border-l border-white/10 pl-8 flex-1">
          <p className="text-[#556B2F] text-xs font-semibold uppercase tracking-widest">What to Wear Today</p>
          <p className="font-display text-xl font-medium text-white mt-2">Layer for the afternoon chill</p>
          <p className="text-white/50 text-sm mt-1.5 leading-relaxed">
            Start with your ivory turtleneck as a base. Your camel blazer handles the 18° morning. Wind at 12 km/h means you don't need a heavy coat. Opt for closed-toe shoes — Chelsea boots are perfect.
          </p>
          <div className="flex gap-2 mt-4">
            {["Ivory Turtleneck", "Camel Blazer", "Chelsea Boots"].map((i) => (
              <span key={i} className="text-xs bg-white/10 text-white/70 px-3 py-1.5 rounded-lg">{i}</span>
            ))}
          </div>
        </div>
      </div>

      {/* 7-Day Forecast */}
      <div className="grid grid-cols-7 gap-3">
        {forecast.map((f, i) => (
          <div key={i} className={`rounded-xl p-4 text-center ${i === 0 ? "bg-[#556B2F] text-white" : "bg-[#F0EFEA]"}`}>
            <p className={`text-xs font-semibold ${i === 0 ? "text-white/70" : "text-[#8C8A82]"}`}>{f.day}</p>
            <span className="text-2xl block my-2">{f.icon}</span>
            <p className={`text-sm font-semibold ${i === 0 ? "text-white" : "text-[#1C1C1C]"}`}>{f.high}°</p>
            <p className={`text-xs ${i === 0 ? "text-white/60" : "text-[#8C8A82]"}`}>{f.low}°</p>
            <p className={`text-[10px] mt-2 leading-tight ${i === 0 ? "text-white/60" : "text-[#8C8A82]"}`}>{f.desc}</p>
          </div>
        ))}
      </div>

      {/* Weekly Outfit Guide */}
      <div className="bg-[#F0EFEA] rounded-xl p-6">
        <h3 className="font-display text-lg font-medium text-[#1C1C1C] mb-4">Weekly Outfit Guide</h3>
        <div className="grid grid-cols-7 gap-3">
          {forecast.map((f, i) => (
            <div key={i} className="text-center">
              <p className="text-xs font-semibold text-[#8C8A82]">{f.day}</p>
              <p className="text-[10px] text-[#1C1C1C] mt-1 leading-tight">
                {f.high >= 20 ? "Light dress + sandals" : f.high >= 16 ? "Blazer + jeans" : f.icon === "🌧️" ? "Trench + boots" : "Layered knit"}
              </p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function ShouldIBuy() {
  const [analyzed, setAnalyzed] = useState(false);
  const [url, setUrl] = useState("");

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-3xl font-semibold text-[#1C1C1C]">Should I Buy?</h1>
        <p className="text-[#8C8A82] text-sm mt-1">Upload a retail screenshot and get an AI purchase analysis</p>
      </div>

      <div className="grid grid-cols-[1fr_360px] gap-6">
        <div className="space-y-4">
          {!analyzed ? (
            <div className="bg-[#F0EFEA] rounded-xl p-8 border-2 border-dashed border-[#E2E0D8] flex flex-col items-center justify-center text-center min-h-[280px]">
              <div className="w-14 h-14 rounded-full bg-[#E2E0D8] flex items-center justify-center mb-4">
                <span className="text-2xl">📷</span>
              </div>
              <p className="font-medium text-[#1C1C1C]">Drop a retail screenshot</p>
              <p className="text-sm text-[#8C8A82] mt-1">or paste a product URL</p>
              <input
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://www.store.com/product…"
                className="mt-4 w-full max-w-sm px-4 py-2.5 bg-white border border-[#E2E0D8] rounded-lg text-sm text-[#1C1C1C] outline-none focus:border-[#556B2F] transition-colors"
              />
              <button
                onClick={() => setAnalyzed(true)}
                className="mt-4 bg-[#1C1C1C] hover:bg-[#333] text-white text-sm font-semibold px-6 py-2.5 rounded-lg transition-colors"
              >
                Analyze Purchase
              </button>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="bg-[#F0EFEA] rounded-xl overflow-hidden flex gap-6 p-6">
                <div className="w-32 h-40 bg-[#E2E0D8] rounded-xl overflow-hidden shrink-0">
                  <img src={FLATLAY_IMG} alt="Item being analyzed" className="w-full h-full object-cover" />
                </div>
                <div>
                  <p className="text-xs text-[#8C8A82] font-medium uppercase tracking-wide">Analyzed Item</p>
                  <h3 className="font-display text-xl font-medium text-[#1C1C1C] mt-1">Cream Ribbed Cardigan</h3>
                  <p className="text-[#8C8A82] text-sm mt-0.5">Totême · $285 USD</p>

                  <div className="flex items-center gap-3 mt-4">
                    <div className="relative">
                      <ScoreRing score={71} size={64} />
                      <span className="absolute inset-0 flex items-center justify-center font-bold text-sm text-[#1C1C1C]">71</span>
                    </div>
                    <div>
                      <p className="font-semibold text-[#1C1C1C]">Purchase Score</p>
                      <p className="text-[#8C8A82] text-xs">Good value · Some overlap detected</p>
                    </div>
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-3 gap-3">
                {[
                  { metric: "Versatility", score: 85, note: "Works with 14 existing items" },
                  { metric: "Budget Alignment", score: 72, note: "$285 is above avg. price point" },
                  { metric: "Redundancy Risk", score: 58, note: "Similar to Ivory Turtleneck" },
                ].map((m) => (
                  <div key={m.metric} className="bg-[#F0EFEA] rounded-xl p-4">
                    <p className="text-xs font-semibold text-[#8C8A82] uppercase tracking-widest">{m.metric}</p>
                    <p className="font-display text-3xl font-semibold text-[#1C1C1C] mt-2">{m.score}</p>
                    <div className="h-1 bg-[#E2E0D8] rounded-full mt-2">
                      <div className="h-full bg-[#556B2F] rounded-full" style={{ width: `${m.score}%` }} />
                    </div>
                    <p className="text-[11px] text-[#8C8A82] mt-1.5">{m.note}</p>
                  </div>
                ))}
              </div>

              <div className="bg-[#E8EDE0] rounded-xl p-4 border border-[#556B2F]/20">
                <p className="text-xs font-semibold text-[#556B2F] uppercase tracking-widest">AI Verdict</p>
                <p className="text-sm text-[#1C1C1C] mt-1.5 leading-relaxed">
                  Good versatility but overlaps with your Ivory Turtleneck (87% similarity). Consider waiting for a sale or opting for a different color to expand your palette. If you love ribbed knits, this could replace the turtleneck rather than add to it.
                </p>
              </div>

              <button
                onClick={() => { setAnalyzed(false); setUrl(""); }}
                className="text-sm text-[#8C8A82] hover:text-[#1C1C1C] transition-colors"
              >
                ← Analyze another item
              </button>
            </div>
          )}
        </div>

        <div className="space-y-4">
          <div className="bg-[#F0EFEA] rounded-xl p-5">
            <p className="text-xs font-semibold text-[#8C8A82] uppercase tracking-widest mb-3">Similar Items You Own</p>
            {wardrobeItems.slice(0, 3).map((item) => (
              <div key={item.id} className="flex items-center gap-3 py-2.5 border-b border-[#E2E0D8] last:border-0">
                <div className="w-10 h-12 rounded bg-[#E2E0D8] overflow-hidden shrink-0">
                  <img src={item.img} alt={item.name} className="w-full h-full object-cover" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-semibold text-[#1C1C1C] truncate">{item.name}</p>
                  <p className="text-[10px] text-[#8C8A82]">{item.color}</p>
                </div>
                <span className="text-xs text-[#556B2F] font-semibold">78%</span>
              </div>
            ))}
          </div>
          <div className="bg-[#1C1C1C] rounded-xl overflow-hidden h-40">
            <img src={RACK_IMG} alt="Wardrobe rack" className="w-full h-full object-cover opacity-50" />
          </div>
        </div>
      </div>
    </div>
  );
}

function AIStylist() {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState([
    {
      role: "ai",
      text: "Hi Sophia! I've reviewed your wardrobe — 84 items across 8 categories. What would you like to style today? I can suggest outfits for specific occasions, help you work with a new piece, or plan a capsule wardrobe for an upcoming trip.",
    },
  ]);

  const quickPrompts = [
    "What should I wear to a dinner party?",
    "Build me a Monday-morning look",
    "How can I style my camel blazer differently?",
    "I have a job interview tomorrow",
  ];

  const send = () => {
    if (!input.trim()) return;
    const userMsg = { role: "user", text: input };
    const aiResponse = {
      role: "ai",
      text: `Great choice! Based on today's 18°C weather and your wardrobe, I'd suggest pairing your Ivory Turtleneck with the Charcoal Wide-Leg Trousers and Chelsea Boots. The camel blazer ties it together beautifully — that's a 94/100 synergy score. Want me to show you alternate colorways or shoes?`,
    };
    setMessages((m) => [...m, userMsg, aiResponse]);
    setInput("");
  };

  return (
    <div className="space-y-6 flex flex-col h-full">
      <div>
        <h1 className="font-display text-3xl font-semibold text-[#1C1C1C]">AI Stylist</h1>
        <p className="text-[#8C8A82] text-sm mt-1">Your personal wardrobe intelligence, always on</p>
      </div>

      <div className="flex gap-6 flex-1 min-h-0">
        <div className="flex-1 flex flex-col bg-[#F0EFEA] rounded-xl overflow-hidden">
          {/* Messages */}
          <div className="flex-1 overflow-y-auto p-6 space-y-4">
            {messages.map((m, i) => (
              <div key={i} className={`flex gap-3 ${m.role === "user" ? "flex-row-reverse" : ""}`}>
                <div className={`w-8 h-8 rounded-full shrink-0 flex items-center justify-center text-xs font-semibold ${m.role === "ai" ? "bg-[#556B2F] text-white" : "bg-[#1C1C1C] text-white"}`}>
                  {m.role === "ai" ? "AI" : "S"}
                </div>
                <div className={`max-w-[75%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${m.role === "ai" ? "bg-white text-[#1C1C1C] rounded-tl-none" : "bg-[#1C1C1C] text-white rounded-tr-none"}`}>
                  {m.text}
                </div>
              </div>
            ))}

            {/* Outfit card */}
            <div className="ml-11 bg-white rounded-xl overflow-hidden border border-[#E2E0D8] max-w-sm">
              <div className="h-32 overflow-hidden">
                <img src={OUTFIT_IMG} alt="Suggested outfit" className="w-full h-full object-cover object-top" />
              </div>
              <div className="p-4">
                <div className="flex items-center justify-between">
                  <p className="text-sm font-semibold text-[#1C1C1C]">Autumn Business Casual</p>
                  <span className="text-xs font-semibold text-[#556B2F] bg-[#E8EDE0] px-2 py-0.5 rounded-full">94/100</span>
                </div>
                <p className="text-xs text-[#8C8A82] mt-1">Blazer · Turtleneck · Trousers · Boots</p>
                <button className="mt-3 w-full text-xs font-semibold border border-[#E2E0D8] rounded-lg py-2 text-[#1C1C1C] hover:bg-[#F0EFEA] transition-colors">
                  Save to Outfit Studio
                </button>
              </div>
            </div>
          </div>

          {/* Quick prompts */}
          <div className="px-6 py-3 border-t border-[#E2E0D8] flex gap-2 flex-wrap">
            {quickPrompts.map((q) => (
              <button
                key={q}
                onClick={() => setInput(q)}
                className="text-xs bg-white border border-[#E2E0D8] text-[#1C1C1C] px-3 py-1.5 rounded-full hover:border-[#556B2F] transition-colors"
              >
                {q}
              </button>
            ))}
          </div>

          {/* Input */}
          <div className="p-4 border-t border-[#E2E0D8] flex gap-3">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && send()}
              placeholder="Ask your AI stylist anything…"
              className="flex-1 px-4 py-2.5 bg-white border border-[#E2E0D8] rounded-xl text-sm text-[#1C1C1C] outline-none focus:border-[#556B2F] transition-colors"
            />
            <button
              onClick={send}
              className="bg-[#556B2F] hover:bg-[#6B8A3A] text-white px-4 py-2.5 rounded-xl text-sm font-semibold transition-colors"
            >
              Send
            </button>
          </div>
        </div>

        {/* Sidebar context */}
        <div className="w-64 space-y-4">
          <div className="bg-[#F0EFEA] rounded-xl p-5">
            <p className="text-xs font-semibold text-[#8C8A82] uppercase tracking-widest mb-3">Active Context</p>
            {[
              { l: "Weather", v: "18°C, Cloudy" },
              { l: "Occasion", v: "Work Day" },
              { l: "Style Profile", v: "Smart Casual" },
              { l: "Wardrobe Items", v: "84 pieces" },
            ].map((c) => (
              <div key={c.l} className="flex justify-between py-2 border-b border-[#E2E0D8] last:border-0">
                <span className="text-xs text-[#8C8A82]">{c.l}</span>
                <span className="text-xs font-medium text-[#1C1C1C]">{c.v}</span>
              </div>
            ))}
          </div>
          <div className="bg-[#1C1C1C] rounded-xl overflow-hidden h-36">
            <img src={EDITORIAL_IMG} alt="Style editorial" className="w-full h-full object-cover opacity-60" />
          </div>
        </div>
      </div>
    </div>
  );
}

function StyleProfile() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-3xl font-semibold text-[#1C1C1C]">Style Profile</h1>
        <p className="text-[#8C8A82] text-sm mt-1">Your taste, preferences, and aesthetic fingerprint</p>
      </div>

      <div className="grid grid-cols-[1fr_280px] gap-6">
        <div className="space-y-5">
          <div className="bg-[#F0EFEA] rounded-xl p-6">
            <h3 className="font-display text-lg font-medium text-[#1C1C1C] mb-4">Style Aesthetics</h3>
            {[
              { label: "Minimalist", pct: 80 },
              { label: "Classic / Timeless", pct: 72 },
              { label: "Smart Casual", pct: 65 },
              { label: "Editorial / Fashion-Forward", pct: 48 },
              { label: "Boho / Relaxed", pct: 20 },
            ].map((s) => (
              <div key={s.label} className="mb-4">
                <div className="flex justify-between text-sm mb-1.5">
                  <span className="font-medium text-[#1C1C1C]">{s.label}</span>
                  <span className="text-[#8C8A82]">{s.pct}%</span>
                </div>
                <div className="h-2 bg-[#E2E0D8] rounded-full overflow-hidden">
                  <div className="h-full bg-[#556B2F] rounded-full transition-all" style={{ width: `${s.pct}%` }} />
                </div>
              </div>
            ))}
          </div>

          <div className="grid grid-cols-2 gap-5">
            <div className="bg-[#F0EFEA] rounded-xl p-6">
              <h3 className="font-display text-lg font-medium text-[#1C1C1C] mb-4">Favorite Colors</h3>
              <div className="flex gap-2 flex-wrap">
                {[
                  { name: "Ivory", hex: "#FFFFF0" },
                  { name: "Camel", hex: "#C19A6B" },
                  { name: "Charcoal", hex: "#36454F" },
                  { name: "Olive", hex: "#556B2F" },
                  { name: "Indigo", hex: "#4B0082" },
                  { name: "Blush", hex: "#FFB7C5" },
                ].map((c) => (
                  <div key={c.name} className="flex flex-col items-center gap-1">
                    <div className="w-8 h-8 rounded-full border border-[#E2E0D8]" style={{ backgroundColor: c.hex }} />
                    <span className="text-[9px] text-[#8C8A82]">{c.name}</span>
                  </div>
                ))}
              </div>
            </div>
            <div className="bg-[#F0EFEA] rounded-xl p-6">
              <h3 className="font-display text-lg font-medium text-[#1C1C1C] mb-4">Preferred Occasions</h3>
              {["Work / Office", "Smart Casual", "Weekend Leisure", "Evening / Dinner", "Travel"].map((o) => (
                <div key={o} className="flex items-center gap-2 py-1.5">
                  <div className="w-1.5 h-1.5 rounded-full bg-[#556B2F]" />
                  <span className="text-sm text-[#1C1C1C]">{o}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="space-y-4">
          <div className="bg-[#1C1C1C] rounded-2xl overflow-hidden h-52">
            <img src={EDITORIAL_IMG} alt="Style profile editorial" className="w-full h-full object-cover opacity-70" />
            <div className="absolute inset-0 flex items-end p-5" style={{ position: "relative", marginTop: "-208px" }}>
              <div>
                <p className="text-white/60 text-xs">Your Style Archetype</p>
                <p className="font-display text-xl text-white font-medium">The Refined Minimalist</p>
              </div>
            </div>
          </div>
          <div className="bg-[#F0EFEA] rounded-xl p-5">
            <p className="text-xs font-semibold text-[#8C8A82] uppercase tracking-widest mb-3">Size Profile</p>
            {[["Top", "S / EU 36"], ["Bottom", "S / EU 36"], ["Shoes", "EU 38"], ["Dress", "XS-S"]].map(([l, v]) => (
              <div key={l} className="flex justify-between py-2 border-b border-[#E2E0D8] last:border-0">
                <span className="text-xs text-[#8C8A82]">{l}</span>
                <span className="text-xs font-semibold text-[#1C1C1C]">{v}</span>
              </div>
            ))}
          </div>
          <button className="w-full bg-[#556B2F] hover:bg-[#6B8A3A] text-white text-sm font-semibold py-3 rounded-lg transition-colors">
            Edit Profile
          </button>
        </div>
      </div>
    </div>
  );
}

function FindSimilar() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-3xl font-semibold text-[#1C1C1C]">Find Similar</h1>
        <p className="text-[#8C8A82] text-sm mt-1">Upload a photo and find matching pieces from top retailers</p>
      </div>

      <div className="grid grid-cols-[320px_1fr] gap-6">
        <div className="space-y-4">
          <div className="bg-[#F0EFEA] rounded-xl overflow-hidden border-2 border-dashed border-[#E2E0D8] flex flex-col items-center justify-center text-center p-8">
            <span className="text-3xl mb-3">🔍</span>
            <p className="font-medium text-[#1C1C1C] text-sm">Drop or paste an image</p>
            <p className="text-xs text-[#8C8A82] mt-1">of any clothing item</p>
            <button className="mt-4 bg-[#1C1C1C] text-white text-xs font-semibold px-5 py-2.5 rounded-lg hover:bg-[#333] transition-colors">
              Browse Files
            </button>
          </div>
          <div className="bg-[#F0EFEA] rounded-xl overflow-hidden h-40">
            <img src={FLATLAY_IMG} alt="Reference item" className="w-full h-full object-cover" />
          </div>
          <div className="bg-[#F0EFEA] rounded-xl p-4">
            <p className="text-xs font-semibold text-[#8C8A82] uppercase tracking-widest mb-2">Reference Item</p>
            <p className="text-sm font-medium text-[#1C1C1C]">White Shirt & Brown Boots</p>
            <p className="text-xs text-[#8C8A82] mt-0.5">Uploaded · Analyzing…</p>
          </div>
        </div>

        <div>
          <p className="text-xs font-semibold text-[#8C8A82] uppercase tracking-widest mb-4">Similar Results — 12 found</p>
          <div className="grid grid-cols-3 gap-4">
            {[
              { name: "Classic Oxford Shirt", brand: "COS", price: "$79", match: 96 },
              { name: "Linen Button-Down", brand: "Everlane", price: "$68", match: 91 },
              { name: "Poplin Shirt", brand: "Arket", price: "$89", match: 88 },
              { name: "Oversized Cotton Shirt", brand: "& Other Stories", price: "$59", match: 84 },
              { name: "Relaxed Oxford", brand: "Uniqlo", price: "$39", match: 80 },
              { name: "Silk Blend Shirt", brand: "Massimo Dutti", price: "$129", match: 77 },
            ].map((r, i) => (
              <div key={i} className="bg-[#F0EFEA] rounded-xl overflow-hidden group cursor-pointer hover:shadow-md transition-shadow">
                <div className="h-40 bg-[#E2E0D8] overflow-hidden">
                  <img src={wardrobeItems[i % wardrobeItems.length].img} alt={r.name} className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500" />
                </div>
                <div className="p-3">
                  <div className="flex items-start justify-between gap-1">
                    <div>
                      <p className="text-xs font-semibold text-[#1C1C1C] leading-tight">{r.name}</p>
                      <p className="text-[10px] text-[#8C8A82]">{r.brand}</p>
                    </div>
                    <span className="text-[10px] font-bold text-[#556B2F] bg-[#E8EDE0] px-1.5 py-0.5 rounded-full shrink-0">{r.match}%</span>
                  </div>
                  <div className="flex items-center justify-between mt-2">
                    <span className="text-sm font-semibold text-[#1C1C1C]">{r.price}</span>
                    <button className="text-[10px] text-[#556B2F] font-semibold hover:underline">View →</button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function Settings() {
  const [notifications, setNotifications] = useState(true);
  const [weatherSync, setWeatherSync] = useState(true);
  const [aiTips, setAiTips] = useState(false);

  const Toggle = ({ value, onChange }: { value: boolean; onChange: () => void }) => (
    <button
      onClick={onChange}
      className={`w-10 h-6 rounded-full transition-colors relative ${value ? "bg-[#556B2F]" : "bg-[#E2E0D8]"}`}
    >
      <span className={`absolute top-1 w-4 h-4 bg-white rounded-full shadow transition-transform ${value ? "left-5" : "left-1"}`} />
    </button>
  );

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h1 className="font-display text-3xl font-semibold text-[#1C1C1C]">Settings</h1>
        <p className="text-[#8C8A82] text-sm mt-1">Manage your account and preferences</p>
      </div>

      {[
        {
          title: "Account",
          items: [
            { label: "Full Name", value: "Sophia Laurent", type: "text" },
            { label: "Email", value: "sophia@example.com", type: "text" },
            { label: "Location", value: "New York, NY", type: "text" },
          ],
        },
        {
          title: "Preferences",
          items: [
            { label: "Default Currency", value: "USD", type: "select", opts: ["USD", "EUR", "GBP", "JPY"] },
            { label: "Temperature Unit", value: "Celsius", type: "select", opts: ["Celsius", "Fahrenheit"] },
            { label: "Size System", value: "EU", type: "select", opts: ["EU", "US", "UK"] },
          ],
        },
      ].map((section) => (
        <div key={section.title} className="bg-[#F0EFEA] rounded-xl p-6 space-y-4">
          <h3 className="font-display text-lg font-medium text-[#1C1C1C]">{section.title}</h3>
          {section.items.map((item) => (
            <div key={item.label} className="flex items-center justify-between">
              <label className="text-sm font-medium text-[#1C1C1C]">{item.label}</label>
              {item.type === "text" ? (
                <input
                  defaultValue={item.value}
                  className="bg-white border border-[#E2E0D8] rounded-lg px-3 py-2 text-sm text-[#1C1C1C] outline-none focus:border-[#556B2F] transition-colors w-56"
                />
              ) : (
                <select className="bg-white border border-[#E2E0D8] rounded-lg px-3 py-2 text-sm text-[#1C1C1C] outline-none w-56">
                  {item.opts?.map((o) => <option key={o}>{o}</option>)}
                </select>
              )}
            </div>
          ))}
        </div>
      ))}

      <div className="bg-[#F0EFEA] rounded-xl p-6 space-y-4">
        <h3 className="font-display text-lg font-medium text-[#1C1C1C]">Notifications & AI</h3>
        {[
          { label: "Daily Outfit Recommendations", sub: "Get your AI pick every morning", val: notifications, set: () => setNotifications(!notifications) },
          { label: "Weather Sync", sub: "Auto-adjust suggestions for local forecast", val: weatherSync, set: () => setWeatherSync(!weatherSync) },
          { label: "AI Style Tips", sub: "Weekly wardrobe insights and gap analysis", val: aiTips, set: () => setAiTips(!aiTips) },
        ].map((s) => (
          <div key={s.label} className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-[#1C1C1C]">{s.label}</p>
              <p className="text-xs text-[#8C8A82]">{s.sub}</p>
            </div>
            <Toggle value={s.val} onChange={s.set} />
          </div>
        ))}
      </div>

      <button className="bg-[#556B2F] hover:bg-[#6B8A3A] text-white text-sm font-semibold px-8 py-3 rounded-lg transition-colors">
        Save Changes
      </button>
    </div>
  );
}

export default function App() {
  const [page, setPage] = useState<Page>("dashboard");

  const renderPage = () => {
    switch (page) {
      case "dashboard": return <Dashboard onNav={setPage} />;
      case "wardrobe": return <MyWardrobe />;
      case "wardrobe-gaps": return <WardrobeGapsPage />;
      case "outfit-studio": return <OutfitStudio />;
      case "help-me-pack": return <HelpMePack />;
      case "weather": return <WeatherPage />;
      case "should-i-buy": return <ShouldIBuy />;
      case "ai-stylist": return <AIStylist />;
      case "style-profile": return <StyleProfile />;
      case "find-similar": return <FindSimilar />;
      case "settings": return <Settings />;
    }
  };

  return (
    <div className="flex h-screen overflow-hidden bg-[#FAF9F6]">
      <Sidebar current={page} onNav={setPage} />
      <main className="ml-[260px] flex-1 overflow-y-auto">
        <div className="p-10 max-w-[1200px]">
          {renderPage()}
        </div>
      </main>
    </div>
  );
}
