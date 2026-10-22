import { FilesetResolver, ImageSegmenter } from "@mediapipe/tasks-vision"

export type SilhouetteBox = {
  minX: number
  minY: number
  maxX: number
  maxY: number
  width: number
  height: number
}

export type Silhouette = {
  width: number
  height: number
  data: Uint8Array
  box: SilhouetteBox
}

export type RowMeasurement = {
  fraction: number
  width: number
  left: number
  right: number
  center: number
}

let segmenterPromise: Promise<ImageSegmenter> | null = null

function getSegmenter(): Promise<ImageSegmenter> {
  if (!segmenterPromise) {
    segmenterPromise = (async () => {
      const fileset = await FilesetResolver.forVisionTasks("/mediapipe/wasm")
      const base = {
        modelAssetPath: "/mediapipe/selfie_segmenter.tflite",
        delegate: "GPU" as const,
      }
      const options = {
        baseOptions: base,
        runningMode: "IMAGE" as const,
        outputCategoryMask: true,
        outputConfidenceMasks: false,
      }
      try {
        return await ImageSegmenter.createFromOptions(fileset, options)
      } catch {
        return await ImageSegmenter.createFromOptions(fileset, {
          ...options,
          baseOptions: { ...base, delegate: "CPU" as const },
        })
      }
    })()
  }
  return segmenterPromise
}

export function preloadSilhouetteModel(): Promise<ImageSegmenter> {
  return getSegmenter()
}

export async function extractSilhouette(image: HTMLImageElement): Promise<Silhouette> {
  const segmenter = await getSegmenter()
  const result = segmenter.segment(image)
  const mask = result.categoryMask
  if (!mask) {
    throw new Error("MediaPipe did not return a silhouette mask.")
  }

  const width = mask.width
  const height = mask.height
  const data = mask.getAsUint8Array()
  mask.close()

  let foreground = 0
  for (let i = 0; i < data.length; i++) {
    if (data[i] > 0) foreground++
  }

  const invert = foreground > data.length * 0.9
  let minX = width
  let minY = height
  let maxX = -1
  let maxY = -1
  let pixels = 0

  for (let y = 0; y < height; y++) {
    const row = y * width
    for (let x = 0; x < width; x++) {
      const isPerson = invert ? data[row + x] === 0 : data[row + x] > 0
      if (!isPerson) continue
      pixels++
      if (x < minX) minX = x
      if (x > maxX) maxX = x
      if (y < minY) minY = y
      if (y > maxY) maxY = y
    }
  }

  if (pixels < width * height * 0.02 || maxX < minX || maxY < minY) {
    throw new Error("No clear body silhouette was found in this photo.")
  }

  return {
    width,
    height,
    data: invert ? data.map((value) => (value === 0 ? 1 : 0)) : data,
    box: {
      minX,
      minY,
      maxX,
      maxY,
      width: maxX - minX + 1,
      height: maxY - minY + 1,
    },
  }
}

export function measureRow(silhouette: Silhouette, fraction: number): RowMeasurement {
  const clamped = Math.min(1, Math.max(0, fraction))
  const y = Math.round(silhouette.box.minY + clamped * (silhouette.box.maxY - silhouette.box.minY))
  const row = Math.min(silhouette.height - 1, Math.max(0, y)) * silhouette.width

  let left = -1
  let right = -1
  let pixels = 0
  for (let x = silhouette.box.minX; x <= silhouette.box.maxX; x++) {
    if (silhouette.data[row + x] > 0) {
      if (left < 0) left = x
      right = x
      pixels++
    }
  }

  return {
    fraction: clamped,
    width: pixels,
    left: left < 0 ? silhouette.box.minX : left,
    right: right < 0 ? silhouette.box.maxX : right,
    center: left < 0 ? (silhouette.box.minX + silhouette.box.maxX) / 2 : (left + right) / 2,
  }
}

export function silhouetteAspect(silhouette: Silhouette): number {
  return silhouette.box.height > 0 ? silhouette.box.width / silhouette.box.height : 0
}

export function silhouetteToPngDataUrl(silhouette: Silhouette, size = 512): string {
  if (typeof document === "undefined") return ""

  const source = document.createElement("canvas")
  source.width = silhouette.width
  source.height = silhouette.height
  const sourceContext = source.getContext("2d")
  if (!sourceContext) return ""

  const image = sourceContext.createImageData(silhouette.width, silhouette.height)
  for (let i = 0; i < silhouette.data.length; i++) {
    if (silhouette.data[i] <= 0) continue
    const offset = i * 4
    image.data[offset] = 255
    image.data[offset + 1] = 255
    image.data[offset + 2] = 255
    image.data[offset + 3] = 255
  }
  sourceContext.putImageData(image, 0, 0)

  const target = document.createElement("canvas")
  target.width = size
  target.height = size
  const context = target.getContext("2d")
  if (!context) return ""

  const scale = size / Math.max(silhouette.box.width, silhouette.box.height)
  const drawWidth = silhouette.box.width * scale
  const drawHeight = silhouette.box.height * scale
  const drawX = (size - drawWidth) / 2
  const drawY = size - drawHeight
  context.drawImage(
    source,
    silhouette.box.minX,
    silhouette.box.minY,
    silhouette.box.width,
    silhouette.box.height,
    drawX,
    drawY,
    drawWidth,
    drawHeight,
  )
  return target.toDataURL("image/png")
}
