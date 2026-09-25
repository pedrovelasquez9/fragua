import React from "react";
import {
  AbsoluteFill, Img, interpolate, spring, staticFile,
  useCurrentFrame, useVideoConfig,
} from "remotion";

export type Theme = { bg: string; bgAlpha: number; fg: string; accent: string };
export type CardProps = {
  kind: string;
  dur: number;
  width: number;
  base: number;
  theme: Theme;
  spec: Record<string, unknown>;
};

const RADIUS = 26;
const PAD = 34;
const EXIT_FRAMES = 8;

const FONT_FACE = `@font-face {
  font-family: "Fragua";
  src: url("${staticFile("Roboto-Variable.ttf")}") format("truetype");
  font-weight: 100 900;
}
@font-face {
  font-family: "FraguaMono";
  src: url("${staticFile("JetBrainsMono-Variable.ttf")}") format("truetype");
  font-weight: 100 800;
}`;

const alpha = (hex: string, a: number) => {
  const v = Math.max(0, Math.min(255, Math.round(a)));
  return `${hex}${v.toString(16).padStart(2, "0")}`;
};

const listOf = (spec: Record<string, unknown>, key: string): string[] => {
  const explicit = spec[key];
  if (Array.isArray(explicit)) return explicit as string[];
  return String(spec.body ?? "").split("\n").filter(Boolean);
};

/** Rounded surface with the same hairline border the Pillow cards draw. */
const Panel: React.FC<React.PropsWithChildren<{
  theme: Theme; radius?: number; style?: React.CSSProperties;
}>> = ({ theme, radius = RADIUS, style, children }) => (
  <div style={{
    boxSizing: "border-box",
    background: alpha(theme.bg, theme.bgAlpha),
    border: `2px solid ${alpha(theme.accent, 90)}`,
    borderRadius: radius,
    boxShadow: "0 18px 40px rgba(0,0,0,0.45)",
    ...style,
  }}>{children}</div>
);

// El orden de entrada dentro de una card, en fotogramas desde su llegada. El
// filete detrás del título: dibujar un subrayado antes de que exista lo que
// subraya se lee como un error de render.
const HEADING = 4;
const RULE = 8;
const ITEMS = 12;

/** Stagger helper: element `i` starts `step` frames after the one before it. */
const useStagger = (i: number, step = 5, delay = ITEMS, damping = 15) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return spring({ frame: frame - delay - i * step, fps, config: { damping, mass: 0.5 } });
};

const Enter: React.FC<React.PropsWithChildren<{
  i?: number; from?: number; delay?: number;
}>> = ({ i = 0, from = -18, delay = ITEMS, children }) => {
  const t = useStagger(i, 5, delay);
  return (
    <div style={{ opacity: t, transform: `translateX(${interpolate(t, [0, 1], [from, 0])}px)` }}>
      {children}
    </div>
  );
};

const Heading: React.FC<React.PropsWithChildren<{ theme: Theme; base: number }>> = ({
  theme, base, children,
}) => (
  <Enter from={-10} delay={HEADING}>
    <div style={{ fontSize: base * 0.82, fontWeight: 800, color: theme.accent }}>{children}</div>
  </Enter>
);

const Rule: React.FC<{ theme: Theme }> = ({ theme }) => (
  <div style={{
    height: 2, marginTop: PAD * 0.5, marginBottom: PAD * 0.35,
    background: alpha(theme.accent, 90), transformOrigin: "left center",
    transform: `scaleX(${useStagger(0, 0, RULE, 200)})`,
  }} />
);

