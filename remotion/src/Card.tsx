import React from "react";
import {
  AbsoluteFill, interpolate, spring, staticFile,
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

const KINDS: Record<string, React.FC<CardProps>> = {
  bullets: Bullets, panel: PanelCard, flow: Flow, stat: Stat, chip: Chip,
};

export const Card: React.FC<CardProps> = (props) => {
  const frame = useCurrentFrame();
  const { durationInFrames, fps } = useVideoConfig();
  const Kind = KINDS[props.kind] ?? PanelCard;

  // The whole card arrives first, then its contents fill in. Without this the
  // surface pops in empty and the viewer watches a box wait for its own text.
  const arrive = spring({ frame, fps, config: { damping: 14, mass: 0.6 } });

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
