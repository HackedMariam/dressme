import { supabase } from "../lib/supabase";

export type WeatherDay = {
  date: string;
  temperature_max_c: number;
  temperature_min_c: number;
  precipitation_mm: number;
  precipitation_probability: number | null;
  wind_speed_kmh: number | null;
  uv_index: number | null;
  weather_code: number | null;
};

export type WeatherResponse = {
  location: { name: string; country: string | null; latitude: number; longitude: number };
  source: "open-meteo" | "met-no";
  fallback_used: boolean;
  warning: string | null;
  retrieved_at: string;
  current: {
    temperature_c: number | null;
    feels_like_c: number | null;
    humidity_percent: number | null;
    wind_speed_kmh: number | null;
    weather_code: number | null;
  };
  days: WeatherDay[];
};

export async function fetchWeather(city: string, country?: string | null): Promise<WeatherResponse> {
  const { data, error } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  if (error || !token) throw new Error("Please sign in to use live weather.");
  const params = new URLSearchParams({ city });
  if (country) params.set("country", country);
  const response = await fetch(`/api/weather?${params}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail ?? `Weather request failed (${response.status})`);
  }
  return response.json() as Promise<WeatherResponse>;
}

export function weatherLabel(code: number | null): string {
  if (code === 0) return "Clear";
  if (code === 1 || code === 2) return "Partly cloudy";
  if (code === 3) return "Overcast";
  if (code === 45 || code === 48) return "Foggy";
  if (code !== null && code >= 51 && code <= 67) return "Rain";
  if (code !== null && code >= 71 && code <= 86) return "Snow";
  if (code !== null && code >= 95) return "Thunderstorms";
  return "Cloudy";
}

export function weatherIcon(code: number | null): string {
  if (code === 0) return "☀";
  if (code === 1 || code === 2) return "⛅";
  if (code === 3) return "☁";
  if (code === 45 || code === 48) return "〰";
  if (code !== null && code >= 51 && code <= 67) return "🌧";
  if (code !== null && code >= 71 && code <= 86) return "❄";
  if (code !== null && code >= 95) return "⛈";
  return "☁";
}