/** Word by word. Staggering a paragraph line by line reads as jumpy. */
const WordsIn: React.FC<{ text: string; style: React.CSSProperties; delay?: number }> = ({
  text, style, delay = ITEMS,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return (
    <span style={style}>
      {text.split(" ").map((word, i) => (
        <span key={i} style={{
          opacity: spring({ frame: frame - delay - i * 1.5, fps, config: { damping: 200 } }),
        }}>{word}{" "}</span>
      ))}
    </span>
  );
};

const Bullets: React.FC<CardProps> = ({ theme, base, width, spec }) => {
  const items = listOf(spec, "items");
  const marker = Math.max(10, base / 6);
  return (
    <Panel theme={theme} style={{ width: width * 0.8, padding: PAD }}>
      <Heading theme={theme} base={base}>{String(spec.title ?? "")}</Heading>
      <Rule theme={theme} />
      {items.map((item, i) => (
        <Bullet key={i} i={i} item={item} theme={theme} base={base} marker={marker} />
      ))}
    </Panel>
  );
};

const Bullet: React.FC<{
  i: number; item: string; theme: Theme; base: number; marker: number;
}> = ({ i, item, theme, base, marker }) => {
  const pop = useStagger(i, 5, ITEMS, 9);
  return (
    <div style={{ display: "flex", alignItems: "center", height: base * 1.15 }}>
      <Enter i={i}>
        <div style={{ display: "flex", alignItems: "center" }}>
          <div style={{
            width: marker, height: marker, borderRadius: marker / 3,
            background: theme.accent, marginRight: marker * 0.9,
            transform: `scale(${pop})`,
          }} />
          <span style={{ fontSize: base * 0.76, fontWeight: 500, color: theme.fg }}>{item}</span>
        </div>
      </Enter>
    </div>
  );
};

const PanelCard: React.FC<CardProps> = ({ theme, base, width, spec }) => {
  const title = String(spec.title ?? "");
  return (
    <Panel theme={theme} style={{ width: width * 0.8, overflow: "hidden" }}>
      {title ? (
        <div style={{
          background: alpha(theme.accent, 30), padding: `${PAD / 2}px ${PAD}px`,
          borderBottom: `2px solid ${alpha(theme.accent, 90)}`, textAlign: "center",
        }}>
          <Enter from={0} delay={HEADING}>
            <span style={{ fontSize: base * 0.82, fontWeight: 800, color: theme.accent }}>
              {title}
            </span>
          </Enter>
        </div>
      ) : null}
      <div style={{ padding: PAD, textAlign: "center" }}>
        <WordsIn text={String(spec.body ?? "").replace(/\n/g, " ")}
                 style={{ fontSize: base * 0.72, fontWeight: 500, color: theme.fg,
                          lineHeight: `${base * 1.02}px` }} />
      </div>
    </Panel>
  );
};

const Flow: React.FC<CardProps> = ({ theme, base, width, spec }) => {
  const nodes = listOf(spec, "nodes");
  const root = String(spec.root ?? spec.title ?? "");
  const gap = base * 0.46;
  const spine = useStagger(0, 0, RULE, 200);
  return (
    <div style={{ width, paddingLeft: width * 0.1, paddingRight: width * 0.1 }}>
      <Enter from={-24} delay={HEADING}>
        <Panel theme={theme} radius={999} style={{
          display: "inline-block", padding: `${PAD * 0.8}px ${PAD}px`,
        }}>
          <span style={{ fontSize: base * 0.8, fontWeight: 800, color: theme.accent }}>{root}</span>
        </Panel>
      </Enter>
      <div style={{ position: "relative", marginLeft: base * 0.55 }}>
        {/* The spine draws itself top-down before the nodes arrive. */}
        <div style={{
          position: "absolute", left: 0, top: 0, bottom: gap, width: 3,
          background: alpha(theme.accent, 90), transformOrigin: "top center",
          transform: `scaleY(${spine})`,
        }} />
        {nodes.map((node, i) => (
          <div key={i} style={{ display: "flex", alignItems: "center", marginTop: gap }}>
            <Enter i={i} from={-14}>
              <div style={{ display: "flex", alignItems: "center" }}>
                <div style={{
                  width: 14, height: 14, borderRadius: 7, background: theme.accent,
                  marginLeft: -7,
                }} />
                <div style={{
                  width: base * 0.95 - 7, height: 3, background: alpha(theme.accent, 90),
                }} />
                <Panel theme={theme} radius={base} style={{ padding: `${PAD * 0.8}px ${PAD}px` }}>
                  <span style={{ fontSize: base * 0.68, fontWeight: 500, color: theme.fg }}>
                    {node}
                  </span>
                </Panel>
              </div>
            </Enter>
          </div>
        ))}
      </div>
    </div>
  );
};

const Stat: React.FC<CardProps> = ({ theme, base, width, spec }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const raw = String(spec.value ?? "");
  // If the figure is a number, count up to it. This is what makes the stat card
  // worth using, and it is exactly what a still PNG cannot do.
  const numeric = raw.match(/^(\D*)(\d[\d.,]*)(\D*)$/);
  const grow = spring({ frame, fps, config: { damping: 18, mass: 0.8 } });
  const value = numeric
    ? `${numeric[1]}${Math.round(Number(numeric[2].replace(/[.,]/g, "")) * grow)
        .toLocaleString("es-ES")}${numeric[3]}`
    : raw;
  return (
    <Panel theme={theme} style={{ width: width * 0.72, padding: PAD, textAlign: "center" }}>
      <div style={{
        fontSize: base * 2.1, fontWeight: 900, color: theme.accent, lineHeight: 1.05,
        transform: `scale(${interpolate(grow, [0, 1], [0.86, 1])})`,
      }}>{value}</div>
      <WordsIn text={String(spec.label ?? "")} delay={10}
               style={{ fontSize: base * 0.7, fontWeight: 500, color: theme.fg,
                        lineHeight: `${base * 0.95}px` }} />
    </Panel>
  );
};

const Chip: React.FC<CardProps> = ({ theme, base, spec }) => (
  <Enter from={0}>
    <Panel theme={theme} radius={999} style={{
      display: "inline-block", padding: `${PAD * 0.9}px ${PAD * 1.4}px`,
    }}>
      <span style={{ fontSize: base * 0.86, fontWeight: 800, color: theme.accent }}>
        {String(spec.title ?? spec.content ?? "")}
      </span>
    </Panel>
  </Enter>
);

/** Loose text with no panel behind it, for the black band a pullback opens.
    A dark panel on black reads as a box floating in nothing. */
const Title: React.FC<CardProps> = ({ theme, base, width, spec }) => (
  <div style={{ width: width * 0.86, textAlign: "center" }}>
    <WordsIn text={String(spec.title ?? spec.body ?? "")} delay={HEADING}
             style={{ fontSize: base * 1.25, fontWeight: 900, color: theme.accent,
                      lineHeight: `${base * 1.5}px`, display: "inline-block" }} />
  </div>
);

type Column = { title?: string; items?: string[] };

/** X frente a Y. Las columnas llegan de izquierda a derecha, y dentro de cada
    una sus puntos: se lee la comparación en el orden en que se construye. */
const Compare: React.FC<CardProps> = ({ theme, base, width, spec }) => {
  const columns = ((spec.columns as Column[]) ?? []).slice(0, 3);
  const title = String(spec.title ?? "");
  return (
    <Panel theme={theme} style={{ width: width * 0.86, padding: PAD }}>
      {title ? (
        <>
          <Enter from={0} delay={HEADING}>
            <div style={{ fontSize: base * 0.82, fontWeight: 800, color: theme.fg,
                          textAlign: "center" }}>{title}</div>
          </Enter>
          <Rule theme={theme} />
        </>
      ) : null}
      <div style={{ display: "flex" }}>
        {columns.map((column, c) => (
          <div key={c} style={{
            flex: 1, textAlign: "center",
            borderLeft: c ? `2px solid ${alpha(theme.accent, 90)}` : "none",
          }}>
            <Enter i={c * 3} from={0}>
              <div style={{ fontSize: base * 0.8, fontWeight: 800, color: theme.accent,
                            height: base * 1.2, lineHeight: `${base * 1.2}px` }}>
                {column.title ?? ""}
              </div>
            </Enter>
            {(column.items ?? []).map((item, k) => (
              <Enter key={k} i={c * 3 + k + 1} from={0}>
                <div style={{ fontSize: base * 0.66, fontWeight: 500, color: theme.fg,
                              lineHeight: `${base * 0.98}px`, padding: `0 ${PAD / 2}px` }}>
                  {item}
                </div>
              </Enter>
            ))}
          </div>
        ))}
      </div>
    </Panel>
  );
};

// Las casillas se marcan después de que la lista haya llegado, y cada una unos
// fotogramas detrás de la anterior: lo que se ve es una lista que se va
// cumpliendo, que es justo lo que una imagen fija no puede contar.
const TICK_DELAY = 10;
const TICK_STEP = 9;

const Tick: React.FC<{ i: number; theme: Theme; side: number; ticked: boolean }> = ({
  i, theme, side, ticked,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const start = ITEMS + TICK_DELAY + i * TICK_STEP;
  const fill = ticked ? spring({ frame: frame - start, fps, config: { damping: 14 } }) : 0;
  const draw = ticked ? interpolate(frame, [start + 2, start + 9], [0, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }) : 0;
  return (
    <div style={{
      position: "relative", width: side, height: side, borderRadius: side / 4,
      border: `${Math.max(3, side / 8)}px solid ${alpha(theme.accent, 90)}`,
      boxSizing: "border-box", marginRight: side * 0.55, flexShrink: 0,
    }}>
      <div style={{
        position: "absolute", inset: -Math.max(3, side / 8), borderRadius: side / 4,
        background: theme.accent, transform: `scale(${fill})`,
      }} />
      <svg viewBox="0 0 1 1" style={{ position: "absolute", inset: 0, width: "100%",
                                      height: "100%", overflow: "visible" }}>
        <polyline points="0.22,0.52 0.42,0.72 0.78,0.30" fill="none"
                  stroke={theme.bg} strokeWidth={0.14} strokeLinecap="round"
                  strokeLinejoin="round" pathLength={1} strokeDasharray={1}
                  strokeDashoffset={1 - draw} />
      </svg>
    </div>
  );
};

const Checklist: React.FC<CardProps> = ({ theme, base, width, spec }) => {
  const items = listOf(spec, "items");
  const done = Number(spec.done ?? items.length);
  const side = base * 0.72;
  return (
    <Panel theme={theme} style={{ width: width * 0.8, padding: PAD }}>
      <Heading theme={theme} base={base}>{String(spec.title ?? "")}</Heading>
      <Rule theme={theme} />
      {items.map((item, i) => (
        <div key={i} style={{ display: "flex", alignItems: "center", height: base * 1.25 }}>
          <Enter i={i}>
            <div style={{ display: "flex", alignItems: "center" }}>
              <Tick i={i} theme={theme} side={side} ticked={i < done} />
              <span style={{ fontSize: base * 0.74, fontWeight: 500,
                             color: i < done ? theme.fg : alpha(theme.fg, 150) }}>{item}</span>
            </div>
          </Enter>
        </div>
      ))}
    </Panel>
  );
};

/** El comando se teclea. Se reparte en poco más de la mitad de la card, para que
    quede tiempo de leerlo entero antes de que se vaya. */
const TYPE_SHARE = 0.55;
const TYPE_MIN_CPS = 28;

const Code: React.FC<CardProps> = ({ theme, base, width, spec, dur }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const lines = listOf(spec, "lines");
  const prompt = String(spec.prompt ?? "$");
  const total = lines.reduce((n, line) => n + line.length, 0);
  const cps = Math.max(TYPE_MIN_CPS, total / Math.max(0.5, dur * TYPE_SHARE));
  let remaining = Math.max(0, Math.floor(((frame - ITEMS) / fps) * cps));
  const longest = Math.max(1, ...lines.map((l) => l.length + (prompt ? prompt.length + 1 : 0)));
  // Igual que la fija: la letra se encoge para que quepa la línea más larga,
  // porque un comando partido deja de poder copiarse de la pantalla.
  const size = Math.max(base * 0.36, Math.min(base * 0.66,
    (width * 0.86 - PAD * 2) / (longest * 0.6)));
  const cursorOn = Math.floor(frame / (fps * 0.5)) % 2 === 0;
  const dot = Math.max(8, base / 7);
  return (
    <Panel theme={theme} style={{ width: width * 0.86, overflow: "hidden" }}>
      <div style={{
        position: "relative", height: base * 1.05, display: "flex", alignItems: "center",
        paddingLeft: PAD, borderBottom: `2px solid ${alpha(theme.accent, 90)}`,
      }}>
        {["#FF5F56", "#FFBD2E", "#27C93F"].map((c, i) => (
          <div key={i} style={{ width: dot, height: dot, borderRadius: dot,
                                background: alpha(c, 170), marginRight: dot * 1.4 }} />
        ))}
        <span style={{ position: "absolute", left: 0, right: 0, textAlign: "center",
                       fontSize: base * 0.56, fontWeight: 500, color: alpha(theme.fg, 160) }}>
          {String(spec.title ?? "")}
        </span>
      </div>
      <div style={{ padding: `${PAD / 2}px ${PAD}px`, fontFamily: "FraguaMono, monospace",
                    fontSize: size, lineHeight: `${size * 1.48}px`, color: theme.fg,
                    whiteSpace: "pre" }}>
        {lines.map((line, i) => {
          // Como en una terminal de verdad: el prompt de una línea no aparece
          // hasta que se ha terminado la anterior. Enseñarlos todos vacíos desde
          // el principio se lee como una lista de huecos esperando.
          const reached = i === 0 || remaining > 0;
          const shown = line.slice(0, remaining);
          const here = reached && (remaining <= line.length || i === lines.length - 1);
          remaining = Math.max(0, remaining - line.length);
          if (!reached) {
            // El sitio se reserva igual: si la card creciera al teclear, daría saltos.
            return <div key={i}>{"\u00a0"}</div>;
          }
          return (
            <div key={i}>
              {prompt ? <span style={{ color: theme.accent }}>{prompt} </span> : null}
              {shown}
              {here && cursorOn ? (
                <span style={{ background: theme.accent, color: theme.bg }}>{" "}</span>
              ) : null}
            </div>
          );
        })}
      </div>
    </Panel>
  );
};

const SECTION_NUMBER = "#FF8A3D";
const SECTION_TEXT = "#F0E4CD";
const STAMP_RED = "#F0343A";
const CHECK_GREEN = "#34C759";

/** «02 · TÍTULO» arriba a la izquierda. El número entra deslizándose y el
    título letra a letra: una etiqueta que se escribe se lee como estructura, una
    que aparece entera de golpe se lee como un rótulo más. */
const Section: React.FC<CardProps> = ({ base, width, spec }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const number = spec.number != null ? String(spec.number).padStart(2, "0") : "";
  const title = String(spec.title ?? "").toUpperCase();
  const t = spring({ frame: frame - HEADING, fps, config: { damping: 18 } });
  return (
    <div style={{
      width, boxSizing: "border-box", paddingLeft: width * 0.065, paddingTop: base * 0.2,
      display: "flex", alignItems: "baseline", textShadow: "0 2px 6px rgba(0,0,0,0.8)",
    }}>
      {number ? (
        <span style={{
          fontSize: base * 0.62, fontWeight: 900, color: SECTION_NUMBER, letterSpacing: 2,
          marginRight: base * 0.28, opacity: t, display: "inline-block",
          transform: `translateX(${interpolate(t, [0, 1], [-20, 0])}px)`,
        }}>{number}</span>
      ) : null}
      <span style={{ fontSize: base * 0.46, fontWeight: 700, color: SECTION_TEXT,
                     letterSpacing: base * 0.07 }}>
        {title.split("").map((ch, i) => (
          <span key={i} style={{
            opacity: spring({ frame: frame - ITEMS - i * 0.8, fps, config: { damping: 200 } }),
          }}>{ch}</span>
        ))}
      </span>
    </div>
  );
};

type LogoItem = { src?: string; label?: string; check?: boolean };

const Logo: React.FC<{
  i: number; item: LogoItem; side: number; big: boolean; square: boolean;
  theme: Theme; base: number;
}> = ({ i, item, side, big, square, theme, base }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  // Salta con rebote, y el visto llega después de que el logo esté puesto:
  // aprobar algo que todavía no ha aparecido se lee como un error.
  const pop = spring({ frame: frame - ITEMS - i * 5, fps, config: { damping: 9, mass: 0.6 } });
  const tick = spring({ frame: frame - ITEMS - 12 - i * 5, fps, config: { damping: 10 } });
  const s = big ? side * 1.14 : side;
  const radius = square ? s / 4 : s / 2;
  return (
    <div style={{ width: side, display: "flex", flexDirection: "column", alignItems: "center" }}>
      <div style={{ position: "relative", width: s, height: s, transform: `scale(${pop})` }}>
        <div style={{
          position: "absolute", inset: 0, borderRadius: radius, boxSizing: "border-box",
          background: "rgba(22,24,32,0.94)",
          border: `3px solid ${big ? theme.accent : alpha(theme.accent, 90)}`,
          boxShadow: big ? `0 0 ${base * 0.7}px ${alpha(theme.accent, 200)}`
                         : "0 10px 24px rgba(0,0,0,0.6)",
          display: "flex", alignItems: "center", justifyContent: "center",
        }}>
          {item.src ? <Img src={item.src} style={{ width: s * 0.62, height: s * 0.62,
                                                   objectFit: "contain" }} /> : null}
        </div>
        {item.check ? (
          <div style={{
            position: "absolute", right: -s * 0.02, top: -s * 0.02, width: s * 0.34,
            height: s * 0.34, borderRadius: "50%", background: CHECK_GREEN,
            border: "3px solid #0C0E14", boxSizing: "border-box", transform: `scale(${tick})`,
          }}>
            <svg viewBox="0 0 1 1" style={{ width: "100%", height: "100%" }}>
              <polyline points="0.22,0.52 0.42,0.72 0.78,0.30" fill="none" stroke="#fff"
                        strokeWidth={0.14} strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
        ) : null}
      </div>
      {item.label ? (
        <div style={{ marginTop: base * 0.3, fontSize: base * 0.44, fontWeight: 700,
                      color: theme.fg, opacity: pop }}>{item.label}</div>
      ) : null}
    </div>
  );
};

const Logos: React.FC<CardProps> = ({ theme, base, width, spec }) => {
  const items = (spec.items as LogoItem[]) ?? [];
  const square = spec.shape === "square";
  const highlight = spec.highlight as number | undefined;
  const count = Math.max(1, items.length);
  const side = Math.min(base * 2.3, (width * 0.82) / count - base * 0.35);
  const title = String(spec.title ?? "").toUpperCase();
  return (
    <div style={{ width, display: "flex", flexDirection: "column", alignItems: "center",
                  paddingTop: base * 0.25 }}>
      {title ? (
        <Enter from={0} delay={HEADING}>
          <div style={{ fontSize: base * 0.46, fontWeight: 700, color: SECTION_TEXT,
                        letterSpacing: base * 0.07, marginBottom: base * 0.3 }}>{title}</div>
        </Enter>
      ) : null}
      <div style={{ display: "flex", gap: base * 0.35, alignItems: "center" }}>
        {items.map((item, i) => (
          <Logo key={i} i={i} item={item} side={side} big={i === highlight}
                square={square} theme={theme} base={base} />
        ))}
      </div>
    </div>
  );
};

/** El sello cae de golpe —de casi el doble de tamaño a su sitio en unos
    fotogramas— con un fallo de señal rojo y cian mientras cae. Es puntuación:
    tiene que sonar como un golpe, no deslizarse como una card. */
const Stamp: React.FC<CardProps> = ({ base, width, spec }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const text = String(spec.title ?? spec.text ?? "").toUpperCase();
  const angle = Number(spec.angle ?? -8);
  const slam = spring({ frame, fps, config: { damping: 12, stiffness: 320, mass: 0.7 } });
  const scale = interpolate(slam, [0, 1], [1.9, 1]);
  const glitch = frame < 7 ? (7 - frame) * 2.4 : 0;
  const stroke = Math.max(6, base / 7);
  const box = (color: string, dx: number, absolute: boolean) => (
    <div style={{
      position: absolute ? "absolute" : "relative", left: 0, top: 0,
      transform: `translateX(${dx}px)`, border: `${stroke}px solid ${color}`,
      borderRadius: base * 0.25, padding: `${base * 0.3}px ${base * 0.45}px`,
      fontSize: base * 1.35, fontWeight: 900, color, lineHeight: 1, whiteSpace: "nowrap",
    }}>{text}</div>
  );
  return (
    <div style={{ width, display: "flex", justifyContent: "center", paddingTop: 10 }}>
      <div style={{ position: "relative", opacity: Math.min(1, slam * 3),
                    transform: `rotate(${angle}deg) scale(${scale})` }}>
        {box(STAMP_RED, 0, false)}
        {glitch ? box("rgba(0,229,255,0.7)", -glitch, true) : null}
        {glitch ? box("rgba(255,0,90,0.7)", glitch, true) : null}
      </div>
    </div>
  );
};

const KINDS: Record<string, React.FC<CardProps>> = {
  bullets: Bullets, panel: PanelCard, flow: Flow, stat: Stat, chip: Chip,
  title: Title, compare: Compare, checklist: Checklist, code: Code,
  section: Section, logos: Logos, stamp: Stamp,
};

export const Card: React.FC<CardProps> = (props) => {
  const frame = useCurrentFrame();
  const { durationInFrames, fps } = useVideoConfig();
  const Kind = KINDS[props.kind] ?? PanelCard;

  // The whole card arrives first, then its contents fill in. Without this the
  // surface pops in empty and the viewer watches a box wait for its own text.
  // El sello trae su propia entrada de golpe; suavizarla aquí la mataría.
  const arrive = props.kind === "stamp" ? 1
    : spring({ frame, fps, config: { damping: 14, mass: 0.6 } });

  // The exit is as quick as the entrance: a card that leaves slowly reads as a
  // video that has frozen.
  const out = interpolate(frame, [durationInFrames - EXIT_FRAMES, durationInFrames], [1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  return (
    <AbsoluteFill style={{
      opacity: out * arrive, fontFamily: "Fragua, sans-serif",
      alignItems: "center", justifyContent: "flex-start",
      transform: `translateY(${interpolate(arrive, [0, 1], [34, 0])}px)`,
    }}>
      <style>{FONT_FACE}</style>
      <Kind {...props} />
    </AbsoluteFill>
  );
};
