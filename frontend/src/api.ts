import type { AnalyzeResponse, SearchResult } from "./types";

const DEFAULT_API_BASE_URL = "";
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? DEFAULT_API_BASE_URL;

export async function searchLocation(query: string): Promise<SearchResult[]> {
  const url = new URL(`${API_BASE_URL}/api/search`, window.location.origin);
  url.searchParams.set("query", query);

  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Search failed with ${response.status}`);
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
    throw new Error(`Analyze failed with ${response.status}`);
  }

  return response.json() as Promise<AnalyzeResponse>;
}
