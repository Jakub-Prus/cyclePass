# Architecture

## System Overview

CyclePass should score short road segments with a hybrid pipeline that fuses map attributes, street-level imagery, and explicit policy rules.

## Processing Flow

1. Segment the road network into short units, ideally `20-50 m`.
2. Collect nearby forward and backward street-level views for each segment.
3. Extract structured OSM features.
4. Run a rules-first classifier on structured features.
5. Escalate only ambiguous or low-confidence segments to the visual stack.
6. Fuse structured and visual features for escalated segments only.
7. Apply a rules layer for legal and safety overrides.
8. Emit class, confidence, score, and explanation.

This is the MVP architecture. A future v2 can move to an always-on fused model, but the initial system should be a true two-path pipeline.

## Core Components

### 1. Road-Network Segmentation

Each segment should include:

- segment identifier
- geometry
- road class
- speed limit
- lanes
- bicycle and sidewalk tags
- intersection flags
- optional slope/elevation

### 2. Visual Understanding

Candidate model tasks:

- semantic segmentation for road, sidewalk, curb, vegetation, parked cars, barriers
- object detection for signs, bollards, lane markings, and separators
- optional depth estimation for width and separation cues

Candidate model families:

- segmentation: SegFormer, Mask2Former, DeepLab-style models
- detection: YOLOv8/11, RT-DETR
- image encoders: DINOv2, CLIP, ConvNeXt, ViT

### 3. Map Feature Encoder

Structured inputs should include:

- `highway`
- `maxspeed`
- `lanes`
- `oneway`
- `sidewalk`
- `cycleway`
- `bicycle`
- `surface`
- `lit`
- `smoothness`
- nearby crossings and barriers

### 4. Fusion Layer

Recommended path:

- MVP: gradient-boosted trees over engineered map features for the rules-first stage, plus a second-stage model over map and visual features for escalated segments
- v2: multimodal neural network
- v3: graph neural network for connected segment smoothing

### 5. Rules Layer

Some conditions should remain hard or semi-hard rules:

- `bicycle=no` -> legally not rideable
- `bicycle=dismount` or equivalent access restrictions -> physically traversable but not legally rideable in-saddle
- high speed with no protected infrastructure -> usually low comfort or not suitable
- narrow high-speed arterial with no separation -> usually not suitable
- sidewalk/shared path -> map separately for legal status and physical usability based on local rules

The rules layer must not collapse legality, physical traversability, and comfort into one field. Those signals should remain separate and then be mapped into the final class.

## Product Surfaces

- scoring API
- map QA dashboard
- routing-engine integration
