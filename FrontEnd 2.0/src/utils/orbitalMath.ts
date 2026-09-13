/**
 * ASTRA Astrodynamics & 3D Globe Projection Utilities
 * Maps real SGP4 geodetic latitude, longitude, and altitude onto the 3D Canvas Globe.
 */

export interface Vector3D {
  x: number;
  y: number;
  z: number;
}

export interface ProjectedSatellitePoint {
  norad_id: number;
  name: string;
  lat: number;
  lon: number;
  alt_km: number;
  vel_kms: number;
  screenX: number;
  screenY: number;
  z: number;
  isVisible: boolean;
  radialRatio: number;
}

const EARTH_RADIUS_KM = 6371.0;

/**
 * Calculates realistic visual radial ratio above Earth surface.
 * Clamped with logarithmic compression for high orbits (GEO/HEO) so they stay visible within the viewport.
 */
export function getOrbitRadialRatio(altKm: number): number {
  const alt = Math.max(0, altKm || 400);
  if (alt <= 2000) {
    // LEO: 1.02 to 1.15 of Earth radius
    return 1.0 + (alt / EARTH_RADIUS_KM) * 0.45;
  }
  if (alt <= 20000) {
    // MEO: 1.15 to 1.30 of Earth radius
    return 1.14 + (Math.log10(alt / 2000) * 0.16);
  }
  // GEO / HEO: 1.30 to 1.45 of Earth radius
  return 1.30 + Math.min(0.18, Math.log10(alt / 20000) * 0.20);
}

/**
 * Computes Greenwich Mean Sidereal Time (GMST) in degrees from current UTC timestamp.
 * Matches the TEME-to-geodetic SGP4 conversion used by the backend.
 * Earth rotates at ~0.004178°/sec (360° per 86164.09 seconds).
 */
export function getRealTimeGMST(nowMs: number = Date.now()): number {
  const jd = (nowMs / 86400000.0) + 2440587.5;
  const dJ2000 = jd - 2451545.0;
  const t = dJ2000 / 36525.0;
  let gmst = (280.46061837 + 360.98564736629 * dJ2000 + 0.000387933 * t * t - (t * t * t) / 38710000.0) % 360.0;
  if (gmst < 0) gmst += 360.0;
  return gmst;
}

/**
 * Converts Geodetic coordinates (Lat, Lon, Alt) to 3D Cartesian coordinates relative to Earth center.
 * @param lat Latitude in degrees [-90, +90]
 * @param lon Longitude in degrees [-180, +180]
 * @param altKm Altitude in kilometers
 * @param globeRadius Visual radius of the globe on screen in pixels
 * @param viewCenterLon Longitude of the Earth meridian facing the viewer [0, 360)
 */
export function latLonAltTo3D(
  lat: number,
  lon: number,
  altKm: number,
  globeRadius: number,
  viewCenterLon: number
): Vector3D {
  // Relative longitude normalized to [-180, +180] relative to camera viewpoint
  const relLon = ((lon - viewCenterLon + 540) % 360) - 180;
  const phi = (lat * Math.PI) / 180;
  const lambda = (relLon * Math.PI) / 180;
  const rRatio = getOrbitRadialRatio(altKm);
  const r = globeRadius * rRatio;

  const x = r * Math.cos(phi) * Math.sin(lambda);
  const y = -r * Math.sin(phi); // Canvas Y is inverted
  const z = r * Math.cos(phi) * Math.cos(lambda);

  return { x, y, z };
}

/**
 * Projects a 3D point onto the 2D screen Canvas.
 * @param pos 3D Vector
 * @param cX Center X of the canvas
 * @param cY Center Y of the canvas
 * @param globeRadius Visual radius of Earth
 */
export function project3DToScreen(
  pos: Vector3D,
  cX: number,
  cY: number,
  globeRadius: number
): { screenX: number; screenY: number; isVisible: boolean } {
  const screenX = cX + pos.x;
  const screenY = cY + pos.y;
  
  // Point is on the visible front hemisphere if z >= 0
  // Or if it's high enough above the limb that Earth doesn't occlude it
  const distFromCenterSq = pos.x * pos.x + pos.y * pos.y;
  const isOccludedByEarth = pos.z < 0 && distFromCenterSq < (globeRadius * globeRadius * 0.98);

  return {
    screenX,
    screenY,
    isVisible: !isOccludedByEarth,
  };
}

/**
 * Fast proximity hit-test to find the nearest satellite to mouse click.
 */
export function findSatelliteAtScreenPos(
  mouseX: number,
  mouseY: number,
  satellites: ProjectedSatellitePoint[],
  hitRadius = 15
): ProjectedSatellitePoint | null {
  let closest: ProjectedSatellitePoint | null = null;
  let minDistanceSq = hitRadius * hitRadius;

  for (const sat of satellites) {
    if (!sat.isVisible) continue;
    const dx = sat.screenX - mouseX;
    const dy = sat.screenY - mouseY;
    const distSq = dx * dx + dy * dy;

    if (distSq < minDistanceSq) {
      minDistanceSq = distSq;
      closest = sat;
    }
  }

  return closest;
}
