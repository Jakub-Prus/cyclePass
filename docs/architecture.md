# Architecture

## System Overview

CyclePass should score short road segments with a hybrid pipeline that fuses map attributes, street-level imagery, and explicit policy rules.

## Processing Flow

1. Segment the road network into short units, ideally `20-50 m`.
2. Collect nearby forward and backward street-level views for each segment.
3. Extract structured OSM features.
4. Run visual models for scene understanding on ambiguous or low-confidence cases.
5. Fuse structured and visual features into a segment classifier.
6. Apply a rules layer for legal and safety overrides.
7. Emit class, confidence, score, and explanation.

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

- MVP: gradient-boosted trees over engineered map and visual features
- v2: multimodal neural network
- v3: graph neural network for connected segment smoothing

### 5. Rules Layer

Some conditions should remain hard or semi-hard rules:

- `bicycle=no` -> not crossable
- high speed with no protected infrastructure -> usually not suitable
- narrow high-speed arterial with no separation -> fail
- sidewalk/shared path -> only allowed when local rules permit it

This makes the system easier to explain and more robust than a pure vision model.

## Product Surfaces

- scoring API
- map QA dashboard
- routing-engine integration
