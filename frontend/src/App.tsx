import { useEffect, useRef, useState } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

import { analyzeArea, findRoute, searchLocation } from "./api";
import type { AnalyzeResponse, RouteResponse, Segment, SegmentClass } from "./types";

const DEFAULT_CENTER = { lat: 51.9721, lon: 17.5012 };
const DEFAULT_INSPECTION_RADIUS_M = 350;
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
const START_MARKER_COLOR = "#0b8f55";
const END_MARKER_COLOR = "#c13f30";

function App() {
  const mapElementRef = useRef<HTMLDivElement | null>(null);
  const mapInstanceRef = useRef<L.Map | null>(null);
  const segmentLayerRef = useRef<L.LayerGroup | null>(null);
  const routeLayerRef = useRef<L.LayerGroup | null>(null);
  const pickerLayerRef = useRef<L.LayerGroup | null>(null);
  const pickModeRef = useRef<"start" | "end" | null>(null);

  const [startQuery, setStartQuery] = useState("");
  const [endQuery, setEndQuery] = useState("");
  const [inspectionRadiusM, setInspectionRadiusM] = useState(DEFAULT_INSPECTION_RADIUS_M);
  const [center, setCenter] = useState(DEFAULT_CENTER);
  const [status, setStatus] = useState("Set a route start and end, then find a bike-safe route.");
  const [isPending, setIsPending] = useState(false);
  const [analysis, setAnalysis] = useState<AnalyzeResponse | null>(null);
  const [selectedSegment, setSelectedSegment] = useState<Segment | null>(null);
  const [route, setRoute] = useState<RouteResponse | null>(null);
  const [routeStart, setRouteStart] = useState<{ lat: number; lon: number } | null>(null);
  const [routeEnd, setRouteEnd] = useState<{ lat: number; lon: number } | null>(null);
  const [pickMode, setPickMode] = useState<"start" | "end" | null>(null);

  useEffect(() => {
    pickModeRef.current = pickMode;
  }, [pickMode]);

  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map) {
      return;
    }

    const container = map.getContainer();
    if (pickMode) {
      container.classList.add("map-picking");
      return;
    }

    container.classList.remove("map-picking");
  }, [pickMode]);

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
    const routeLayer = L.layerGroup().addTo(map);
    const pickerLayer = L.layerGroup().addTo(map);

    map.on("moveend", () => {
      const mapCenter = map.getCenter();
      setCenter({ lat: mapCenter.lat, lon: mapCenter.lng });
    });

    map.on("click", (event: L.LeafletMouseEvent) => {
      const activePickMode = pickModeRef.current;
      if (!activePickMode) {
        return;
      }

      const nextPoint = {
        lat: event.latlng.lat,
        lon: event.latlng.lng,
      };
      setRoute(null);
      const formattedPoint = formatPoint(nextPoint);

      if (activePickMode === "start") {
        setRouteStart(nextPoint);
        setStartQuery(formattedPoint);
        setStatus("Route start set from the map. Now set the end or run routing.");
      } else {
        setRouteEnd(nextPoint);
        setEndQuery(formattedPoint);
        setStatus("Route end set from the map. Now set the start or run routing.");
      }

      setPickMode(null);
    });

    mapInstanceRef.current = map;
    segmentLayerRef.current = segmentLayer;
    routeLayerRef.current = routeLayer;
    pickerLayerRef.current = pickerLayer;
  }, []);

  useEffect(() => {
    if (!pickerLayerRef.current) {
      return;
    }

    pickerLayerRef.current.clearLayers();

    if (routeStart) {
      const startMarker = L.marker([routeStart.lat, routeStart.lon], {
        draggable: true,
        title: "Route start",
        icon: buildRoutePinIcon("A", START_MARKER_COLOR),
      });

      startMarker.on("dragend", (event: L.DragEndEvent) => {
        const marker = event.target as L.Marker;
        const nextLatLng = marker.getLatLng();
        const nextPoint = { lat: nextLatLng.lat, lon: nextLatLng.lng };
        setRouteStart(nextPoint);
        setStartQuery(formatPoint(nextPoint));
        setRoute(null);
        setStatus("Route start moved. Run routing again to refresh the path.");
      });

      startMarker.bindTooltip("Route start");
      startMarker.addTo(pickerLayerRef.current);
    }

    if (routeEnd) {
      const endMarker = L.marker([routeEnd.lat, routeEnd.lon], {
        draggable: true,
        title: "Route end",
        icon: buildRoutePinIcon("B", END_MARKER_COLOR),
      });

      endMarker.on("dragend", (event: L.DragEndEvent) => {
        const marker = event.target as L.Marker;
        const nextLatLng = marker.getLatLng();
        const nextPoint = { lat: nextLatLng.lat, lon: nextLatLng.lng };
        setRouteEnd(nextPoint);
        setEndQuery(formatPoint(nextPoint));
        setRoute(null);
        setStatus("Route end moved. Run routing again to refresh the path.");
      });

      endMarker.bindTooltip("Route end");
      endMarker.addTo(pickerLayerRef.current);
    }
  }, [routeStart, routeEnd]);

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

  useEffect(() => {
    if (!routeLayerRef.current) {
      return;
    }

    routeLayerRef.current.clearLayers();
    if (!route) {
      return;
    }

    for (const segment of route.segments) {
      const polyline = L.polyline(
        segment.geometry.map((point) => [point.lat, point.lon]),
        {
          color: CLASS_COLORS[segment.score.bike_crossable_class],
          weight: 7,
          opacity: 0.95,
        }
      );

      polyline.on("click", () => {
        setSelectedSegment(segment);
      });

      polyline.bindPopup(
        `<strong>${segment.name}</strong><br />${segment.score.bike_crossable_label}<br />Comfort: ${segment.score.bike_comfort}/100`
      );

      polyline.addTo(routeLayerRef.current);
    }

    L.circleMarker([route.snapped_start.lat, route.snapped_start.lon], {
      radius: 7,
      color: "#0b8f55",
      fillColor: "#0b8f55",
      fillOpacity: 1,
    })
      .bindTooltip("Route start")
      .addTo(routeLayerRef.current);

    L.circleMarker([route.snapped_end.lat, route.snapped_end.lon], {
      radius: 7,
      color: "#c13f30",
      fillColor: "#c13f30",
      fillOpacity: 1,
    })
      .bindTooltip("Route end")
      .addTo(routeLayerRef.current);
  }, [route]);

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

  async function handleRouteSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if ((!routeStart && !startQuery.trim()) || (!routeEnd && !endQuery.trim())) {
      setStatus("Set both route endpoints by map click or by typing both locations.");
      return;
    }

    setIsPending(true);
    setStatus("Resolving route endpoints...");

    try {
      let nextRouteStart = routeStart;
      let nextRouteEnd = routeEnd;

      if (!nextRouteStart && startQuery.trim()) {
        const startResults = await searchLocation(startQuery.trim());
        const startResult = startResults[0];
        if (!startResult) {
          setStatus("No matching start location was found.");
          return;
        }
        nextRouteStart = { lat: startResult.lat, lon: startResult.lon };
        setRouteStart(nextRouteStart);
      }

      if (!nextRouteEnd && endQuery.trim()) {
        const endResults = await searchLocation(endQuery.trim());
        const endResult = endResults[0];
        if (!endResult) {
          setStatus("No matching end location was found.");
          return;
        }
        nextRouteEnd = { lat: endResult.lat, lon: endResult.lon };
        setRouteEnd(nextRouteEnd);
      }

      if (!nextRouteStart || !nextRouteEnd) {
        setStatus("Both route endpoints must be resolved before routing.");
        return;
      }

      setStatus("Finding a bike-safe route...");
      const response = await findRoute(nextRouteStart, nextRouteEnd);
      setRoute(response);
      setSelectedSegment(response.segments[0] ?? null);
      setCenter(response.snapped_start);

      const map = mapInstanceRef.current;
      if (map) {
        const bounds = L.latLngBounds(response.geometry.map((point) => [point.lat, point.lon] as [number, number]));
        map.fitBounds(bounds.pad(0.15));
      }

      setStatus(`Route found: ${Math.round(response.total_length_m)} m with average comfort ${response.average_comfort}/100.`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Route failed.");
    } finally {
      setIsPending(false);
    }
  }

  const summary = analysis?.summary ?? { total: 0, protected: 0, "low-stress": 0, shared: 0, "not-suitable": 0 };

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="panel">
          <p className="eyebrow">CyclePass MVP</p>
          <h1>Bike-safe route finding</h1>
          <p className="lede">
            Set a start and end point, then let the backend avoid hostile roads and prefer calmer bike-usable links.
          </p>
        </div>

        <form className="panel controls" onSubmit={handleRouteSubmit}>
          <h2>Route planner</h2>

          <label className="field">
            <span>Start location</span>
            <div className="picker-field">
              <input
                type="search"
                value={startQuery}
                onChange={(event) => {
                  setStartQuery(event.target.value);
                  setRouteStart(null);
                  setRoute(null);
                }}
                placeholder="Type a start location or pick it on the map"
              />
              <button
                type="button"
                className="picker-button"
                disabled={isPending}
                onClick={() => {
                  setPickMode("start");
                  setStatus("Click on the map to set the route start.");
                }}
              >
                {pickMode === "start" ? "Picking..." : "Pick"}
              </button>
            </div>
          </label>

          <label className="field">
            <span>End location</span>
            <div className="picker-field">
              <input
                type="search"
                value={endQuery}
                onChange={(event) => {
                  setEndQuery(event.target.value);
                  setRouteEnd(null);
                  setRoute(null);
                }}
                placeholder="Type a destination or pick it on the map"
              />
              <button
                type="button"
                className="picker-button"
                disabled={isPending}
                onClick={() => {
                  setPickMode("end");
                  setStatus("Click on the map to set the route end.");
                }}
              >
                {pickMode === "end" ? "Picking..." : "Pick"}
              </button>
            </div>
          </label>

          <div className="route-builder">
            <button type="submit" disabled={isPending}>
              Find bike-safe route
            </button>
          </div>

          <p className="status">{status}</p>
        </form>

        <section className="panel controls">
          <h2>Area inspection</h2>
          <p className="detail-note">
            Segment analysis is secondary now. Use it only when you want to inspect the current map center manually.
          </p>
          <div className="button-row">
            <button
              type="button"
              disabled={isPending}
              onClick={() => {
                void loadAnalysis(center.lat, center.lon, inspectionRadiusM);
              }}
            >
              Analyze current map center
            </button>
            <button
              type="button"
              disabled={isPending && !analysis}
              onClick={() => {
                setAnalysis(null);
                segmentLayerRef.current?.clearLayers();
                setSelectedSegment(route?.segments[0] ?? null);
                setStatus("Area inspection roads cleared.");
              }}
            >
              Clear roads
            </button>
          </div>

          <label className="field">
            <span>Inspection radius</span>
            <input
              type="range"
              min="150"
              max="900"
              step="50"
              value={inspectionRadiusM}
              onChange={(event) => setInspectionRadiusM(Number(event.target.value))}
            />
            <strong>{inspectionRadiusM} m</strong>
          </label>
        </section>

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

        <section className="panel">
          <h2>Route summary</h2>
          {route ? (
            <>
              <dl className="summary">
                <div>
                  <dt>Distance</dt>
                  <dd>{Math.round(route.total_length_m)} m</dd>
                </div>
                <div>
                  <dt>Avg comfort</dt>
                  <dd>{route.average_comfort}</dd>
                </div>
                <div>
                  <dt>Mode</dt>
                  <dd>{route.routing_mode === "strict" ? "bike-safe" : "safest available"}</dd>
                </div>
              </dl>
              <ul className="reason-list">
                {route.explanation.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </>
          ) : (
            <p>No route calculated yet.</p>
          )}
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
          <dt>Segment id</dt>
          <dd>{segment.id}</dd>
        </div>
      </dl>

      <p className="detail-note">
        Parent OSM way: {segment.parent_way_id ?? "unknown"}
      </p>

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

function formatPoint(point: { lat: number; lon: number } | null): string {
  if (!point) {
    return "not set";
  }

  return `${point.lat.toFixed(5)}, ${point.lon.toFixed(5)}`;
}

function buildRoutePinIcon(label: string, color: string): L.DivIcon {
  return L.divIcon({
    className: "route-pin-wrapper",
    html: `<span class="route-pin" style="--pin-color: ${color};"><span class="route-pin-label">${label}</span></span>`,
    iconSize: [28, 28],
    iconAnchor: [14, 28],
  });
}

export default App;
