import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import type { CardProps } from "./Card";

// El mapa de piezas que se enciende: cards.py ya lo trae colocado (layout), así
// que aquí sólo se dibuja y se anima. La versión fija dibuja los mismos nodos.
type DNode = {
  label?: string; group?: string; color: string; svg?: string | null;
  x: number; y: number; w: number; h: number; path: string;
};
type Layout = {
  nodes: DNode[]; hub: number; active: number; mode: "piece" | "overview" | "finale";
  header: { x: number; y: number; scale: number };
};

// Mismo resorte que Card.tsx: pico a 0.25 s pasándose un 8 %.
const POP = { stiffness: 262, damping: 20.4, mass: 1 };
const EXIT = 6;
const LIGHT = 10;   // fotograma en que se enciende la pieza activa
const SOFT = { damping: 200 };

const hexA = (hex: string, a: number) =>
  `${hex}${Math.round(Math.max(0, Math.min(1, a)) * 255).toString(16).padStart(2, "0")}`;
// Los SVG de Phosphor traen su color en `fill`: se cambia por el del estado.
const recolor = (svg: string, color: string) =>
  svg.replace(/fill="#[0-9A-Fa-f]{3,8}"/, `fill="${color}"`)
     .replace("<svg ", `<svg width="100%" height="100%" `);
const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

