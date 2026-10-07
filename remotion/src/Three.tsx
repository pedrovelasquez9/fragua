// Elementos 3D con three.js: logos de marca extruidos y el fondo con profundidad
// del pullback. Todo se calcula a partir del fotograma, nunca del reloj: el
// render de Remotion pide los fotogramas sueltos y en cualquier orden.
import React, { useEffect, useMemo } from "react";
import { ThreeCanvas } from "@remotion/three";
import { useThree } from "@react-three/fiber";
import * as THREE from "three";
import { SVGLoader } from "three/examples/jsm/loaders/SVGLoader.js";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";
import { AbsoluteFill, spring, useCurrentFrame, useVideoConfig } from "remotion";

const POP = { stiffness: 262, damping: 20.4, mass: 1 };
const SWING = { stiffness: 90, damping: 9, mass: 1 };
const RIM = "#5b7cff";

/** Reflejos de un estudio generado al vuelo: el acabado sin descargar un HDR. */
const Studio: React.FC = () => {
  const { gl, scene } = useThree();
  // Al montar, no en un efecto: un still captura el primer fotograma, y con
  // useEffect el entorno llegaba tarde y el logo salía apagado.
  const pmrem = useMemo(() => {
    const generator = new THREE.PMREMGenerator(gl);
    scene.environment = generator.fromScene(new RoomEnvironment(), 0.04).texture;
    scene.environmentIntensity = 0.4;
    return generator;
  }, [gl, scene]);
  useEffect(() => () => pmrem.dispose(), [pmrem]);
  return null;
};

/** Luz del set del autor: principal cálida arriba a la izquierda, contraluz azul. */
const SetLights: React.FC = () => (
  <>
    <Studio />
    <ambientLight intensity={0.15} />
    <directionalLight position={[-3, 4, 5]} intensity={2.4} color="#fff1e0" />
    <directionalLight position={[4, -1, -4]} intensity={3.2} color={RIM} />
    <pointLight position={[2, 2, 3]} intensity={12} color="#ffffff" />
  </>
);

/** El SVG extruido, centrado y escalado a `fit` unidades, un trozo por color. */
const useExtruded = (svg: string, fit: number) =>
  useMemo(() => {
    const parsed = new SVGLoader().parse(svg);
    const parts = parsed.paths.map((path) => {
      const shapes = SVGLoader.createShapes(path);
      return { shapes, color: `#${path.color.getHexString()}` };
    });
    const flat = new THREE.ShapeGeometry(parts.flatMap((p) => p.shapes));
    flat.computeBoundingBox();
    const box = flat.boundingBox!;
    const size = Math.max(box.max.x - box.min.x, box.max.y - box.min.y) || 1;
    const centre = new THREE.Vector3(); box.getCenter(centre);
    flat.dispose();
    return parts.map(({ shapes, color }) => {
      const g = new THREE.ExtrudeGeometry(shapes, {
        depth: size * 0.12, bevelEnabled: true, bevelThickness: size * 0.025,
        bevelSize: size * 0.015, bevelSegments: 6, curveSegments: 24,
      });
      g.translate(-centre.x, -centre.y, -size * 0.06);
      // El SVG tiene la y hacia abajo. Se gira, no se escala en negativo: eso
      // invierte las normales y la luz deja de llegarle (sale negro).
      g.rotateX(Math.PI);
      g.scale(fit / size, fit / size, fit / size);
      return { geometry: g, color };
    });
  }, [svg, fit]);

export const LogoMesh: React.FC<{ svg: string; fit?: number; pop?: boolean; delay?: number }> = ({
  svg, fit = 2.6, pop = true, delay = 0,
}) => {
  const frame = useCurrentFrame() - delay;
  const { fps } = useVideoConfig();
  const parts = useExtruded(svg, fit);
  const grow = pop ? spring({ frame, fps, config: POP }) : 1;
  // Entra girando media vuelta y se queda en un vaivén lento: 3D que se nota sin
  // marear, y siempre vuelve a mirar a cámara.
  const swing = spring({ frame, fps, config: SWING });
  const t = Math.max(0, frame) / fps;
  return (
    <group scale={grow} position={[0, 0.06 * Math.sin(t * 2.2), 0]}
           rotation={[0.16 * Math.sin(t * 1.3), -2.4 * (1 - swing) + 0.32 * Math.sin(t * 1.1), 0]}>
      {parts.map(({ geometry, color }, i) => (
        <mesh key={i} geometry={geometry}>
          <meshPhysicalMaterial color={color} metalness={0.35} roughness={0.22}
                                clearcoat={1} clearcoatRoughness={0.15}
                                emissive={color} emissiveIntensity={0.14} />
        </mesh>
      ))}
    </group>
  );
};

