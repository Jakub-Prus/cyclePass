# Data Model

## Segment Entity

Suggested primary record for a road segment:

```md
segment_id
geometry
length_m
country_code
road_class
maxspeed_kph
lane_count
oneway
surface
smoothness
sidewalk_type
cycleway_type
bicycle_access
intersection_flag
slope_percent
image_ids
satellite_tile_ids
traffic_proxy
```

## Model Inputs

### Structured Features

- OSM road tags
- access restrictions
- lane count
- speed limit
- surface and smoothness
- slope/elevation
- adjacency and continuity features

### Visual Features

- image embeddings from multiple views
- segmentation outputs
- object detections
- optional depth-derived width or separation estimates

## Labels

Recommended annotation schema:

```md
legally_rideable: yes | no | uncertain
physically_rideable: yes | no | uncertain
comfort_score: 0-100
novice_safe: yes | no | uncertain
facility_type:
  protected_lane
  painted_lane
  calm_mixed_street
  sidewalk_shared_path
  dismount_push_only
  forbidden
final_class:
  protected_dedicated
  low_stress_mixed
  sidewalk_shared_usable
  not_suitable
confidence: 0-1
```

## Derived Score

Suggested v1 score decomposition:

`BikeScore = legality + separation + speed_safety + width + surface + continuity + intersection_safety`

Suggested dimensions:

- legality: from OSM access rules
- separation: protected lane, buffer, or separated path
- speed_safety: maxspeed and road type
- width: estimated from imagery or geometry
- surface: OSM plus visual cues
- continuity: whether favorable conditions continue across adjacent segments
- intersection_safety: crossing complexity and barriers

## Explainability Fields

Store reasons alongside predictions:

- triggered rules
- top map features
- top detected visual cues
- model confidence
- uncertainty reason
