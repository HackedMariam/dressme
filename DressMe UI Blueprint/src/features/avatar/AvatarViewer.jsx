import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'

// Shows a GLB (a blob URL) that can be turned around with the mouse or a finger. The parent sets the size.
export default function AvatarViewer({ url, label = '3D model' }) {
  const mountRef = useRef(null)
  const [state, setState] = useState('loading') // loading | ready | error

  useEffect(() => {
    const mount = mountRef.current
    if (!mount || !url) return undefined
    setState('loading')

    const scene = new THREE.Scene()
    const camera = new THREE.PerspectiveCamera(35, 1, 0.01, 100)
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.outputColorSpace = THREE.SRGBColorSpace
    mount.appendChild(renderer.domElement)

    scene.add(new THREE.HemisphereLight(0xffffff, 0x8a8478, 1.7))
    const sun = new THREE.DirectionalLight(0xffffff, 2.2)
    sun.position.set(2, 4, 3)
    scene.add(sun)

    const controls = new OrbitControls(camera, renderer.domElement)
    controls.enableDamping = true
    controls.enablePan = false
    controls.autoRotate = true
    controls.autoRotateSpeed = 1.4
    controls.addEventListener('start', () => { controls.autoRotate = false })

    const resize = () => {
      const { clientWidth: w, clientHeight: h } = mount
      if (!w || !h) return
      renderer.setSize(w, h)
      camera.aspect = w / h
      camera.updateProjectionMatrix()
    }
    const observer = new ResizeObserver(resize)
    observer.observe(mount)
    resize()

    let frame = 0
    let disposed = false
    let model = null
    new GLTFLoader().load(
      url,
      (gltf) => {
        if (disposed) return
        model = gltf.scene
        const box = new THREE.Box3().setFromObject(model)
        const size = box.getSize(new THREE.Vector3())
        model.position.sub(box.getCenter(new THREE.Vector3())) // centre it on the origin
        const height = size.y || 1
        camera.position.set(0, 0, (height / 2 / Math.tan(THREE.MathUtils.degToRad(camera.fov / 2))) * 1.25)
        controls.minDistance = height * 0.8
        controls.maxDistance = height * 6
        controls.target.set(0, 0, 0)
        scene.add(model)
        setState('ready')
      },
      undefined,
      () => { if (!disposed) setState('error') },
    )

    const tick = () => {
      frame = requestAnimationFrame(tick)
      controls.update()
      renderer.render(scene, camera)
    }
    tick()

    return () => {
      disposed = true
      cancelAnimationFrame(frame)
      observer.disconnect()
      controls.dispose()
      if (model) {
        model.traverse((node) => {
          if (node.geometry) node.geometry.dispose()
          const materials = Array.isArray(node.material) ? node.material : node.material ? [node.material] : []
          materials.forEach((material) => {
            Object.values(material).forEach((value) => { if (value && value.isTexture) value.dispose() })
            material.dispose()
          })
        })
      }
      renderer.dispose()
      if (renderer.domElement.parentNode === mount) mount.removeChild(renderer.domElement)
    }
  }, [url])

  return (
    <div className="relative h-full w-full" role="img" aria-label={label}>
      <div ref={mountRef} className="h-full w-full cursor-grab active:cursor-grabbing" />
      {state === 'loading' && (
        <div className="pointer-events-none absolute inset-0 grid place-items-center text-sm text-[#8C8A82]">Loading 3D model…</div>
      )}
      {state === 'error' && (
        <div className="absolute inset-0 grid place-items-center px-4 text-center text-sm text-red-700">Could not display this 3D model.</div>
      )}
      {state === 'ready' && (
        <div className="pointer-events-none absolute bottom-2 left-0 right-0 text-center text-[10px] text-[#8C8A82]">Drag to turn · scroll to zoom</div>
      )}
    </div>
  )
}
