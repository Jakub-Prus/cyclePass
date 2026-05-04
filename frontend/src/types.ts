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
  id: number;
  name: string;
  geometry: Array<{ lat: number; lon: number }>;
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
