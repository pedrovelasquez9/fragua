import { Composition } from "remotion";
import { Card, CardProps } from "./Card";

// One composition for every kind. cards.py passes the plan.json entry straight
// through as props, so there is nothing to keep in sync between the two.
export const Root: React.FC = () => (
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
);
