import { Component, type ErrorInfo, type ReactNode } from "react"

// A failure in the 3D scene must not blank the whole app: show a message and a way back to the grid instead.
export default class ViewBoundary extends Component<
  { children: ReactNode; onBack: () => void },
  { failed: boolean }
> {
  state = { failed: false }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("3D wardrobe failed", error, info.componentStack)
  }

  render() {
    if (!this.state.failed) return this.props.children
    return (
      <div className="rounded-xl border border-amber-200 bg-amber-50 px-6 py-8 text-center">
        <p className="font-medium text-[#1C1C1C]">The 3D wardrobe could not be displayed.</p>
        <p className="mt-1 text-sm text-amber-800">
          Your clothes are safe. Your browser may not support 3D graphics, or one item has unusable data.
        </p>
        <button
          type="button"
          onClick={this.props.onBack}
          className="mt-4 rounded-lg bg-[#1C1C1C] px-4 py-2 text-sm font-semibold text-white hover:bg-black"
        >
          Back to the grid
        </button>
      </div>
    )
  }
}
