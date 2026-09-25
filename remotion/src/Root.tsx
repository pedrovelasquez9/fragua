import { Composition } from "remotion";
import { Card, CardProps } from "./Card";
import { LottieClip, LottieProps } from "./LottieClip";

// One composition for every kind. cards.py passes the plan.json entry straight
// through as props, so there is nothing to keep in sync between the two.
export const Root: React.FC = () => (
  <>
    <Composition
      id="Card"
      component={Card}
      fps={30}
      width={1080}
      height={760}
      durationInFrames={90}
      defaultProps={{
        kind: "bullets",
        dur: 5,
        width: 1080,
        base: 51,
        theme: { bg: "#14161F", bgAlpha: 232, fg: "#ECECEC", accent: "#D6B64C" },
        spec: {
          title: "Lo que se te abre",
          body: "Clientes nuevos\nFeedback de la comunidad\nOtra mirada técnica",
        },
      } satisfies CardProps}
      calculateMetadata={({ props }) => ({
        durationInFrames: Math.max(2, Math.round(props.dur * 30)),
        width: props.width,
      })}
    />
    {/* Tamaño y duración los manda lottie.py: los del sticker y su hueco en el
        plan, no los que traiga el fichero. */}
    <Composition
      id="LottieClip"
      component={LottieClip}
      fps={30}
      width={200}
      height={200}
      durationInFrames={60}
      defaultProps={{
        animationData: { v: "5.7.4", fr: 30, ip: 0, op: 60, w: 200, h: 200, layers: [] },
        dur: 2, width: 200, height: 200, loop: true, playbackRate: 1,
      } as unknown as LottieProps}
      calculateMetadata={({ props }) => ({
        durationInFrames: Math.max(2, Math.round(props.dur * 30)),
        width: props.width,
        height: props.height,
      })}
    />
  </>
);
