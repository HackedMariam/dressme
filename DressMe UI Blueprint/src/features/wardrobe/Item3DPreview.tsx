import { Component, Suspense, useMemo, type ReactNode } from "react"
import { Canvas } from "@react-three/fiber"
import { ContactShadows, Environment, OrbitControls, useGLTF } from "@react-three/drei"
import * as THREE from "three"

function PreviewModel({ url }: { url: string }) {
  const { scene } = useGLTF(url)

  const { position, scale } = useMemo(() => {
    const box = new THREE.Box3().setFromObject(scene)
    const size = box.getSize(new THREE.Vector3())
    const center = box.getCenter(new THREE.Vector3())
    const largest = Math.max(size.x, size.y, size.z, 0.001)
    const factor = 1.7 / largest
    return {
      position: [-center.x * factor, -box.min.y * factor, -center.z * factor] as const,
      scale: factor,
    }
  }, [scene])

  return (
    <group position={position} scale={scale}>
      <primitive object={scene} />
    </group>
  )
}

class PreviewErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  render() {
    if (this.state.failed) {
      return (
        <div className="flex h-full items-center justify-center px-6 text-center text-xs text-[#8C8A82]">
          Could not load this 3D model.
        </div>
      )
    }
    return this.props.children
  }
}

export default function Item3DPreview({ url }: { url: string }) {
  return (
    <div className="relative h-[280px] overflow-hidden rounded-xl border border-[#E2E0D8] bg-[#F0EFEA]">
      <PreviewErrorBoundary>
        <Canvas shadows dpr={[1, 2]} camera={{ position: [0, 1.1, 3.4], fov: 42 }}>
          <color attach="background" args={["#F0EFEA"]} />
          <ambientLight intensity={0.7} />
          <directionalLight position={[2, 3, 2]} intensity={1.6} castShadow />
          <Suspense fallback={null}>
            <PreviewModel url={url} />
            <Environment preset="city" />
            <ContactShadows position={[0, 0, 0]} opacity={0.3} scale={4} blur={2.4} far={2} />
          </Suspense>
          <OrbitControls
            enablePan={false}
            minPolarAngle={Math.PI / 5}
            maxPolarAngle={Math.PI / 1.9}
            minDistance={1.2}
            maxDistance={5}
            target={[0, 0.85, 0]}
          />
        </Canvas>
      </PreviewErrorBoundary>
      <span className="pointer-events-none absolute left-3 top-3 rounded-full bg-[#1C1C1C]/80 px-2.5 py-1 text-[10px] font-semibold text-white">
        3D item
      </span>
    </div>
  )
}
