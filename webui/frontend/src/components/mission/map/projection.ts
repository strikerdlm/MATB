import type { PointMM, TerrainBounds } from "@/types/simulation";

export interface ProjectionViewport {
  width: number;
  height: number;
}

export interface ProjectedPoint {
  x: number;
  y: number;
}

export interface MissionProjection {
  point(point: PointMM): ProjectedPoint;
  inverse(point: ProjectedPoint): PointMM;
  polygon(points: PointMM[]): string;
  route(points: PointMM[]): string;
  missionDistanceToPixels(distanceMm: number): number;
}

/**
 * Create the one deterministic mission-to-SVG transform used by the console.
 * Mission coordinates are millimetres with an origin at the lower-left; SVG
 * coordinates have their origin at the upper-left, hence the y inversion.
 */
export function createProjection(
  bounds: TerrainBounds,
  viewport: ProjectionViewport,
): MissionProjection {
  const widthMm = Math.max(1, bounds.max_x_mm - bounds.min_x_mm);
  const heightMm = Math.max(1, bounds.max_y_mm - bounds.min_y_mm);
  const scaleX = viewport.width / widthMm;
  const scaleY = viewport.height / heightMm;

  const point = (value: PointMM): ProjectedPoint => ({
    x: (value.x_mm - bounds.min_x_mm) * scaleX,
    y: viewport.height - (value.y_mm - bounds.min_y_mm) * scaleY,
  });

  const inverse = (value: ProjectedPoint): PointMM => ({
    x_mm: Math.round(value.x / scaleX + bounds.min_x_mm),
    y_mm: Math.round((viewport.height - value.y) / scaleY + bounds.min_y_mm),
  });

  const serialize = (points: PointMM[]): string =>
    points.map((value) => {
      const projected = point(value);
      return `${projected.x.toFixed(2)},${projected.y.toFixed(2)}`;
    }).join(" ");

  return {
    point,
    inverse,
    polygon: serialize,
    route: serialize,
    missionDistanceToPixels: (distanceMm) => distanceMm * Math.min(scaleX, scaleY),
  };
}
