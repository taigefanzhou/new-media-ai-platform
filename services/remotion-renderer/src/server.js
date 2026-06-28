import express from "express";
import path from "node:path";
import {fileURLToPath} from "node:url";
import fs from "node:fs/promises";
import {bundle} from "@remotion/bundler";
import {renderMedia, selectComposition} from "@remotion/renderer";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const entryPoint = path.join(__dirname, "remotion-entry.js");
const port = Number(process.env.PORT || 3100);
const chromiumExecutable = process.env.PUPPETEER_EXECUTABLE_PATH || "/usr/bin/chromium";

let bundledServeUrl = null;
let bundlingPromise = null;

async function serveUrl() {
  if (bundledServeUrl) return bundledServeUrl;
  if (!bundlingPromise) {
    bundlingPromise = bundle({
      entryPoint,
      webpackOverride: (config) => config,
    }).then((url) => {
      bundledServeUrl = url;
      return url;
    });
  }
  return bundlingPromise;
}

function localVideoUrl(value) {
  if (!value) return "";
  if (String(value).startsWith("http://") || String(value).startsWith("https://")) {
    return String(value);
  }
  return `http://127.0.0.1:${port}/media?path=${encodeURIComponent(path.resolve(String(value)))}`;
}

function safeSeconds(value) {
  const seconds = Number(value || 0);
  if (!Number.isFinite(seconds) || seconds <= 0) return 6;
  return Math.max(3, Math.min(900, seconds));
}

function safeDimension(value, fallback) {
  const number = Number(value || 0);
  if (!Number.isFinite(number) || number < 240) return fallback;
  return Math.round(number);
}

function normalizeScenes(value) {
  if (!Array.isArray(value)) return [];
  return value
    .filter((item) => item && typeof item === "object")
    .slice(0, 24)
    .map((item) => ({
      title: String(item.title || item.screen_text || "").slice(0, 80),
      screen_text: String(item.screen_text || item.title || "").slice(0, 80),
      visual: String(item.visual || item.prompt || "").slice(0, 220),
      prompt: String(item.prompt || "").slice(0, 260),
      shot_type: String(item.shot_type || "").slice(0, 60),
    }));
}

async function renderProfessionalVideo(payload) {
  const sourcePath = payload.source_video_path || payload.sourceVideo || "";
  const outputPath = path.resolve(String(payload.output_path || payload.outputPath || "/tmp/remotion-output.mp4"));
  const durationSeconds = safeSeconds(payload.duration_seconds || payload.durationSeconds);
  const fps = Number(payload.fps || 30);
  const width = safeDimension(payload.width, 1080);
  const height = safeDimension(payload.height, 1920);
  await fs.mkdir(path.dirname(outputPath), {recursive: true});

  const inputProps = {
    title: String(payload.title || "专业讲解视频"),
    hook: String(payload.hook || ""),
    voiceover: String(payload.voiceover || ""),
    sourceVideo: localVideoUrl(sourcePath),
    durationSeconds,
    brandName: String(payload.brand_name || payload.brandName || "TECHARK"),
    template: String(payload.template || "business_talking"),
    scenes: normalizeScenes(payload.scenes),
  };

  const url = await serveUrl();
  const selected = await selectComposition({
    serveUrl: url,
    id: "ProfessionalVideo",
    inputProps,
    browserExecutable: chromiumExecutable,
    chromiumOptions: {
      disableWebSecurity: true,
    },
  });
  const composition = {
    ...selected,
    width,
    height,
    fps,
    durationInFrames: Math.max(1, Math.round(durationSeconds * fps)),
  };

  await renderMedia({
    composition,
    serveUrl: url,
    codec: "h264",
    outputLocation: outputPath,
    inputProps,
    browserExecutable: chromiumExecutable,
    chromiumOptions: {
      disableWebSecurity: true,
    },
    overwrite: true,
  });
  return outputPath;
}

const app = express();
app.use(express.json({limit: "20mb"}));

app.get("/health", (_req, res) => {
  res.json({status: "ok", renderer: "remotion"});
});

app.get("/media", (req, res) => {
  const filePath = path.resolve(String(req.query.path || ""));
  res.sendFile(filePath, (error) => {
    if (error && !res.headersSent) {
      res.status(error.statusCode || 404).json({error: "media not found"});
    }
  });
});

app.post("/render", async (req, res) => {
  try {
    const outputPath = await renderProfessionalVideo(req.body || {});
    res.json({output_path: outputPath, provider: "remotion", template: req.body?.template || "business_talking"});
  } catch (error) {
    console.error(error);
    res.status(500).json({error: error?.message || "render failed"});
  }
});

app.listen(port, () => {
  console.log(`Remotion renderer listening on ${port}`);
});
