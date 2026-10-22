import { Suspense, useEffect, useMemo, useState } from "react";
import { Canvas } from "@react-three/fiber";
import { ContactShadows, Environment, OrbitControls, useGLTF } from "@react-three/drei";
import * as THREE from "three";

const DEFAULT_AVATAR_URL = "/models/avatar.glb";

function AvatarModel({ url, onInfo }: { url: string; onInfo?: (heightMeters: number) => void }) {
  const { scene } = useGLTF(url);

  const { position, scale, heightMeters } = useMemo(() => {
    const box = new THREE.Box3().setFromObject(scene);
    const size = box.getSize(new THREE.Vector3());
    const center = box.getCenter(new THREE.Vector3());
    // MPFB avatars are authored in metres. Only normalize when a file is clearly
    // not in that range, so changing the height parameter stays visible.
    const needsNormalization = !Number.isFinite(size.y) || size.y < 0.2 || size.y > 4;
    const s = needsNormalization && size.y > 0 ? 1.7 / size.y : 1;
    return {
      position: new THREE.Vector3(-center.x * s, -box.min.y * s, -center.z * s),
      scale: s,
      heightMeters: size.y * s,
    };
  }, [scene]);

  useEffect(() => {
    onInfo?.(heightMeters);
  }, [heightMeters, onInfo]);

  return (
    <group position={position} scale={scale}>
      <primitive object={scene} />
    </group>
  );
}

export function AvatarCanvas({ url = DEFAULT_AVATAR_URL }: { url?: string }) {
  const [heightMeters, setHeightMeters] = useState<number | null>(null);

  return (
    <div className="relative h-[560px] rounded-xl overflow-hidden bg-[#F0EFEA] border border-[#E2E0D8]">
      <Canvas shadows dpr={[1, 2]} camera={{ position: [0, 1.15, 3.2], fov: 45 }}>
        <color attach="background" args={["#F0EFEA"]} />
        <ambientLight intensity={0.6} />
        <directionalLight position={[2, 3, 2]} intensity={1.5} castShadow />
        <gridHelper args={[6, 12, "#D8D5CC", "#E2E0D8"]} position={[0, 0.002, 0]} />
        <Suspense
          fallback={
            <mesh position={[0, 0.9, 0]}>
              <sphereGeometry args={[0.35, 32, 32]} />
              <meshStandardMaterial color="#556B2F" transparent opacity={0.35} />
            </mesh>
          }
        >
          <AvatarModel url={url} onInfo={setHeightMeters} />
          <Environment preset="city" />
          <ContactShadows position={[0, 0, 0]} opacity={0.35} scale={5} blur={2.5} far={2} />
        </Suspense>
        <OrbitControls
          enablePan={false}
          minPolarAngle={Math.PI / 6}
          maxPolarAngle={Math.PI / 1.9}
          minDistance={1.2}
          maxDistance={5}
          target={[0, 1.0, 0]}
        />
      </Canvas>
      {heightMeters !== null && (
        <div className="absolute bottom-3 left-3 bg-white/85 backdrop-blur-sm border border-[#E2E0D8] rounded-lg px-3 py-1.5 text-xs font-semibold text-[#1C1C1C] tabular-nums">
          {heightMeters.toFixed(2)} m
        </div>
      )}
    </div>
  );
}

export default function AvatarViewer() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-3xl font-semibold text-[#1C1C1C]">Avatar Test</h1>
        <p className="text-[#8C8A82] text-sm mt-1">Preview your 3D avatar — drag to rotate, scroll to zoom</p>
      </div>

      <AvatarCanvas />
    </div>
  );
}

useGLTF.preload(DEFAULT_AVATAR_URL);
