import { useEffect, useMemo, useRef, useState } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import { asset } from '../../lib/api'
import { cap, seasonLabel, TAXONOMY } from '../../lib/taxonomy'

// ----- dimensions (metres) -------------------------------------------------
const H = 2.3, D = 0.62, T = 0.035, FLOOR_Y = 0.1, RAIL_Y = 2.06, SP = 0.3, SHELF_W = 1.05
const SHELVES_Y = [1.18, 1.7, 0.66]           // filled in this order (eye level first)
const RAIL_ORDER = ['Outerwear', 'Tops', 'Dresses', 'Bottoms']
const HANG_H = { dress: 1.12, pants: 1.0, jacket: 0.86, sweater: 0.72, top: 0.66, vest: 0.6, skirt: 0.62, shorts: 0.46 }
const SHELF_H = { bag: 0.36, hat: 0.24, scarf: 0.34, umbrella: 0.42 }
const FAN = -0.62                              // rotation of hanging items, like flipping through a rack

// perceived lightness, used to arrange each section from light to dark like a real closet
const lightness = (hex = '#888888') => {
  const n = parseInt(hex.slice(1), 16) || 0
  return 0.299 * (n >> 16) + 0.587 * ((n >> 8) & 255) + 0.114 * (n & 255)
}
const fits = (i, f) => (!f.season || (i.seasons || []).includes(f.season))
  && (!f.occasion || (i.occasions || []).includes(f.occasion))
  && (!f.style || i.style === f.style)
  && (!f.color || i.color_name === f.color)

// ----- procedural wood texture ----------------------------------------------
function woodTexture(base = '#b88a5a', dark = '#8d6239') {
  const c = document.createElement('canvas')
  c.width = 512; c.height = 512
  const g = c.getContext('2d')
  g.fillStyle = base; g.fillRect(0, 0, 512, 512)
  for (let i = 0; i < 90; i++) {
    g.strokeStyle = dark; g.globalAlpha = 0.05 + Math.random() * 0.12
    g.lineWidth = 1 + Math.random() * 3
    const x = Math.random() * 512
    g.beginPath(); g.moveTo(x, 0)
    for (let y = 0; y <= 512; y += 32) g.lineTo(x + Math.sin(y / 60 + i) * 6, y)
    g.stroke()
  }
  const t = new THREE.CanvasTexture(c)
  t.colorSpace = THREE.SRGBColorSpace
  t.wrapS = t.wrapT = THREE.RepeatWrapping
  return t
}

function makeHanger(mat) {
  const g = new THREE.Group()
  const hook = new THREE.Mesh(new THREE.TorusGeometry(0.028, 0.004, 8, 24, Math.PI * 1.35), mat)
  hook.rotation.z = -Math.PI * 0.1
  hook.position.y = 0.0
  g.add(hook)
  const rod = (a, b) => {
    const v = new THREE.Vector3().subVectors(b, a)
    const m = new THREE.Mesh(new THREE.CylinderGeometry(0.006, 0.006, v.length(), 8), mat)
    m.position.copy(a).addScaledVector(v, 0.5)
    m.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), v.clone().normalize())
    g.add(m)
  }
  const top = new THREE.Vector3(0, -0.03, 0)
  const l = new THREE.Vector3(-0.2, -0.11, 0), r = new THREE.Vector3(0.2, -0.11, 0)
  rod(top, l); rod(top, r); rod(l, r)
  return g
}

