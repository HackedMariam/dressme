export type TripDetails = {
  destination: string | null;
  country?: string | null;
  start_date: string | null;
  end_date: string | null;
  duration_days: number | null;
  activities: string[];
  daily_activities?: Record<string, string[]>;
  occasions?: string[];
  dress_code?: string | null;
  max_luggage_weight_kg: number | null;
  max_items_target?: number | null;
  allow_laundry?: boolean;
  notes?: string | null;
  missing_fields?: string[];
};

export type WeatherDay = {
  date: string | null;
  weather: string;
  temperature_c: number;
  temperature_min_c?: number | null;
  temperature_max_c?: number | null;
  precipitation_mm: number;
  precipitation_probability?: number | null;
  wind_speed_kmh?: number | null;
  uv_index?: number | null;
  source: string;
  synthetic: boolean;
};

export type WeatherData = {
  destination: string;
  latitude?: number | null;
  longitude?: number | null;
  days: WeatherDay[];
  source: "open-meteo" | "synthetic_fallback";
  warning?: string | null;
  resolved_name?: string | null;
  resolved_country?: string | null;
  requested_country?: boolean;
  geocoding_note?: string | null;
  retrieved_at?: string;
};

export type DailyRequirement = {
  trip_id: string;
  day_number: number;
  date: string;
  activity: string;
  weather: string;
  temperature_c: number;
  precipitation_mm: number;
  required_style: string;
  needs_outerwear: boolean;
  needs_warm_layer: boolean;
  needs_rain_protection: boolean;
  needs_sun_protection: boolean;
  activities: string[];
  weather_source?: string | null;
};

export type OutfitItem = {
  item_id: string;
  name: string;
  category: string;
  item_type?: string | null;
  weight_g: number;
  style?: string | null;
  color?: string | null;
};

export type CapsuleDay = {
  day_number: number;
  date: string;
  activity: string;
  activities: string[];
  weather: string;
  temperature_c: number;
  precipitation_mm: number;
  required_style: string;
  outfit_item_ids: string[];
  outfit_items: OutfitItem[];
  compatibility?: number | null;
  quality?: number | null;
};

export type ChecklistItem = {
  item_id: string;
  name: string;
  category: string;
  item_type?: string | null;
  weight_g: number;
  quantity: number;
  packed: boolean;
};

export type ChecklistSummary = {
  items: ChecklistItem[];
  total_items: number;
  packed_items: number;
  unpacked_items: number;
  updated_at?: string;
};

export type Capsule = {
  trip: {
    destination: string;
    country?: string | null;
    start_date: string;
    end_date: string;
    duration_days: number;
    activities: string[];
    dress_code?: string | null;
    max_luggage_weight_kg: number;
    weather_source: string;
  };
  days: CapsuleDay[];
  selected_items: OutfitItem[];
  total_weight_g: number;
  optimization_status: string;
  number_of_items: number;
  checklist: ChecklistSummary;
  created_at?: string;
  metadata?: Record<string, unknown>;
};

export type TripPayload = {
  session_id: string;
  status: string;
  message?: string;
  trip_details: TripDetails | null;
  weather: WeatherData | null;
  weather_summary?: Array<Record<string, unknown>>;
  daily_requirements: DailyRequirement[];
  capsule: Capsule | null;
  checklist: ChecklistSummary | null;
  missing_info: string[];
  clarification_question?: string | null;
  suggestions: string[];
  errors: string[];
  optimization_status?: string | null;
  optimization_runs?: number;
};

export type GapAnalysisResponse = {
  session_id: string;
  gap_analysis: {
    ok: boolean;
    available: boolean;
    message?: string;
    findings?: {
      provider: string;
      status: string;
      capsule_days: number;
      selected_categories: Record<string, number>;
      gaps: Array<{
        type: string;
        severity: string;
        category: string;
        suggestion: string;
      }>;
      summary: string;
    };
  };
  capsule: Capsule;
};

type CreateTripInput =
  | { mode: "text"; text: string; session_id?: string }
  | { mode: "structured"; trip: Record<string, unknown>; session_id?: string };

const API_BASE = (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(
  /\/$/,
  "",
);

export class TripApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "TripApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 180_000);
  try {
    const response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(init?.headers || {}),
      },
      signal: controller.signal,
    });
    const text = await response.text();
    let data: unknown = null;
    if (text) {
      try {
        data = JSON.parse(text);
      } catch {
        data = { detail: text };
      }
    }
    if (!response.ok) {
      const detail = (data as { detail?: unknown } | null)?.detail;
      let message = `Request failed (${response.status})`;
      if (typeof detail === "string") {
        message = detail;
      } else if (detail && typeof detail === "object") {
        const record = detail as Record<string, unknown>;
        message =
          (typeof record.message === "string" && record.message) ||
          (typeof record.error === "string" && record.error) ||
          JSON.stringify(detail);
      }
      throw new TripApiError(message, response.status);
    }
    return data as T;
  } catch (error) {
    if (error instanceof TripApiError) throw error;
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new TripApiError(
        "The Trip Agent took too long to respond. Please try again.",
        408,
      );
    }
    throw new TripApiError(
      error instanceof Error ? error.message : "Network request failed",
      0,
    );
  } finally {
    window.clearTimeout(timeout);
  }
}

export function createTrip(input: CreateTripInput): Promise<TripPayload> {
  return request<TripPayload>("/api/trips", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function continueTrip(
  sessionId: string,
  text: string,
): Promise<TripPayload> {
  return request<TripPayload>(
    `/api/trips/${encodeURIComponent(sessionId)}/messages`,
    {
      method: "POST",
      body: JSON.stringify({ text }),
    },
  );
}

export function getTrip(sessionId: string): Promise<TripPayload> {
  return request<TripPayload>(`/api/trips/${encodeURIComponent(sessionId)}`);
}

export function updateTrip(
  sessionId: string,
  updates: Record<string, unknown>,
  reoptimize = true,
): Promise<TripPayload> {
  return request<TripPayload>(`/api/trips/${encodeURIComponent(sessionId)}`, {
    method: "PATCH",
    body: JSON.stringify({ updates, reoptimize }),
  });
}

export function updateChecklist(
  sessionId: string,
  itemId: string,
  packed: boolean,
): Promise<{
  session_id: string;
  message: string;
  checklist: ChecklistSummary;
  optimization_runs: number;
  optimizer_rerun: boolean;
}> {
  return request(
    `/api/trips/${encodeURIComponent(sessionId)}/checklist/${encodeURIComponent(itemId)}`,
    {
      method: "PATCH",
      body: JSON.stringify({ packed }),
    },
  );
}

export function getGapAnalysis(sessionId: string): Promise<GapAnalysisResponse> {
  return request<GapAnalysisResponse>(
    `/api/trips/${encodeURIComponent(sessionId)}/gap-analysis`,
    { method: "POST", body: "{}" },
  );
}

export function getWeather(
  sessionId: string,
  forceRefresh = false,
): Promise<Record<string, unknown>> {
  return request(`/api/trips/${encodeURIComponent(sessionId)}/weather`, {
    method: "POST",
    body: JSON.stringify({ force_refresh: forceRefresh }),
  });
}

export function getRequirements(
  sessionId: string,
): Promise<Record<string, unknown>> {
  return request(`/api/trips/${encodeURIComponent(sessionId)}/requirements`, {
    method: "POST",
    body: "{}",
  });
}

export function optimizeTrip(
  sessionId: string,
): Promise<Record<string, unknown>> {
  return request(`/api/trips/${encodeURIComponent(sessionId)}/optimize`, {
    method: "POST",
    body: "{}",
  });
}
