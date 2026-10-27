export type GalleryPhoto = {
  id: string
  userId: string
  name: string
  type: string
  size: number
  feature: string
  createdAt: number
  blob: Blob
}

const DB_NAME = "dressme-gallery"
const STORE_NAME = "photos"
const DB_VERSION = 1

function openDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION)
    request.onerror = () => reject(request.error ?? new Error("Could not open photo gallery."))
    request.onsuccess = () => resolve(request.result)
    request.onupgradeneeded = () => {
      const database = request.result
      if (!database.objectStoreNames.contains(STORE_NAME)) {
        const store = database.createObjectStore(STORE_NAME, { keyPath: "id" })
        store.createIndex("userId", "userId", { unique: false })
        store.createIndex("createdAt", "createdAt", { unique: false })
      }
    }
  })
}

export async function saveGalleryPhoto(
  userId: string,
  file: File,
  feature: string,
): Promise<GalleryPhoto> {
  const photo: GalleryPhoto = {
    id: crypto.randomUUID(),
    userId,
    name: file.name || "DressMe photo",
    type: file.type || "image/jpeg",
    size: file.size,
    feature,
    createdAt: Date.now(),
    blob: file,
  }
  const database = await openDatabase()
  await new Promise<void>((resolve, reject) => {
    const request = database
      .transaction(STORE_NAME, "readwrite")
      .objectStore(STORE_NAME)
      .add(photo)
    request.onerror = () => reject(request.error ?? new Error("Could not save photo."))
    request.onsuccess = () => resolve()
  })
  database.close()
  return photo
}

export async function listGalleryPhotos(userId: string): Promise<GalleryPhoto[]> {
  const database = await openDatabase()
  const photos = await new Promise<GalleryPhoto[]>((resolve, reject) => {
    const request = database
      .transaction(STORE_NAME, "readonly")
      .objectStore(STORE_NAME)
      .index("userId")
      .getAll(userId)
    request.onerror = () => reject(request.error ?? new Error("Could not load photo gallery."))
    request.onsuccess = () => resolve((request.result as GalleryPhoto[]).sort((a, b) => b.createdAt - a.createdAt))
  })
  database.close()
  return photos
}

export async function deleteGalleryPhoto(id: string): Promise<void> {
  const database = await openDatabase()
  await new Promise<void>((resolve, reject) => {
    const request = database.transaction(STORE_NAME, "readwrite").objectStore(STORE_NAME).delete(id)
    request.onerror = () => reject(request.error ?? new Error("Could not delete photo."))
    request.onsuccess = () => resolve()
  })
  database.close()
}

export function galleryPhotoUrl(photo: GalleryPhoto): string {
  return URL.createObjectURL(photo.blob)
}
