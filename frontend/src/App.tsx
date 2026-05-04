import { useEffect, useRef, useState } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

import { analyzeArea, searchLocation } from "./api";
import type { AnalyzeResponse, Segment, SegmentClass } from "./types";

const DEFAULT_CENTER = { lat: 52.2297, lon: 21.0122 };
const DEFAULT_RADIUS_M = 350;
const DEFAULT_ZOOM = 15;
const SUMMARY_KEYS: Array<{ key: SegmentClass | "total"; label: string }> = [
  { key: "total", label: "Segments" },
  { key: "protected", label: "Protected" },
  { key: "low-stress", label: "Low-stress" },
  { key: "shared", label: "Shared" },
  { key: "not-suitable", label: "Not suitable" },
];

const CLASS_COLORS: Record<SegmentClass, string> = {
  protected: "#0b8f55",
  "low-stress": "#1d7ed6",
  shared: "#d08b12",
  "not-suitable": "#c13f30",
};

function App() {
  const mapElementRef = useRef<HTMLDivElement | null>(null);
  const mapInstanceRef = useRef<L.Map | null>(null);
  const segmentLayerRef = useRef<L.LayerGroup | null>(null);

  const [query, setQuery] = useState("Warsaw, Poland");
  const [radiusM, setRadiusM] = useState(DEFAULT_RADIUS_M);
  const [center, setCenter] = useState(DEFAULT_CENTER);
  const [status, setStatus] = useState("Searching nearby OSM roads...");
  const [isPending, setIsPending] = useState(false);
  const [analysis, setAnalysis] = useState<AnalyzeResponse | null>(null);
  const [selectedSegment, setSelectedSegment] = useState<Segment | null>(null);

  useEffect(() => {
    if (!mapElementRef.current || mapInstanceRef.current) {
      return;
    }

    const map = L.map(mapElementRef.current, {
      zoomControl: true,
    }).setView([DEFAULT_CENTER.lat, DEFAULT_CENTER.lon], DEFAULT_ZOOM);

    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(map);

    const segmentLayer = L.layerGroup().addTo(map);

    map.on("moveend", () => {
      const mapCenter = map.getCenter();
      setCenter({ lat: mapCenter.lat, lon: mapCenter.lng });
    });

    mapInstanceRef.current = map;
    segmentLayerRef.current = segmentLayer;
  }, []);

  useEffect(() => {
    void loadAnalysis(DEFAULT_CENTER.lat, DEFAULT_CENTER.lon, DEFAULT_RADIUS_M);
  }, []);

  useEffect(() => {
    if (!analysis || !segmentLayerRef.current) {
      return;
    }

    segmentLayerRef.current.clearLayers();

    for (const segment of analysis.segments) {
      const polyline = L.polyline(
        segment.geometry.map((point) => [point.lat, point.lon]),
        {
          color: CLASS_COLORS[segment.score.bike_crossable_class],
          weight: 6,
          opacity: 0.85,
        }
      );

      polyline.on("click", () => {
        setSelectedSegment(segment);
      });

      polyline.bindPopup(
        `<strong>${segment.name}</strong><br />${segment.score.bike_crossable_label}<br />Comfort: ${segment.score.bike_comfort}/100`
      );

      polyline.addTo(segmentLayerRef.current);
    }
  }, [analysis]);

  async function loadAnalysis(lat: number, lon: number, nextRadiusM: number) {
    setIsPending(true);
    setStatus("Fetching nearby road data from the backend...");

    try {
      const response = await analyzeArea(lat, lon, nextRadiusM);
      setAnalysis(response);
      setSelectedSegment(response.segments[0] ?? null);
      setStatus(`Loaded ${response.summary.total ?? response.segments.length} nearby road segments.`);

      const map = mapInstanceRef.current;
      if (map) {
        map.setView([lat, lon], map.getZoom());
      }
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Analysis failed.");
    } finally {
      setIsPending(false);
    }
  }

  async function handleSearchSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!query.trim()) {
      setStatus("Enter a location name first.");
      return;
    }

    setIsPending(true);
    setStatus(`Searching for "${query}"...`);

    try {
      const results = await searchLocation(query.trim());
      const result = results[0];

      if (!result) {
        setStatus("No matching place was found.");
        return;
      }

      const nextCenter = { lat: result.lat, lon: result.lon };
      setCenter(nextCenter);
      setStatus(`Found ${result.display_name}. Loading nearby roads...`);
      await loadAnalysis(nextCenter.lat, nextCenter.lon, radiusM);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Search failed.");
    } finally {
      setIsPending(false);
    }
  }

  function handleUseMyLocation() {
    if (!navigator.geolocation) {
      setStatus("Geolocation is not available in this browser.");
      return;
    }

    setIsPending(true);
    setStatus("Requesting your current location...");

    navigator.geolocation.getCurrentPosition(
      async (position) => {
        const nextCenter = {
          lat: position.coords.latitude,
          lon: position.coords.longitude,
        };
        setCenter(nextCenter);
        await loadAnalysis(nextCenter.lat, nextCenter.lon, radiusM);
        setIsPending(false);
      },
      () => {
        setStatus("Unable to read your location.");
        setIsPending(false);
      },
      { enableHighAccuracy: true, timeout: 10000 }
    );
  }

  const summary = analysis?.summary ?? { total: 0, protected: 0, "low-stress": 0, shared: 0, "not-suitable": 0 };

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="panel">
          <p className="eyebrow">CyclePass MVP</p>
          <h1>React frontend + Python backend</h1>
          <p className="lede">
            This MVP uses only free OpenStreetMap-derived data. The backend fetches and scores nearby road segments;
            the frontend renders them for inspection on a live map.
          </p>
        </div>

        <form className="panel controls" onSubmit={handleSearchSubmit}>
          <label className="field">
            <span>Search location</span>
            <input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Warsaw, Berlin, Amsterdam..."
            />
          </label>

          <div className="button-row">
            <button type="submit" disabled={isPending}>
              Search
            </button>
            <button type="button" disabled={isPending} onClick={handleUseMyLocation}>
              Use my location
            </button>
          </div>

          <label className="field">
            <span>Fetch radius</span>
            <input
              type="range"
              min="150"
              max="900"
              step="50"
              value={radiusM}
              onChange={(event) => setRadiusM(Number(event.target.value))}
            />
            <strong>{radiusM} m</strong>
          </label>

          <button
            type="button"
            disabled={isPending}
            onClick={() => {
              void loadAnalysis(center.lat, center.lon, radiusM);
            }}
          >
            Analyze current map center
          </button>

          <p className="status">{status}</p>
        </form>

        <section className="panel">
          <h2>Legend</h2>
          <ul className="legend">
            {Object.entries(CLASS_COLORS).map(([className, color]) => (
              <li key={className}>
                <span className="swatch" style={{ backgroundColor: color }} />
                {analysis?.segments.find((segment) => segment.score.bike_crossable_class === className)?.score
                  .bike_crossable_label ??
                  fallbackClassLabel(className as SegmentClass)}
              </li>
            ))}
          </ul>
        </section>

        <section className="panel">
          <h2>Area summary</h2>
          <dl className="summary">
            {SUMMARY_KEYS.map((item) => (
              <div key={item.key}>
                <dt>{item.label}</dt>
                <dd>{summary[item.key] ?? 0}</dd>
              </div>
            ))}
          </dl>
        </section>
      </aside>

      <main className="map-shell">
        <div ref={mapElementRef} id="map" aria-label="Map with scored road segments" />
      </main>

      <aside className="inspector">
        <section className="panel detail-panel">
          <h2>Selected segment</h2>
          {selectedSegment ? <SegmentDetails segment={selectedSegment} /> : <p>No segment selected yet.</p>}
        </section>
      </aside>
    </div>
  );
}

