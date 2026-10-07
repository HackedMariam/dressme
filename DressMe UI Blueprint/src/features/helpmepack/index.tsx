import { useState } from "react"
import {
  CORE_IDS,
  DEFAULT_TRIP,
  ITEMS,
  OPTIONAL_IDS,
  OPTIMIZER,
  byId,
  revisionFor,
  type Revision,
  type Step,
  type Trip,
} from "./data"
import TripContext from "./form"
import TripAnalysis from "./analysis/TripAnalysis"
import WardrobeAnalysis from "./analysis/WardrobeAnalysis"
import Processing from "./analysis/Processing"
import Outfits from "./looks/Outfits"
import Optimization from "./packlist/Optimization"
import PackList from "./packlist/PackList"
import Coverage from "./packlist/Coverage"
import ItemDetail from "./packlist/ItemDetail"
import Purchase from "./packlist/Purchase"
import Feedback from "./packlist/Feedback"
import AgentActivity from "./packlist/AgentActivity"
import { Stepper } from "./ui"

const initialPacked = () => {
  const map: Record<string, boolean> = {}
  ITEMS.forEach((i) => {
    map[i.id] = CORE_IDS.includes(i.id) || i.id === "flats"
  })
  return map
}

export default function HelpMePack() {
  const [step, setStep] = useState<Step>("form")
  const [trip, setTrip] = useState<Trip>(DEFAULT_TRIP)
  const [packed, setPacked] = useState<Record<string, boolean>>(initialPacked)
  const [detailId, setDetailId] = useState<string | null>(null)
  const [showPurchase, setShowPurchase] = useState(false)
  const [showAgents, setShowAgents] = useState(false)
  const [purchaseState, setPurchaseState] =
    useState<"pending" | "included" | "skipped">("pending")
  const [revision, setRevision] = useState<Revision | null>(null)
  const [revisionReason, setRevisionReason] = useState<string | null>(null)

  const removedIds = revision?.removedIds ?? []
  const coreItems = CORE_IDS.filter((id) => !removedIds.includes(id)).map(byId)
  const items =
    purchaseState === "included" ? [...coreItems, byId("flats")] : coreItems
  const optionalItems = OPTIONAL_IDS.map(byId)
  const combos = revision ? revision.combos : OPTIMIZER.combos
  const coverageBase = revision ? revision.coverage : OPTIMIZER.baseCoverage
  const unpacked = items.filter((i) => packed[i.id] === false).length
  const coverage = Math.max(
    50,
    coverageBase -
      unpacked * 4 -
      (purchaseState === "skipped" ? 3 : 0) +
      (purchaseState === "included" ? 2 : 0),
  )

  const togglePacked = (id: string) =>
    setPacked((p) => ({ ...p, [id]: !(p[id] ?? true) }))

  const go = (s: Step) => {
    setStep(s)
    document.querySelector("main")?.scrollTo({ top: 0 })
  }

  const regenerate = (reason: string) => {
    setRevision(revisionFor(reason))
    setRevisionReason(reason)
    setPurchaseState("pending")
  }

  const screen = () => {
    switch (step) {
      case "form":
        return (
          <TripContext
            trip={trip}
            setTrip={setTrip}
            onNext={() => go("trip")}
          />
        )
      case "trip":
        return (
          <TripAnalysis
            trip={trip}
            onBack={() => go("form")}
            onNext={() => go("wardrobe")}
          />
        )
      case "wardrobe":
        return (
          <WardrobeAnalysis
            onBack={() => go("trip")}
            onNext={() => go("processing")}
            onOpenItem={setDetailId}
          />
        )
      case "processing":
        return (
          <Processing
            onBack={() => go("wardrobe")}
            onNext={() => go("outfits")}
            onOpenAgents={() => setShowAgents(true)}
          />
        )
      case "outfits":
        return (
          <Outfits
            onBack={() => go("processing")}
            onNext={() => go("optimize")}
            onOpenItem={setDetailId}
          />
        )
      case "optimize":
        return (
          <Optimization
            onBack={() => go("outfits")}
            onNext={() => go("list")}
          />
        )
      case "list":
        return (
          <PackList
            trip={trip}
            items={items}
            optionalItems={optionalItems}
            packed={packed}
            onToggle={togglePacked}
            coverage={coverage}
            combos={combos}
            purchaseState={purchaseState}
            revisionSummary={revision ? revision.summary : null}
            onBack={() => go("optimize")}
            onNext={() => go("coverage")}
            onOpenItem={setDetailId}
            onOpenPurchase={() => setShowPurchase(true)}
            onEditTrip={() => go("form")}
          />
        )
      case "coverage":
        return (
          <Coverage
            coverage={coverage}
            combos={combos}
            itemCount={items.length}
            unpacked={unpacked}
            purchaseState={purchaseState}
            onBack={() => go("list")}
            onNext={() => go("feedback")}
            onReview={() => go("list")}
            onOpenPurchase={() => setShowPurchase(true)}
          />
        )
      case "feedback":
        return (
          <Feedback
            coverage={coverage}
            combos={combos}
            itemCount={items.length}
            revision={revision}
            revisionReason={revisionReason}
            onBack={() => go("coverage")}
            onViewPlan={() => go("list")}
            onRegenerate={regenerate}
          />
        )
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between gap-6">
        <div>
          <h1 className="font-display text-3xl font-semibold text-[#1C1C1C]">
            Help Me Pack
          </h1>
          <p className="text-[#8C8A82] text-sm mt-1">
            Smart packing optimized for your trip and wardrobe
          </p>
        </div>
        {step !== "form" && (
          <div className="text-right">
            <p className="text-sm font-medium text-[#1C1C1C]">
              {trip.dest} · {trip.dates}
            </p>
            <p className="text-[11px] text-[#8C8A82] mt-0.5">
              {trip.tripType} · {trip.dresscode} · {trip.bags}
            </p>
          </div>
        )}
      </div>

      <Stepper step={step} onGo={go} onOpenAgents={() => setShowAgents(true)} />

      {screen()}

      {detailId && (
        <ItemDetail item={byId(detailId)} onClose={() => setDetailId(null)} />
      )}

      {showPurchase && (
        <Purchase
          state={purchaseState}
          onClose={() => setShowPurchase(false)}
          onInclude={() => {
            setPurchaseState("included")
            setShowPurchase(false)
          }}
          onSkip={() => {
            setPurchaseState("skipped")
            setShowPurchase(false)
          }}
        />
      )}

      {showAgents && <AgentActivity onClose={() => setShowAgents(false)} />}
    </div>
  )
}
