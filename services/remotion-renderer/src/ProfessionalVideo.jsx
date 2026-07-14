import React from "react";
import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
  Video,
} from "remotion";

const palette = {
  ink: "#101827",
  panel: "rgba(15, 23, 42, 0.76)",
  softPanel: "rgba(255, 255, 255, 0.88)",
  white: "#f8fafc",
  muted: "#cbd5e1",
  teal: "#0f766e",
  green: "#16a34a",
  yellow: "#facc15",
  blue: "#2563eb",
};

function splitText(text, max = 18, count = 3) {
  const clean = String(text || "").replace(/\s+/g, " ").trim();
  if (!clean) return [];
  const parts = [];
  let current = "";
  for (const char of clean) {
    current += char;
    if (current.length >= max || "。！？!?；;，,".includes(char)) {
      parts.push(current.trim());
      current = "";
    }
    if (parts.length >= count) break;
  }
  if (current.trim() && parts.length < count) parts.push(current.trim());
  return parts.slice(0, count);
}

function currentCue(text, progress) {
  const cues = splitText(text, 22, 8);
  if (!cues.length) return "";
  const index = Math.min(cues.length - 1, Math.floor(progress * cues.length));
  return cues[index];
}

function sceneForProgress(scenes, progress) {
  if (!Array.isArray(scenes) || !scenes.length) return null;
  const index = Math.min(scenes.length - 1, Math.floor(progress * scenes.length));
  return scenes[index] || null;
}

function fitModeStyle(width, height) {
  if (width >= height) {
    return {
      width: "100%",
      height: "auto",
      top: "50%",
      transform: "translateY(-50%)",
    };
  }
  return {
    width: "100%",
    height: "100%",
    objectFit: "cover",
  };
}

function highlightedCue(text) {
  const keywords = /(收益|利润|满房|节能|入住率|成本|效率|溢价|智能客控|数字化)/g;
  const highlighted = /^(收益|利润|满房|节能|入住率|成本|效率|溢价|智能客控|数字化)$/;
  return String(text || "").split(keywords).map((part, index) =>
    highlighted.test(part) ? <span key={`${part}-${index}`} style={{color: "#ffd54a"}}>{part}</span> : part,
  );
}

function HeYiyiHotelVideo({title, hook, voiceover, sourceVideo, brandName, scenes, brollVideos}) {
  const frame = useCurrentFrame();
  const {durationInFrames, fps, width, height} = useVideoConfig();
  const progress = Math.min(1, frame / Math.max(1, durationInFrames - 1));
  const cue = currentCue(voiceover || hook, progress);
  const brollList = Array.isArray(brollVideos) ? brollVideos : [];
  const firstInsert = brollList.length > 0 && progress >= 0.065 && progress < 0.115;
  const fullScreenInsert = brollList.length > 0 && progress >= 0.27 && progress < 0.325;
  const systemInsert = brollList.length > 0 && progress >= 0.47 && progress < 0.61;
  const activeBroll = brollList.length ? brollList[Math.min(brollList.length - 1, fullScreenInsert ? 0 : 1)] : "";
  const cleanTitle = String(title || hook || "酒店数字化").replace(/^\d+[.、]\s*/, "").replace(/[？?！!。]/g, "");
  const titleLine1 = cleanTitle.includes("酒店") ? "酒店客控" : cleanTitle.slice(0, 6);
  const titleLine2 = "一招制胜";
  const videoStyle = fitModeStyle(width, height);

  return (
    <AbsoluteFill style={{backgroundColor: "#111", fontFamily: '"Noto Sans CJK SC", sans-serif', letterSpacing: 0}}>
      {sourceVideo ? <Video src={sourceVideo} muted={false} style={{position: "absolute", ...videoStyle}} /> : null}

      {activeBroll && fullScreenInsert ? (
        <Video src={activeBroll} muted loop style={{position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "cover"}} />
      ) : null}
      {activeBroll && (firstInsert || systemInsert) ? (
        <div style={{position: "absolute", left: firstInsert ? 0 : 48, right: firstInsert ? 0 : 48, top: firstInsert ? 0 : 210, height: firstInsert ? "48%" : "43%", overflow: "hidden", boxShadow: "0 14px 34px rgba(0,0,0,.38)"}}>
          <Video src={activeBroll} muted loop style={{position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "cover"}} />
        </div>
      ) : null}

      {!firstInsert && !fullScreenInsert && !systemInsert ? (
        <div style={{position: "absolute", left: 30, top: 38, color: "#fff8df", fontFamily: '"Noto Serif CJK SC", serif', fontSize: 96, lineHeight: 1.02, fontWeight: 900, whiteSpace: "nowrap", textShadow: "4px 5px 0 rgba(28,20,12,.9), 0 0 6px rgba(0,0,0,.65)"}}>
          <div>{titleLine1}</div>
          <div>{titleLine2}</div>
        </div>
      ) : null}

      {durationInFrames >= fps * 20 && progress < 0.13 && !firstInsert ? (
        <div style={{position: "absolute", left: 52, top: 590, color: "#89c8ff", fontSize: 34, lineHeight: 1.28, fontWeight: 900, textShadow: "0 3px 4px rgba(0,0,0,.8)"}}>
          <div>× 别只看设备</div>
          <div>× 先算经营账</div>
        </div>
      ) : null}

      <div style={{position: "absolute", left: 34, right: 34, bottom: 136, color: "white", fontSize: 46, lineHeight: 1.2, fontWeight: 700, textAlign: "center", textShadow: "0 3px 4px #000, 0 0 3px #000"}}>
        {highlightedCue(cue)}
      </div>
    </AbsoluteFill>
  );
}