function SegmentDetails({ segment }: { segment: Segment }) {
  const interpretedTagsToShow = [
    ["name", segment.name],
    ["highway", segment.score.normalized_tags.highway ?? "unknown"],
    ["bicycle", segment.score.normalized_tags.bicycle ?? "unknown"],
    ["cycleway", segment.score.normalized_tags.cycleway ?? "none"],
    ["cycleway_left", segment.score.normalized_tags.cycleway_left ?? "none"],
    ["cycleway_right", segment.score.normalized_tags.cycleway_right ?? "none"],
    ["sidewalk", segment.score.normalized_tags.sidewalk ?? "unknown"],
    ["footway", segment.score.normalized_tags.footway ?? "unknown"],
    ["surface", segment.score.normalized_tags.surface ?? "unknown"],
    ["maxspeed_kph", segment.score.normalized_tags.maxspeed ?? "unknown"],
  ];
  const rawTagsToShow = Object.entries(segment.tags)
    .sort(([leftKey], [rightKey]) => leftKey.localeCompare(rightKey))
    .map(([key, value]) => [key, value] as const);

  return (
    <>
      <p>
        <span className={`pill ${segment.score.bike_crossable_class}`}>{segment.score.bike_crossable_label}</span>
      </p>

      <dl className="metric-grid">
        <div>
          <dt>Bike allowed</dt>
          <dd>{segment.score.bike_allowed}</dd>
        </div>
        <div>
          <dt>Comfort</dt>
          <dd>{segment.score.bike_comfort}/100</dd>
        </div>
        <div>
          <dt>Confidence</dt>
          <dd>{segment.score.confidence}</dd>
        </div>
        <div>
          <dt>OSM way id</dt>
          <dd>{segment.id}</dd>
        </div>
      </dl>

      <h3>Why</h3>
      <ul className="reason-list">
        {(segment.score.reasons.length ? segment.score.reasons : ["No strong rules fired."]).map((reason) => (
          <li key={reason}>{reason}</li>
        ))}
      </ul>

      <h3>Interpreted inputs</h3>
      <ul className="tag-list">
        {interpretedTagsToShow.map(([key, value]) => (
          <li key={key}>
            <strong>{key}</strong>: {String(value)}
          </li>
        ))}
      </ul>

      <h3>Raw OSM tags</h3>
      <ul className="tag-list">
        {rawTagsToShow.length ? (
          rawTagsToShow.map(([key, value]) => (
            <li key={key}>
              <strong>{key}</strong>: {value}
            </li>
          ))
        ) : (
          <li>No raw OSM tags were returned for this segment.</li>
        )}
      </ul>
    </>
  );
}

function fallbackClassLabel(className: SegmentClass): string {
  if (className === "protected") {
    return "Protected / dedicated bike infrastructure";
  }
  if (className === "low-stress") {
    return "Low-stress mixed street";
  }
  if (className === "shared") {
    return "Sidewalk/shared path usable by bike";
  }
  return "Not suitable for cycling";
}

export default App;
