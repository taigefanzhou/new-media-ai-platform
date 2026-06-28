import React from "react";
import {Composition} from "remotion";
import {registerRoot} from "remotion";
import {ProfessionalVideo} from "./ProfessionalVideo.jsx";

const RemotionRoot = () => (
  <Composition
    id="ProfessionalVideo"
    component={ProfessionalVideo}
    durationInFrames={180}
    fps={30}
    width={1080}
    height={1920}
    defaultProps={{
      title: "专业讲解视频",
      hook: "用一条视频讲清楚核心卖点",
      voiceover: "",
      sourceVideo: "",
      durationSeconds: 6,
      brandName: "TECHARK",
      template: "business_talking",
      scenes: [],
    }}
  />
);

registerRoot(RemotionRoot);
