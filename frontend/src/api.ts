import type { AnalyzeResponse, RouteResponse, SearchResult } from "./types";

const DEFAULT_API_BASE_URL = "";
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? DEFAULT_API_BASE_URL;

async function readErrorMessage(response: Response, fallbackMessage: string): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: string };
    return body.detail ?? fallbackMessage;
  } catch {
    return fallbackMessage;
  }
}

export async function searchLocation(query: string): Promise<SearchResult[]> {
  const url = new URL(`${API_BASE_URL}/api/search`, window.location.origin);
  url.searchParams.set("query", query);

  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(await readErrorMessage(response, `Search failed with ${response.status}`));
  }

  return response.json() as Promise<SearchResult[]>;
}

export async function analyzeArea(lat: number, lon: number, radiusM: number): Promise<AnalyzeResponse> {
  const response = await fetch(`${API_BASE_URL}/api/analyze`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      lat,
      lon,
      radius_m: radiusM,
    }),
  });

  if (!response.ok) {
    throw new Error(await readErrorMessage(response, `Analyze failed with ${response.status}`));
  }

  return response.json() as Promise<AnalyzeResponse>;
}

export async function findRoute(
  start: { lat: number; lon: number },
  end: { lat: number; lon: number }
): Promise<RouteResponse> {
  const response = await fetch(`${API_BASE_URL}/api/route`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      start_lat: start.lat,
      start_lon: start.lon,
      end_lat: end.lat,
      end_lon: end.lon,
      radius_m: 600,
    }),
  });

  if (!response.ok) {
    throw new Error(await readErrorMessage(response, `Route failed with ${response.status}`));
  }

  return response.json() as Promise<RouteResponse>;
}