/** Un lienzo 3D transparente con la luz del set, del tamaño que se le pida. */
export const LogoCanvas: React.FC<{
  svg: string; width: number; height: number; fit?: number; pop?: boolean; delay?: number;
}> = ({ svg, width, height, fit, pop, delay }) => (
  // flat: sin el tone mapping cinematográfico por defecto, que lava los colores
  // saturados y dejaba los iconos neón en pastel.
  <ThreeCanvas width={width} height={height} gl={{ alpha: true, antialias: true }} flat
               camera={{ position: [0, 0, 6], fov: 35 }}>
    <SetLights />
    <LogoMesh svg={svg} fit={fit} pop={pop} delay={delay} />
  </ThreeCanvas>
);

export type Logo3DProps = { svg: string; dur: number; size: number; fps: number; pop: boolean };

/** Composición: un logo 3D solo, sobre transparencia, para los stickers. El
    tamaño, la entrada y la salida los pone motion.py, igual que a un PNG; aquí
    sólo gira. */
export const Logo3D: React.FC<Logo3DProps> = ({ svg, size, pop }) => (
  // fit 3.0 llena ~80 % del lienzo, como el PNG con plato al que sustituye, y
  // deja margen para el escorzo del giro.
  <LogoCanvas svg={svg} width={size} height={size} pop={pop} fit={3.0} />
);

// --- Fondo con profundidad ---------------------------------------------------

const random = (seed: number) => () => {
  // mulberry32: el mismo fondo en cada render, fotograma a fotograma.
  seed |= 0; seed = (seed + 0x6d2b79f5) | 0;
  let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
  t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
};

const softDot = () => {
  const c = document.createElement("canvas");
  c.width = c.height = 64;
  const g = c.getContext("2d")!;
  const grad = g.createRadialGradient(32, 32, 0, 32, 32, 32);
  grad.addColorStop(0, "rgba(255,255,255,1)");
  grad.addColorStop(0.35, "rgba(255,255,255,0.55)");
  grad.addColorStop(1, "rgba(255,255,255,0)");
  g.fillStyle = grad;
  g.fillRect(0, 0, 64, 64);
  return new THREE.CanvasTexture(c);
};

const Bokeh: React.FC<{ seed: number; count: number; color: string; size: number; opacity: number }> = ({
  seed, count, color, size, opacity,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const texture = useMemo(softDot, []);
  const geometry = useMemo(() => {
    const r = random(seed);
    const pos = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) {
      pos[i * 3] = (r() - 0.5) * 9;
      pos[i * 3 + 1] = (r() - 0.5) * 14;
      pos[i * 3 + 2] = -r() * 14 + 1.5;
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    return g;
  }, [seed, count]);
  const t = frame / fps;
  // Deriva lenta hacia arriba: profundidad sin llamar la atención.
  return (
    <points geometry={geometry} position={[0.15 * Math.sin(t * 0.4 + seed), t * 0.12, 0]}>
      <pointsMaterial map={texture} color={color} size={size} sizeAttenuation transparent
                      opacity={opacity} depthWrite={false} blending={THREE.AdditiveBlending} />
    </points>
  );
};

export type BackdropProps = { dur: number; width: number; height: number; fps: number; accent?: string };

/** El fondo de la banda del pullback: penumbra con luces desenfocadas que
    flotan a distintas profundidades y una cámara que avanza despacio. En vez
    del negro plano que dejaba el vídeo al encogerse. */
export const Backdrop: React.FC<BackdropProps> = ({ width, height, accent = "#FF8A3D" }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const z = 6 - 0.35 * (frame / fps);
  return (
    <AbsoluteFill style={{
      background: "radial-gradient(ellipse at 50% 40%, #1b1f30 0%, #0d0f17 55%, #06070b 100%)",
    }}>
      <ThreeCanvas width={width} height={height} gl={{ alpha: true, antialias: true }}
                   camera={{ position: [0, 0, z], fov: 50 }}>
        <Bokeh seed={11} count={90} color={RIM} size={0.55} opacity={0.32} />
        <Bokeh seed={23} count={26} color={accent} size={0.7} opacity={0.22} />
        <Bokeh seed={37} count={50} color="#ffffff" size={0.12} opacity={0.35} />
      </ThreeCanvas>
    </AbsoluteFill>
  );
};
