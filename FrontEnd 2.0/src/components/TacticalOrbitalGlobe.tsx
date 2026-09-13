"use client";

import React, { useEffect, useRef, useState, useCallback } from "react";
import {
  getRealTimeGMST,
  latLonAltTo3D,
  project3DToScreen,
  findSatelliteAtScreenPos,
  ProjectedSatellitePoint,
} from "@/utils/orbitalMath";
import { PropagatedSatelliteState, GroundContactPass } from "@/services/astraApi";

interface TacticalOrbitalGlobeProps {
  selectedNoradId: number;
  onSelectNoradId: (noradId: number) => void;
  spacecraftStates: PropagatedSatelliteState[];
  orbitPath?: Array<{ lat: number; lon: number; alt_km: number }>;
  groundContact?: GroundContactPass | null;
  selectedCoordinates?: {
    latitude: number | null;
    longitude: number | null;
    altitude_km: number | null;
  } | null;
}

// ASTRA Reference Ground Station Coordinates
const ASTRA_REF_GS = {
  name: "ASTRA REFERENCE GROUND STATION",
  lat: 17.3850,
  lon: 78.4867,
  alt_km: 0.545,
};

export function TacticalOrbitalGlobe({
  selectedNoradId,
  onSelectNoradId,
  spacecraftStates,
  orbitPath = [],
  groundContact = null,
  selectedCoordinates,
}: TacticalOrbitalGlobeProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const offscreenPlanetRef = useRef<HTMLCanvasElement | null>(null);
  const offscreenGlowRef = useRef<HTMLCanvasElement | null>(null);
  const cachedRadiusRef = useRef<number>(0);
  const cachedGlowRadiusRef = useRef<number>(0);
  const projectedSatsRef = useRef<ProjectedSatellitePoint[]>([]);

  // Real-Time Buffer for Smooth Visualization between Backend-Propagated SGP4 State Updates
  const interpolatorRef = useRef<
    Map<
      number,
      {
        prev: { lat: number; lon: number; alt_km: number; time: number };
        curr: { lat: number; lon: number; alt_km: number; time: number };
        vel_kms: number;
        name: string;
      }
    >
  >(new Map());

  // Earth View Orientation Drag Offset
  const userViewOffsetLonRef = useRef<number>(0.0);
  const isDraggingRef = useRef<boolean>(false);
  const lastMouseXRef = useRef<number>(0);
  const hasDraggedRef = useRef<boolean>(false);

  const [worldData, setWorldData] = useState<any | null>(null);

  // Load GeoJSON landmass boundaries from public/world-geojson.js if available
  useEffect(() => {
    if (typeof window !== "undefined" && (window as any).WORLD_GEOJSON) {
      setWorldData((window as any).WORLD_GEOJSON);
    } else {
      const existingScript = document.getElementById("world-geojson-script");
      if (!existingScript) {
        const script = document.createElement("script");
        script.id = "world-geojson-script";
        script.src = "/world-geojson.js";
        script.onload = () => {
          if ((window as any).WORLD_GEOJSON) {
            setWorldData((window as any).WORLD_GEOJSON);
          }
        };
        document.body.appendChild(script);
      }
    }
  }, []);

  // Update SGP4 States whenever spacecraftStates prop updates
  useEffect(() => {
    const nowMs = Date.now();
    spacecraftStates.forEach((sat) => {
      const existing = interpolatorRef.current.get(sat.norad_id);
      if (!existing) {
        interpolatorRef.current.set(sat.norad_id, {
          prev: { lat: sat.lat, lon: sat.lon, alt_km: sat.alt_km, time: nowMs - 2000 },
          curr: { lat: sat.lat, lon: sat.lon, alt_km: sat.alt_km, time: nowMs },
          vel_kms: sat.vel_kms || 7.6,
          name: sat.name,
        });
      } else {
        if (sat.lat !== existing.curr.lat || sat.lon !== existing.curr.lon) {
          existing.prev = { ...existing.curr };
          existing.curr = { lat: sat.lat, lon: sat.lon, alt_km: sat.alt_km, time: nowMs };
          existing.vel_kms = sat.vel_kms || existing.vel_kms;
          existing.name = sat.name;
        }
      }
    });
  }, [spacecraftStates]);

  // Update 1 Hz WebSocket State for Selected Satellite
  useEffect(() => {
    if (!selectedCoordinates || !selectedNoradId) return;
    if (selectedCoordinates.latitude === null || selectedCoordinates.longitude === null) return;
    const nowMs = Date.now();
    const lat = selectedCoordinates.latitude;
    const lon = selectedCoordinates.longitude;
    const alt_km = selectedCoordinates.altitude_km ?? 400;

    const existing = interpolatorRef.current.get(selectedNoradId);
    if (existing) {
      if (lat !== existing.curr.lat || lon !== existing.curr.lon) {
        existing.prev = { ...existing.curr };
        existing.curr = {
          lat,
          lon,
          alt_km,
          time: nowMs,
        };
      }
    } else {
      interpolatorRef.current.set(selectedNoradId, {
        prev: {
          lat,
          lon,
          alt_km,
          time: nowMs - 1000,
        },
        curr: {
          lat,
          lon,
          alt_km,
          time: nowMs,
        },
        vel_kms: 7.66,
        name: "TARGET SPACECRAFT",
      });
    }
  }, [selectedCoordinates, selectedNoradId]);

  // Handle Mouse Drag for User Earth View Panning
  const handleMouseDown = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    isDraggingRef.current = true;
    hasDraggedRef.current = false;
    lastMouseXRef.current = e.clientX;
  }, []);

  const handleMouseMove = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!isDraggingRef.current) return;
    const dx = e.clientX - lastMouseXRef.current;
    if (Math.abs(dx) > 2) hasDraggedRef.current = true;
    lastMouseXRef.current = e.clientX;
    userViewOffsetLonRef.current = (userViewOffsetLonRef.current - dx * 0.35 + 360.0) % 360.0;
  }, []);

  const handleMouseUp = useCallback(() => {
    isDraggingRef.current = false;
  }, []);

  // Handle Canvas Click to Select Satellite (Only if not dragging)
  const handleCanvasClick = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      if (hasDraggedRef.current) return;
      const canvas = canvasRef.current;
      if (!canvas) return;
      const rect = canvas.getBoundingClientRect();
      const mouseX = e.clientX - rect.left;
      const mouseY = e.clientY - rect.top;

      const hit = findSatelliteAtScreenPos(mouseX, mouseY, projectedSatsRef.current, 14);
      if (hit) {
        onSelectNoradId(hit.norad_id);
      }
    },
    [onSelectNoradId]
  );

  // Main Canvas Rendering Loop (Physically Real-Time, Synchronized to UTC)
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let animId: number;

    // Static procedural starfield
    const starCount = 120;
    const stars: Array<{ x: number; y: number; opacity: number }> = [];
    for (let i = 0; i < starCount; i++) {
      stars.push({
        x: Math.random(),
        y: Math.random(),
        opacity: 0.15 + Math.random() * 0.4,
      });
    }

    // Function to render the 3D volumetric planet sphere onto an offscreen canvas
    const getPlanetCanvas = (radius: number): HTMLCanvasElement => {
      const roundedRadius = Math.round(radius);
      if (offscreenPlanetRef.current && cachedRadiusRef.current === roundedRadius) {
        return offscreenPlanetRef.current;
      }

      const size = roundedRadius * 2;
      const offscreen = document.createElement("canvas");
      offscreen.width = size;
      offscreen.height = size;
      const offCtx = offscreen.getContext("2d");
      if (!offCtx) return offscreen;

      const imgData = offCtx.createImageData(size, size);
      const data = imgData.data;
      const r2 = roundedRadius * roundedRadius;

      // Light direction from upper-left: (-0.68, -0.42, 0.60)
      const lx = -0.68, ly = -0.42, lz = 0.60;
      const lLen = Math.sqrt(lx * lx + ly * ly + lz * lz);
      const nLx = lx / lLen, nLy = ly / lLen, nLz = lz / lLen;

      for (let y = 0; y < size; y++) {
        for (let x = 0; x < size; x++) {
          const dx = x - roundedRadius;
          const dy = y - roundedRadius;
          const distSq = dx * dx + dy * dy;

          if (distSq <= r2) {
            const idx = (y * size + x) * 4;
            const nx = dx / roundedRadius;
            const ny = dy / roundedRadius;
            const nz = Math.sqrt(Math.max(0, 1.0 - nx * nx - ny * ny));

            const dotNL = Math.max(0.0, nx * nLx + ny * nLy + nz * nLz);
            const smoothLight = Math.min(1.0, Math.max(0.0, (dotNL - 0.05) / 0.72));

            const dayR = 24, dayG = 76, dayB = 92;
            const nightR = 3, nightG = 12, nightB = 18;

            let r = nightR + (dayR - nightR) * smoothLight;
            let g = nightG + (dayG - nightG) * smoothLight;
            let b = nightB + (dayB - nightB) * smoothLight;

            const warmFactor = Math.pow(dotNL, 2.8) * 0.45;
            r += 65 * warmFactor;
            g += 46 * warmFactor;
            b += 20 * warmFactor;

            const fresnel = Math.pow(1.0 - nz, 3.2);
            r += 32 * fresnel * 0.7;
            g += 120 * fresnel * 0.7;
            b += 115 * fresnel * 0.7;

            const sunLimb = Math.pow(Math.max(0.0, -nx * 0.75 - ny * 0.45), 1.6);
            r += 140 * fresnel * sunLimb * 0.75;
            g += 135 * fresnel * sunLimb * 0.75;
            b += 110 * fresnel * sunLimb * 0.75;

            const edgeDist = Math.sqrt(distSq);
            let alpha = 1.0;
            if (edgeDist > roundedRadius - 1.5) {
              alpha = Math.max(0.0, (roundedRadius - edgeDist) / 1.5);
            }

            data[idx] = Math.min(255, Math.round(r));
            data[idx + 1] = Math.min(255, Math.round(g));
            data[idx + 2] = Math.min(255, Math.round(b));
            data[idx + 3] = Math.round(alpha * 255);
          }
        }
      }

      offCtx.putImageData(imgData, 0, 0);
      offscreenPlanetRef.current = offscreen;
      cachedRadiusRef.current = roundedRadius;
      return offscreen;
    };

    // Function to render atmospheric glow onto an offscreen canvas
    const getAtmosphereCanvas = (radius: number): HTMLCanvasElement => {
      const roundedRadius = Math.round(radius);
      if (roundedRadius <= 10) return document.createElement("canvas");
      if (offscreenGlowRef.current && cachedGlowRadiusRef.current === roundedRadius) {
        return offscreenGlowRef.current;
      }

      const scale = roundedRadius / 260;
      const padding = Math.round(95 * scale);
      const size = (roundedRadius + padding) * 2;
      const offscreen = document.createElement("canvas");
      offscreen.width = size;
      offscreen.height = size;
      const gCtx = offscreen.getContext("2d");
      if (!gCtx) return offscreen;

      const c = size / 2;
      const imgData = gCtx.createImageData(size, size);
      const data = imgData.data;

      const R = roundedRadius;
      const R_inner = R - 3;

      for (let y = 0; y < size; y++) {
        const dy = y - c;
        const dy2 = dy * dy;
        for (let x = 0; x < size; x++) {
          const dx = x - c;
          const distSq = dx * dx + dy2;

          if (distSq < R_inner * R_inner) continue;
          const dist = Math.sqrt(distSq);
          const dOut = Math.max(0, dist - R);

          const nx = dx / dist;
          const ny = dy / dist;

          const rawAngle = -nx * 0.94 - ny * 0.18 + 0.14;
          if (rawAngle <= 0) continue;

          const sunAngleWeight = Math.min(1.0, Math.pow(rawAngle / 1.08, 1.15));
          const maxReach = (26 + 42 * sunAngleWeight) * scale;
          if (dOut > maxReach) continue;

          const u = dOut / maxReach;
          const radialFade = Math.pow(1.0 - u, 2.0);

          const hotspotAngle = Math.max(0.0, -nx * 0.98 - ny * 0.14);
          const hotspot =
            Math.pow(hotspotAngle, 5.0) *
            Math.pow(Math.max(0.0, 1.0 - dOut / (34 * scale)), 2.0);

          let r = 218 * (1.0 - u * 0.6) + 52 * (u * 0.6);
          let g = 224 * (1.0 - u * 0.5) + 155 * (u * 0.5);
          let b = 196 * (1.0 - u * 0.4) + 150 * (u * 0.4);

          r = r * (1.0 - hotspot * 0.55) + 245 * (hotspot * 0.55);
          g = g * (1.0 - hotspot * 0.55) + 240 * (hotspot * 0.55);
          b = b * (1.0 - hotspot * 0.55) + 215 * (hotspot * 0.55);

          let alpha = radialFade * sunAngleWeight * 0.55 + hotspot * 0.38;
          if (dist < R) {
            alpha *= (dist - R_inner) / (R - R_inner);
          }

          alpha = Math.min(1.0, Math.max(0.0, alpha));

          const idx = (y * size + x) * 4;
          data[idx] = Math.min(255, Math.round(r));
          data[idx + 1] = Math.min(255, Math.round(g));
          data[idx + 2] = Math.min(255, Math.round(b));
          data[idx + 3] = Math.round(alpha * 255);
        }
      }

      gCtx.putImageData(imgData, 0, 0);
      offscreenGlowRef.current = offscreen;
      cachedGlowRadiusRef.current = roundedRadius;
      return offscreen;
    };

    const render = () => {
      if (!canvas) return;

      if (canvas.width < 50 || canvas.height < 50) {
        if (canvas.parentElement) {
          canvas.width = canvas.parentElement.clientWidth || 800;
          canvas.height = canvas.parentElement.clientHeight || 600;
        }
      }

      const w = canvas.width;
      const h = canvas.height;
      if (w <= 20 || h <= 20) {
        animId = requestAnimationFrame(render);
        return;
      }

      const cX = w / 2;
      const cY = h / 2;
      const radius = Math.min(w, h) * 0.38;
      if (radius <= 10) {
        animId = requestAnimationFrame(render);
        return;
      }

      // 1. Transparent Canvas Clear
      ctx.clearRect(0, 0, w, h);

      // Starfield background
      stars.forEach((star) => {
        const sx = star.x * w;
        const sy = star.y * h;
        ctx.fillStyle = `rgba(226, 232, 240, ${star.opacity * 0.45})`;
        ctx.fillRect(sx, sy, 1.2, 1.2);
      });

      // 2. Atmospheric Glow Behind Planet
      const glowCanvas = getAtmosphereCanvas(radius);
      ctx.drawImage(glowCanvas, cX - glowCanvas.width / 2, cY - glowCanvas.height / 2);

      // 3. Volumetric Planet Sphere
      const planetCanvas = getPlanetCanvas(radius);
      ctx.drawImage(planetCanvas, cX - radius, cY - radius);

      // 4. Real-Time UTC Greenwich Mean Sidereal Time (GMST) Earth Orientation
      // 1 real second = 1 second. Earth rotates at ~0.004178°/s. No accelerated speed multipliers.
      const nowMs = Date.now();
      const gmstDeg = getRealTimeGMST(nowMs);
      const earthViewCenterLon = ((gmstDeg + userViewOffsetLonRef.current) % 360.0 + 360.0) % 360.0;

      // 5. GeoJSON Continents (Clipped to Planet Disc, True Spherical Orthographic Projection)
      if (worldData && worldData.features) {
        ctx.save();
        ctx.beginPath();
        ctx.arc(cX, cY, radius - 1, 0, Math.PI * 2);
        ctx.clip();

        ctx.fillStyle = "rgba(111, 147, 138, 0.09)";
        ctx.strokeStyle = "rgba(111, 147, 138, 0.22)";
        ctx.lineWidth = 0.7;

        worldData.features.forEach((feature: any) => {
          const geometry = feature.geometry;
          if (!geometry) return;

          const renderPoly = (coords: number[][]) => {
            if (!coords || coords.length < 2) return;
            ctx.beginPath();
            coords.forEach(([lng, lat], idx) => {
              const relLon = ((lng - earthViewCenterLon + 540) % 360) - 180;
              if (Math.abs(relLon) < 89) {
                const phi = (lat * Math.PI) / 180;
                const lambda = (relLon * Math.PI) / 180;
                const px = cX + radius * Math.cos(phi) * Math.sin(lambda);
                const py = cY - radius * Math.sin(phi);
                if (idx === 0) ctx.moveTo(px, py);
                else ctx.lineTo(px, py);
              }
            });
            ctx.fill();
            ctx.stroke();
          };

          if (geometry.type === "Polygon") {
            geometry.coordinates.forEach(renderPoly);
          } else if (geometry.type === "MultiPolygon") {
            geometry.coordinates.forEach((poly: any) => poly.forEach(renderPoly));
          }
        });
        ctx.restore();
      }

      // 6. ASTRA Reference Ground Station Marker (Fixed on Earth's surface)
      const gsPos3D = latLonAltTo3D(
        ASTRA_REF_GS.lat,
        ASTRA_REF_GS.lon,
        0,
        radius,
        earthViewCenterLon
      );
      const gsScreen = project3DToScreen(gsPos3D, cX, cY, radius);

      if (gsScreen.isVisible) {
        ctx.beginPath();
        ctx.arc(gsScreen.screenX, gsScreen.screenY, 3.5, 0, Math.PI * 2);
        ctx.fillStyle = "#39C98A";
        ctx.fill();

        ctx.beginPath();
        ctx.arc(gsScreen.screenX, gsScreen.screenY, 8, 0, Math.PI * 2);
        ctx.strokeStyle = "rgba(57, 201, 138, 0.4)";
        ctx.lineWidth = 1;
        ctx.stroke();

        ctx.fillStyle = "rgba(57, 201, 138, 0.9)";
        ctx.font = "600 8.5px 'JetBrains Mono', monospace";
        ctx.fillText("ASTRA_REF_GS", gsScreen.screenX + 9, gsScreen.screenY + 3);
      }

      // 7. Draw Real Predicted SGP4 Orbit Path of Selected Satellite
      if (orbitPath && orbitPath.length > 1) {
        ctx.save();
        ctx.beginPath();
        ctx.strokeStyle = "rgba(214, 181, 74, 0.65)";
        ctx.lineWidth = 1.2;
        ctx.setLineDash([3, 4]);

        let hasMoved = false;
        orbitPath.forEach((pt) => {
          const pt3D = latLonAltTo3D(pt.lat, pt.lon, pt.alt_km || 400, radius, earthViewCenterLon);
          const sc = project3DToScreen(pt3D, cX, cY, radius);

          if (sc.isVisible) {
            if (!hasMoved) {
              ctx.moveTo(sc.screenX, sc.screenY);
              hasMoved = true;
            } else {
              ctx.lineTo(sc.screenX, sc.screenY);
            }
          } else {
            hasMoved = false;
          }
        });
        ctx.stroke();
        ctx.restore();
      }

      // 8. Smooth Visualization Interpolation between Backend-Propagated SGP4 State Updates (1 real sec = 1 sim sec)
      const projectedList: ProjectedSatellitePoint[] = [];

      spacecraftStates.forEach((sat) => {
        let curLat = sat.lat;
        let curLon = sat.lon;
        let curAlt = sat.alt_km;

        const entry = interpolatorRef.current.get(sat.norad_id);
        if (entry) {
          const timeSinceCurrMs = nowMs - entry.curr.time;

          // Smooth interpolation between authoritative updates; snap directly if backgrounded (> 8s)
          if (timeSinceCurrMs >= 0 && timeSinceCurrMs < 8000) {
            const elapsedSec = timeSinceCurrMs / 1000.0;
            const dtTrack = (entry.curr.time - entry.prev.time) / 1000.0;

            if (dtTrack > 0.05 && dtTrack < 10.0) {
              const dLat = entry.curr.lat - entry.prev.lat;
              const dLon = ((entry.curr.lon - entry.prev.lon + 540) % 360) - 180;
              const vLat = dLat / dtTrack;
              const vLon = dLon / dtTrack;

              curLat = entry.curr.lat + vLat * elapsedSec;
              curLon = ((entry.curr.lon + vLon * elapsedSec + 540) % 360) - 180;
              curAlt = entry.curr.alt_km;
            } else {
              // Initial frame fallback: compute real angular speed from physical velocity
              const orbitR = 6378.137 + (entry.curr.alt_km || 400);
              const angSpeedDegPerSec = ((entry.vel_kms || 7.6) / orbitR) * (180.0 / Math.PI);
              const dTravel = angSpeedDegPerSec * elapsedSec;
              curLon = ((entry.curr.lon + dTravel + 540) % 360) - 180;
            }
          } else {
            curLat = entry.curr.lat;
            curLon = entry.curr.lon;
            curAlt = entry.curr.alt_km;
          }
        }

        const satPos3D = latLonAltTo3D(
          curLat,
          curLon,
          curAlt,
          radius,
          earthViewCenterLon
        );
        const screen = project3DToScreen(satPos3D, cX, cY, radius);

        const isSelected = sat.norad_id === selectedNoradId;

        projectedList.push({
          norad_id: sat.norad_id,
          name: sat.name,
          lat: curLat,
          lon: curLon,
          alt_km: curAlt,
          vel_kms: sat.vel_kms,
          screenX: screen.screenX,
          screenY: screen.screenY,
          z: satPos3D.z,
          isVisible: screen.isVisible,
          radialRatio: radius,
        });

        if (isSelected) {
          // Contact line to ground station if visible pass
          if (groundContact?.is_visible && gsScreen.isVisible && screen.isVisible) {
            ctx.beginPath();
            ctx.moveTo(gsScreen.screenX, gsScreen.screenY);
            ctx.lineTo(screen.screenX, screen.screenY);
            ctx.strokeStyle = "rgba(57, 201, 138, 0.55)";
            ctx.lineWidth = 1;
            ctx.setLineDash([2, 3]);
            ctx.stroke();
            ctx.setLineDash([]);
          }

          // Selected Spacecraft Target Reticle
          ctx.beginPath();
          ctx.arc(screen.screenX, screen.screenY, 13, 0, Math.PI * 2);
          ctx.strokeStyle = "rgba(214, 181, 74, 0.85)";
          ctx.lineWidth = 1.2;
          ctx.stroke();

          ctx.beginPath();
          ctx.arc(screen.screenX, screen.screenY, 4, 0, Math.PI * 2);
          ctx.fillStyle = "#F6D365";
          ctx.fill();

          // Target Crosshairs
          ctx.strokeStyle = "rgba(246, 211, 101, 0.75)";
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.moveTo(screen.screenX - 16, screen.screenY);
          ctx.lineTo(screen.screenX - 6, screen.screenY);
          ctx.moveTo(screen.screenX + 6, screen.screenY);
          ctx.lineTo(screen.screenX + 16, screen.screenY);
          ctx.moveTo(screen.screenX, screen.screenY - 16);
          ctx.lineTo(screen.screenX, screen.screenY - 6);
          ctx.moveTo(screen.screenX, screen.screenY + 6);
          ctx.lineTo(screen.screenX, screen.screenY + 16);
          ctx.stroke();

          // Restrained Target HUD Label
          ctx.fillStyle = "#F6D365";
          ctx.font = "600 10.5px 'JetBrains Mono', monospace";
          ctx.fillText(sat.name, screen.screenX + 14, screen.screenY - 5);

          ctx.fillStyle = "rgba(180, 216, 207, 0.95)";
          ctx.font = "400 9px 'JetBrains Mono', monospace";
          ctx.fillText(
            `${curLat.toFixed(2)}° | ${curLon.toFixed(2)}° | ${curAlt.toFixed(0)} km`,
            screen.screenX + 14,
            screen.screenY + 8
          );
        } else if (screen.isVisible) {
          // Front hemisphere regular satellite point
          ctx.beginPath();
          ctx.arc(screen.screenX, screen.screenY, 2.2, 0, Math.PI * 2);
          ctx.fillStyle = "rgba(102, 143, 135, 0.75)";
          ctx.fill();
        } else {
          // Rear hemisphere occluded satellite (subtle depth fading)
          ctx.beginPath();
          ctx.arc(screen.screenX, screen.screenY, 1.2, 0, Math.PI * 2);
          ctx.fillStyle = "rgba(102, 143, 135, 0.18)";
          ctx.fill();
        }
      });

      projectedSatsRef.current = projectedList;
      animId = requestAnimationFrame(render);
    };

    render();
    return () => cancelAnimationFrame(animId);
  }, [worldData, selectedNoradId, spacecraftStates, orbitPath, groundContact]);

  // Handle Canvas Resize
  useEffect(() => {
    const handleResize = () => {
      const canvas = canvasRef.current;
      if (canvas && canvas.parentElement) {
        const pWidth = canvas.parentElement.clientWidth;
        const pHeight = canvas.parentElement.clientHeight;
        if (pWidth > 0 && pHeight > 0 && (canvas.width !== pWidth || canvas.height !== pHeight)) {
          canvas.width = pWidth;
          canvas.height = pHeight;
          cachedRadiusRef.current = 0;
          cachedGlowRadiusRef.current = 0;
        }
      }
    };
    handleResize();
    window.addEventListener("resize", handleResize);

    let ro: ResizeObserver | null = null;
    const canvas = canvasRef.current;
    if (canvas && canvas.parentElement && typeof ResizeObserver !== "undefined") {
      ro = new ResizeObserver(() => handleResize());
      ro.observe(canvas.parentElement);
    }

    return () => {
      window.removeEventListener("resize", handleResize);
      if (ro) ro.disconnect();
    };
  }, []);

  return (
    <div className="relative w-full h-full flex flex-col items-center justify-center bg-transparent overflow-hidden">
      <canvas
        ref={canvasRef}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onClick={handleCanvasClick}
        className="w-full h-full block cursor-crosshair select-none"
      />
    </div>
  );
}

export default TacticalOrbitalGlobe;
