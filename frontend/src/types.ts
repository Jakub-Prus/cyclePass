export type SegmentClass = "protected" | "low-stress" | "shared" | "not-suitable";

export type SegmentScore = {
  bike_allowed: "yes" | "no" | "uncertain";
  bike_comfort: number;
  bike_crossable_class: SegmentClass;
  bike_crossable_label: string;
  confidence: number;
  reasons: string[];
  normalized_tags: Record<string, string | number | null>;
};

export type Segment = {
  id: string;
  parent_way_id?: number;
  name: string;
  geometry: Array<{ lat: number; lon: number }>;
  length_m: number;
  tags: Record<string, string>;
  score: SegmentScore;
};

export type AnalyzeResponse = {
  center: { lat: number; lon: number };
  radius_m: number;
  summary: Record<string, number>;
  segments: Segment[];
};

export type SearchResult = {
  display_name: string;
  lat: number;
  lon: number;
};

export type RouteResponse = {
  start: { lat: number; lon: number };
  end: { lat: number; lon: number };
  snapped_start: { lat: number; lon: number };
  snapped_end: { lat: number; lon: number };
  total_length_m: number;
  average_comfort: number;
  routing_mode: "strict" | "fallback";
  explanation: string[];
  segments: Segment[];
  geometry: Array<{ lat: number; lon: number }>;
};

export type InspectResponse = {
  requested_point: { lat: number; lon: number };
  snapped_point: { lat: number; lon: number };
  segment_point: { lat: number; lon: number };
  snap_distance_m: number;
  segment_distance_m: number;
  segment: Segment;
};
