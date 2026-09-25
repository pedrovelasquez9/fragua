import React from "react";
import { Lottie, LottieAnimationData } from "@remotion/lottie";
import { AbsoluteFill } from "remotion";

export type LottieProps = {
  animationData: LottieAnimationData;
  dur: number;
  width: number;
  height: number;
  loop: boolean;
  playbackRate: number;
};

/** Una animación Lottie sobre transparencia, al tamaño exacto del sticker.

    Se renderiza ya a su tamaño final en vez de a lo grande para escalarla
    después: es vectorial, y dejar que ffmpeg la reduzca sería tirar la única
    ventaja que tiene sobre un GIF. */
export const LottieClip: React.FC<LottieProps> = ({ animationData, loop, playbackRate }) => (
  <AbsoluteFill>
    <Lottie animationData={animationData} loop={loop} playbackRate={playbackRate}
            style={{ width: "100%", height: "100%" }} />
  </AbsoluteFill>
);
