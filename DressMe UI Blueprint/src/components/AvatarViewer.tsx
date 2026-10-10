import { Suspense, useMemo } from "react";
import { Canvas } from "@react-three/fiber";
import { ContactShadows, Environment, OrbitControls, useGLTF } from "@react-three/drei";
import * as THREE from "three";

const DEFAULT_AVATAR_URL = "/models/avatar.glb";

function AvatarModel({ url }: { url: string }) {
  const { scene } = useGLTF(url);

  const { position, scale } = useMemo(() => {
    const box = new THREE.Box3().setFromObject(scene);
    const size = box.getSize(new THREE.Vector3());
    const center = box.getCenter(new THREE.Vector3());
    const s = size.y > 0 ? 1.7 / size.y : 1;
    return {
      position: new THREE.Vector3(-center.x * s, -box.min.y * s, -center.z * s),
      scale: s,
    };
  }, [scene]);

  return (
    <group position={position} scale={scale}>
      <primitive object={scene} />
    </group>
  );
}

export function AvatarCanvas({ url = DEFAULT_AVATAR_URL }: { url?: string }) {
  return (
    <div className="relative h-[560px] rounded-xl overflow-hidden bg-[#F0EFEA] border border-[#E2E0D8]">
      <Canvas shadows dpr={[1, 2]} camera={{ position: [0, 1.1, 2.8], fov: 45 }}>
        <color attach="background" args={["#F0EFEA"]} />
        <ambientLight intensity={0.6} />
        <directionalLight position={[2, 3, 2]} intensity={1.5} castShadow />
        <Suspense
          fallback={
            <mesh position={[0, 0.9, 0]}>
              <sphereGeometry args={[0.35, 32, 32]} />
              <meshStandardMaterial color="#556B2F" transparent opacity={0.35} />
            </mesh>
          }
        >
          <AvatarModel url={url} />
          <Environment preset="city" />
          <ContactShadows position={[0, 0, 0]} opacity={0.35} scale={5} blur={2.5} far={2} />
        </Suspense>
        <OrbitControls
          enablePan={false}
          minPolarAngle={Math.PI / 6}
          maxPolarAngle={Math.PI / 1.9}
          minDistance={1.2}
          maxDistance={5}
          target={[0, 0.9, 0]}
        />
      </Canvas>
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
