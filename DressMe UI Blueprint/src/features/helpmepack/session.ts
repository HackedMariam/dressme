// Where Help Me Pack remembers the trip of a user. The assistant writes the same key to open a trip it planned.
export const TRIP_SESSION_KEY = "dressme.trip.session"

export const tripSessionKey = (userId?: string | null) => `${TRIP_SESSION_KEY}.${userId || "local"}`