export const Diagram: React.FC<CardProps> = ({ theme, spec }) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const { nodes, hub, active, mode, header } = spec.layout as Layout;
  const brand = theme.brand ?? theme.accent;
  const s = header.scale;

  const fadeIn = interpolate(frame, [0, 8], [0, 1], clamp);
  const fadeOut = interpolate(frame, [durationInFrames - EXIT, durationInFrames - 1], [1, 0], clamp);
  const zoom = interpolate(fadeIn, [0, 1], [0.965, 1]) * interpolate(fadeOut, [0, 1], [0.985, 1]);

  // 0 → 1: cuánto está encendida cada pieza en este fotograma.
  const lit = (i: number) => {
    if (mode === "finale") return spring({ frame: frame - LIGHT - i * 3, fps, config: SOFT });
    return i === active ? spring({ frame: frame - LIGHT, fps, config: SOFT }) : 0;
  };
  const done = (i: number) => mode === "piece" && i < active && i !== hub;
  // En el resumen las piezas entran una a una; si no, ya están en su sitio.
  const appear = (i: number) =>
    mode === "overview" ? spring({ frame: frame - 6 - i * 3, fps, config: POP }) : 1;
  const draw = (i: number) => {
    if (mode === "overview") return spring({ frame: frame - 14 - i * 3, fps, config: SOFT });
    if (mode === "finale" || i !== active) return 1;
    return spring({ frame: frame - LIGHT - 2, fps, config: { damping: 200, mass: 0.8 } });
  };

  const headIn = spring({ frame: frame - 3, fps, config: SOFT });
  const subIn = spring({ frame: frame - 8, fps, config: SOFT });
  const hubGlow = mode === "finale" ? lit(hub)
    : active >= 0 ? spring({ frame: frame - LIGHT - 12, fps, config: SOFT }) : 0;
  const pulse = 0.5 + 0.5 * Math.sin((frame / fps) * Math.PI * 1.6);
  const activeColor = active >= 0 ? nodes[active].color : brand;
  const W = 1920 * s * 4;   // cualquier lienzo mayor que el fotograma vale para el SVG

  return (
    <AbsoluteFill style={{ fontFamily: "Fragua, sans-serif", opacity: Math.min(fadeIn, fadeOut) }}>
      {/* Telón: oscurece el vídeo y deja un resplandor del color de la pieza. */}
      <AbsoluteFill style={{
        background: `radial-gradient(ellipse at 50% 52%, ${hexA(activeColor, 0.14)} 0%, `
          + `rgba(8,10,18,0.955) 55%, rgba(5,6,12,0.975) 100%)`,
      }} />
      <AbsoluteFill style={{ transform: `scale(${zoom})` }}>
        <div style={{ position: "absolute", left: header.x, top: header.y }}>
          {spec.heading ? (
            <div style={{ fontSize: 26 * s, fontWeight: 700, color: brand, letterSpacing: 1,
                          opacity: headIn, transform: `translateX(${(1 - headIn) * -16}px)` }}>
              {String(spec.heading)}
            </div>
          ) : null}
          <div style={{ fontSize: 60 * s, fontWeight: 850, color: "#F4F6FB", marginTop: 4 * s,
                        opacity: headIn, transform: `translateX(${(1 - headIn) * -24}px)` }}>
            {String(spec.title ?? "")}
          </div>
          {spec.sub ? (
            <div style={{ fontFamily: "FraguaMono, monospace", fontSize: 26 * s, color: "#9AA3B5",
                          marginTop: 8 * s, opacity: subIn,
                          transform: `translateX(${(1 - subIn) * -16}px)` }}>
              {String(spec.sub)}
            </div>
          ) : null}
        </div>

        {/* Conectores al núcleo; el de la pieza activa brilla y lleva datos. */}
        <svg width={W} height={W} style={{ position: "absolute", left: 0, top: 0 }}>
          {nodes.map((p, i) => {
            if (!p.path) return null;
            const on = lit(i);
            const k = draw(i);
            const base = done(i) ? hexA(p.color, 0.55) : "rgba(150,160,185,0.28)";
            return (
              <g key={i} opacity={appear(i)}>
                <path d={p.path} fill="none" stroke={base} strokeWidth={2.5 * s}
                      pathLength={1} strokeDasharray="1 1" strokeDashoffset={1 - (on > 0 ? 1 : k)} />
                {on > 0.01 ? (
                  <>
                    <path d={p.path} fill="none" stroke={p.color} strokeWidth={5 * s} opacity={on}
                          pathLength={1} strokeDasharray="1 1" strokeDashoffset={1 - k}
                          style={{ filter: `drop-shadow(0 0 ${8 * s}px ${p.color})` }} />
                    <path d={p.path} fill="none" stroke="#FFFFFF" strokeWidth={4 * s}
                          strokeLinecap="round" opacity={on * k * 0.9} pathLength={100}
                          strokeDasharray="1.5 9" strokeDashoffset={-(frame * 0.9)} />
                  </>
                ) : null}
              </g>
            );
          })}
        </svg>

        {nodes.map((p, i) => {
          const isHub = i === hub;
          const on = lit(i);
          const a = appear(i);
          const isDone = done(i);
          const glow = isHub ? Math.max(on, hubGlow * 0.6) : on;
          const ring = isHub && on < 0.5 ? activeColor : p.color;
          const bump = mode === "piece" && i === active
            ? spring({ frame: frame - LIGHT, fps, config: POP }) : on;
          const scale = a * (1 + (mode === "finale" ? 0.03 : 0.07) * bump
            + (i === active ? 0.012 * pulse : 0));
          const ink = on > 0.5 ? "#0B0D14" : isDone || isHub ? p.color : "#7C8598";
          const label = String(p.label ?? "");
          const icon = p.svg ? p.h * (isHub ? 0.38 : 0.45) : 0;
          const pad = p.h * (isHub ? 0.24 : 0.24);
          // La letra encoge hasta que la etiqueta cabe en la pieza.
          const room = p.w - pad * 2 - (icon ? icon + p.h * 0.19 : 0);
          const size = Math.min(p.h * (isHub ? 0.27 : 0.32), room / Math.max(1, label.length * 0.56));
          return (
            <div key={i} style={{
              position: "absolute", left: p.x, top: p.y, width: p.w, height: p.h,
              transform: `scale(${scale})`, opacity: Math.min(1, a * 1.2),
              boxSizing: "border-box", borderRadius: isHub ? p.h / 2 : 20 * s,
              display: "flex", alignItems: "center", gap: p.h * 0.19, padding: `0 ${pad}px`,
              background: on > 0
                ? `linear-gradient(135deg, ${hexA(p.color, 0.35 + 0.65 * on)}, ${hexA(p.color, 0.2 + 0.55 * on)})`
                : isHub ? "rgba(26,22,10,0.92)" : "rgba(20,23,33,0.92)",
              border: `${2 * s}px solid ${on > 0 || isDone || isHub ? hexA(p.color, 0.9) : "rgba(130,140,165,0.35)"}`,
              boxShadow: glow > 0
                ? `0 0 ${(24 + 26 * pulse * glow) * s}px ${hexA(ring, 0.55 * glow)}, 0 0 ${4 * s}px ${hexA(ring, glow)}`
                : "0 12px 30px rgba(0,0,0,0.45)",
            }}>
              {p.svg ? (
                <div style={{ width: icon, height: icon, flexShrink: 0 }}
                     dangerouslySetInnerHTML={{ __html: recolor(p.svg, ink) }} />
              ) : null}
              <div style={{ display: "flex", flexDirection: "column", lineHeight: 1.05, minWidth: 0 }}>
                {p.group ? (
                  <span style={{ fontSize: p.h * 0.18, fontWeight: 700, letterSpacing: 0.6,
                                 color: on > 0.5 ? "rgba(10,12,20,0.75)"
                                   : hexA(p.color, isDone || isHub ? 1 : 0.6) }}>
                    {p.group}
                  </span>
                ) : null}
                <span style={{ fontSize: size, fontWeight: 800, whiteSpace: "nowrap",
                               color: on > 0.5 ? "#0B0D14" : isDone || isHub ? "#EEF1F7" : "#8B93A6" }}>
                  {label}
                </span>
              </div>
              {isDone ? (
                <div style={{
                  position: "absolute", right: -11 * s, top: -11 * s, width: 26 * s, height: 26 * s,
                  borderRadius: 13 * s, background: p.color,
                  display: "flex", alignItems: "center", justifyContent: "center",
                }}>
                  <svg width={16 * s} height={16 * s} viewBox="0 0 16 16">
                    <path d="M3 8.5l3.2 3L13 4.5" fill="none" stroke="#0B0D14" strokeWidth={2.6}
                          strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </div>
              ) : null}
              {/* Onda que sale de la pieza al encenderse. */}
              {mode === "piece" && i === active ? (() => {
                const r = interpolate(frame, [LIGHT, LIGHT + 22], [0, 1], clamp);
                return r > 0 && r < 1 ? (
                  <div style={{
                    position: "absolute", inset: -6 * s, borderRadius: 24 * s,
                    border: `${3 * s}px solid ${p.color}`, opacity: 1 - r,
                    transform: `scale(${1 + r * 0.35})`,
                  }} />
                ) : null;
              })() : null}
            </div>
          );
        })}
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