export default function Wardrobe3D({ items, selectedId, onSelect }) {
  const mountRef = useRef()
  const ctx = useRef({})
  const [hover, setHover] = useState(null)
  const [season, setSeason] = useState('')
  const [occasion, setOccasion] = useState('')
  const [style, setStyle] = useState('')
  const [color, setColor] = useState('')
  const filter = { season, occasion, style, color }
  const colors = useMemo(() => [...new Set(items.map((i) => i.color_name).filter(Boolean))].sort(), [items])
  const [doorsOpen, setDoorsOpen] = useState(true)

  const itemsKey = useMemo(() => items.map((i) => `${i.id}:${i.category}:${i.color_hex}:${i.cutout_url?.length}:${i.mesh_url?.length || 0}:${i.mesh_version || 0}`).join('|'), [items])

  // ---------- one-time scene setup ----------
  useEffect(() => {
    const el = mountRef.current
    const renderer = new THREE.WebGLRenderer({ antialias: true })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.shadowMap.enabled = true
    renderer.shadowMap.type = THREE.PCFSoftShadowMap
    renderer.toneMapping = THREE.ACESFilmicToneMapping
    renderer.toneMappingExposure = 1.05
    renderer.outputColorSpace = THREE.SRGBColorSpace
    el.appendChild(renderer.domElement)

    const scene = new THREE.Scene()
    scene.background = new THREE.Color('#efe9df')
    scene.fog = new THREE.Fog('#efe9df', 9, 18)

    const camera = new THREE.PerspectiveCamera(42, 1, 0.05, 50)
    camera.position.set(0.6, 1.45, 4.2)

    const controls = new OrbitControls(camera, renderer.domElement)
    controls.target.set(0, 1.15, 0)
    controls.enableDamping = true
    controls.minDistance = 1.0
    controls.maxDistance = 9
    controls.maxPolarAngle = Math.PI / 2 - 0.04
    controls.minAzimuthAngle = -1.2
    controls.maxAzimuthAngle = 1.2

    scene.add(new THREE.HemisphereLight('#fffaf0', '#b9a98f', 0.9))
    const sun = new THREE.DirectionalLight('#fff4e0', 1.6)
    sun.position.set(2.5, 5, 5)
    sun.castShadow = true
    sun.shadow.mapSize.set(2048, 2048)
    Object.assign(sun.shadow.camera, { left: -5, right: 5, top: 4, bottom: -1, near: 0.5, far: 15 })
    sun.shadow.bias = -0.0005
    scene.add(sun)
    const warm = new THREE.PointLight('#ffd9a0', 1.2, 4, 1.5)
    warm.position.set(0, 2.15, 0.35)
    scene.add(warm)

    const floor = new THREE.Mesh(new THREE.CircleGeometry(12, 64), new THREE.MeshStandardMaterial({ color: '#e4dccd', roughness: 0.95 }))
    floor.rotation.x = -Math.PI / 2
    floor.receiveShadow = true
    scene.add(floor)

    const content = new THREE.Group()
    scene.add(content)

    const raycaster = new THREE.Raycaster()
    const pointer = new THREE.Vector2()
    let hovered = null
    const onMove = (e) => {
      const r = renderer.domElement.getBoundingClientRect()
      pointer.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1)
      raycaster.setFromCamera(pointer, camera)
      const hit = raycaster.intersectObjects(ctx.current.pickables || [], true)[0]
      const id = hit?.object.userData.itemId || null
      if (id !== hovered) {
        hovered = id
        ctx.current.hoveredId = id
        renderer.domElement.style.cursor = id ? 'pointer' : 'grab'
      }
      setHover(id ? { id, x: e.clientX - r.left, y: e.clientY - r.top } : null)
    }
    let downAt = null
    const onDown = (e) => { downAt = [e.clientX, e.clientY] }
    const onUp = (e) => {
      if (!downAt || Math.hypot(e.clientX - downAt[0], e.clientY - downAt[1]) > 5) return
      if (hovered) ctx.current.onSelect?.(hovered)
    }
    renderer.domElement.addEventListener('pointermove', onMove)
    renderer.domElement.addEventListener('pointerdown', onDown)
    renderer.domElement.addEventListener('pointerup', onUp)
    renderer.domElement.addEventListener('pointerleave', () => { hovered = null; ctx.current.hoveredId = null; setHover(null) })

    const resize = () => {
      const w = el.clientWidth, h = el.clientHeight
      renderer.setSize(w, h)
      camera.aspect = w / h
      camera.updateProjectionMatrix()
    }
    const ro = new ResizeObserver(resize)
    ro.observe(el)
    resize()

    const clock = new THREE.Clock()
    let raf
    const loop = () => {
      const dt = Math.min(clock.getDelta(), 0.05)
      const k = 1 - Math.pow(0.0015, dt)
      const c = ctx.current
      // doors
      ;(c.doors || []).forEach((d) => { d.rotation.y += (d.userData.target(c.doorsOpen) - d.rotation.y) * k * 0.8 })
      // items
      ;(c.nodes || []).forEach((n) => {
        const u = n.userData
        const active = u.itemId === c.selectedId || u.itemId === c.hoveredId
        const rotY = active ? 0 : u.baseRot
        const z = u.baseZ + (active ? 0.16 : 0) + (u.dim ? -0.04 : 0)
        n.rotation.y += (rotY - n.rotation.y) * k
        n.position.z += (z - n.position.z) * k
        if (u.zone === 'rail') n.rotation.z = Math.sin(clock.elapsedTime * 1.3 + u.phase) * (active ? 0 : 0.012)
        if (u.mat.map) {
          const target = u.dim ? 0.28 : 1
          u.mat.color.setScalar(u.mat.color.r + (target - u.mat.color.r) * k)
        }
      })
      controls.update()
      renderer.render(scene, camera)
      raf = requestAnimationFrame(loop)
    }
    loop()

    ctx.current = { ...ctx.current, renderer, scene, camera, controls, content, doorsOpen: true }
    return () => {
      cancelAnimationFrame(raf)
      ro.disconnect()
      controls.dispose()
      renderer.dispose()
      el.removeChild(renderer.domElement)
    }
  }, [])

  // ---------- (re)build the wardrobe when items change ----------
  useEffect(() => {
    const c = ctx.current
    const { content, camera, controls } = c
    content.traverse((o) => { o.geometry?.dispose(); if (o.material) [].concat(o.material).forEach((m) => { m.map?.dispose(); m.dispose() }) })
    content.clear()

    const rail = items.filter((i) => RAIL_ORDER.includes(i.category_group))
      .sort((a, b) => RAIL_ORDER.indexOf(a.category_group) - RAIL_ORDER.indexOf(b.category_group)
        || lightness(b.color_hex) - lightness(a.color_hex))
    const byLight = (a, b) => lightness(b.color_hex) - lightness(a.color_hex)
    const shelf = items.filter((i) => ['Bags', 'Accessories'].includes(i.category_group)).sort(byLight)
    const shoes = items.filter((i) => i.category_group === 'Shoes').sort(byLight)

    const railW = Math.min(Math.max(rail.length * SP + 0.55, 1.5), 7)
    const W = railW + SHELF_W + T * 3
    const x0 = -W / 2

    // materials
    const wood = new THREE.MeshStandardMaterial({ map: woodTexture(), roughness: 0.7 })
    const woodInner = new THREE.MeshStandardMaterial({ map: woodTexture('#d9c3a1', '#b89870'), roughness: 0.85 })
    const metal = new THREE.MeshStandardMaterial({ color: '#c8c2b6', metalness: 0.85, roughness: 0.3 })
    const hangerMat = new THREE.MeshStandardMaterial({ color: '#d8b98c', roughness: 0.5 })

    const box = (w, h, d, x, y, z, mat = wood) => {
      const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat)
      m.position.set(x, y, z); m.castShadow = true; m.receiveShadow = true
      content.add(m); return m
    }
    // carcass
    box(W, H, T, 0, H / 2, -D / 2 + T / 2, woodInner)             // back
    box(T, H, D, x0 + T / 2, H / 2, 0)                              // left
    box(T, H, D, -x0 - T / 2, H / 2, 0)                             // right
    box(W, T, D, 0, H - T / 2, 0)                                   // top
    box(W, FLOOR_Y, D, 0, FLOOR_Y / 2, 0)                           // plinth / floor
    const divX = x0 + T + railW
    box(T, H - FLOOR_Y - T, D - T, divX + T / 2, (H + FLOOR_Y) / 2, T / 2)  // divider
    const shelfX0 = divX + T, shelfX1 = -x0 - T
    SHELVES_Y.forEach((y) => box(shelfX1 - shelfX0, T * 0.8, D - T, (shelfX0 + shelfX1) / 2, y, T / 2))
    // rail
    const railMesh = new THREE.Mesh(new THREE.CylinderGeometry(0.014, 0.014, railW, 16), metal)
    railMesh.rotation.z = Math.PI / 2
    railMesh.position.set(x0 + T + railW / 2, RAIL_Y, 0)
    content.add(railMesh)

    // doors (hinged on the outside edges)
    const doorMat = new THREE.MeshStandardMaterial({ map: woodTexture('#c29464', '#946a40'), roughness: 0.6 })
    const doors = [-1, 1].map((side) => {
      const pivot = new THREE.Group()
      pivot.position.set(side * W / 2, 0, D / 2)
      const panel = new THREE.Mesh(new THREE.BoxGeometry(W / 2, H, T), doorMat)
      panel.position.set(-side * W / 4, H / 2, T / 2)
      panel.castShadow = true
      pivot.add(panel)
      const handle = new THREE.Mesh(new THREE.CylinderGeometry(0.01, 0.01, 0.3, 12), metal)
      handle.position.set(-side * (W / 2 - 0.08), H / 2 + 0.1, T + 0.025)
      pivot.add(handle)
      pivot.userData.target = (open) => (open ? side * 2.55 : 0) // folds back along the sides
      pivot.rotation.y = 0
      content.add(pivot)
      return pivot
    })

    const loader = new THREE.TextureLoader()
    loader.setCrossOrigin('anonymous')
    const gltfLoader = new GLTFLoader()
    const nodes = [], pickables = []

    const addItem = (item, zone, h, place) => {
      const node = new THREE.Group()
      const mat = new THREE.MeshStandardMaterial({ transparent: true, alphaTest: 0.35, side: THREE.DoubleSide, roughness: 0.9, color: new THREE.Color(1, 1, 1) })
      const plane = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), mat)
      plane.castShadow = true
      plane.userData.itemId = item.id
      plane.scale.set(h * 0.8, h, 1)
      plane.position.y = zone === 'rail' ? -0.1 - h / 2 : h / 2
      node.add(plane)
      if (zone === 'rail') node.add(makeHanger(hangerMat))

      const loadCutout = () => {
        mat.opacity = 1
        mat.needsUpdate = true
        if (!item.cutout_url) {
          mat.color.set(item.color_hex || '#999')
          return
        }
        loader.load(asset(item.cutout_url), (tex) => {
          tex.colorSpace = THREE.SRGBColorSpace
          tex.anisotropy = 4
          mat.map = tex; mat.needsUpdate = true
          const img = tex.image
          const aspect = (img.width || 1) / (img.height || 1)
          let w = h * aspect, hh = h
          const maxW = zone === 'rail' ? 0.62 : zone === 'floor' ? 0.42 : 0.32
          if (w > maxW) { hh = h * (maxW / w); w = maxW }
          plane.scale.set(w, hh, 1)
          plane.position.y = zone === 'rail' ? -0.1 - hh / 2 : hh / 2
        })
      }

      if (item.mesh_url) {
        mat.opacity = 0
        mat.needsUpdate = true
        const sep = item.mesh_url.includes('?') ? '&' : '?'
        const url = `${asset(item.mesh_url)}${sep}v=${item.mesh_version || 0}`
        gltfLoader.load(url, (gltf) => {
          if (node.parent !== content) return
          const model = gltf.scene
          model.traverse((o) => {
            if (o.isMesh) {
              o.castShadow = true
              o.receiveShadow = true
              o.userData.itemId = item.id
            }
          })
          const box = new THREE.Box3().setFromObject(model)
          const size = box.getSize(new THREE.Vector3())
          const scale = h / Math.max(size.y, 0.001)
          model.scale.setScalar(scale)
          const scaled = new THREE.Box3().setFromObject(model)
          const center = scaled.getCenter(new THREE.Vector3())
          model.position.x -= center.x
          model.position.z -= center.z
          model.position.y += (zone === 'rail' ? -0.1 - h : 0) - scaled.min.y
          node.add(model)
          pickables.push(model)
        }, undefined, loadCutout)
      } else {
        loadCutout()
      }
      place(node)
      node.userData = { ...node.userData, itemId: item.id, zone, mat, baseRot: node.rotation.y, baseZ: node.position.z, phase: Math.random() * 6 }
      content.add(node)
      nodes.push(node); pickables.push(plane)
    }

    // hanging items
    const sp = rail.length > 1 ? Math.min(SP, (railW - 0.5) / (rail.length - 1)) : 0
    const railStart = x0 + T + railW / 2 - (sp * (rail.length - 1)) / 2
    rail.forEach((item, i) => addItem(item, 'rail', HANG_H[item.category] || 0.7, (n) => {
      n.position.set(railStart + i * sp, RAIL_Y, 0)
      n.rotation.y = rail.length > 1 ? FAN : 0
    }))

    // shelves: bags & accessories
    const perShelf = Math.max(3, Math.ceil(shelf.length / SHELVES_Y.length))
    const shelfInner = shelfX1 - shelfX0 - 0.1
    shelf.forEach((item, i) => {
      const s = Math.min(Math.floor(i / perShelf), SHELVES_Y.length - 1)
      const slot = i % perShelf
      const onThis = Math.min(perShelf, shelf.length - s * perShelf)
      const step = shelfInner / onThis
      addItem(item, 'shelf', (SHELF_H[item.category] || 0.22) * Math.min(1, 3 / onThis + 0.2), (n) => {
        n.position.set(shelfX0 + 0.05 + step * (slot + 0.5), SHELVES_Y[s] + T * 0.4, 0.02)
      })
    })

    // shoes along the floor, at the front
    const shoeStep = shoes.length ? Math.min(0.36, (W - 0.3) / shoes.length) : 0
    const shoeStart = -(shoeStep * (shoes.length - 1)) / 2
    shoes.forEach((item, i) => addItem(item, 'floor', 0.3, (n) => {
      n.position.set(shoeStart + i * shoeStep, FLOOR_Y, 0.16)
    }))

    Object.assign(c, { nodes, pickables, doors, width: W })
    // frame the whole wardrobe on first build / when it grows a lot
    if (!c.framedW || Math.abs(c.framedW - W) > 0.8) {
      const dist = Math.max(3.4, W * 1.05 + 1.2)
      camera.position.set(W * 0.12, 1.5, dist)
      controls.target.set(0, 1.12, 0)
      controls.maxDistance = dist + 4
      c.framedW = W
    }
  }, [itemsKey]) // eslint-disable-line react-hooks/exhaustive-deps

  // ---------- reactive state -> animation targets ----------
  useEffect(() => {
    const c = ctx.current
    c.selectedId = selectedId
    c.onSelect = onSelect
    c.doorsOpen = doorsOpen
    const byId = Object.fromEntries(items.map((i) => [i.id, i]))
    ;(c.nodes || []).forEach((n) => {
      const it = byId[n.userData.itemId]
      n.userData.dim = !!it && !fits(it, { season, occasion, style, color })
    })
  }, [selectedId, onSelect, doorsOpen, season, occasion, style, color, items, itemsKey])

  const hovItem = hover && items.find((i) => i.id === hover.id)
  const matching = items.filter((i) => fits(i, filter)).length
  const filtering = season || occasion || style || color

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 className="font-display text-lg font-medium text-[#1C1C1C]">3D view</h2>
          <p className="mt-1 text-sm text-[#8C8A82]">
            Drag to turn, scroll to zoom, click an item to see its details.
          </p>
        </div>
        <button
          type="button"
          className="rounded-lg border border-[#E2E0D8] bg-white px-4 py-2 text-sm font-semibold text-[#1C1C1C] hover:bg-[#F0EFEA]"
          onClick={() => setDoorsOpen(!doorsOpen)}
        >
          {doorsOpen ? 'Close doors' : 'Open doors'}
        </button>
      </header>
      <div className="flex flex-wrap items-center gap-2 rounded-xl border border-[#E2E0D8] bg-white p-3 text-xs text-[#8C8A82]">
        <span>Highlight what fits</span>
        <select className="rounded-lg border border-[#E2E0D8] bg-white px-2 py-1.5 text-xs capitalize text-[#1C1C1C] outline-none focus:border-[#556B2F]" value={season} onChange={(e) => setSeason(e.target.value)}>
          <option value="">Any season</option>
          {TAXONOMY.seasons.map((s) => <option key={s} value={s}>{cap(s)}</option>)}
        </select>
        <select className="rounded-lg border border-[#E2E0D8] bg-white px-2 py-1.5 text-xs capitalize text-[#1C1C1C] outline-none focus:border-[#556B2F]" value={occasion} onChange={(e) => setOccasion(e.target.value)}>
          <option value="">Any occasion</option>
          {TAXONOMY.occasions.map((s) => <option key={s} value={s}>{cap(s)}</option>)}
        </select>
        <select className="rounded-lg border border-[#E2E0D8] bg-white px-2 py-1.5 text-xs capitalize text-[#1C1C1C] outline-none focus:border-[#556B2F]" value={style} onChange={(e) => setStyle(e.target.value)}>
          <option value="">Any style</option>
          {TAXONOMY.styles.map((s) => <option key={s} value={s}>{cap(s)}</option>)}
        </select>
        <select className="rounded-lg border border-[#E2E0D8] bg-white px-2 py-1.5 text-xs capitalize text-[#1C1C1C] outline-none focus:border-[#556B2F]" value={color} onChange={(e) => setColor(e.target.value)}>
          <option value="">Any colour</option>
          {colors.map((s) => <option key={s} value={s}>{cap(s)}</option>)}
        </select>
        {filtering && <>
          <b className="text-[#1C1C1C]">{matching} of {items.length} items</b>
          <button type="button" className="font-semibold text-[#556B2F] underline" onClick={() => { setSeason(''); setOccasion(''); setStyle(''); setColor('') }}>Clear</button>
        </>}
      </div>
      <div className="relative h-[560px] w-full overflow-hidden rounded-xl border border-[#E2E0D8] bg-[#F0EFEA]" ref={mountRef}>
        {hovItem && (
          <div className="pointer-events-none absolute z-10 max-w-[220px] rounded-lg bg-[#1C1C1C] px-3 py-2 text-xs text-white shadow-lg" style={{ left: hover.x + 14, top: hover.y + 14 }}>
            <b className="block text-[11px] font-semibold">{hovItem.name}</b>
            <span className="mt-1 flex items-center gap-1.5 text-white/70">
              <i className="inline-block h-2 w-2 rounded-full" style={{ background: hovItem.color_hex }} />
              {cap(hovItem.color_name)} · {seasonLabel(hovItem.seasons)} · {cap(hovItem.style || '')}
            </span>
          </div>
        )}
        {!items.length && <div className="pointer-events-none absolute inset-0 flex items-center justify-center px-6 text-center text-sm text-[#8C8A82]">Your wardrobe is empty - add clothing from <b>My Wardrobe</b>.</div>}
      </div>
    </div>
  )
}