function BusinessVideo({
  title,
  hook,
  voiceover,
  sourceVideo,
  durationSeconds,
  brandName,
  scenes,
}) {
  const frame = useCurrentFrame();
  const {fps, durationInFrames, width, height} = useVideoConfig();
  const progress = Math.min(1, frame / Math.max(1, durationInFrames - 1));
  const cue = currentCue(voiceover || hook, progress);
  const scene = sceneForProgress(scenes, progress);
  const intro = spring({frame, fps, config: {damping: 18, stiffness: 90}});
  const cardY = interpolate(intro, [0, 1], [70, 0]);
  const videoScale = interpolate(progress, [0, 1], [1.02, 1.065]);
  const pulse = interpolate(Math.sin(frame / 18), [-1, 1], [0.88, 1]);
  const shortTitle = String(title || hook || "专业讲解视频").replace(/^\d+[.、]\s*/, "").slice(0, 28);
  const sceneTitle = String(scene?.screen_text || scene?.title || hook || "核心卖点").slice(0, 18);
  const sceneBody = String(scene?.visual || scene?.prompt || voiceover || "").slice(0, 44);
  const sourceMeta = String(scene?.shot_type || "专业口播").replace(/_/g, " ");
  const videoStyle = fitModeStyle(width, height);

  return (
    <AbsoluteFill style={{backgroundColor: "#0b1724", fontFamily: "Noto Sans CJK SC, Arial, sans-serif"}}>
      <AbsoluteFill>
        <div
          style={{
            position: "absolute",
            inset: 0,
            background:
              "linear-gradient(145deg, rgba(15,118,110,0.32), transparent 42%), linear-gradient(25deg, rgba(37,99,235,0.28), transparent 48%), #0b1724",
          }}
        />
        {[0, 1, 2, 3, 4, 5].map((item) => (
          <div
            key={item}
            style={{
              position: "absolute",
              width: 420,
              height: 2,
              left: -80 + ((frame * 5 + item * 180) % (width + 220)),
              top: 220 + item * 210,
              transform: "rotate(9deg)",
              background: "rgba(255,255,255,0.12)",
            }}
          />
        ))}
      </AbsoluteFill>

      <div
        style={{
          position: "absolute",
          left: 56,
          right: 56,
          top: 52,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          color: palette.white,
          fontSize: 28,
          letterSpacing: 0,
        }}
      >
        <div style={{display: "flex", alignItems: "center", gap: 14}}>
          <div style={{width: 16, height: 16, borderRadius: 999, background: palette.green, transform: `scale(${pulse})`}} />
          <strong>{brandName || "TECHARK"}</strong>
        </div>
        <span style={{color: palette.muted}}>AI VIDEO</span>
      </div>

      <div
        style={{
          position: "absolute",
          left: 44,
          right: 44,
          top: 120,
          bottom: 420,
          borderRadius: 36,
          overflow: "hidden",
          border: "2px solid rgba(255,255,255,0.16)",
          boxShadow: "0 34px 90px rgba(0,0,0,0.38)",
          background: "#111827",
        }}
      >
        {sourceVideo ? (
          <Video
            src={sourceVideo}
            muted={false}
            style={{
              position: "absolute",
              ...videoStyle,
              transform: `${videoStyle.transform || ""} scale(${videoScale})`,
              transformOrigin: "center center",
            }}
          />
        ) : (
          <div style={{position: "absolute", inset: 0, background: "linear-gradient(160deg, #0f766e, #111827)"}} />
        )}
        <div style={{position: "absolute", inset: 0, background: "linear-gradient(180deg, rgba(0,0,0,0.32), transparent 34%, rgba(0,0,0,0.56))"}} />
      </div>

      <div
        style={{
          position: "absolute",
          left: 72,
          right: 72,
          top: 154,
          transform: `translateY(${cardY}px)`,
          color: palette.white,
        }}
      >
        <div style={{fontSize: 30, color: palette.yellow, fontWeight: 800}}>重点讲解</div>
        <div style={{fontSize: 58, lineHeight: 1.18, fontWeight: 900, marginTop: 10, textShadow: "0 6px 24px rgba(0,0,0,0.38)"}}>
          {shortTitle}
        </div>
      </div>

      <div
        style={{
          position: "absolute",
          left: 72,
          right: 72,
          bottom: 284,
          borderRadius: 28,
          background: palette.softPanel,
          padding: "28px 34px",
          color: palette.ink,
          boxShadow: "0 24px 60px rgba(0,0,0,0.22)",
        }}
      >
        <div style={{display: "flex", justifyContent: "space-between", alignItems: "center", gap: 20}}>
          <div>
            <div style={{fontSize: 40, fontWeight: 900, lineHeight: 1.14}}>{sceneTitle}</div>
            <div style={{fontSize: 25, lineHeight: 1.35, marginTop: 12, color: "#475569"}}>{sceneBody}</div>
          </div>
          <div
            style={{
              minWidth: 168,
              height: 168,
              borderRadius: 28,
              background: "linear-gradient(160deg, #0f766e, #2563eb)",
              color: palette.white,
              display: "flex",
              flexDirection: "column",
              justifyContent: "center",
              alignItems: "center",
              fontWeight: 900,
            }}
          >
            <span style={{fontSize: 54}}>{Math.max(1, Math.ceil(progress * 5))}</span>
            <span style={{fontSize: 22}}>STEP</span>
          </div>
        </div>
      </div>

      <div
        style={{
          position: "absolute",
          left: 72,
          right: 72,
          bottom: 128,
          borderRadius: 28,
          background: palette.panel,
          color: palette.white,
          padding: "28px 34px",
          fontSize: 46,
          lineHeight: 1.28,
          fontWeight: 850,
          textAlign: "center",
          boxShadow: "0 18px 46px rgba(0,0,0,0.28)",
        }}
      >
        {cue}
      </div>

      <div
        style={{
          position: "absolute",
          left: 72,
          right: 72,
          bottom: 72,
          height: 14,
          borderRadius: 999,
          background: "rgba(255,255,255,0.18)",
          overflow: "hidden",
        }}
      >
        <div style={{height: "100%", width: `${progress * 100}%`, background: `linear-gradient(90deg, ${palette.green}, ${palette.yellow})`}} />
      </div>

      <div
        style={{
          position: "absolute",
          right: 74,
          top: 88,
          borderRadius: 999,
          padding: "12px 22px",
          color: palette.white,
          background: "rgba(15,23,42,0.68)",
          fontSize: 24,
        }}
      >
        {sourceMeta}
      </div>
    </AbsoluteFill>
  );
}

export function ProfessionalVideo(props) {
  return props.template === "he_yiyi_hotel" ? <HeYiyiHotelVideo {...props} /> : <BusinessVideo {...props} />;
}
