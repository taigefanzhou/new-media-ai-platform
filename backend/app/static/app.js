const api = {
  token: localStorage.getItem("authToken"),
  async get(path) {
    const res = await fetch(`/api${path}`, { headers: authHeaders() });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },
  async post(path, body = {}) {
    const res = await fetch(`/api${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },
  async postBlob(path, body = {}) {
    const res = await fetch(`/api${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.blob();
  },
  async patch(path, body = {}) {
    const res = await fetch(`/api${path}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },
  async delete(path) {
    const res = await fetch(`/api${path}`, {
      method: "DELETE",
      headers: authHeaders(),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },
};

const state = {
  latestScriptId: null,
  latestHumanId: null,
  latestTaskId: null,
  latestPortraitId: null,
  latestSourceVideoId: null,
  latestTrendingSearchId: null,
  latestTranscriptionId: null,
  latestVideoAnalysisId: null,
  highlightedScriptId: null,
  currentPage: "overview",
  materials: [],
  scripts: [],
  videoTasks: [],
  platformAccounts: [],
  publishRecords: [],
  platformCredentials: [],
  digitalHumans: [],
  exportProfiles: [],
  transcriptions: [],
  videoAnalyses: [],
  trendingSearches: [],
  trendingVideos: [],
  modelConfigs: [],
  integrations: {},
  modelUsage: null,
  modelDiagnostics: null,
  videoStorage: null,
  remoteUpload: null,
  wechatLoginConfig: null,
  wechatLoginRequests: [],
  wechatIdentities: [],
  videoProductionSkills: null,
  productModules: null,
  localSaveDirectoryHandle: null,
  localSaveDirectoryName: localStorage.getItem("localSaveDirectoryName") || "",
  autoSaveToLocalFolder: localStorage.getItem("autoSaveToLocalFolder") === "1",
  localSavedVideoIds: new Set(JSON.parse(localStorage.getItem("localSavedVideoIds") || "[]")),
  localSavingVideoIds: new Set(),
  users: [],
  currentUser: null,
  currentSettingsSection: "usage",
  currentReferenceTab: "history",
  overviewActivityTab: "scripts",
  taskScriptPage: 1,
  listPages: {},
  previewTaskId: null,
  activeAnalysisDetailId: null,
  voicePreviewUrl: "",
};

const settingsSections = {
  usage: { title: "模型用量", eyebrow: "Settings / Usage" },
  models: { title: "AI 模型接入", eyebrow: "Settings / AI Models" },
  storage: { title: "视频存储位置", eyebrow: "Settings / Video Storage" },
  collectors: { title: "短视频采集接入", eyebrow: "Settings / Collectors" },
  accounts: { title: "账号管理", eyebrow: "Settings / Accounts" },
  wechat: { title: "微信登录", eyebrow: "Settings / WeChat Login" },
};

const linkResolverPresets = {
  "wechat-public": {
    display_name: "视频号公开测试解析",
    platform: "wechat_channels",
    purpose: "link_resolver",
    api_base: "https://sph.litao.workers.dev/api/fetch_video_profile",
    client_id: "",
    client_secret: "",
    access_token: "",
    refresh_token: "",
    webhook_url: "",
    notes: "method=post\ntimeout=8\n返回结构：data.feedInfo.h264VideoInfo.videoUrl / data.feedInfo.videoUrl\n用途：临时验证视频号链接是否可解析，正式使用请换成自有服务。",
  },
  "wechat-justone": {
    display_name: "Just One 视频号解析",
    platform: "wechat_channels",
    purpose: "link_resolver",
    api_base: "http://47.117.133.51:30015",
    client_id: "",
    client_secret: "",
    access_token: "",
    refresh_token: "",
    webhook_url: "",
    notes: "method=get\nprovider=justone\ntimeout=12\n说明：需要在 Access Token 填 Just One token；后端会走视频号 basic-info + download-url 两步解析。",
  },
  "wechat-self-hosted": {
    display_name: "视频号自有解析服务",
    platform: "wechat_channels",
    purpose: "link_resolver",
    api_base: "",
    client_id: "",
    client_secret: "",
    access_token: "",
    refresh_token: "",
    webhook_url: "",
    notes: "method=post\ntimeout=12\n返回结构：data.feedInfo.h264VideoInfo.videoUrl / data.feedInfo.videoUrl\n说明：请填写你自己的解析接口地址；8099 已收回为服务器内部素材上传端口，不再作为公网解析入口。",
  },
  "trending-tikhub": {
    display_name: "TikHub 抖音主题采集",
    platform: "douyin",
    purpose: "trending",
    api_base: "https://api.tikhub.io",
    client_id: "",
    client_secret: "",
    access_token: "",
    refresh_token: "",
    webhook_url: "",
    notes: "provider=tikhub\nmethod=post\ntimeout=20\npath=/api/v1/douyin/search/fetch_video_search_v2\n说明：Access Token 填 TikHub API Key；如接视频号或其他平台，请按 TikHub 控制台文档替换 path。采集结果只做选题和结构参考。",
  },
  "volcengine-jimeng-digital-human": {
    display_name: "火山即梦数字人 AK/SK",
    platform: "volcengine",
    purpose: "digital_human",
    api_base: "https://visual.volcengineapi.com",
    client_id: "",
    client_secret: "",
    access_token: "",
    refresh_token: "",
    webhook_url: "",
    notes: "provider=volcengine_jimeng\ncredential_type=ak_sk\nclient_id=AccessKeyID\nclient_secret=SecretAccessKey\nservice=cv\nregion=cn-north-1\napp_id=101606596\nreq_key=pippit_iv2v_v20_cvtob_with_vinput\n说明：需先在火山控制台开通即梦 AI 小云雀/动作模仿对应 OpenAPI 能力；模型配置里选择“火山即梦数字人”。",
  },
};

const pages = {
  overview: { title: "模块总览", eyebrow: "Modular Console" },
  materials: { title: "素材库与数字人", eyebrow: "Assets" },
  creation: { title: "脚本方向创作", eyebrow: "Script Direction" },
  analysis: { title: "参考视频学习", eyebrow: "Reference Learning" },
  humans: { title: "素材库与数字人", eyebrow: "Assets & Avatars" },
  tasks: { title: "视频库", eyebrow: "Video Library" },
  trending: { title: "主题自动采集", eyebrow: "Trending" },
  publish: { title: "账号发布", eyebrow: "Publishing" },
  settings: { title: "系统设置", eyebrow: "Settings" },
};

const providerOptions = {
  script: [
    { value: "volcengine-ark", label: "火山方舟 / Doubao Seed 2.0 Pro", model: "doubao-seed-2-0-pro-260215", base: "https://ark.cn-beijing.volces.com/api/v3" },
    { value: "volcengine-ark-lite", label: "火山方舟 / Doubao Seed 2.0 Lite", model: "doubao-seed-2-0-lite-260215", base: "https://ark.cn-beijing.volces.com/api/v3" },
    { value: "volcengine-ark-mini", label: "火山方舟 / Doubao Seed 2.0 Mini", model: "doubao-seed-2-0-mini-260428", base: "https://ark.cn-beijing.volces.com/api/v3" },
    { value: "aliyun-bailian", label: "阿里云百炼 / Qwen3.7 Plus", model: "qwen3.7-plus", base: "https://dashscope.aliyuncs.com/compatible-mode/v1" },
    { value: "aliyun-bailian-max", label: "阿里云百炼 / Qwen3.7 Max", model: "qwen3.7-max", base: "https://dashscope.aliyuncs.com/compatible-mode/v1" },
    { value: "aliyun-bailian-latest", label: "阿里云百炼 / Qwen Plus Latest", model: "qwen-plus-latest", base: "https://dashscope.aliyuncs.com/compatible-mode/v1" },
    { value: "deepseek", label: "DeepSeek", model: "deepseek-chat", base: "https://api.deepseek.com/v1" },
    { value: "openai-compatible", label: "其他 OpenAI 兼容接口", model: "gpt-4.1-mini", base: "https://api.openai.com/v1" },
    { value: "vllm", label: "vLLM 自建服务", model: "Qwen/Qwen3-30B-A3B-Instruct-2507", base: "http://localhost:8000/v1" },
  ],
  tts: [
    { value: "aliyun-cosyvoice", label: "阿里云百炼 / CosyVoice 真实语音", model: "cosyvoice-v3-flash", base: "https://dashscope.aliyuncs.com/api/v1" },
    { value: "volcengine-tts", label: "火山语音", model: "volcano-tts" },
    { value: "cosyvoice", label: "CosyVoice", model: "cosyvoice-v2", base: "http://localhost:9880" },
    { value: "fish-speech", label: "Fish Speech", model: "fish-speech", base: "http://localhost:9881" },
    { value: "aliyun-tts", label: "阿里云语音", model: "cosyvoice-v3-flash", base: "https://dashscope.aliyuncs.com/api/v1" },
    { value: "mock", label: "Mock 测试", model: "mock-tts" },
  ],
  voice_clone: [
    { value: "aliyun-cosyvoice-clone", label: "阿里云百炼 / CosyVoice 声音复刻", model: "cosyvoice-v3-flash", base: "https://dashscope.aliyuncs.com/api/v1" },
    { value: "volcengine-voice-clone", label: "火山引擎 / 声音复刻", model: "volcengine-voice-clone" },
    { value: "cosyvoice-clone", label: "CosyVoice 声音克隆服务", model: "cosyvoice-clone", base: "http://localhost:9880" },
    { value: "openvoice", label: "OpenVoice 本地服务", model: "openvoice-v2", base: "http://localhost:9010" },
    { value: "f5-tts", label: "F5-TTS 本地服务", model: "f5-tts", base: "http://localhost:9011" },
    { value: "openai-compatible", label: "其他声音复刻接口", model: "voice-clone" },
  ],
  video: [
    { value: "seedance", label: "火山方舟 / Seedance 2.0", model: "doubao-seedance-2-0-260128", base: "https://ark.cn-beijing.volces.com/api/v3" },
    { value: "seedance-fast", label: "火山方舟 / Seedance 2.0 Fast", model: "doubao-seedance-2-0-fast-260128", base: "https://ark.cn-beijing.volces.com/api/v3" },
    { value: "seedance-mini", label: "火山方舟 / Seedance 2.0 Mini", model: "doubao-seedance-2-0-mini-260615", base: "https://ark.cn-beijing.volces.com/api/v3" },
    { value: "comfyui", label: "ComfyUI", model: "wan2.1-workflow", base: "http://localhost:8188" },
    { value: "wan", label: "Wan2.1", model: "wan2.1-t2v-1.3b" },
    { value: "hunyuan-video", label: "HunyuanVideo", model: "hunyuan-video" },
    { value: "mock", label: "Mock 测试", model: "mock-video" },
  ],
  digital_human: [
    { value: "volcengine-jimeng-digital-human", label: "火山引擎 / 即梦数字人（预接入）", model: "jimeng-digital-human", base: "https://visual.volcengineapi.com" },
    { value: "aliyun-videoretalk", label: "阿里云百炼 / VideoRetalk 源视频驱动", model: "videoretalk", base: "https://dashscope.aliyuncs.com/api/v1" },
    { value: "aliyun-liveportrait", label: "阿里云百炼 / LivePortrait 实验项（不推荐）", model: "liveportrait", base: "https://dashscope.aliyuncs.com/api/v1" },
    { value: "aliyun-wan-s2v", label: "阿里云百炼 / 万相数字人", model: "wan2.2-s2v", base: "https://dashscope.aliyuncs.com/api/v1" },
    { value: "volcengine-digital-human", label: "火山引擎 / 数字人驱动", model: "volcengine-digital-human" },
    { value: "sadtalker", label: "SadTalker 本地/HTTP 服务", model: "sadtalker", base: "http://localhost:7860" },
    { value: "heygen", label: "HeyGen 数字人", model: "heygen-avatar" },
    { value: "d-id", label: "D-ID 数字人", model: "d-id-talking-avatar", base: "https://api.d-id.com" },
    { value: "mock", label: "Mock 测试", model: "mock-digital-human" },
  ],
  asr: [
    { value: "volcengine", label: "火山引擎 / 豆包 ASR", model: "volcengine-asr" },
    { value: "aliyun-bailian", label: "阿里云百炼 / Qwen-ASR", model: "qwen3-asr-flash", base: "https://dashscope.aliyuncs.com/compatible-mode/v1" },
    { value: "openai-compatible", label: "OpenAI 兼容转写", model: "whisper-1" },
    { value: "whisperx", label: "WhisperX 本地服务", model: "whisperx-large-v3", base: "http://localhost:9000" },
    { value: "mock", label: "Mock 测试", model: "mock-asr" },
  ],
  video_understanding: [
    { value: "volcengine-ark", label: "火山方舟 / 视频理解", model: "doubao-seed-2-0-pro-260215", base: "https://ark.cn-beijing.volces.com/api/v3" },
    { value: "aliyun-bailian", label: "阿里云百炼 / Qwen3-VL", model: "qwen3-vl-plus", base: "https://dashscope.aliyuncs.com/compatible-mode/v1" },
    { value: "gemini", label: "Gemini Video Understanding", model: "gemini-2.5-pro", base: "https://generativelanguage.googleapis.com/v1beta" },
    { value: "local", label: "本地镜头/节奏分析", model: "local-video-analyzer" },
  ],
  compliance: [
    { value: "volcengine-ark", label: "火山方舟 / Doubao Seed 2.0 Pro", model: "doubao-seed-2-0-pro-260215", base: "https://ark.cn-beijing.volces.com/api/v3" },
    { value: "aliyun-bailian", label: "阿里云百炼 / Qwen3.7 Plus", model: "qwen3.7-plus", base: "https://dashscope.aliyuncs.com/compatible-mode/v1" },
    { value: "aliyun-bailian-max", label: "阿里云百炼 / Qwen3.7 Max", model: "qwen3.7-max", base: "https://dashscope.aliyuncs.com/compatible-mode/v1" },
    { value: "deepseek", label: "DeepSeek", model: "deepseek-chat", base: "https://api.deepseek.com/v1" },
    { value: "openai-compatible", label: "其他 OpenAI 兼容接口", model: "gpt-4.1-mini", base: "https://api.openai.com/v1" },
  ],
  knowledge: [
    { value: "aliyun-bailian", label: "阿里云百炼 / Qwen3.7 Plus", model: "qwen3.7-plus", base: "https://dashscope.aliyuncs.com/compatible-mode/v1" },
    { value: "aliyun-bailian-max", label: "阿里云百炼 / Qwen3.7 Max", model: "qwen3.7-max", base: "https://dashscope.aliyuncs.com/compatible-mode/v1" },
    { value: "aliyun-bailian-latest", label: "阿里云百炼 / Qwen Plus Latest", model: "qwen-plus-latest", base: "https://dashscope.aliyuncs.com/compatible-mode/v1" },
    { value: "volcengine-ark", label: "火山方舟 / Doubao Seed 2.0 Pro", model: "doubao-seed-2-0-pro-260215", base: "https://ark.cn-beijing.volces.com/api/v3" },
    { value: "deepseek", label: "DeepSeek", model: "deepseek-chat", base: "https://api.deepseek.com/v1" },
    { value: "openai-compatible", label: "其他 OpenAI 兼容接口", model: "gpt-4.1-mini", base: "https://api.openai.com/v1" },
  ],
};

function authHeaders() {
  return api.token ? { Authorization: `Bearer ${api.token}` } : {};
}

function authenticatedMediaUrl(path) {
  if (!api.token) return path;
  const separator = path.includes("?") ? "&" : "?";
  return `${path}${separator}access_token=${encodeURIComponent(api.token)}`;
}

const localSaveDbName = "new-media-ai-platform-local-save";
const localSaveStoreName = "handles";
const localSaveHandleKey = "video-output-directory";

function openLocalSaveDb() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(localSaveDbName, 1);
    request.onupgradeneeded = () => {
      request.result.createObjectStore(localSaveStoreName);
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function saveLocalDirectoryHandle(handle) {
  const db = await openLocalSaveDb();
  await new Promise((resolve, reject) => {
    const tx = db.transaction(localSaveStoreName, "readwrite");
    tx.objectStore(localSaveStoreName).put(handle, localSaveHandleKey);
    tx.oncomplete = resolve;
    tx.onerror = () => reject(tx.error);
  });
  db.close();
}

async function loadLocalDirectoryHandle() {
  if (!window.indexedDB) return null;
  const db = await openLocalSaveDb();
  const handle = await new Promise((resolve, reject) => {
    const tx = db.transaction(localSaveStoreName, "readonly");
    const request = tx.objectStore(localSaveStoreName).get(localSaveHandleKey);
    request.onsuccess = () => resolve(request.result || null);
    request.onerror = () => reject(request.error);
  });
  db.close();
  return handle;
}

async function verifyLocalDirectoryPermission(handle) {
  if (!handle) return false;
  const options = { mode: "readwrite" };
  if ((await handle.queryPermission(options)) === "granted") return true;
  return (await handle.requestPermission(options)) === "granted";
}

function persistLocalSaveState() {
  localStorage.setItem("localSaveDirectoryName", state.localSaveDirectoryName || "");
  localStorage.setItem("autoSaveToLocalFolder", state.autoSaveToLocalFolder ? "1" : "0");
  localStorage.setItem("localSavedVideoIds", JSON.stringify([...state.localSavedVideoIds]));
}

function renderLocalSaveDirectoryState() {
  const nameTarget = document.querySelector("#currentLocalSaveDirectory");
  const statusTarget = document.querySelector("#localSaveStatus");
  const autoSaveInput = document.querySelector("#autoSaveToLocalFolder");
  const hasHandle = Boolean(state.localSaveDirectoryHandle);
  if (nameTarget) {
    nameTarget.textContent = hasHandle ? state.localSaveDirectoryName || "已选择文件夹" : "未选择文件夹";
  }
  if (statusTarget) {
    statusTarget.textContent = hasHandle
      ? `已选择：${state.localSaveDirectoryName || "电脑文件夹"}。页面保持打开时，可在成片生成后自动写入这里。`
      : "未选择电脑文件夹，生成的成片会先保留在服务器。";
    statusTarget.classList.toggle("ready", hasHandle);
  }
  if (autoSaveInput) autoSaveInput.checked = state.autoSaveToLocalFolder;
}

async function initLocalSaveDirectory() {
  renderLocalSaveDirectoryState();
  try {
    const handle = await loadLocalDirectoryHandle();
    if (!handle) return;
    state.localSaveDirectoryHandle = handle;
    state.localSaveDirectoryName = handle.name || state.localSaveDirectoryName;
    renderLocalSaveDirectoryState();
  } catch {
    state.localSaveDirectoryHandle = null;
    renderLocalSaveDirectoryState();
  }
}

async function chooseLocalSaveDirectory() {
  if (!window.showDirectoryPicker) {
    toast("当前浏览器不支持直接选择电脑文件夹，请使用最新版 Chrome 或 Edge");
    return null;
  }
  const handle = await window.showDirectoryPicker({ mode: "readwrite" });
  const granted = await verifyLocalDirectoryPermission(handle);
  if (!granted) {
    toast("没有获得这个文件夹的写入权限");
    return null;
  }
  state.localSaveDirectoryHandle = handle;
  state.localSaveDirectoryName = handle.name || "电脑文件夹";
  await saveLocalDirectoryHandle(handle);
  persistLocalSaveState();
  renderLocalSaveDirectoryState();
  return handle;
}

function localVideoFilename(video) {
  const title = (video.script_title || `视频任务-${video.task_id}`)
    .replace(/[\\/:*?"<>|]/g, "-")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 42);
  return `${video.task_id}-${title || "AI成片"}.mp4`;
}

async function saveVideoToLocalFolder(video, silent = false) {
  if (!video || !video.task_id) return false;
  if (!state.localSaveDirectoryHandle) {
    const handle = await chooseLocalSaveDirectory();
    if (!handle) return false;
  }
  const granted = await verifyLocalDirectoryPermission(state.localSaveDirectoryHandle);
  if (!granted) {
    state.localSaveDirectoryHandle = null;
    renderLocalSaveDirectoryState();
    if (!silent) toast("电脑文件夹权限已失效，请重新选择");
    return false;
  }
  const source = video.storage_kind === "external" && video.output_path
    ? video.output_path
    : `/api/video-tasks/${video.task_id}/output`;
  const response = await fetch(source, {
    headers: source.startsWith("/api") ? authHeaders() : {},
  });
  if (!response.ok) throw new Error("成片文件读取失败");
  const blob = await response.blob();
  const fileHandle = await state.localSaveDirectoryHandle.getFileHandle(localVideoFilename(video), { create: true });
  const writable = await fileHandle.createWritable();
  await writable.write(blob);
  await writable.close();
  state.localSavedVideoIds.add(Number(video.task_id));
  persistLocalSaveState();
  if (!silent) toast(`已保存到电脑文件夹：${state.localSaveDirectoryName || ""}`);
  renderVideoStorage(state.videoStorage);
  return true;
}

async function autoSaveVideosToLocal(videos) {
  if (!state.autoSaveToLocalFolder || !state.localSaveDirectoryHandle) return;
  for (const video of videos || []) {
    if (!video?.task_id || video.storage_kind === "placeholder" || !video.exists && video.storage_kind !== "external") continue;
    const taskId = Number(video.task_id);
    if (state.localSavedVideoIds.has(taskId) || state.localSavingVideoIds.has(taskId)) continue;
    state.localSavingVideoIds.add(taskId);
    try {
      await saveVideoToLocalFolder(video, true);
    } catch {
      toast(`视频任务 #${taskId} 自动保存到电脑失败`);
    } finally {
      state.localSavingVideoIds.delete(taskId);
    }
  }
}

function formData(form) {
  return Object.fromEntries(new FormData(form).entries());
}

function fillForm(form, values) {
  Object.entries(values).forEach(([key, value]) => {
    const field = form.elements[key];
    if (!field) return;
    if (field.type === "checkbox") {
      field.checked = Boolean(value);
      return;
    }
    field.value = value ?? "";
  });
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function compactNumber(value) {
  const number = Number(value || 0);
  if (!Number.isFinite(number) || number <= 0) return "0";
  if (number >= 10000) return `${(number / 10000).toFixed(number >= 100000 ? 0 : 1)}万`;
  return String(Math.round(number));
}

function isHttpUrl(value) {
  return /^https?:\/\//i.test(String(value || ""));
}

function toDateTimeInput(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const pad = (number) => String(number).padStart(2, "0");
  return [
    date.getFullYear(),
    pad(date.getMonth() + 1),
    pad(date.getDate()),
  ].join("-") + `T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function formatNumber(value) {
  return Number(value || 0).toLocaleString("zh-CN");
}

function formatBytes(value) {
  const bytes = Number(value || 0);
  if (bytes <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const index = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)));
  const size = bytes / 1024 ** index;
  return `${size >= 10 || index === 0 ? size.toFixed(0) : size.toFixed(1)} ${units[index]}`;
}

function formatDateTime(value) {
  if (!value) return "-";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "-" : date.toLocaleString("zh-CN", { hour12: false });
}

const listPageSize = 6;

function pagedItems(key, items, pageSize = listPageSize) {
  const list = Array.isArray(items) ? items : [];
  const totalPages = Math.max(1, Math.ceil(list.length / pageSize));
  const currentPage = Math.min(Math.max(1, Number(state.listPages[key] || 1)), totalPages);
  state.listPages[key] = currentPage;
  const start = (currentPage - 1) * pageSize;
  return {
    items: list.slice(start, start + pageSize),
    page: currentPage,
    totalPages,
    total: list.length,
  };
}

function pagerHtml(key, pageInfo) {
  if (!pageInfo || pageInfo.total <= listPageSize) return "";
  return `
    <div class="tablePager">
      <span>第 ${pageInfo.page} / ${pageInfo.totalPages} 页，共 ${pageInfo.total} 条</span>
      <div>
        <button type="button" class="secondary" data-action="list-page-prev" data-list-key="${key}" ${pageInfo.page <= 1 ? "disabled" : ""}>上一页</button>
        <button type="button" class="secondary" data-action="list-page-next" data-list-key="${key}" ${pageInfo.page >= pageInfo.totalPages ? "disabled" : ""}>下一页</button>
      </div>
    </div>
  `;
}

function rerenderPagedList(key) {
  const renderers = {
    taskTable: () => renderTaskTable(state.videoTasks),
    taskScripts: () => renderTaskScriptTable(state.scripts),
    scriptCandidates: () => renderScriptCandidates(state.scripts),
    publishRecords: () => renderPublishRecords(state.publishRecords),
    platformAccounts: () => renderPlatformAccounts(state.platformAccounts),
    materials: () => renderMaterials(state.materials),
    referenceMaterials: () => renderReferenceMaterials(state.materials),
    digitalHumans: () => renderDigitalHumans(state.digitalHumans),
    models: () => renderModels(state.modelConfigs),
    modelUsage: () => renderModelUsage(state.modelUsage),
    modelUsageHistory: () => renderModelUsage(state.modelUsage),
    videoStorage: () => renderVideoStorage(state.videoStorage),
    users: () => renderSystemUsers(state.users),
    platformCredentials: () => renderPlatformCredentials(state.platformCredentials),
    wechatRequests: () => renderWechatLogin(state.wechatLoginConfig, state.wechatLoginRequests, state.wechatIdentities),
    wechatIdentities: () => renderWechatLogin(state.wechatLoginConfig, state.wechatLoginRequests, state.wechatIdentities),
    trendingSearches: () => renderTrending(state.trendingSearches || [], state.trendingVideos || []),
    trendingVideos: () => renderTrending(state.trendingSearches || [], state.trendingVideos || []),
    transcriptions: () => renderTranscriptions(state.transcriptions),
    videoAnalyses: () => renderVideoAnalyses(state.videoAnalyses),
    overviewScripts: () => renderOverviewActivity(),
    overviewTasks: () => renderOverviewActivity(),
  };
  renderers[key]?.();
  enhanceResponsiveTables();
}

function enhanceResponsiveTables(root = document) {
  root.querySelectorAll("table").forEach((table) => {
    const headers = Array.from(table.querySelectorAll("thead th")).map((header) => header.textContent.trim());
    if (!headers.length) return;
    table.classList.add("responsiveTable");
    table.querySelectorAll("tbody tr").forEach((row) => {
      Array.from(row.children).forEach((cell, index) => {
        if (cell.tagName !== "TD") return;
        cell.dataset.label = headers[index] || "";
      });
    });
  });
}

function roleLabel(role) {
  return {
    admin: "管理员",
    operator: "运营人员",
    reviewer: "审核人员",
  }[role] || role || "-";
}

function isAdminUser(user = state.currentUser) {
  return user?.role === "admin";
}

function applyRoleAccess(user = state.currentUser) {
  const isAdmin = isAdminUser(user);
  document.body.classList.toggle("role-admin", isAdmin);
  document.body.classList.toggle("role-limited", Boolean(user) && !isAdmin);
  document.querySelectorAll("[data-page='settings'], .subNav").forEach((el) => {
    el.classList.toggle("hiddenPanel", !isAdmin);
  });
  if (!isAdmin && state.currentPage === "settings") {
    switchPage("overview", null, true);
  }
}

function accountInitials(username) {
  const value = String(username || "").trim();
  return value ? Array.from(value).slice(0, 2).join("").toUpperCase() : "--";
}

function loginUrl() {
  const next = encodeURIComponent(`${window.location.pathname}${window.location.hash}`);
  return `/login.html?next=${next}`;
}

function redirectToLogin() {
  window.location.replace(loginUrl());
}

function toast(message) {
  const el = document.querySelector("#toast");
  el.textContent = message;
  el.classList.add("show");
  setTimeout(() => el.classList.remove("show"), 2600);
}

function apiErrorMessage(error, fallback = "操作失败，请稍后重试") {
  const message = error?.message || "";
  if (!message) return fallback;
  try {
    const parsed = JSON.parse(message);
    if (typeof parsed.detail === "string") return parsed.detail;
    if (Array.isArray(parsed.detail) && parsed.detail.length) {
      return parsed.detail
        .map((item) => item.msg || item.message || "")
        .filter(Boolean)
        .join("；") || fallback;
    }
  } catch {
    return message;
  }
  return message;
}

function parseRoute(hash) {
  const value = hash.replace("#", "") || "overview";
  if (value.startsWith("settings-")) {
    const section = value.replace("settings-", "");
    return { page: "settings", section: settingsSections[section] ? section : "usage" };
  }
  return { page: pages[value] ? value : "overview", section: null };
}

function switchSettingsSection(section, updateHash = true) {
  const nextSection = settingsSections[section] ? section : "usage";
  state.currentSettingsSection = nextSection;
  document.querySelectorAll(".settingsPane").forEach((pane) => {
    pane.classList.toggle("activeSettingsPane", pane.id === `settings-tab-${nextSection}`);
  });
  document.querySelectorAll(".subNavItem").forEach((item) => {
    item.classList.toggle("active", item.dataset.settingsSection === nextSection);
  });
  document.querySelector("#pageTitle").textContent = settingsSections[nextSection].title;
  document.querySelector("#pageEyebrow").textContent = settingsSections[nextSection].eyebrow;
  if (updateHash) {
    window.location.hash = `settings-${nextSection}`;
  }
}

function switchPage(page, section = null, updateHash = true) {
  state.currentPage = page;
  document.querySelectorAll(".page").forEach((el) => el.classList.remove("activePage"));
  document.querySelector(`#page-${page}`)?.classList.add("activePage");
  document.querySelectorAll(".navItem").forEach((el) => el.classList.toggle("active", el.dataset.page === page));
  if (page === "settings") {
    switchSettingsSection(section || state.currentSettingsSection, updateHash);
    return;
  }
  document.querySelectorAll(".subNavItem").forEach((item) => item.classList.remove("active"));
  document.querySelector("#pageTitle").textContent = pages[page].title;
  document.querySelector("#pageEyebrow").textContent = pages[page].eyebrow;
  if (updateHash) {
    window.location.hash = page;
  }
  if (page === "analysis") {
    setReferenceTab(state.currentReferenceTab || "history");
    if (api.token && updateHash) {
      refresh().catch((err) => toast(err.message));
    }
  }
}

window.addEventListener("hashchange", () => {
  const route = parseRoute(window.location.hash);
  if (route.page !== state.currentPage || route.section !== state.currentSettingsSection) {
    switchPage(route.page, route.section, false);
  }
});

function syncProviderOptions() {
  const form = document.querySelector("#modelConfigForm");
  const purpose = form.querySelector("[name='purpose']").value;
  const provider = form.querySelector("[name='provider']");
  const model = form.querySelector("[name='model_name']");
  const apiBase = form.querySelector("[name='api_base']");
  const options = providerOptions[purpose] || providerOptions.script;
  provider.innerHTML = options.map((item) => `<option value="${item.value}">${item.label}</option>`).join("");
  if (!model.value || model.dataset.autofilled === "true") {
    model.value = options[0].model;
    model.dataset.autofilled = "true";
  }
  if (options[0].base && (!apiBase.value || apiBase.dataset.autofilled === "true")) {
    apiBase.value = options[0].base;
    apiBase.dataset.autofilled = "true";
  } else if (!options[0].base && apiBase.dataset.autofilled === "true") {
    apiBase.value = "";
    apiBase.dataset.autofilled = "true";
  }
}

function applyProviderDefaultModel() {
  const form = document.querySelector("#modelConfigForm");
  const purpose = form.querySelector("[name='purpose']").value;
  const provider = form.querySelector("[name='provider']").value;
  const model = form.querySelector("[name='model_name']");
  const apiBase = form.querySelector("[name='api_base']");
  const selected = (providerOptions[purpose] || []).find((item) => item.value === provider);
  if (selected) {
    model.value = selected.model;
    model.dataset.autofilled = "true";
    if (selected.base) {
      apiBase.value = selected.base;
      apiBase.dataset.autofilled = "true";
    } else if (apiBase.dataset.autofilled === "true") {
      apiBase.value = "";
    }
  }
}

const modelPresets = {
  "volcengine-jimeng-digital-human": {
    name: "火山即梦数字人",
    purpose: "digital_human",
    provider: "volcengine-jimeng-digital-human",
    api_base: "https://visual.volcengineapi.com",
    model_name: "jimeng-digital-human",
    notes: "real_adapter=volcengine_jimeng\nadapter_route=xiaoyunque_reference\ncredential_platform=volcengine\ncredential_purpose=digital_human\ncredential_type=ak_sk\nservice=cv\nregion=cn-north-1\napp_id=101606596\nreq_key=pippit_iv2v_v20_cvtob_with_vinput\nallow_script_prompt=false\nprompt_policy=clean_no_text_plate\nsubtitle_policy=reference_style_short_captions\nrequires_public_portrait_url=true\nrequires_public_source_video_url=true\nstatus=adapter_ready",
  },
  "aliyun-videoretalk": {
    name: "阿里云百炼 VideoRetalk 源视频驱动",
    purpose: "digital_human",
    provider: "aliyun-videoretalk",
    api_base: "https://dashscope.aliyuncs.com/api/v1",
    model_name: "videoretalk",
    notes: "real_adapter=aliyun_videoretalk\nrequires_public_source_video_url=true\nrequires_public_audio_url=true\nuse_ref_image=false",
  },
  "aliyun-liveportrait": {
    name: "阿里云百炼 LivePortrait 头像驱动（实验项）",
    purpose: "digital_human",
    provider: "aliyun-liveportrait",
    api_base: "https://dashscope.aliyuncs.com/api/v1",
    model_name: "liveportrait",
    notes: "real_adapter=aliyun_liveportrait\nrequires_public_portrait_url=true\nrequires_public_audio_url=true\ntemplate_id=normal\nquality_status=failed_face_artifacts\nnot_for_production=true",
  },
  "aliyun-wan-s2v": {
    name: "阿里云百炼万相数字人",
    purpose: "digital_human",
    provider: "aliyun-wan-s2v",
    api_base: "https://dashscope.aliyuncs.com/api/v1",
    model_name: "wan2.2-s2v",
    notes: "real_adapter=aliyun_wan_s2v\nresolution=480P\nrequires_public_portrait_url=true\nrequires_public_audio_url=true\naudio_limit_seconds=20",
  },
  did: {
    name: "D-ID 真实数字人口播",
    purpose: "digital_human",
    provider: "d-id",
    api_base: "https://api.d-id.com",
    model_name: "d-id-talking-avatar",
    notes: "D-ID uses the same API Key for /images, /audios and /talks.",
  },
  "qwen-asr": {
    name: "阿里云百炼 Qwen-ASR 真实转写",
    purpose: "asr",
    provider: "aliyun-bailian",
    api_base: "https://dashscope.aliyuncs.com/compatible-mode/v1",
    model_name: "qwen3-asr-flash",
    notes: "real_adapter=qwen_asr",
  },
  "cosyvoice-tts": {
    name: "阿里云百炼 CosyVoice 真实语音合成",
    purpose: "tts",
    provider: "aliyun-cosyvoice",
    api_base: "https://dashscope.aliyuncs.com/api/v1",
    model_name: "cosyvoice-v3-flash",
    notes: "voice=longanyang",
  },
  "cosyvoice-clone": {
    name: "阿里云百炼 CosyVoice 声音复刻",
    purpose: "voice_clone",
    provider: "aliyun-cosyvoice-clone",
    api_base: "https://dashscope.aliyuncs.com/api/v1",
    model_name: "cosyvoice-v3-flash",
    notes: "target_model=cosyvoice-v3-flash\nrequires_public_source_url=true",
  },
};

function findModelConfig(purpose, provider) {
  return state.modelConfigs.find((model) => model.purpose === purpose && model.provider === provider);
}

function fillModelConfigForm(values, existing = null) {
  const form = document.querySelector("#modelConfigForm");
  form.dataset.modelId = existing?.id || "";
  form.querySelector("[name='name']").value = existing?.name || values.name || "";
  form.querySelector("[name='purpose']").value = values.purpose || existing?.purpose || "script";
  syncProviderOptions();
  form.querySelector("[name='provider']").value = values.provider || existing?.provider || "";
  applyProviderDefaultModel();
  form.querySelector("[name='api_base']").value = existing?.api_base || values.api_base || "";
  form.querySelector("[name='model_name']").value = existing?.model_name || values.model_name || "";
  form.querySelector("[name='notes']").value = existing?.notes || values.notes || "";
  form.querySelector("[name='is_active']").checked = values.is_active ?? existing?.is_active ?? true;
  const keyInput = form.querySelector("[name='api_key']");
  keyInput.value = "";
  keyInput.placeholder = existing?.has_api_key ? "已保存 Key，可留空" : "保存后不会展示明文";
}

function renderMetrics(counts) {
  const labels = {
    materials: "素材",
    topics: "选题",
    scripts: "脚本",
    digital_humans: "数字人",
    video_tasks: "视频任务",
    publish_records: "发布记录",
    trending_videos: "爆款参考",
    transcriptions: "转写任务",
    video_analyses: "深度拆解",
  };
  document.querySelector("#overview").innerHTML = Object.entries(labels)
    .map(([key, label]) => `<div class="metric"><strong>${counts[key] ?? 0}</strong><span>${label}</span></div>`)
    .join("");
}

function renderProductModules(report) {
  const target = document.querySelector("#productModuleList");
  if (!target) return;
  const modules = report?.modules || [];
  if (!modules.length) {
    target.innerHTML = `<div class="item">模块配置加载中</div>`;
    return;
  }
  target.innerHTML = modules.map((module) => `
    <article class="productModuleCard">
      <div class="productModuleHeader">
        <span>${escapeHtml(module.role || "模块")}</span>
        <strong>${escapeHtml(module.label || module.key)}</strong>
      </div>
      <p>${escapeHtml(module.summary || "")}</p>
      <div class="moduleStageLine">
        ${(module.stages || []).slice(0, 6).map((stage) => `<span>${escapeHtml(stage)}</span>`).join("")}
      </div>
      <div class="moduleOutputLine">
        ${(module.outputs || []).slice(0, 5).map((output) => `<span>${escapeHtml(output)}</span>`).join("")}
      </div>
      <button type="button" class="secondary" data-module-page="${escapeHtml(module.primary_action?.page || module.page || "overview")}">
        ${escapeHtml(module.primary_action?.label || "进入模块")}
      </button>
    </article>
  `).join("");
}

function renderOverviewActivity() {
  const target = document.querySelector("#overviewActivityContent");
  if (!target) return;
  document.querySelectorAll("[data-overview-tab]").forEach((button) => {
    button.classList.toggle("active", button.dataset.overviewTab === state.overviewActivityTab);
  });
  if (state.overviewActivityTab === "tasks") {
    const pageInfo = pagedItems("overviewTasks", state.videoTasks || []);
    const tasks = pageInfo.items;
    if (!tasks.length) {
      target.innerHTML = `<div class="item">还没有视频任务</div>`;
      return;
    }
    target.innerHTML = `
      <table class="settingsTable compactTable overviewActivityTable">
        <thead>
          <tr>
            <th>任务</th>
            <th>脚本</th>
            <th>状态</th>
            <th>方式/进度</th>
            <th>更新时间</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          ${tasks
            .map((task) => `
              <tr>
                <td><strong>#${task.id}</strong></td>
                <td class="overviewTitleCell">${escapeHtml(scriptName(task.script_id))}</td>
                <td><span class="status taskStatus ${taskStatusClass(task.status)}">${taskStatusLabel(task.status)}</span></td>
                <td>
                  <strong>${productionModeLabel(task.production_mode)}</strong>
                  <div class="recordMeta">${taskProgress(task)}% · ${escapeHtml(taskSegmentMeta(task))}</div>
                </td>
                <td>${formatDateTime(task.updated_at || task.created_at)}</td>
                <td><button type="button" class="secondary compactButton" data-action="overview-view-task" data-id="${task.id}">详情</button></td>
              </tr>
            `)
            .join("")}
        </tbody>
      </table>
      ${pagerHtml("overviewTasks", pageInfo)}
    `;
    return;
  }

  const pageInfo = pagedItems("overviewScripts", state.scripts || []);
  const scripts = pageInfo.items;
  if (!scripts.length) {
    target.innerHTML = `<div class="item">还没有脚本</div>`;
    return;
  }
  target.innerHTML = `
    <table class="settingsTable compactTable overviewActivityTable">
      <thead>
        <tr>
          <th>脚本</th>
          <th>平台/时长</th>
          <th>视频任务</th>
          <th>创建时间</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        ${scripts
          .map((script) => `
            <tr>
              <td class="overviewTitleCell">
                <strong title="${escapeHtml(script.hook || "未命名脚本")}">#${script.id} ${escapeHtml(script.hook || "未命名脚本")}</strong>
                <span>${escapeHtml((script.hashtags || "").split(/\s+/).filter(Boolean).slice(0, 3).join(" ") || "未设置标签")}</span>
              </td>
              <td>
                <strong>${platformLabel(script.target_platform || "douyin")}</strong>
                <div class="recordMeta">${Number(script.duration_seconds || 30)} 秒</div>
              </td>
              <td><strong>${scriptTaskCount(script.id)}</strong> 个</td>
              <td>${formatDateTime(script.created_at)}</td>
              <td><button type="button" class="secondary compactButton" data-action="overview-view-script" data-id="${script.id}">详情</button></td>
            </tr>
          `)
          .join("")}
      </tbody>
    </table>
    ${pagerHtml("overviewScripts", pageInfo)}
  `;
}

function hideScriptDetail(clearContent = false) {
  const panel = document.querySelector("#scriptDetailPanel");
  if (panel) panel.classList.add("hiddenPanel");
  if (!clearContent) return;
  const titleTarget = document.querySelector("#titleSuggestionList");
  const creationTarget = document.querySelector("#scriptPreviewCreation");
  if (titleTarget) titleTarget.innerHTML = "";
  if (creationTarget) {
    creationTarget.className = "scriptResult empty";
    creationTarget.textContent = "还没有脚本";
  }
}

function renderScripts(scripts) {
  state.scripts = scripts;
  renderScriptSelects(scripts);
  renderTaskScriptTable(scripts);
  renderTaskWorkflowStats();
  const creationTarget = document.querySelector("#scriptPreviewCreation");
  const resultStatus = document.querySelector("#scriptResultStatus");
  renderOverviewActivity();
  if (!scripts.length) {
    renderScriptCandidates([]);
    hideScriptDetail(true);
    [creationTarget].filter(Boolean).forEach((target) => {
      target.className = "preview empty";
      target.textContent = "还没有脚本";
    });
    if (resultStatus) {
      resultStatus.textContent = "点击标题会按该方向重写";
      resultStatus.classList.remove("isGenerating");
    }
    return;
  }
  const script = scripts.find((item) => item.id === state.highlightedScriptId) || scripts[0];
  state.latestScriptId = script.id;
  const taskScriptSelect = document.querySelector("[name='script_id']");
  if (taskScriptSelect) taskScriptSelect.value = script.id;
  renderScriptCandidates(scripts);
  const detailPanel = document.querySelector("#scriptDetailPanel");
  const keepDetailOpen = detailPanel && !detailPanel.classList.contains("hiddenPanel");
  if (keepDetailOpen) {
    renderTitleSuggestions(script);
    renderScriptDetail(script, state.highlightedScriptId === script.id);
  } else if (resultStatus) {
    resultStatus.textContent = scripts.length ? `已有 ${scripts.length} 条脚本，点详情查看` : "生成后先选择方案";
    resultStatus.classList.remove("isGenerating");
  }
}

function productionModeLabel(mode) {
  return {
    dynamic_explainer: "图文草稿",
    digital_human: "真人口播",
    material_mix: "素材库混剪",
    seedance_scene: "Seedance 实景",
    talking_head_template: "口播模板",
  }[mode] || "口播模板";
}

function exportProfileLabel(profileKey) {
  const profile = state.exportProfiles.find((item) => item.key === profileKey);
  return profile ? profile.label : (profileKey || "自动匹配");
}

function exportProfileMeta(task) {
  const profile = state.exportProfiles.find((item) => item.key === task.export_profile);
  if (profile) {
    return `${profile.label} · ${profile.width}x${profile.height}`;
  }
  if (task.export_width && task.export_height) {
    return `${task.export_width}x${task.export_height}`;
  }
  return exportProfileLabel(task.export_profile);
}

function defaultExportProfileForPlatform(platform) {
  if (platform === "wechat_channels") return "wechat_channels_vertical";
  if (platform === "manual") return "archive_landscape";
  return "douyin_vertical";
}

function renderExportProfileSelects(profiles) {
  state.exportProfiles = profiles || [];
  const options = state.exportProfiles
    .map((profile) => (
      `<option value="${profile.key}">${escapeHtml(profile.label)} · ${profile.width}x${profile.height}</option>`
    ))
    .join("");
  document.querySelectorAll("#taskExportProfileSelect, #batchExportProfileSelect").forEach((select) => {
    const current = select.value;
    select.innerHTML = `<option value="">按脚本平台自动匹配</option>${options}`;
    select.value = current || "";
  });
  syncCreationExportProfileHint();
}

function syncCreationExportProfileHint() {
  const target = document.querySelector("#creationExportProfileHint");
  const platformSelect = document.querySelector("#scriptForm [name='target_platform']");
  if (!target || !platformSelect) return;
  const key = defaultExportProfileForPlatform(platformSelect.value);
  const profile = state.exportProfiles.find((item) => item.key === key);
  if (!profile) {
    target.textContent = "输出规格会按目标平台自动匹配。";
    return;
  }
  target.textContent = `${platformLabel(platformSelect.value)}默认导出：${profile.label}，${profile.width}x${profile.height}，${profile.notes}`;
}

function renderVideoProductionSkills(report) {
  const target = document.querySelector("#videoProductionSkillPanel");
  if (!target) return;
  const skills = report?.skills || [];
  if (!skills.length) {
    target.innerHTML = "";
    return;
  }
  target.innerHTML = `
    <div class="skillPanelHeader">
      <strong>视频生产 Skill 已启用</strong>
      <span>${escapeHtml((report.pipeline || []).join(" / "))}</span>
    </div>
    <div class="skillPillGrid">
      ${skills.map((skill) => `
        <span title="${escapeHtml(skill.summary || "")}">
          ${escapeHtml(skill.label || skill.key)}
        </span>
      `).join("")}
    </div>
  `;
}

function parseStoryboardPlan(script) {
  if (!script?.storyboard_plan) return storyboardRowsFromText(script?.storyboard || "", script?.duration_seconds || 30);
  try {
    const parsed = JSON.parse(script.storyboard_plan);
    if (Array.isArray(parsed) && parsed.length) return parsed;
  } catch {
    return storyboardRowsFromText(script?.storyboard || "", script?.duration_seconds || 30);
  }
  return storyboardRowsFromText(script?.storyboard || "", script?.duration_seconds || 30);
}

function storyboardRowsFromText(storyboard, durationSeconds) {
  const lines = String(storyboard || "")
    .split(/\n+/)
    .map((line) => line.trim())
    .filter(Boolean);
  const total = Number(durationSeconds || 30);
  const segment = Math.max(5, Math.ceil(total / Math.max(1, lines.length || 1)));
  return lines.map((line, index) => ({
    start_second: index * segment,
    end_second: Math.min(total, (index + 1) * segment),
    shot_type: index === 0 || index === lines.length - 1 ? "talking_head" : "text_card",
    visual: line,
    person_action: "根据口播自然讲解，画面需要有轻微镜头运动",
    screen_text: line.slice(0, 18),
    asset_or_background: "business hotel scene",
    ai_prompt: line,
    needs_lip_sync: index === 0 || index === lines.length - 1,
  }));
}

function storyboardPlanJson(script) {
  const rows = parseStoryboardPlan(script);
  return JSON.stringify(rows, null, 2);
}

function renderStoryboardPlanTable(script) {
  const rows = parseStoryboardPlan(script);
  if (!rows.length) return `<div class="item">还没有结构化分镜，保存脚本时可在高级项里补充。</div>`;
  return `
    <div class="storyboardPlanBlock">
      <div class="candidateHeader">
        <strong>分镜执行表</strong>
        <span>用于决定画面怎么动，不只是口播文字。</span>
      </div>
      <div class="storyboardPlanTableWrap">
        <table class="storyboardPlanTable compactTable">
          <thead>
            <tr>
              <th>时间</th>
              <th>画面类型</th>
              <th>画面动作</th>
              <th>屏幕文字</th>
              <th>数字人</th>
            </tr>
          </thead>
          <tbody>
            ${rows
              .map((row) => `
                <tr>
                  <td>${Number(row.start_second || 0)}-${Number(row.end_second || 0)}s</td>
                  <td>${escapeHtml(row.shot_type || "-")}</td>
                  <td>${escapeHtml(row.visual || row.person_action || "-")}</td>
                  <td>${escapeHtml(row.screen_text || "-")}</td>
                  <td>${row.needs_lip_sync ? "需口型" : "不需要"}</td>
                </tr>
              `)
              .join("")}
          </tbody>
        </table>
      </div>
    </div>
  `;
}

function renderScriptDetail(script, isFresh = false) {
  const panel = document.querySelector("#scriptDetailPanel");
  const creationTarget = document.querySelector("#scriptPreviewCreation");
  const resultStatus = document.querySelector("#scriptResultStatus");
  if (!creationTarget) return;
  if (panel) panel.classList.remove("hiddenPanel");
  creationTarget.className = `scriptResult${isFresh ? " scriptResultFresh" : ""}`;
  creationTarget.innerHTML = `
    <form id="scriptEditForm" class="scriptEditForm" data-script-id="${script.id}" data-dirty="false">
      <div class="scriptEditGrid">
        <label>开头钩子<textarea name="hook" rows="2">${escapeHtml(script.hook)}</textarea></label>
        <label>标签<input name="hashtags" value="${escapeHtml(script.hashtags)}" /></label>
      </div>
      <label>口播稿<textarea name="voiceover" rows="8">${escapeHtml(script.voiceover)}</textarea></label>
      <label>分镜/画面<textarea name="storyboard" rows="5">${escapeHtml(script.storyboard)}</textarea></label>
      ${renderStoryboardPlanTable(script)}
      <details class="scriptAdvancedEdit">
        <summary>视频提示词、标题和合规提醒</summary>
        <label>分镜执行表 JSON<textarea name="storyboard_plan" rows="8">${escapeHtml(storyboardPlanJson(script))}</textarea></label>
        <label>视频提示词<textarea name="seedance_prompt" rows="5">${escapeHtml(script.seedance_prompt)}</textarea></label>
        <label>标题建议<textarea name="title_options" rows="4">${escapeHtml(script.title_options)}</textarea></label>
        <label>合规提醒<textarea name="compliance_notes" rows="4">${escapeHtml(script.compliance_notes)}</textarea></label>
      </details>
      <div class="scriptEditActions">
        <button type="submit">保存脚本修改</button>
        <span id="scriptEditSaveState" class="resultHint">可直接修改，生成视频前会自动保存。</span>
      </div>
    </form>
  `;
  if (resultStatus) {
    resultStatus.textContent = isFresh ? `脚本 #${script.id} · 刚刚生成` : `脚本 #${script.id}`;
    resultStatus.classList.remove("isGenerating");
  }
}

function openScriptDetail(script, options = {}) {
  if (!script) return;
  state.latestScriptId = script.id;
  state.highlightedScriptId = script.id;
  renderScriptCandidates(state.scripts);
  renderTitleSuggestions(script);
  renderScriptDetail(script, Boolean(options.isFresh));
  if (options.scroll !== false) {
    document.querySelector("#scriptDetailPanel")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

function renderScriptLoading(message = "AI 正在生成标题、口播稿、分镜和视频提示词...", keepTitles = false) {
  const detailPanel = document.querySelector("#scriptDetailPanel");
  const titleTarget = document.querySelector("#titleSuggestionList");
  const candidateTarget = document.querySelector("#scriptCandidateList");
  const creationTarget = document.querySelector("#scriptPreviewCreation");
  const resultStatus = document.querySelector("#scriptResultStatus");
  if (detailPanel) {
    detailPanel.classList.toggle("hiddenPanel", !keepTitles);
  }
  if (candidateTarget && !keepTitles) {
    candidateTarget.innerHTML = `<div class="item">正在生成候选方案...</div>`;
  }
  if (titleTarget && !keepTitles) {
    titleTarget.innerHTML = `<div class="item">正在生成标题建议...</div>`;
  }
  if (creationTarget) {
    creationTarget.className = "scriptResult scriptResultFresh";
    creationTarget.innerHTML = `<div class="scriptLoading">${escapeHtml(message)}</div>`;
  }
  if (resultStatus) {
    resultStatus.textContent = "生成中...";
    resultStatus.classList.add("isGenerating");
  }
}

function applyGeneratedScript(script, options = {}) {
  state.latestScriptId = script.id;
  state.highlightedScriptId = script.id;
  state.scripts = [script, ...state.scripts.filter((item) => item.id !== script.id)];
  const scriptInput = document.querySelector("[name='script_id']");
  if (scriptInput) scriptInput.value = script.id;
  renderScriptSelects(state.scripts);
  renderScriptCandidates(state.scripts);
  renderTitleSuggestions(script);
  if (options.openDetail) {
    openScriptDetail(script, { isFresh: true });
  } else {
    hideScriptDetail();
    const resultStatus = document.querySelector("#scriptResultStatus");
    if (resultStatus) {
      resultStatus.textContent = `已生成 ${state.scripts.length} 条候选，点详情查看`;
      resultStatus.classList.remove("isGenerating");
    }
  }
}

function renderScriptCandidates(scripts) {
  const target = document.querySelector("#scriptCandidateList");
  if (!target) return;
  if (!scripts.length) {
    target.innerHTML = `<div class="item">输入视频内容后，可生成多版候选脚本。</div>`;
    return;
  }
  const pageInfo = pagedItems("scriptCandidates", scripts);
  target.innerHTML = `
    <div class="candidateHeader">
      <strong>候选方案</strong>
      <span>点详情审核脚本，或直接生成视频任务。</span>
    </div>
    <div class="candidateRows">
      ${pageInfo.items
        .map(
          (script, index) => `
            <div class="candidateRow ${script.id === state.latestScriptId ? "selectedCandidate" : ""}">
              <div class="candidateMain">
                <span>方案 ${(pageInfo.page - 1) * listPageSize + index + 1} · #${script.id} · ${script.duration_seconds || 30}s</span>
                <strong>${escapeHtml(script.hook || "未命名方案")}</strong>
                <em>${escapeHtml((script.voiceover || "").slice(0, 78))}</em>
              </div>
              <div class="candidateActions">
                <button type="button" class="secondary" data-action="view-script" data-script-id="${script.id}">详情/编辑</button>
                <button type="button" data-action="auto-video-script" data-script-id="${script.id}">生成视频</button>
              </div>
            </div>
          `,
        )
        .join("")}
    </div>
    ${pagerHtml("scriptCandidates", pageInfo)}
  `;
}

function renderScriptSelects(scripts) {
  const select = document.querySelector("#taskScriptSelect");
  const batchSelect = document.querySelector("#batchScriptSelect");
  const options = scripts
    .map((script) => `<option value="${script.id}">#${script.id} ${escapeHtml(script.hook || "未命名脚本").slice(0, 44)}</option>`)
    .join("");
  if (select) {
    const current = select.value;
    select.innerHTML = `<option value="">先生成脚本</option>${options}`;
    select.value = current || state.latestScriptId || "";
  }
  if (batchSelect) {
    const selected = new Set([...batchSelect.selectedOptions].map((item) => item.value));
    batchSelect.innerHTML = options || `<option value="">先生成脚本</option>`;
    [...batchSelect.options].forEach((option) => {
      option.selected = selected.has(option.value);
    });
  }
}

function renderTitleSuggestions(script) {
  const target = document.querySelector("#titleSuggestionList");
  if (!target) return;
  if (!script || !script.title_options) {
    target.innerHTML = `<div class="item">生成脚本后会显示 AI 标题建议</div>`;
    return;
  }
  const titles = script.title_options
    .split(/\n+/)
    .map((item) => item.replace(/^\d+[.、]\s*/, "").trim())
    .filter(Boolean);
  target.innerHTML = titles.length
    ? titles
        .map((title, index) => `
          <button type="button" class="titleOption" data-title="${escapeHtml(title)}">
            <span>标题 ${index + 1}</span>
            <strong>${escapeHtml(title)}</strong>
          </button>
        `)
        .join("")
    : `<div class="item">这次脚本没有返回标题建议</div>`;
}

function currentScriptEditForm() {
  return document.querySelector("#scriptEditForm");
}

function updateScriptInState(script) {
  const exists = state.scripts.some((item) => item.id === script.id);
  state.scripts = exists
    ? state.scripts.map((item) => (item.id === script.id ? script : item))
    : [script, ...state.scripts];
  state.latestScriptId = script.id;
  state.highlightedScriptId = script.id;
  renderScriptSelects(state.scripts);
  renderScriptCandidates(state.scripts);
}

async function saveCurrentScriptEdits(options = {}) {
  const form = currentScriptEditForm();
  if (!form || form.dataset.dirty !== "true") {
    return state.scripts.find((item) => item.id === state.latestScriptId) || null;
  }
  const scriptId = Number(form.dataset.scriptId);
  const saveState = form.querySelector("#scriptEditSaveState");
  const submitButton = form.querySelector("button[type='submit']");
  if (saveState) saveState.textContent = "正在保存修改...";
  if (submitButton) submitButton.disabled = true;
  const payload = formData(form);
  try {
    const script = await api.patch(`/scripts/${scriptId}`, payload);
    updateScriptInState(script);
    renderTitleSuggestions(script);
    renderScriptDetail(script);
    if (!options.silent) toast("脚本修改已保存");
    return script;
  } finally {
    if (submitButton) submitButton.disabled = false;
  }
}

function taskStatusLabel(status) {
  return {
    draft: "草稿",
    queued: "已创建",
    running: "生成中",
    needs_review: "待审核",
    approved: "已通过",
    rejected: "已驳回",
    failed: "失败",
  }[status] || status;
}

function analysisStatusLabel(status) {
  return {
    draft: "草稿",
    queued: "待拆解",
    running: "拆解中",
    needs_review: "已拆解待采纳",
    approved: "已采纳",
    rejected: "不采用",
    failed: "失败",
  }[status] || status;
}

function transcriptionStatusLabel(status) {
  return {
    draft: "草稿",
    queued: "待转写",
    running: "转写中",
    needs_review: "已转写",
    approved: "已确认",
    rejected: "不采用",
    failed: "失败",
  }[status] || status;
}

function taskStatusClass(status) {
  return {
    draft: "taskStatusDraft",
    queued: "taskStatusQueued",
    running: "taskStatusRunning",
    needs_review: "taskStatusReview",
    approved: "taskStatusApproved",
    rejected: "taskStatusRejected",
    failed: "taskStatusFailed",
  }[status] || "";
}

function subtitleStyleLabel(style) {
  return {
    auto: "AI 自动",
    business: "商务清晰",
    viral: "爆款大字",
    digital_human: "数字人口播",
    tutorial: "教程说明",
    minimal: "极简底栏",
  }[style] || style || "AI 自动";
}

function subtitleStatusLabel(status) {
  return {
    pending: "待生成字幕",
    running: "字幕生成中",
    completed: "已生成字幕",
    failed: "字幕失败",
    skipped: "未烧录字幕",
    disabled: "未启用字幕",
  }[status] || status || "待生成字幕";
}

function taskProgress(task) {
  if (task.status === "running" && Number(task.segment_count || 0) > 1) {
    const completed = Number(task.completed_segments || 0);
    const total = Number(task.segment_count || 1);
    return Math.min(84, 25 + Math.round((completed / total) * 58));
  }
  return {
    draft: 8,
    queued: 25,
    running: 60,
    needs_review: 85,
    approved: 100,
    rejected: 100,
    failed: 100,
  }[task.status] || 0;
}

function taskSegmentMeta(task) {
  const total = Number(task.segment_count || 1);
  const modeLabel = productionModeLabel(task.production_mode);
  if (total <= 1) return modeLabel;
  const completed = Number(task.completed_segments || 0);
  const mode = task.generation_mode === "long" ? "长视频" : "分段视频";
  return `${modeLabel} · ${mode} · ${completed}/${total} 段`;
}

function taskTargetPlatformLabel(task) {
  return platformLabel(task.target_platform || "douyin");
}

function humanName(id) {
  if (!id) return "不露脸";
  const human = state.digitalHumans.find((item) => item.id === id);
  return human ? human.name : `#${id}`;
}

function scriptName(id) {
  const script = state.scripts.find((item) => item.id === id);
  return script ? script.hook : `脚本 #${id}`;
}

function taskVideoSrc(task) {
  const outputPath = task.captioned_output_path || task.output_path;
  if (!outputPath || outputPath.startsWith("mock://")) return "";
  if (outputPath.startsWith("http")) return outputPath;
  return authenticatedMediaUrl(`/api/video-tasks/${task.id}/output`);
}

function taskActionState(task) {
  const hasOutput = Boolean(task.captioned_output_path || task.output_path);
  const isRunning = task.status === "running";
  return {
    canSelectForRun: !hasOutput && ["draft", "queued", "failed"].includes(task.status),
    canPreview: Boolean(taskVideoSrc(task)),
    canRun: !hasOutput && ["draft", "queued", "failed"].includes(task.status),
    canApprove: task.status === "needs_review" && hasOutput,
    canPublish: task.status === "approved" && hasOutput,
    canDeleteOutput: hasOutput && !isRunning,
    canDeleteTask: !isRunning,
    runLabel: isRunning ? "生成中" : hasOutput ? "已生成" : "开始生成",
    previewLabel: hasOutput ? (taskVideoSrc(task) ? "成片预览" : "不可预览") : "暂无成片",
  };
}

function actionErrorMessage(action) {
  return {
    "run-video-task": "这个任务当前不能开始生成，请先删除成片或检查任务状态",
    "approve-video-task": "只有待审核且已生成成片的任务才能审核通过",
    "prepare-publish": "只有已审核通过的成片才能准备发布",
    "delete-task-output": "当前不能删除成片，可能任务正在生成或还没有成片",
    "delete-video-task": "当前不能删除任务，可能任务正在生成",
  }[action] || "操作失败，请刷新后再试";
}

function taskActionButtons(task, options = {}) {
  const actions = taskActionState(task);
  const button = (action, label, className = "secondary", disabled = false) => (
    `<button type="button" class="${className}" data-action="${action}" data-id="${task.id}" ${disabled ? "disabled aria-disabled=\"true\"" : ""}>${label}</button>`
  );
  const buttons = options.includeDetail === false ? [] : [button("view-video-task", "详情")];
  if (task.status === "running") {
    buttons.push(button("run-video-task", "生成中", "", true));
  } else if (actions.canRun) {
    buttons.push(button("run-video-task", "生成"));
  }
  if (actions.canApprove) buttons.push(button("approve-video-task", "审核通过"));
  if (actions.canPublish) buttons.push(button("prepare-publish", "准备发布"));
  if (actions.canDeleteOutput) buttons.push(button("delete-task-output", "删除成片"));
  if (actions.canDeleteTask) buttons.push(button("delete-video-task", "删除任务", "danger"));
  return buttons.join("");
}

function updateText(selector, value) {
  const target = document.querySelector(selector);
  if (target) target.textContent = String(value);
}

function renderTaskWorkflowStats() {
  const tasks = state.videoTasks || [];
  updateText("#taskFlowScriptCount", (state.scripts || []).length);
  updateText("#taskFlowRunningCount", tasks.filter((task) => ["queued", "running"].includes(task.status)).length);
  updateText("#taskFlowReviewCount", tasks.filter((task) => task.status === "needs_review").length);
  updateText("#taskFlowReadyCount", tasks.filter((task) => task.status === "approved").length);
}

function scriptTaskCount(scriptId) {
  return (state.videoTasks || []).filter((task) => Number(task.script_id) === Number(scriptId)).length;
}

function renderTaskScriptTable(scripts = state.scripts) {
  const target = document.querySelector("#taskScriptList");
  if (!target) return;
  if (!scripts.length) {
    target.innerHTML = `<div class="item">还没有已生成脚本</div>`;
    return;
  }
  state.listPages.taskScripts = state.taskScriptPage || state.listPages.taskScripts || 1;
  const pageInfo = pagedItems("taskScripts", scripts);
  state.taskScriptPage = pageInfo.page;
  const pageScripts = pageInfo.items;
  target.innerHTML = `
    <table class="taskTable compactTable scriptTaskTable">
      <thead>
        <tr>
          <th>脚本</th>
          <th>平台/时长</th>
          <th>视频任务</th>
          <th>创建时间</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        ${pageScripts.map((script) => `
          <tr>
            <td class="scriptTitleCell">
              <strong title="${escapeHtml(script.hook || "未命名脚本")}">#${script.id} ${escapeHtml(script.hook || "未命名脚本")}</strong>
              <span>${escapeHtml((script.hashtags || "").split(/\s+/).filter(Boolean).slice(0, 3).join(" ") || "未设置标签")}</span>
            </td>
            <td>
              <strong>${platformLabel(script.target_platform || "douyin")}</strong>
              <div class="recordMeta">${Number(script.duration_seconds || 30)} 秒</div>
            </td>
            <td><strong>${scriptTaskCount(script.id)}</strong> 个</td>
            <td>${formatDateTime(script.created_at)}</td>
            <td>
              <div class="tableActions">
                <button type="button" class="secondary" data-action="view-task-script" data-id="${script.id}">详情</button>
                <button type="button" data-action="create-task-from-script" data-id="${script.id}">生成视频</button>
              </div>
            </td>
          </tr>
        `).join("")}
      </tbody>
    </table>
    ${pagerHtml("taskScripts", pageInfo)}
  `;
}

function openTaskScriptDetailDrawer(scriptId) {
  const drawer = document.querySelector("#taskDetailDrawer");
  const title = document.querySelector("#taskDetailTitle");
  const eyebrow = document.querySelector("#taskDetailEyebrow");
  const content = document.querySelector("#taskDetailContent");
  if (!drawer || !title || !eyebrow || !content) return;
  const script = state.scripts.find((item) => Number(item.id) === Number(scriptId));
  if (!script) {
    toast("没有找到这条脚本");
    return;
  }
  title.textContent = `脚本 #${script.id}`;
  eyebrow.textContent = "Script Detail";
  content.innerHTML = `
    <div class="drawerSummary">
      <div class="assetMetaLine">
        <span class="status">${platformLabel(script.target_platform || "douyin")}</span>
        <span class="status">${Number(script.duration_seconds || 30)} 秒</span>
        <span class="status">${scriptTaskCount(script.id)} 个视频任务</span>
      </div>
      <div class="assetDetailGrid">
        <div><span>开头钩子</span><strong>${escapeHtml(script.hook || "-")}</strong></div>
        <div><span>创建时间</span><strong>${formatDateTime(script.created_at)}</strong></div>
        <div><span>标签</span><strong>${escapeHtml(script.hashtags || "-")}</strong></div>
        <div><span>合规提醒</span><strong>${escapeHtml(script.compliance_notes || "-")}</strong></div>
      </div>
    </div>
    <div class="analysisGrid drawerAnalysisGrid">
      <div><h3>口播稿</h3><pre>${escapeHtml(script.voiceover || "暂无")}</pre></div>
      <div><h3>分镜/画面</h3><pre>${escapeHtml(script.storyboard || "暂无")}</pre></div>
      <div><h3>视频提示词</h3><pre>${escapeHtml(script.seedance_prompt || "暂无")}</pre></div>
      <div><h3>标题建议</h3><pre>${escapeHtml(script.title_options || "暂无")}</pre></div>
    </div>
    <div class="drawerActions">
      <button type="button" data-action="create-task-from-script" data-id="${script.id}">生成视频</button>
      <button type="button" class="secondary" data-action="edit-script-from-task-drawer" data-id="${script.id}">去编辑脚本</button>
    </div>
  `;
  drawer.classList.remove("hiddenPanel");
  drawer.setAttribute("aria-hidden", "false");
}

async function createTaskFromTaskScript(scriptId, button) {
  const script = state.scripts.find((item) => Number(item.id) === Number(scriptId));
  if (!script) {
    toast("没有找到这条脚本");
    return;
  }
  const originalText = button?.textContent || "";
  if (button) {
    button.disabled = true;
    button.textContent = "进入队列...";
  }
  const form = document.querySelector("#taskForm");
  let productionMode = form?.querySelector("[name='production_mode']")?.value || "dynamic_explainer";
  const humanValue = form?.querySelector("[name='digital_human_id']")?.value || "";
  const exportProfile = form?.querySelector("[name='export_profile']")?.value || defaultExportProfileForPlatform(script.target_platform || "douyin");
  if (["digital_human", "talking_head_template"].includes(productionMode) && !humanValue) {
    productionMode = "dynamic_explainer";
  }
  try {
    const payload = {
      production_mode: productionMode,
      target_platform: script.target_platform || "douyin",
      export_profile: exportProfile,
      subtitle_enabled: true,
      subtitle_style: form?.querySelector("[name='subtitle_style']")?.value || "auto",
    };
    if (humanValue) payload.digital_human_id = Number(humanValue);
    const endpoint = productionMode === "material_mix" ? "video-task" : "auto-video-task";
    const task = await api.post(`/scripts/${script.id}/${endpoint}`, payload);
    state.latestTaskId = task.id;
    toast(productionMode === "material_mix" ? `已创建素材方案任务 #${task.id}` : `已进入自动生成队列 #${task.id}`);
    closeTaskDetailDrawer();
    await refresh();
    if (productionMode === "material_mix") {
      await openTaskDetailDrawer(task.id);
    }
  } catch (error) {
    toast(apiErrorMessage(error, "创建视频任务失败"));
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = originalText;
    }
  }
}

async function openTaskDetailDrawer(taskId) {
  const drawer = document.querySelector("#taskDetailDrawer");
  const title = document.querySelector("#taskDetailTitle");
  const eyebrow = document.querySelector("#taskDetailEyebrow");
  const content = document.querySelector("#taskDetailContent");
  if (!drawer || !title || !eyebrow || !content) return;
  const task = state.videoTasks.find((item) => Number(item.id) === Number(taskId));
  if (!task) {
    toast("没有找到这个视频任务");
    return;
  }
  const script = state.scripts.find((item) => Number(item.id) === Number(task.script_id));
  const videoSrc = taskVideoSrc(task);
  title.textContent = `视频任务 #${task.id}`;
  eyebrow.textContent = "Video Task";
  content.innerHTML = `
    <div class="drawerSummary">
      <div class="assetMetaLine">
        <span class="status taskStatus ${taskStatusClass(task.status)}">${taskStatusLabel(task.status)}</span>
        <span class="status">${productionModeLabel(task.production_mode)}</span>
        <span class="status">${escapeHtml(exportProfileMeta(task))}</span>
        <span class="status">${subtitleStyleLabel(task.subtitle_style)}</span>
        <span class="status taskStatus ${task.subtitle_status === "failed" ? "taskStatusFailed" : task.subtitle_status === "completed" ? "taskStatusApproved" : "taskStatusQueued"}">${subtitleStatusLabel(task.subtitle_status)}</span>
      </div>
      <div class="assetDetailGrid">
        <div><span>脚本</span><strong>#${task.script_id} ${escapeHtml(script?.hook || "")}</strong></div>
        <div><span>数字人</span><strong>${escapeHtml(humanName(task.digital_human_id))}</strong></div>
        <div><span>目标平台</span><strong>${escapeHtml(taskTargetPlatformLabel(task))}</strong></div>
        <div><span>字幕成片</span><strong>${task.captioned_output_path ? "已生成" : subtitleStatusLabel(task.subtitle_status)}</strong></div>
        <div><span>更新时间</span><strong>${formatDateTime(task.updated_at)}</strong></div>
      </div>
      ${task.error_message ? `<div class="errorText">${escapeHtml(task.error_message)}</div>` : ""}
    </div>
    <section class="taskDrawerVideoPanel">
      <h3>成片视频</h3>
      ${videoSrc ? `<video class="taskOutputPreviewVideo drawerVideo" src="${videoSrc}" controls preload="metadata"></video>` : `<div class="item">这个任务还没有生成可预览的视频。</div>`}
    </section>
    ${script ? `
      <div class="analysisGrid drawerAnalysisGrid">
        <div><h3>口播稿</h3><pre>${escapeHtml(script.voiceover || "暂无")}</pre></div>
        <div><h3>分镜/画面</h3><pre>${escapeHtml(script.storyboard || "暂无")}</pre></div>
      </div>
    ` : ""}
    <div id="taskSegmentDetailList" class="taskSegmentDetailList"></div>
    <div class="drawerActions">
      ${taskActionButtons(task, { includeDetail: false })}
    </div>
  `;
  drawer.classList.remove("hiddenPanel");
  drawer.setAttribute("aria-hidden", "false");
  try {
    const segments = await api.get(`/video-tasks/${task.id}/segments`);
    renderTaskSegmentsInDrawer(segments);
  } catch {
    renderTaskSegmentsInDrawer([]);
  }
}

function renderTaskSegmentsInDrawer(segments) {
  const target = document.querySelector("#taskSegmentDetailList");
  if (!target) return;
  if (!segments?.length) {
    target.innerHTML = "";
    return;
  }
  target.innerHTML = `
    <details class="analysisTimelineDetails" open>
      <summary>分段生成明细</summary>
      <table class="compactTable analysisTimelineTable">
        <thead>
          <tr>
            <th>段落</th>
            <th>标题</th>
            <th>时长</th>
            <th>素材方案</th>
            <th>状态</th>
          </tr>
        </thead>
        <tbody>
          ${segments.map((segment) => `
            <tr>
              <td>#${Number(segment.segment_index || 0) + 1}</td>
              <td>${escapeHtml(segment.title || "-")}</td>
              <td>${Number(segment.duration_seconds || 0)} 秒</td>
              <td>${renderSegmentMaterialControl(segment)}</td>
              <td><span class="status taskStatus ${taskStatusClass(segment.status)}">${taskStatusLabel(segment.status)}</span></td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </details>
  `;
}

function eligibleSceneMaterials() {
  return state.materials.filter((material) => (
    ["image", "product", "portrait", "video"].includes(material.kind)
    && ["owned", "licensed"].includes(material.copyright_status)
  ));
}

function renderSegmentMaterialControl(segment) {
  const materials = eligibleSceneMaterials();
  const selectedId = String(segment.material_id || "");
  const options = [
    `<option value="">用 Seedance 补镜头</option>`,
    ...materials.map((material) => (
      `<option value="${material.id}" ${String(material.id) === selectedId ? "selected" : ""}>#${material.id} ${escapeHtml(material.name)} · ${materialKindLabel(material.kind)}</option>`
    )),
  ].join("");
  return `
    <div class="segmentMaterialControl">
      <select data-segment-material-select="${segment.id}">${options}</select>
      <button type="button" class="secondary compactButton" data-action="assign-segment-material" data-id="${segment.id}" data-task-id="${segment.video_task_id}">保存</button>
      <div class="recordMeta">${escapeHtml(segment.material_match_notes || "未绑定素材，生成时会用 AI 补镜头。")}</div>
    </div>
  `;
}

function closeTaskDetailDrawer() {
  const drawer = document.querySelector("#taskDetailDrawer");
  if (!drawer) return;
  drawer.classList.add("hiddenPanel");
  drawer.setAttribute("aria-hidden", "true");
}

function renderTaskOutputPreview(task) {
  const panel = document.querySelector("#taskPreviewPanel");
  const meta = document.querySelector("#taskPreviewMeta");
  const content = document.querySelector("#taskPreviewContent");
  if (!panel || !meta || !content) return;
  if (!task) {
    panel.classList.add("hiddenPanel");
    content.innerHTML = "";
    return;
  }
  const videoSrc = taskVideoSrc(task);
  panel.classList.remove("hiddenPanel");
  meta.textContent = `任务 #${task.id} · ${taskStatusLabel(task.status)} · ${taskSegmentMeta(task)} · ${exportProfileMeta(task)}`;
  content.innerHTML = videoSrc
    ? `<video class="taskOutputPreviewVideo" src="${videoSrc}" controls preload="metadata"></video>`
    : `<div class="item">这个任务还没有可预览的成片。</div>`;
}

function renderTaskCompact(tasks) {
  const target = document.querySelector("#taskList");
  if (!target) return;
  if (!tasks.length) {
    target.innerHTML = `<div class="item">还没有视频任务</div>`;
    return;
  }
  target.innerHTML = tasks
    .slice(0, 5)
    .map(
      (task) => `
        <div class="item">
          <strong>任务 #${task.id}</strong>
          <div>${escapeHtml(scriptName(task.script_id)).slice(0, 54)}</div>
          <span class="status taskStatus ${taskStatusClass(task.status)}">${taskStatusLabel(task.status)}</span>
          <div class="recordMeta">${taskSegmentMeta(task)}</div>
        </div>
      `,
    )
    .join("");
}

function renderTaskTable(tasks) {
  const target = document.querySelector("#taskListTasks");
  if (!target) return;
  if (!tasks.length) {
    target.innerHTML = `<div class="item">还没有视频任务</div>`;
    return;
  }
  const pageInfo = pagedItems("taskTable", tasks);
  target.innerHTML = `
    <table class="taskTable compactTable">
      <thead>
        <tr>
          <th>选择</th>
          <th>任务</th>
          <th>脚本</th>
          <th>数字人</th>
          <th>方式</th>
          <th>规格</th>
          <th>字幕</th>
          <th>进度</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        ${pageInfo.items
          .map((task) => {
            const progress = taskProgress(task);
            const videoSrc = taskVideoSrc(task);
            const actions = taskActionState(task);
            return `
              <tr>
                <td><input type="checkbox" class="taskSelectCheckbox" value="${task.id}" ${actions.canSelectForRun ? "" : "disabled"} /></td>
                <td>
                  <strong>#${task.id}</strong>
                  <span class="status taskStatus ${taskStatusClass(task.status)}">${taskStatusLabel(task.status)}</span>
                </td>
                <td>${escapeHtml(scriptName(task.script_id)).slice(0, 72)}</td>
                <td>${escapeHtml(humanName(task.digital_human_id))}</td>
                <td>${productionModeLabel(task.production_mode)}</td>
                <td>
                  <strong class="taskExportPill">${escapeHtml(taskTargetPlatformLabel(task))}</strong>
                  <div class="recordMeta">${escapeHtml(exportProfileMeta(task))}</div>
                </td>
                <td>
                  <strong>${escapeHtml(subtitleStyleLabel(task.subtitle_style))}</strong>
                  <div class="recordMeta">${escapeHtml(subtitleStatusLabel(task.subtitle_status))}</div>
                </td>
                <td>
                  <div class="progressBar"><span style="width:${progress}%"></span></div>
                  <div class="recordMeta">${progress}% · ${taskStatusLabel(task.status)}</div>
                  <div class="recordMeta">${taskSegmentMeta(task)}</div>
                  ${task.error_message ? `<div class="errorText">${escapeHtml(task.error_message)}</div>` : ""}
                </td>
                <td>
                  <div class="tableActions">
                    ${taskActionButtons(task)}
                  </div>
                </td>
              </tr>
            `;
          })
          .join("")}
      </tbody>
    </table>
    ${pagerHtml("taskTable", pageInfo)}
  `;
}

function renderTasks(tasks) {
  state.videoTasks = tasks;
  if (tasks.length) {
    state.latestTaskId = tasks[0].id;
  }
  renderTaskWorkflowStats();
  renderTaskScriptTable(state.scripts);
  renderOverviewActivity();
  renderTaskTable(tasks);
  if (state.previewTaskId) {
    const task = tasks.find((item) => item.id === state.previewTaskId);
    renderTaskOutputPreview(task);
  }
}

function renderPublishRecords(records) {
  const target = document.querySelector("#publishRecordList");
  if (!target) return;
  renderPublishStatusBoard(records);
  if (!records.length) {
    target.innerHTML = `<div class="item">还没有发布记录</div>`;
    return;
  }
  const pageInfo = pagedItems("publishRecords", records);
  target.innerHTML = pageInfo.items
    .map((record) => {
      const accountOptions = state.platformAccounts
        .map((account) => {
          const selected = account.id === record.platform_account_id ? "selected" : "";
          const defaultText = account.is_default ? " · 默认" : "";
          return `<option value="${account.id}" ${selected}>${escapeHtml(account.platform)} · ${escapeHtml(account.account_name)}${defaultText}</option>`;
        })
        .join("");
      return `
        <div class="item publishRecord">
          <div class="itemHeader">
            <strong>发布 #${record.id} · 视频任务 #${record.video_task_id}</strong>
            <span class="status">${publishStatusLabel(record.publish_status)}</span>
          </div>
          <form class="publishEditForm" data-id="${record.id}">
            <div class="formGrid">
              <label>标题<input name="title" value="${escapeHtml(record.title)}" /></label>
              <label>平台账号
                <select name="platform_account_id">
                  <option value="">不指定账号</option>
                  ${accountOptions}
                </select>
              </label>
              <label>话题标签<input name="hashtags" value="${escapeHtml(record.hashtags || "")}" /></label>
              <label>计划发布时间<input name="scheduled_at" type="datetime-local" value="${toDateTimeInput(record.scheduled_at)}" /></label>
            </div>
            <label>发布文案<textarea name="caption">${escapeHtml(record.caption || "")}</textarea></label>
            <div class="recordMeta">
              <span>${escapeHtml(record.platform)} · ${escapeHtml(record.account_name || "未指定账号")}</span>
              <span>${record.published_at ? `已发布：${escapeHtml(record.published_at)}` : "待发布"}</span>
            </div>
            <div class="itemActions publishActions">
              <button type="button" data-action="save-publish" data-id="${record.id}">保存修改</button>
              <button type="button" class="secondary" data-action="mark-published" data-id="${record.id}">标记已发布</button>
              <button type="button" class="secondary" data-action="fail-publish" data-id="${record.id}">标记失败</button>
              <button type="button" class="secondary" data-action="cancel-publish" data-id="${record.id}">取消发布</button>
            </div>
          </form>
        </div>
      `;
    })
    .join("") + pagerHtml("publishRecords", pageInfo);
}

function renderPublishStatusBoard(records) {
  const target = document.querySelector("#publishStatusBoard");
  if (!target) return;
  const groups = {
    prepared: records.filter((item) => item.publish_status === "prepared").length,
    published: records.filter((item) => item.publish_status === "published").length,
    failed: records.filter((item) => item.publish_status === "failed").length,
    canceled: records.filter((item) => item.publish_status === "canceled").length,
  };
  target.innerHTML = Object.entries(groups)
    .map(([status, count]) => `
      <div class="statusCard">
        <strong>${count}</strong>
        <span>${publishStatusLabel(status)}</span>
      </div>
    `)
    .join("");
}

function publishStatusLabel(status) {
  return {
    prepared: "待发布",
    published: "已发布",
    failed: "发布失败",
    canceled: "已取消",
  }[status] || status;
}

function renderPlatformAccounts(accounts) {
  const target = document.querySelector("#platformAccountList");
  if (!target) return;
  if (!accounts.length) {
    target.innerHTML = `<div class="item">还没有平台账号</div>`;
    return;
  }
  const pageInfo = pagedItems("platformAccounts", accounts);
  target.innerHTML = pageInfo.items
    .map(
      (account) => `
        <div class="item">
          <div class="itemHeader">
            <strong>#${account.id} ${escapeHtml(account.account_name)}</strong>
            <span class="status">${account.is_default ? "默认账号" : escapeHtml(account.status)}</span>
          </div>
          <div>${escapeHtml(account.platform)} · ${escapeHtml(account.owner || "未指定负责人")}</div>
          <div class="itemActions accountActions">
            <button type="button" class="secondary" data-action="set-default-account" data-id="${account.id}">设为默认</button>
          </div>
        </div>
      `,
    )
    .join("") + pagerHtml("platformAccounts", pageInfo);
}

function materialKindLabel(kind) {
  return {
    portrait: "数字人头像",
    avatar_source: "数字人口播视频源",
    product: "产品素材",
    image: "图片",
    video: "视频",
    reference: "参考素材",
  }[kind] || kind;
}

function materialCopyrightLabel(status) {
  return {
    owned: "自有版权",
    licensed: "授权可用",
    reference_only: "仅作参考",
  }[status] || status || "未标记";
}

function humanStyleLabel(style) {
  return {
    business: "商务",
    ai_recommended: "AI 推荐",
    realistic: "写实",
    casual: "自然",
  }[style] || String(style || "未设置").replace(/_/g, " ");
}

function isImageMaterial(material) {
  return ["portrait", "product", "image"].includes(material.kind);
}

function isVideoMaterial(material) {
  return ["avatar_source", "video"].includes(material.kind) || (material.kind === "reference" && material.file_path);
}

function isReferenceMaterial(material) {
  return ["avatar_source", "video", "reference"].includes(material.kind);
}

function renderMaterialPreview(material, className = "materialThumb") {
  const src = authenticatedMediaUrl(`/api/materials/${material.id}/preview`);
  if (isImageMaterial(material)) {
    return `<img class="${className}" src="${src}" alt="${escapeHtml(material.name)}" />`;
  }
  if (isVideoMaterial(material)) {
    return `<video class="${className}" src="${src}" controls preload="metadata"></video>`;
  }
  if (material.kind === "reference" && material.source_url) {
    return `<div class="${className} materialFile">链接</div>`;
  }
  return `<div class="${className} materialFile">文件</div>`;
}

function assetStateLabel(hasValue, readyLabel, pendingLabel) {
  return `<span class="assetState ${hasValue ? "ready" : "pending"}">${hasValue ? readyLabel : pendingLabel}</span>`;
}

function volcengineAuthStatusLabel(status) {
  return {
    not_started: "未认证",
    pending: "认证中",
    callback_received: "已回调",
    active: "已通过",
    failed: "未通过",
  }[status || "not_started"] || status || "未认证";
}

function volcengineAuthStateLabel(human) {
  const active = human?.volcengine_auth_status === "active" || Boolean(human?.volcengine_asset_group_id);
  return `<span class="assetState ${active ? "ready" : "pending"}">火山真人${volcengineAuthStatusLabel(human?.volcengine_auth_status)}</span>`;
}

function volcengineCallbackUrl() {
  return `${window.location.origin}/api/volcengine/portrait-auth/callback`;
}

function materialSummaryPreview(material) {
  const src = authenticatedMediaUrl(`/api/materials/${material.id}/preview`);
  if (isImageMaterial(material)) {
    return `<img class="assetMiniThumb" src="${src}" alt="${escapeHtml(material.name)}" />`;
  }
  if (isVideoMaterial(material)) {
    return `<div class="assetMiniThumb mediaIcon">视频</div>`;
  }
  if (material.kind === "reference" && material.source_url) {
    return `<div class="assetMiniThumb mediaIcon">链接</div>`;
  }
  return `<div class="assetMiniThumb mediaIcon">文件</div>`;
}

function renderMaterials(materials) {
  const target = document.querySelector("#materialList");
  if (!target) return;
  renderMaterialSelects(materials);
  if (!materials.length) {
    target.innerHTML = `<div class="item">还没有上传素材</div>`;
    return;
  }
  const pageInfo = pagedItems("materials", materials);
  target.innerHTML = `
    <table class="settingsTable compactTable assetListTable">
      <thead>
        <tr>
          <th>素材</th>
          <th>类型</th>
          <th>状态</th>
          <th>版权 / 标签</th>
          <th>创建时间</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        ${pageInfo.items.map((material) => `
          <tr>
            <td>
              <strong>#${material.id} ${escapeHtml(material.name)}</strong>
              <div class="recordMeta">${escapeHtml(material.source_url || "未上传云端地址")}</div>
            </td>
            <td><span class="status subtle">${materialKindLabel(material.kind)}</span></td>
            <td>${assetStateLabel(Boolean(material.source_url), "云端已就绪", "待补传")}</td>
            <td>
              <span class="status subtle">${escapeHtml(materialCopyrightLabel(material.copyright_status))}</span>
              <div class="recordMeta">${escapeHtml(material.tags || "未打标签")}</div>
            </td>
            <td>${formatDateTime(material.created_at)}</td>
            <td>
              <div class="tableActions">
                <button type="button" class="secondary" data-action="view-material-detail" data-id="${material.id}">详情</button>
                ${material.source_url ? `<button type="button" class="secondary" data-action="copy-material-url" data-url="${escapeHtml(material.source_url)}">复制地址</button>` : `<button type="button" class="secondary" data-action="remote-upload-material" data-id="${material.id}">补传</button>`}
                <button type="button" class="danger" data-action="delete-material" data-id="${material.id}">删除</button>
              </div>
            </td>
          </tr>
        `).join("")}
      </tbody>
    </table>
    ${pagerHtml("materials", pageInfo)}
  `;
}

function renderMaterialSelects(materials) {
  const portraitSelect = document.querySelector("#portraitMaterialSelect");
  const sourceVideoSelect = document.querySelector("#sourceVideoMaterialSelect");
  const analysisSelect = document.querySelector("#analysisMaterialSelect");
  if (portraitSelect) {
    const current = portraitSelect.value;
    const portraits = materials.filter((item) => item.kind === "portrait" || item.kind === "image");
    portraitSelect.innerHTML = `<option value="">先上传头像素材</option>${portraits
      .map((item) => `<option value="${item.id}">#${item.id} ${escapeHtml(item.name)}</option>`)
      .join("")}`;
    portraitSelect.value = current || state.latestPortraitId || "";
  }
  if (sourceVideoSelect) {
    const current = sourceVideoSelect.value;
    const sources = materials.filter((item) => ["avatar_source", "video"].includes(item.kind));
    sourceVideoSelect.innerHTML = `<option value="">可选，先上传带语音的视频源</option>${sources
      .map((item) => `<option value="${item.id}">#${item.id} ${escapeHtml(item.name)} · ${materialKindLabel(item.kind)}</option>`)
      .join("")}`;
    sourceVideoSelect.value = current || state.latestSourceVideoId || "";
  }
  if (analysisSelect) {
    const current = analysisSelect.value;
    const references = materials.filter(isReferenceMaterial);
    analysisSelect.innerHTML = `<option value="">先上传或选择参考素材</option>${references
      .map((item) => `<option value="${item.id}">#${item.id} ${escapeHtml(item.name)} · ${materialKindLabel(item.kind)}</option>`)
      .join("")}`;
    const latestReference = materials.find(isReferenceMaterial);
    analysisSelect.value = current || (latestReference ? latestReference.id : "");
    renderAnalysisMaterialPreview();
  }
}

function renderAnalysisMaterialPreview() {
  const select = document.querySelector("#analysisMaterialSelect");
  const target = document.querySelector("#analysisMaterialPreview");
  if (!select || !target) return;
  const material = state.materials.find((item) => String(item.id) === String(select.value));
  if (!material) {
    target.innerHTML = `<div class="item">选择参考素材后可预览</div>`;
    return;
  }
  target.innerHTML = `
    <div class="analysisPreviewCard">
      ${renderMaterialPreview(material, "analysisPreviewMedia")}
      <div>
        <strong>#${material.id} ${escapeHtml(material.name)}</strong>
        <div class="recordMeta">${materialKindLabel(material.kind)} · ${escapeHtml(material.tags || "未打标签")}</div>
        <div class="recordMeta">${material.file_path ? "本地文件已就绪，可以拆解" : "仅保存链接，需要先解析下载或上传源文件"}</div>
      </div>
    </div>
  `;
}

function latestAnalysisForMaterial(materialId) {
  return state.videoAnalyses.find((analysis) => Number(analysis.material_id) === Number(materialId));
}

function referenceAnalysisActionLabel(analysis) {
  if (!analysis) return "详情";
  if (analysis.status === "needs_review") return "查看/采纳";
  if (analysis.status === "approved") return "查看详情";
  if (analysis.status === "failed") return "查看失败";
  return "查看进度";
}

function latestTranscriptionForMaterial(materialId) {
  return state.transcriptions.find((task) => Number(task.material_id) === Number(materialId));
}

function setReferenceTab(tabName) {
  const nextTab = ["history", "current", "import"].includes(tabName) ? tabName : "history";
  state.currentReferenceTab = nextTab;
  document.querySelectorAll("[data-reference-tab]").forEach((button) => {
    const active = button.dataset.referenceTab === nextTab;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
  });
  document.querySelectorAll("[data-reference-panel]").forEach((panel) => {
    panel.classList.toggle("active", panel.dataset.referencePanel === nextTab);
  });
}

function updateReferenceHistoryCount(materials = state.materials) {
  const target = document.querySelector("#referenceHistoryCount");
  if (!target) return;
  target.textContent = String(materials.filter(isReferenceMaterial).length);
}

function renderReferenceMaterials(materials = state.materials) {
  const target = document.querySelector("#referenceMaterialList");
  if (!target) return;
  const references = materials.filter(isReferenceMaterial);
  updateReferenceHistoryCount(materials);
  setReferenceTab(state.currentReferenceTab || "history");
  if (!references.length) {
    target.innerHTML = `<div class="item">还没有参考素材。粘贴视频链接后会自动进入这里。</div>`;
    syncReferencePlatformHint();
    return;
  }
  const pageInfo = pagedItems("referenceMaterials", references);
  target.innerHTML = `
    <div class="settingsTableWrap">
      <table class="settingsTable compactTable referenceMaterialTable">
        <thead>
          <tr>
            <th>参考素材</th>
            <th>类型/标签</th>
            <th>拆解状态</th>
            <th>来源</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          ${pageInfo.items
            .map((material) => {
      const analysis = latestAnalysisForMaterial(material.id);
      const transcript = latestTranscriptionForMaterial(material.id);
      const canAnalyze = Boolean(material.file_path);
      const canGenerateScript = analysis && analysis.status === "approved";
      const selected = String(document.querySelector("#analysisMaterialSelect")?.value || "") === String(material.id);
      const needsUpload = String(material.tags || "").includes("需上传源文件");
      const statusLabel = canAnalyze ? "可拆解" : needsUpload ? "需上传源文件" : "仅链接";
      const hasSourceLink = Boolean(material.source_url);
      return `
              <tr class="${selected ? "selectedReferenceRow" : ""}">
                <td>
              <strong>#${material.id} ${escapeHtml(material.name)}</strong>
                  <div class="recordMeta">${escapeHtml(material.source_url || "未上传云端地址")}</div>
                </td>
                <td>
                  <span class="status subtle">${materialKindLabel(material.kind)}</span>
                  <div class="recordMeta">${escapeHtml(material.tags || "未打标签")}</div>
                </td>
                <td>
                  <span class="status ${canAnalyze ? "successStatus" : "pendingStatus"}">${statusLabel}</span>
                  <div class="recordMeta">
              ${analysis ? `拆解 #${analysis.id} · ${analysisStatusLabel(analysis.status)}` : "未拆解"}
              ${transcript ? ` · 转写 #${transcript.id} · ${transcriptionStatusLabel(transcript.status)}` : ""}
                  </div>
                </td>
                <td>${material.source_url ? "链接素材" : material.file_path ? "本地文件" : "未补源"}</td>
                <td>
                  <div class="tableActions referenceMaterialActions">
              <button type="button" class="secondary" data-action="select-reference-material" data-id="${material.id}">选择</button>
                    <button type="button" class="secondary" data-action="view-reference-material" data-id="${material.id}">详情</button>
              ${!canAnalyze && hasSourceLink ? `<button type="button" data-action="resolve-reference-material" data-id="${material.id}">解析下载</button>` : ""}
              <button type="button" data-action="analyze-reference-material" data-id="${material.id}" ${canAnalyze ? "" : "disabled"}>深度拆解</button>
              <button type="button" class="secondary" data-action="view-reference-analysis" data-id="${analysis ? analysis.id : ""}" ${analysis ? "" : "disabled"}>${referenceAnalysisActionLabel(analysis)}</button>
              <button type="button" class="secondary" data-action="script-from-reference-analysis" data-id="${analysis ? analysis.id : ""}" ${canGenerateScript ? "" : "disabled"}>生成脚本</button>
                    ${material.source_url ? `<button type="button" class="secondary" data-action="open-reference-source" data-url="${escapeHtml(material.source_url)}">原链接</button>` : ""}
                  </div>
                </td>
              </tr>
      `;
    })
            .join("")}
        </tbody>
      </table>
    </div>
    ${pagerHtml("referenceMaterials", pageInfo)}
  `;
  syncReferencePlatformHint();
}

function analysisMetricsHtml(analysis) {
  return `
    <div class="analysisMetrics">
      <span>${Number(analysis.duration_seconds || 0).toFixed(1)} 秒</span>
      <span>${analysis.width || "-"}x${analysis.height || "-"}</span>
      <span>${analysis.scene_count || 0} 个视觉段落</span>
      <span>平均 ${Number(analysis.avg_shot_seconds || 0).toFixed(1)} 秒/段</span>
      <span>${analysis.model_enhanced ? "模型增强" : "本地基础"} · ${Number(analysis.quality_score || 0).toFixed(0)} 分</span>
    </div>
  `;
}

function renderAnalysisDetailDrawer(analysisId) {
  const drawer = document.querySelector("#analysisDetailDrawer");
  const title = document.querySelector("#analysisDetailTitle");
  const content = document.querySelector("#analysisDetailContent");
  if (!drawer || !title || !content) return;
  const analysis = state.videoAnalyses.find((item) => Number(item.id) === Number(analysisId));
  if (!analysis) {
    toast("还没有可查看的拆解详情");
    return;
  }
  const material = state.materials.find((item) => Number(item.id) === Number(analysis.material_id));
  const transcript = latestTranscriptionForMaterial(analysis.material_id);
  const timeline = parseAnalysisTimeline(analysis);
  const canGenerate = analysis.status === "approved";
  const canApprove = analysis.status !== "approved" && analysis.status !== "failed";
  const canReject = analysis.status !== "rejected";
  state.activeAnalysisDetailId = analysis.id;
  title.textContent = `深度拆解 #${analysis.id}${material ? ` · ${material.name}` : ""}`;
  content.innerHTML = `
    <div class="drawerSummary">
      <span class="status taskStatus ${taskStatusClass(analysis.status)}">${analysisStatusLabel(analysis.status)}</span>
      ${analysisMetricsHtml(analysis)}
      <div class="recordMeta">审核入口在这里：管理员或审核人员确认是否采纳为后续原创脚本模板；这不是成片发布审核。</div>
      ${analysis.quality_summary ? `<div class="analysisQuality">${escapeHtml(analysis.quality_summary)}</div>` : ""}
      ${analysis.error_message ? `<div class="errorText">${escapeHtml(analysis.error_message)}</div>` : ""}
      <div class="referenceMaterialActions drawerActions">
        <button type="button" data-action="approve-reference-analysis" data-id="${analysis.id}" ${canApprove ? "" : "disabled"}>采纳为模板</button>
        <button type="button" class="secondary" data-action="reject-reference-analysis" data-id="${analysis.id}" ${canReject ? "" : "disabled"}>不采用</button>
        <button type="button" data-action="script-from-drawer-analysis" data-id="${analysis.id}" ${canGenerate ? "" : "disabled"}>生成原创脚本</button>
        ${material?.source_url ? `<a class="buttonLike ghostButton" href="${escapeHtml(material.source_url)}" target="_blank" rel="noreferrer">打开原链接</a>` : ""}
      </div>
    </div>
    ${analysis.dense_contact_sheet_path ? `<img class="videoAnalysisSheet drawerSheet" src="${authenticatedMediaUrl(`/api/video-analyses/${analysis.id}/dense-contact-sheet`)}" alt="深度拆解抽帧图" />` : ""}
    <div class="analysisGrid drawerAnalysisGrid">
      <div><h3>脚本策划</h3><pre>${escapeHtml(analysis.script_analysis || "运行后生成")}</pre></div>
      <div><h3>拍摄方式</h3><pre>${escapeHtml(analysis.shooting_analysis || "运行后生成")}</pre></div>
      <div><h3>剪辑方式</h3><pre>${escapeHtml(analysis.editing_analysis || "运行后生成")}</pre></div>
      <div><h3>可复用模板</h3><pre>${escapeHtml(analysis.reusable_template || "运行后生成")}</pre></div>
    </div>
    ${timeline.length ? `
      <details class="analysisTimelineDetails" open>
        <summary>镜头时间轴</summary>
        <table class="compactTable analysisTimelineTable">
          <thead>
            <tr>
              <th>时间</th>
              <th>画面角色</th>
              <th>脚本作用</th>
              <th>复用方式</th>
            </tr>
          </thead>
          <tbody>
            ${timeline.slice(0, 36).map((item) => `
              <tr>
                <td>${Number(item.start_second || 0).toFixed(1)}-${Number(item.end_second || 0).toFixed(1)}s</td>
                <td>${escapeHtml(item.visual_role || "-")}</td>
                <td>${escapeHtml(item.script_function || "-")}</td>
                <td>${escapeHtml(item.reuse_instruction || "-")}</td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      </details>
    ` : ""}
    ${analysis.reuse_notes ? `<pre class="analysisReuseNotes">${escapeHtml(analysis.reuse_notes)}</pre>` : ""}
    ${transcript?.transcript ? `
      <details class="analysisTimelineDetails">
        <summary>口播转写文本</summary>
        <div class="transcript">${escapeHtml(transcript.transcript)}</div>
      </details>
    ` : ""}
  `;
  drawer.classList.remove("hiddenPanel");
  drawer.setAttribute("aria-hidden", "false");
}

function closeAnalysisDetailDrawer() {
  const drawer = document.querySelector("#analysisDetailDrawer");
  if (!drawer) return;
  drawer.classList.add("hiddenPanel");
  drawer.setAttribute("aria-hidden", "true");
  state.activeAnalysisDetailId = null;
}

function findMaterial(id) {
  return state.materials.find((item) => Number(item.id) === Number(id));
}

function openAssetDetailDrawer(kind, id) {
  const drawer = document.querySelector("#assetDetailDrawer");
  const title = document.querySelector("#assetDetailTitle");
  const eyebrow = document.querySelector("#assetDetailEyebrow");
  const content = document.querySelector("#assetDetailContent");
  if (!drawer || !title || !eyebrow || !content) return;

  if (kind === "human") {
    const human = state.digitalHumans.find((item) => Number(item.id) === Number(id));
    if (!human) return;
    const portrait = findMaterial(human.portrait_material_id);
    const sourceVideo = findMaterial(human.source_video_material_id);
    title.textContent = human.name;
    eyebrow.textContent = "Digital Human";
    content.innerHTML = `
      <div class="assetDrawerSummary">
        <div>
          <strong>${escapeHtml(human.role || "未设置角色")}</strong>
          <div class="assetMetaLine">
            <span class="status subtle">${escapeHtml(humanStyleLabel(human.style))}</span>
            ${assetStateLabel(Boolean(human.default_voice), "声音已复刻", "声音未复刻")}
            ${assetStateLabel(Boolean(sourceVideo), "已绑定视频源", "未绑定视频源")}
            ${volcengineAuthStateLabel(human)}
          </div>
        </div>
        <div class="assetDetailGrid">
          <div><span>头像素材</span><strong>#${human.portrait_material_id || "-"}</strong></div>
          <div><span>口播源视频</span><strong>#${human.source_video_material_id || "-"}</strong></div>
          <div><span>授权范围</span><strong>${escapeHtml(human.authorization_scope || "-")}</strong></div>
          <div><span>创建时间</span><strong>${formatDateTime(human.created_at)}</strong></div>
          <div><span>火山真人认证</span><strong>${volcengineAuthStatusLabel(human.volcengine_auth_status)}</strong></div>
          <div><span>Asset Group</span><strong>${escapeHtml(human.volcengine_asset_group_id || "-")}</strong></div>
        </div>
        <div class="assetVoiceBlock">
          <span>声音 ID</span>
          <code>${escapeHtml(human.default_voice || "未复刻")}</code>
        </div>
        <div class="volcengineAuthBlock">
          <div>
            <strong>火山真人资产认证</strong>
            <span>通过 H5 真人认证后，后续才能把这个数字人作为火山 Asset Group / Asset URI 使用。</span>
          </div>
          <div class="assetVoiceBlock">
            <span>认证链接</span>
            <code>${escapeHtml(human.volcengine_auth_url || "未创建")}</code>
          </div>
          <div class="assetDetailGrid">
            <div><span>BytedToken</span><strong>${escapeHtml(human.volcengine_byted_token || "-")}</strong></div>
            <div><span>认证结果码</span><strong>${escapeHtml(human.volcengine_auth_result_code || "-")}</strong></div>
            <div><span>Asset Group URI</span><strong>${escapeHtml(human.volcengine_asset_group_uri || "-")}</strong></div>
            <div><span>Asset URI</span><strong>${escapeHtml(human.volcengine_asset_uri || "-")}</strong></div>
          </div>
          <div class="drawerActions">
            <button type="button" data-action="create-volcengine-auth" data-id="${human.id}">创建认证链接</button>
            ${human.volcengine_auth_url ? `<button type="button" class="secondary" data-action="open-volcengine-auth" data-url="${escapeHtml(human.volcengine_auth_url)}">打开认证页</button>` : ""}
            ${human.volcengine_auth_url ? `<button type="button" class="secondary" data-action="copy-volcengine-auth-url" data-url="${escapeHtml(human.volcengine_auth_url)}">复制链接</button>` : ""}
            <button type="button" class="secondary" data-action="sync-volcengine-auth" data-id="${human.id}">同步认证结果</button>
          </div>
        </div>
      </div>
      <div class="assetDrawerMediaGrid">
        <section>
          <h3>头像</h3>
          ${portrait ? renderMaterialPreview(portrait, "assetDrawerMedia") : `<div class="assetDrawerEmpty">未绑定头像</div>`}
        </section>
        <section>
          <h3>口播源视频</h3>
          ${sourceVideo ? renderMaterialPreview(sourceVideo, "assetDrawerMedia") : `<div class="assetDrawerEmpty">未绑定口播源视频</div>`}
        </section>
      </div>
      <div class="drawerActions">
        ${portrait?.source_url ? `<button type="button" class="secondary" data-action="copy-material-url" data-url="${escapeHtml(portrait.source_url)}">复制头像地址</button>` : ""}
        ${sourceVideo?.source_url ? `<button type="button" class="secondary" data-action="copy-material-url" data-url="${escapeHtml(sourceVideo.source_url)}">复制视频地址</button>` : ""}
        <button type="button" class="danger" data-action="delete-human" data-id="${human.id}">删除数字人</button>
      </div>
    `;
  }

  if (kind === "material") {
    const material = findMaterial(id);
    if (!material) return;
    title.textContent = `#${material.id} ${material.name}`;
    eyebrow.textContent = "Material";
    content.innerHTML = `
      <div class="assetDrawerSummary">
        <div class="assetMetaLine">
          <span class="status">${materialKindLabel(material.kind)}</span>
          ${assetStateLabel(Boolean(material.source_url), "云端已就绪", "待补传")}
        </div>
        <div class="assetDetailGrid">
          <div><span>版权状态</span><strong>${escapeHtml(materialCopyrightLabel(material.copyright_status))}</strong></div>
          <div><span>标签</span><strong>${escapeHtml(material.tags || "未打标签")}</strong></div>
          <div><span>创建时间</span><strong>${formatDateTime(material.created_at)}</strong></div>
          <div><span>素材类型</span><strong>${materialKindLabel(material.kind)}</strong></div>
        </div>
        <div class="assetVoiceBlock">
          <span>云端地址</span>
          <code>${escapeHtml(material.source_url || "未上传")}</code>
        </div>
      </div>
      ${renderMaterialPreview(material, "assetDrawerMedia full")}
      <div class="drawerActions">
        ${material.source_url ? `<button type="button" class="secondary" data-action="copy-material-url" data-url="${escapeHtml(material.source_url)}">复制云端地址</button>` : `<button type="button" class="secondary" data-action="remote-upload-material" data-id="${material.id}">补传服务器</button>`}
        <button type="button" class="danger" data-action="delete-material" data-id="${material.id}">删除素材</button>
      </div>
    `;
  }

  drawer.classList.remove("hiddenPanel");
  drawer.setAttribute("aria-hidden", "false");
}

function closeAssetDetailDrawer() {
  const drawer = document.querySelector("#assetDetailDrawer");
  if (!drawer) return;
  drawer.classList.add("hiddenPanel");
  drawer.setAttribute("aria-hidden", "true");
}

function renderHumanSelects(humans) {
  const select = document.querySelector("#taskHumanSelect");
  const batchSelect = document.querySelector("#batchHumanSelect");
  const creationSelect = document.querySelector("#creationHumanSelect");
  const options = humans
    .map((human) => `<option value="${human.id}">#${human.id} ${escapeHtml(human.name)}</option>`)
    .join("");
  [select, batchSelect, creationSelect].filter(Boolean).forEach((target) => {
    const current = target.value;
    target.innerHTML = `<option value="">不使用数字人露脸</option>${options}`;
    target.value = current || state.latestHumanId || "";
  });
  syncCreationProductionModeWithHuman();
}

function renderDigitalHumans(humans) {
  const target = document.querySelector("#humanList");
  if (!target) return;
  renderHumanSelects(humans);
  if (!humans.length) {
    target.innerHTML = `<div class="item">还没有数字人形象</div>`;
    return;
  }
  const pageInfo = pagedItems("digitalHumans", humans);
  target.innerHTML = `
    <table class="settingsTable compactTable assetListTable humanListTable">
      <thead>
        <tr>
          <th>数字人</th>
          <th>角色</th>
          <th>风格</th>
          <th>声音</th>
          <th>素材绑定</th>
          <th>火山认证</th>
          <th>创建时间</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        ${pageInfo.items.map((human) => `
          <tr>
            <td>
              <strong>#${human.id} ${escapeHtml(human.name)}</strong>
              <div class="recordMeta">详情里可预览头像和口播源视频</div>
            </td>
            <td>${escapeHtml(human.role || "未设置角色")}</td>
            <td><span class="status subtle">${escapeHtml(humanStyleLabel(human.style))}</span></td>
            <td>${assetStateLabel(Boolean(human.default_voice), "声音已复刻", "声音未复刻")}</td>
            <td>
              <div>头像 #${human.portrait_material_id || "-"}</div>
              <div class="recordMeta">口播源 #${human.source_video_material_id || "-"}</div>
            </td>
            <td>
              ${volcengineAuthStateLabel(human)}
              <div class="recordMeta">${escapeHtml(human.volcengine_asset_group_id || "未生成 Asset Group")}</div>
            </td>
            <td>${formatDateTime(human.created_at)}</td>
            <td>
              <div class="tableActions">
                <button type="button" class="secondary" data-action="view-human-detail" data-id="${human.id}">详情</button>
                <button type="button" class="danger" data-action="delete-human" data-id="${human.id}">删除</button>
              </div>
            </td>
          </tr>
        `).join("")}
      </tbody>
    </table>
    ${pagerHtml("digitalHumans", pageInfo)}
  `;
}

function renderVoiceCloneStatus(status) {
  const target = document.querySelector("#voiceCloneStatus");
  if (!target) return;
  const configured = Boolean(status.configured);
  target.innerHTML = `
    <div class="voiceCloneCard ${configured ? "ready" : "pending"}">
      <strong>${configured ? "声音复刻已接入" : "声音复刻未配置"}</strong>
      <span>${escapeHtml(status.provider || "未配置")} · ${configured ? "上传源视频后可生成本人 voice_id" : "不影响创建数字人素材；后续真实复刻声音时再到系统设置配置接口"}</span>
    </div>
  `;
}

function renderIntegrations(status) {
  state.integrations = status || {};
  const labels = {
    script_model: "脚本模型",
    tts: "语音合成",
    voice_clone: "声音复刻",
    digital_human: "数字人",
    video_generation: "视频生成",
    video_understanding: "视频理解",
    composition: "视频合成",
    trending_search: "主题采集",
    asr: "语音识别",
  };
  document.querySelector("#integrationStatus").innerHTML = Object.entries(labels)
    .map(([key, label]) => {
      const item = status[key] || {};
      const configured = item.configured ? "已配置" : "待配置";
      return `<span>${label}: ${item.provider || "-"} · ${configured}</span>`;
    })
    .join("");
  renderVoiceCloneStatus(status.voice_clone || {});
  syncCreationProductionModeWithHuman();
}

function modelDiagnosticLabel(level) {
  return {
    ready: "真实接口可用",
    mock: "本地/测试模式",
    blocked: "待补齐",
  }[level] || "待检查";
}

function modelDiagnosticStatusClass(level) {
  return {
    ready: "taskStatusApproved",
    mock: "taskStatusDraft",
    blocked: "taskStatusFailed",
  }[level] || "taskStatusDraft";
}

function renderModelDiagnostics(report) {
  const target = document.querySelector("#modelDiagnosticsList");
  if (!target) return;
  const items = report?.items || [];
  if (!items.length) {
    target.innerHTML = `<div class="item">还没有模型接入体检结果。</div>`;
    return;
  }
  target.innerHTML = `
    <section class="panel modelDiagnosticsPanel">
      <div class="sectionHeader compactSectionHeader">
        <div>
          <h2>模型接入体检</h2>
          <p>只展示当前各模块能否真实调用，详细配置放到下方高级配置里。</p>
        </div>
        <div class="diagnosticCounts">
          <span>可用 ${formatNumber(report.ready_count)}</span>
          <span>占位 ${formatNumber(report.mock_count)}</span>
          <span>待补齐 ${formatNumber(report.blocked_count)}</span>
        </div>
      </div>
      <table class="settingsTable compactTable modelDiagnosticsTable">
        <thead>
          <tr>
            <th>模块</th>
            <th>供应商 / 模型</th>
            <th>状态</th>
            <th>接口</th>
            <th>Key</th>
            <th>待处理</th>
          </tr>
        </thead>
        <tbody>
        ${items
          .map(
            (item) => `
              <tr class="${item.level === "blocked" ? "diagnosticBlockedRow" : ""}">
                <td><strong>${escapeHtml(item.purpose_label || item.purpose)}</strong></td>
                <td>
                  ${escapeHtml(providerLabel(item.purpose, item.provider || "-"))}
                  <div class="recordMeta">${escapeHtml(item.model_name || "-")}</div>
                </td>
                <td><span class="status taskStatus ${modelDiagnosticStatusClass(item.level)}">${modelDiagnosticLabel(item.level)}</span></td>
                <td><span class="${item.has_api_base ? "ok" : "missing"}">${item.has_api_base ? "已填" : "缺失"}</span></td>
                <td><span class="${item.has_api_key ? "ok" : "missing"}">${item.has_api_key ? "已保存" : "缺失"}</span></td>
                <td>${item.level === "blocked" ? escapeHtml(item.next_action || item.summary || "") : "可运行"}</td>
              </tr>
            `,
          )
          .join("")}
        </tbody>
      </table>
    </section>
  `;
}

function renderModels(models) {
  const target = document.querySelector("#modelConfigList");
  if (!models.length) {
    target.innerHTML = `<div class="item">还没有模型配置</div>`;
    return;
  }
  const pageInfo = pagedItems("models", models);
  target.innerHTML = pageInfo.items
    .map(
      (model) => `
        <div class="item">
          <div class="itemHeader">
            <strong>${model.name}</strong>
            <span class="status taskStatus ${model.is_active ? "taskStatusApproved" : "taskStatusDraft"}">${model.is_active ? "启用" : "停用"}</span>
          </div>
          <div>${purposeLabel(model.purpose)} · ${providerLabel(model.purpose, model.provider)}</div>
          <div class="recordMeta">${escapeHtml(model.model_name)} · 接口${model.api_base ? "已填" : "缺失"} · Key ${model.has_api_key ? "已保存" : "缺失"}</div>
          <div class="itemActions">
            <button type="button" class="secondary" data-action="edit-model-config" data-id="${model.id}">编辑</button>
            <button type="button" class="secondary" data-action="test-model-config" data-id="${model.id}">测试</button>
            <button type="button" data-action="activate-model-config" data-id="${model.id}" ${model.is_active ? "disabled" : ""}>启用</button>
          </div>
        </div>
      `,
    )
    .join("") + pagerHtml("models", pageInfo);
}

function renderModelUsage(report) {
  const summaryTarget = document.querySelector("#modelUsageSummary");
  const listTarget = document.querySelector("#modelUsageList");
  if (!summaryTarget || !listTarget) return;
  const totals = report?.totals || {};
  const cards = [
    ["当前模型", totals.current_model_count],
    ["当前调用", totals.call_count],
    ["历史旧记录", totals.historical_count],
    ["成功", totals.success_count],
    ["失败", totals.failed_count],
    ["总 Token", totals.total_tokens],
  ];
  summaryTarget.innerHTML = cards
    .map(
      ([label, value]) => `
        <div class="statusCard">
          <strong>${formatNumber(value)}</strong>
          <span>${label}</span>
        </div>
      `,
    )
    .join("");

  const items = report?.items || [];
  const historyItems = report?.historical_items || [];
  if (!items.length) {
    listTarget.innerHTML = `<div class="item">还没有当前模型配置。先在“AI 模型接入”里启用模型。</div>`;
    return;
  }
  const statusBadge = (item) => {
    const calls = Number(item.call_count || 0);
    if (!item.current_config) {
      return `<span class="status taskStatus taskStatusFailed">未配置</span>`;
    }
    if (!calls) {
      return `<span class="status taskStatus taskStatusDraft">未调用</span>`;
    }
    if (item.last_status === "success") {
      return `<span class="status taskStatus taskStatusApproved">最近成功</span>`;
    }
    return `<span class="status taskStatus taskStatusFailed">最近失败</span>`;
  };
  const modelRow = (item) => `
    <tr>
      <td>${escapeHtml(item.purpose_label || purposeLabel(item.purpose))}</td>
      <td>
        <span class="usageApiTag ${item.real_api ? "real" : "mock"}">${item.real_api ? "真实" : "本地/占位"}</span>
        ${escapeHtml(providerLabel(item.purpose, item.provider))}
      </td>
      <td>${escapeHtml(item.model_name)}</td>
      <td>${statusBadge(item)}</td>
      <td>${formatNumber(item.call_count)}</td>
      <td>${formatNumber(item.success_count)}</td>
      <td>${formatNumber(item.failed_count)}</td>
      <td>${formatNumber(item.prompt_tokens)}</td>
      <td>${formatNumber(item.completion_tokens)}</td>
      <td>${formatNumber(item.total_tokens)}</td>
      <td>${formatDateTime(item.last_used_at)}</td>
    </tr>
  `;
  const currentPageInfo = pagedItems("modelUsage", items);
  const historyPageInfo = pagedItems("modelUsageHistory", historyItems);
  const historicalBlock = historyItems.length
    ? `
      <details class="usageHistoryDetails">
        <summary>历史旧记录 ${formatNumber(historyItems.reduce((sum, item) => sum + Number(item.call_count || 0), 0))} 次</summary>
        <div class="settingsTableWrap">
          <table class="settingsTable usageTable compactTable usageHistoryTable">
            <thead>
              <tr>
                <th>模块</th>
                <th>接口</th>
                <th>模型</th>
                <th>调用</th>
                <th>输入 Token</th>
                <th>输出 Token</th>
                <th>总 Token</th>
                <th>最近调用</th>
              </tr>
            </thead>
            <tbody>
              ${historyPageInfo.items
                .map(
                  (item) => `
                    <tr>
                      <td>${escapeHtml(item.purpose_label || purposeLabel(item.purpose))}</td>
                      <td>
                        <span class="usageApiTag old">旧记录</span>
                        <span class="usageApiTag ${item.real_api ? "real" : "mock"}">${item.real_api ? "真实" : "本地/占位"}</span>
                        ${escapeHtml(providerLabel(item.purpose, item.provider))}
                      </td>
                      <td>${escapeHtml(item.model_name)}</td>
                      <td>${formatNumber(item.call_count)}</td>
                      <td>${formatNumber(item.prompt_tokens)}</td>
                      <td>${formatNumber(item.completion_tokens)}</td>
                      <td>${formatNumber(item.total_tokens)}</td>
                      <td>${formatDateTime(item.last_used_at)}</td>
                    </tr>
                  `,
                )
                .join("")}
            </tbody>
          </table>
          ${pagerHtml("modelUsageHistory", historyPageInfo)}
        </div>
      </details>
    `
    : "";
  listTarget.innerHTML = `
    <div class="settingsTableWrap">
      <table class="settingsTable usageTable compactTable">
        <thead>
          <tr>
            <th>模块</th>
            <th>接口</th>
            <th>模型</th>
            <th>状态</th>
            <th>调用</th>
            <th>成功</th>
            <th>失败</th>
            <th>输入 Token</th>
            <th>输出 Token</th>
            <th>总 Token</th>
            <th>最近调用</th>
          </tr>
        </thead>
        <tbody>
          ${currentPageInfo.items.map(modelRow).join("")}
        </tbody>
      </table>
      ${pagerHtml("modelUsage", currentPageInfo)}
    </div>
    ${historicalBlock}
  `;
}

function renderVideoStorage(report) {
  const summaryTarget = document.querySelector("#videoStorageSummary");
  const pathsTarget = document.querySelector("#videoStoragePaths");
  const listTarget = document.querySelector("#videoStorageList");
  if (!summaryTarget || !pathsTarget || !listTarget) return;
  renderLocalSaveDirectoryState();
  const totals = report?.totals || {};
  const videos = report?.videos || [];
  const savedCurrentCount = videos.filter((video) => state.localSavedVideoIds.has(Number(video.task_id))).length;
  const cards = [
    ["成片记录", totals.video_count],
    ["本地存在", totals.existing_count],
    ["本地缺失", totals.missing_count],
    ["电脑已保存", savedCurrentCount],
    ["占用空间", formatBytes(totals.size_bytes)],
  ];
  summaryTarget.innerHTML = cards
    .map(
      ([label, value]) => `
        <div class="statusCard">
          <strong>${typeof value === "number" ? formatNumber(value) : escapeHtml(value)}</strong>
          <span>${label}</span>
        </div>
      `,
    )
    .join("");

  const storageGroups = report?.storage_groups || [
    { label: "成片库", description: "最终审核和发布使用的视频。" },
    { label: "分段视频库", description: "AI 生成的分镜片段和中间视频。" },
    { label: "数字人口播库", description: "数字人口播视频和驱动结果。" },
    { label: "音频库", description: "配音、声音复刻和口播音频。" },
  ];
  pathsTarget.innerHTML = storageGroups
    .map(
      (item) => `
        <div class="storagePathRow">
          <span>${escapeHtml(item.label || "保存分组")}</span>
          <p>${escapeHtml(item.description || "")}</p>
        </div>
      `,
    )
    .join("");

  if (!videos.length) {
    listTarget.innerHTML = `<div class="item">还没有生成成片。视频任务生成完成后，这里会显示实际文件路径。</div>`;
    return;
  }
  const pageInfo = pagedItems("videoStorage", videos);
  listTarget.innerHTML = `
    <table class="settingsTable storageTable compactTable">
      <thead>
        <tr>
          <th>任务</th>
          <th>脚本</th>
          <th>状态</th>
          <th>规格</th>
          <th>文件</th>
          <th>保存位置</th>
          <th>大小</th>
          <th>电脑文件夹</th>
          <th>更新时间</th>
        </tr>
      </thead>
      <tbody>
        ${pageInfo.items
          .map(
            (video) => {
              const fileState = video.exists
                ? { label: "存在", className: "storageFileOk" }
                : video.storage_kind === "external"
                  ? { label: "云端", className: "storageFileExternal" }
                  : video.storage_kind === "placeholder"
                    ? { label: "占位", className: "storageFilePlaceholder" }
                    : { label: "缺失", className: "storageFileMissing" };
              const canSaveLocal = video.storage_kind === "external" || video.exists;
              const localSaved = state.localSavedVideoIds.has(Number(video.task_id));
              const localSaving = state.localSavingVideoIds.has(Number(video.task_id));
              return `
              <tr>
                <td>#${video.task_id}</td>
                <td>${escapeHtml(video.script_title || `脚本 #${video.script_id}`).slice(0, 40)}</td>
                <td><span class="status taskStatus ${taskStatusClass(video.status)}">${taskStatusLabel(video.status)}</span></td>
                <td>${escapeHtml(exportProfileLabel(video.export_profile))}<div class="recordMeta">${video.export_width || "-"}x${video.export_height || "-"}</div></td>
                <td><span class="storageFileState ${fileState.className}">${fileState.label}</span></td>
                <td>${escapeHtml(video.storage_label || "成片库")}</td>
                <td>${formatBytes(video.size_bytes)}</td>
                <td>
                  ${
                    canSaveLocal
                      ? `<button type="button" class="secondary localSaveButton ${localSaved ? "saved" : ""}" data-action="save-video-local" data-id="${video.task_id}" ${localSaving ? "disabled" : ""}>${localSaving ? "保存中..." : localSaved ? "已保存" : "保存到电脑"}</button>`
                      : `<span class="recordMeta">暂无成片</span>`
                  }
                </td>
                <td>${formatDateTime(video.updated_at || video.created_at)}</td>
              </tr>
            `;
            },
          )
          .join("")}
      </tbody>
    </table>
    ${pagerHtml("videoStorage", pageInfo)}
  `;
  void autoSaveVideosToLocal(videos);
}

function renderRemoteUpload(settings) {
  const form = document.querySelector("#remoteUploadForm");
  const stateLabel = document.querySelector("#remoteUploadState");
  if (!form) return;
  form.querySelector("[name='enabled']").checked = Boolean(settings?.enabled);
  form.querySelector("[name='upload_url']").value = settings?.upload_url || "";
  form.querySelector("[name='public_base_url']").value = settings?.public_base_url || "";
  form.querySelector("[name='file_field_name']").value = settings?.file_field_name || "file";
  form.querySelector("[name='upload_token']").value = "";
  form.querySelector("[name='upload_token']").placeholder = settings?.has_upload_token ? "已保存 Token，可留空" : "可选 Bearer Token";
  form.querySelector("[name='clear_upload_token']").checked = false;
  if (stateLabel) {
    stateLabel.textContent = settings?.ready ? "已启用" : settings?.enabled ? "缺上传接口" : "未启用";
    stateLabel.className = `pill ${settings?.ready ? "ok" : "subtle"}`;
  }
  const hint = document.querySelector("#remoteUploadHintText");
  if (hint) {
    hint.textContent = settings?.ready
      ? "素材会上传到服务器并生成公网地址。"
      : settings?.enabled
        ? "已勾选启用，但还缺上传接口。"
        : "未启用时只保存在本机。";
  }
}

function renderSystemUsers(users) {
  const target = document.querySelector("#userAccountList");
  if (!target) return;
  if (!users.length) {
    target.innerHTML = `<div class="item">还没有可维护账号，或当前账号没有管理员权限。</div>`;
    return;
  }
  const pageInfo = pagedItems("users", users);
  target.innerHTML = `
    <table class="settingsTable compactTable userTable">
      <thead>
        <tr>
          <th>账号</th>
          <th>角色</th>
          <th>状态</th>
          <th>创建时间</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        ${pageInfo.items
          .map(
            (user) => `
              <tr data-id="${user.id}">
                <td>
                  <strong>${escapeHtml(user.username)}</strong>
                  <div class="recordMeta">#${user.id}</div>
                </td>
                <td>
                  <select data-field="role">
                    <option value="operator" ${user.role === "operator" ? "selected" : ""}>运营人员</option>
                    <option value="reviewer" ${user.role === "reviewer" ? "selected" : ""}>审核人员</option>
                    <option value="admin" ${user.role === "admin" ? "selected" : ""}>管理员</option>
                  </select>
                </td>
                <td>
                  <select data-field="is_active">
                    <option value="true" ${user.is_active ? "selected" : ""}>启用</option>
                    <option value="false" ${!user.is_active ? "selected" : ""}>停用</option>
                  </select>
                </td>
                <td>${formatDateTime(user.created_at)}</td>
                <td>
                  <div class="tableActions">
                    <button type="button" data-action="save-user" data-id="${user.id}">保存</button>
                    <button type="button" class="secondary" data-action="reset-user-password" data-id="${user.id}">重置密码</button>
                  </div>
                </td>
              </tr>
            `,
          )
          .join("")}
      </tbody>
    </table>
    ${pagerHtml("users", pageInfo)}
  `;
}

function renderWechatLogin(config, requests = [], identities = []) {
  const form = document.querySelector("#wechatLoginConfigForm");
  const status = document.querySelector("#wechatLoginConfigStatus");
  const requestTarget = document.querySelector("#wechatLoginRequestList");
  const identityTarget = document.querySelector("#wechatIdentityList");
  if (form && config) {
    const secretInput = form.querySelector("[name='app_secret']");
    const secretEditButton = form.querySelector("#wechatSecretEditBtn");
    form.querySelector("[name='app_id']").value = config.app_id || "";
    secretInput.value = "";
    secretInput.disabled = Boolean(config.has_app_secret);
    secretInput.placeholder = config.has_app_secret ? "已保存 AppSecret，无需重复填写" : "请输入 AppSecret";
    secretEditButton?.classList.toggle("hiddenPanel", !config.has_app_secret);
    form.querySelector("[name='redirect_uri']").value = config.redirect_uri || `${window.location.origin}/api/auth/wechat/callback`;
    form.querySelector("[name='default_role']").value = config.default_role || "operator";
    form.querySelector("[name='is_active']").checked = Boolean(config.is_active);
  }
  if (status) {
    const enabled = Boolean(config?.is_active && config?.app_id && config?.has_app_secret && config?.redirect_uri);
    status.textContent = enabled ? "已启用" : "未启用";
    status.className = `pill ${enabled ? "ok" : "subtle"}`;
  }
  if (requestTarget) {
    const pageInfo = pagedItems("wechatRequests", requests);
    requestTarget.innerHTML = requests.length
      ? `
        <table class="settingsTable wechatLightTable responsiveTable">
          <colgroup>
            <col class="wechatUserColumn" />
            <col class="wechatStatusColumn" />
            <col class="wechatOpenidColumn" />
            <col class="wechatTimeColumn" />
            <col class="wechatActionColumn" />
          </colgroup>
          <thead>
            <tr>
              <th>微信用户</th>
              <th>状态</th>
              <th>OpenID</th>
              <th>申请时间</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            ${pageInfo.items.map((item) => `
              <tr data-id="${item.id}">
                <td data-label="微信用户">
                  <strong>${escapeHtml(item.nickname || "微信用户")}</strong>
                  <div class="recordMeta">${item.avatar_url ? "头像已获取" : "无头像"}</div>
                </td>
                <td data-label="状态"><span class="status">${wechatRequestStatusLabel(item.status)}</span></td>
                <td data-label="OpenID"><span class="monoCell">${escapeHtml(item.openid_suffix || "-")}</span></td>
                <td data-label="申请时间" class="mutedCell">${formatDateTime(item.requested_at)}</td>
                <td data-label="操作">
                  ${item.status === "pending" ? `
                    <div class="wechatApproveBox">
                      <select data-field="approve_mode">
                        <option value="create_user">新建用户</option>
                        <option value="bind_existing">绑定已有用户</option>
                      </select>
                      <input data-field="username" placeholder="新用户名" value="wechat_${item.id}" />
                      <select data-field="role">
                        <option value="operator">运营人员</option>
                        <option value="reviewer">审核人员</option>
                        <option value="admin">管理员</option>
                      </select>
                      <select data-field="user_id">
                        <option value="">选择已有用户</option>
                        ${(state.users || []).map((user) => `<option value="${user.id}">#${user.id} ${escapeHtml(user.username)}</option>`).join("")}
                      </select>
                      <div class="wechatInlineActions">
                        <button type="button" data-action="approve-wechat-request" data-id="${item.id}">批准</button>
                        <button type="button" class="secondary" data-action="reject-wechat-request" data-id="${item.id}">拒绝</button>
                      </div>
                    </div>
                  ` : `<span class="mutedCell">${escapeHtml(item.reject_reason || "-")}</span>`}
                </td>
              </tr>
            `).join("")}
          </tbody>
        </table>
        ${pagerHtml("wechatRequests", pageInfo)}
      `
      : `<div class="item">暂无微信登录申请。</div>`;
  }
  if (identityTarget) {
    const pageInfo = pagedItems("wechatIdentities", identities);
    identityTarget.innerHTML = identities.length
      ? `
        <table class="settingsTable wechatLightTable responsiveTable">
          <colgroup>
            <col class="wechatUserColumn" />
            <col class="wechatNicknameColumn" />
            <col class="wechatOpenidColumn" />
            <col class="wechatStatusColumn" />
            <col class="wechatTimeColumn" />
            <col class="wechatActionColumn" />
          </colgroup>
          <thead>
            <tr>
              <th>系统用户</th>
              <th>微信昵称</th>
              <th>OpenID</th>
              <th>状态</th>
              <th>最近登录</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            ${pageInfo.items.map((item) => `
              <tr>
                <td data-label="系统用户"><strong>#${item.user_id} ${escapeHtml(item.username || "-")}</strong></td>
                <td data-label="微信昵称">${escapeHtml(item.nickname || "-")}</td>
                <td data-label="OpenID"><span class="monoCell">${escapeHtml(item.openid_suffix || "-")}</span></td>
                <td data-label="状态"><span class="status">${item.is_active ? "启用" : "停用"}</span></td>
                <td data-label="最近登录" class="mutedCell">${item.last_login_at ? formatDateTime(item.last_login_at) : "-"}</td>
                <td data-label="操作">
                  <button type="button" class="secondary compactButton" data-action="disable-wechat-identity" data-id="${item.id}" ${item.is_active ? "" : "disabled"}>停用绑定</button>
                </td>
              </tr>
            `).join("")}
          </tbody>
        </table>
        ${pagerHtml("wechatIdentities", pageInfo)}
      `
      : `<div class="item">暂无已绑定微信用户。</div>`;
  }
}

function wechatRequestStatusLabel(status) {
  return {
    pending: "待审批",
    approved: "已批准",
    rejected: "已拒绝",
  }[status] || status || "-";
}

function renderPlatformCredentials(credentials) {
  const target = document.querySelector("#platformCredentialList");
  if (!target) return;
  if (!credentials.length) {
    target.innerHTML = `<div class="item">还没有平台接入配置</div>`;
    return;
  }
  const pageInfo = pagedItems("platformCredentials", credentials);
  target.innerHTML = pageInfo.items
    .map(
      (credential) => `
        <div class="item">
          <div class="itemHeader">
            <strong>#${credential.id} ${escapeHtml(credential.display_name)}</strong>
            <span class="status">${credential.is_active ? "启用" : escapeHtml(credential.status)}</span>
          </div>
          <div>${platformLabel(credential.platform)} · ${credentialPurposeLabel(credential.purpose)}</div>
          <div>${escapeHtml(credential.api_base || "未填写接口地址")}</div>
          <div class="secretFlags">
            <span>${credential.client_id ? "Client ID 已填" : "缺 Client ID"}</span>
            <span>${credential.has_client_secret ? "Secret 已保存" : "缺 Secret"}</span>
            <span>${credential.has_access_token ? "Token 已保存" : "缺 Token"}</span>
          </div>
          <div class="itemActions accountActions">
            <button type="button" class="secondary" data-action="activate-platform-credential" data-id="${credential.id}">设为启用</button>
          </div>
        </div>
      `,
    )
    .join("") + pagerHtml("platformCredentials", pageInfo);
}

function providerLabel(purpose, value) {
  const option = (providerOptions[purpose] || []).find((item) => item.value === value);
  return option ? option.label : value;
}

function platformLabel(value) {
  return {
    douyin: "抖音",
    wechat_channels: "视频号",
    xiaohongshu: "小红书",
    kuaishou: "快手",
    volcengine: "火山引擎",
    aliyun: "阿里云",
    manual: "手动",
  }[value] || value;
}

function activePlatformCredential(platform, purpose) {
  return (state.platformCredentials || []).find((credential) => (
    credential.platform === platform
    && credential.purpose === purpose
    && credential.is_active
    && credential.api_base
  ));
}

function hasRealTrendingProviderFor(platform) {
  if (activePlatformCredential(platform, "trending")) return true;
  const status = state.integrations?.trending_search || {};
  return Boolean(status.real_api) && Number(status.credential_count || 0) === 0;
}

function setCaptureHint(selector, message, kind = "") {
  const target = document.querySelector(selector);
  if (!target) return;
  target.className = `capturePlatformHint ${kind}`.trim();
  target.textContent = message;
}

function syncReferencePlatformHint() {
  const platform = document.querySelector("#referenceLinkPlatformSelect")?.value || "auto";
  const messages = {
    auto: ["自动识别平台；适合不确定来源的真实视频链接。", ""],
    wechat_channels: ["视频号建议走链接解析：解析成功后可继续拆解脚本、画面和剪辑方式。", "ok"],
    douyin: ["抖音链接可先解析保存为参考素材，再进入深度拆解。", "ok"],
    xiaohongshu: ["小红书链接依赖已配置的解析服务；解析失败会只保存参考链接。", "warn"],
    kuaishou: ["快手链接依赖已配置的解析服务；解析失败会只保存参考链接。", "warn"],
    manual: ["其他链接需要是可访问的视频地址，或后续上传源文件。", "warn"],
  }[platform] || ["请选择链接平台。", ""];
  setCaptureHint("#referencePlatformHint", messages[0], messages[1]);
}

function syncTrendingPlatformHint() {
  const platform = document.querySelector("#trendingPlatformSelect")?.value || "douyin";
  if (hasRealTrendingProviderFor(platform)) {
    setCaptureHint("#trendingPlatformHint", `${platformLabel(platform)}真实主题采集已配置，可以创建并运行采集。`, "ok");
    return;
  }
  if (platform === "wechat_channels") {
    setCaptureHint("#trendingPlatformHint", "视频号主题自动采集需要先配置自有采集服务；当前建议先用“链接解析”处理具体视频。", "warn");
    return;
  }
  setCaptureHint("#trendingPlatformHint", `${platformLabel(platform)}真实主题采集未配置；请先在“短视频采集接入”配置自建采集或 TikHub。`, "warn");
}

function credentialPurposeLabel(value) {
  return {
    link_resolver: "链接解析/下载",
    trending: "主题采集",
    digital_human: "数字人生成",
    publishing: "自动发布",
    analytics: "数据回收",
  }[value] || value;
}

function purposeLabel(value) {
  return {
    script: "脚本生成",
    tts: "语音合成",
    voice_clone: "声音复刻",
    video: "视频生成",
    digital_human: "数字人驱动",
    asr: "语音识别",
    video_understanding: "视频理解/深度拆解",
    compliance: "合规检查",
    knowledge: "知识库/文档/长文本",
  }[value] || value;
}

function renderTrending(searches, videos) {
  const searchTarget = document.querySelector("#trendingSearchList");
  const videoTarget = document.querySelector("#trendingVideoList");
  state.trendingSearches = searches || [];
  state.trendingVideos = videos || [];
  if (searches.length) {
    state.latestTrendingSearchId = searches[0].id;
  }
  const searchPageInfo = pagedItems("trendingSearches", searches);
  const videoPageInfo = pagedItems("trendingVideos", videos);
  searchTarget.innerHTML = searches.length
    ? searchPageInfo.items
        .map(
          (item) => `
            <div class="item">
              <strong>#${item.id} ${item.keyword}</strong>
              <div>${platformLabel(item.platform)} · ${item.category || "-"} · ${item.limit || 20}条 · ${escapeHtml(item.sort_by || "engagement")}</div>
              <span class="status">${item.status}</span>
              <div>结果：${item.result_count}</div>
              ${item.notes ? `<div class="errorText">${escapeHtml(item.notes)}</div>` : ""}
            </div>
          `,
        )
        .join("") + pagerHtml("trendingSearches", searchPageInfo)
    : `<div class="item">还没有采集任务</div>`;

  videoTarget.innerHTML = videos.length
    ? videoPageInfo.items
        .map((item) => {
          const canSaveReference = isHttpUrl(item.source_url);
          return `
            <div class="item">
              <strong>${escapeHtml(item.title)}</strong>
              <div>${platformLabel(item.platform)} · ${escapeHtml(item.author || "-")}</div>
              <div class="metricRow">
                <span>播放 ${compactNumber(item.play_count)}</span>
                <span>点赞 ${compactNumber(item.like_count)}</span>
                <span>评论 ${compactNumber(item.comment_count)}</span>
                <span>分享 ${compactNumber(item.share_count)}</span>
              </div>
              <div>${escapeHtml(item.summary || item.hook || "")}</div>
              <div class="mutedLine">${escapeHtml(item.source_url)}</div>
              <span class="status">参考，不搬运</span>
              <div class="itemActions">
                ${
                  canSaveReference
                    ? `<button type="button" data-action="save-trending-reference" data-id="${item.id}">保存到参考素材</button>
                       <a class="buttonLike secondary" href="${escapeHtml(item.source_url)}" target="_blank" rel="noreferrer">打开链接</a>`
                    : `<span class="status subtle">真实采集链接才可保存</span>`
                }
              </div>
            </div>
          `;
        })
        .join("") + pagerHtml("trendingVideos", videoPageInfo)
    : `<div class="item">还没有爆款参考</div>`;
  syncTrendingPlatformHint();
}

function renderTranscriptions(tasks) {
  state.transcriptions = tasks || [];
  const target = document.querySelector("#transcriptionList");
  if (!target) return;
  if (!state.transcriptions.length) {
    target.innerHTML = `<div class="item">还没有转写任务</div>`;
    return;
  }
  state.latestTranscriptionId = state.transcriptions[0].id;
  const pageInfo = pagedItems("transcriptions", state.transcriptions);
  target.innerHTML = pageInfo.items
    .map(
      (task) => `
        <div class="item">
          <strong>转写 #${task.id} · 素材 #${task.material_id}</strong>
          <span class="status">${transcriptionStatusLabel(task.status)}</span>
          <div>${task.summary || ""}</div>
          <div>${task.hook_analysis || ""}</div>
          <div class="transcript">${task.transcript || task.error_message || ""}</div>
          <div class="itemActions">
            <button type="button" data-action="topic-from-transcription" data-id="${task.id}">带到内容创作</button>
            <button type="button" class="secondary" data-action="script-from-transcription" data-id="${task.id}">生成原创脚本</button>
          </div>
        </div>
      `,
    )
    .join("") + pagerHtml("transcriptions", pageInfo);
}

function parseAnalysisTimeline(analysis) {
  if (!analysis?.timeline_json) return [];
  try {
    const parsed = JSON.parse(analysis.timeline_json);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function renderVideoAnalyses(analyses) {
  state.videoAnalyses = analyses || [];
  const target = document.querySelector("#videoAnalysisList");
  if (!target) return;
  if (!state.videoAnalyses.length) {
    target.innerHTML = `<div class="item">还没有深度拆解任务。选择参考视频后，点击“一键深度拆解”。</div>`;
    return;
  }
  state.latestVideoAnalysisId = state.videoAnalyses[0].id;
  const pageInfo = pagedItems("videoAnalyses", state.videoAnalyses);
  target.innerHTML = `
    <div class="settingsTableWrap">
      <table class="settingsTable compactTable videoAnalysisTable">
        <thead>
          <tr>
            <th>拆解任务</th>
            <th>状态</th>
            <th>结构指标</th>
            <th>质量</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          ${pageInfo.items
            .map((analysis) => {
              const canGenerate = analysis.status === "needs_review" || analysis.status === "approved";
              const canRun = ["queued", "failed", "draft"].includes(analysis.status);
              const quality = analysis.quality_summary || analysis.reuse_notes || analysis.error_message || "详情里查看脚本、拍摄、剪辑和抽帧图。";
              return `
                <tr>
                  <td>
                    <strong>深度拆解 #${analysis.id}</strong>
                    <div class="recordMeta">素材 #${analysis.material_id}</div>
                  </td>
                  <td><span class="status taskStatus ${taskStatusClass(analysis.status)}">${analysisStatusLabel(analysis.status)}</span></td>
                  <td>
                    <strong>${Number(analysis.duration_seconds || 0).toFixed(1)} 秒 · ${analysis.scene_count || 0} 段</strong>
                    <div class="recordMeta">${analysis.width || "-"}x${analysis.height || "-"} · 平均 ${Number(analysis.avg_shot_seconds || 0).toFixed(1)} 秒/段</div>
                  </td>
                  <td>
                    <strong>${analysis.model_enhanced ? "模型增强" : "本地基础"} · ${Number(analysis.quality_score || 0).toFixed(0)} 分</strong>
                    <div class="recordMeta">${escapeHtml(quality).slice(0, 72)}</div>
                  </td>
                  <td>
                    <div class="tableActions">
                      <button type="button" class="secondary" data-action="view-video-analysis-detail" data-id="${analysis.id}">详情</button>
                      <button type="button" class="secondary" data-action="run-video-analysis" data-id="${analysis.id}" ${canRun ? "" : "disabled"}>运行拆解</button>
                      <button type="button" data-action="script-from-video-analysis" data-id="${analysis.id}" ${canGenerate ? "" : "disabled"}>生成脚本</button>
                    </div>
                  </td>
                </tr>
              `;
            })
            .join("")}
        </tbody>
      </table>
    </div>
    ${pagerHtml("videoAnalyses", pageInfo)}
  `;
}

function renderAccountMenu(user) {
  const avatar = document.querySelector(".accountAvatar");
  const summary = document.querySelector("#accountMenuSummary");
  if (avatar) avatar.textContent = accountInitials(user?.username);
  if (!summary) return;
  if (!user) {
    summary.innerHTML = `
      <strong>未登录</strong>
      <span>请先登录后使用系统</span>
    `;
    return;
  }
  summary.innerHTML = `
    <strong>${escapeHtml(user.username)}</strong>
    <span>${roleLabel(user.role)} · ${user.is_active ? "已启用" : "已停用"}</span>
  `;
}

function setLoginState(user) {
  state.currentUser = user;
  const label = document.querySelector("#loginState");
  document.body.classList.remove("auth-pending", "is-guest", "is-authenticated");
  if (user) {
    label.textContent = `${user.username} · ${roleLabel(user.role)}`;
    document.body.classList.add("is-authenticated");
  } else {
    label.textContent = "未登录";
    document.body.classList.add("is-guest");
    document.querySelector("#accountMenu")?.classList.add("hiddenPanel");
    closeAccountModal();
  }
  renderAccountMenu(user);
  applyRoleAccess(user);
}

function renderAccountProfile() {
  const user = state.currentUser;
  const target = document.querySelector("#accountProfileContent");
  if (!target || !user) return;
  target.innerHTML = `
    <div class="profileGrid">
      <div class="profileField"><span>账号</span><strong>${escapeHtml(user.username)}</strong></div>
      <div class="profileField"><span>角色</span><strong>${roleLabel(user.role)}</strong></div>
      <div class="profileField"><span>账号 ID</span><strong>#${user.id || "-"}</strong></div>
      <div class="profileField"><span>状态</span><strong>${user.is_active ? "已启用" : "已停用"}</strong></div>
      <div class="profileField"><span>创建时间</span><strong>${formatDateTime(user.created_at)}</strong></div>
      <div class="profileField"><span>当前会话</span><strong>已登录</strong></div>
    </div>
  `;
}

function openAccountModal(mode = "profile") {
  if (!state.currentUser) return;
  renderAccountProfile();
  const modal = document.querySelector("#accountModal");
  const title = document.querySelector("#accountModalTitle");
  const passwordForm = document.querySelector("#changePasswordForm");
  if (!modal || !title || !passwordForm) return;
  title.textContent = mode === "password" ? "修改密码" : "账号资料";
  passwordForm.reset();
  passwordForm.classList.toggle("hiddenPanel", mode === "profile");
  modal.classList.remove("hiddenPanel");
  modal.setAttribute("aria-hidden", "false");
  if (mode === "password") {
    passwordForm.querySelector("[name='current_password']")?.focus();
  }
}

function closeAccountModal() {
  const modal = document.querySelector("#accountModal");
  if (!modal) return;
  modal.classList.add("hiddenPanel");
  modal.setAttribute("aria-hidden", "true");
}

function openHumanHelpModal() {
  const modal = document.querySelector("#humanHelpModal");
  if (!modal) return;
  modal.classList.remove("hiddenPanel");
  modal.setAttribute("aria-hidden", "false");
}

function closeHumanHelpModal() {
  const modal = document.querySelector("#humanHelpModal");
  if (!modal) return;
  modal.classList.add("hiddenPanel");
  modal.setAttribute("aria-hidden", "true");
}

function hideAccountMenu() {
  document.querySelector("#accountMenu")?.classList.add("hiddenPanel");
  document.querySelector("#accountMenuButton")?.setAttribute("aria-expanded", "false");
}

function setMobileNavOpen(open) {
  document.body.classList.toggle("nav-open", open);
  document.querySelector("#mobileNavToggle")?.setAttribute("aria-expanded", String(open));
}

function closeMobileNav() {
  setMobileNavOpen(false);
}

function positionAccountMenu() {
  const menu = document.querySelector("#accountMenu");
  const button = document.querySelector("#accountMenuButton");
  if (!menu || !button) return;
  const rect = button.getBoundingClientRect();
  const menuWidth = menu.offsetWidth || 260;
  const left = Math.max(12, Math.min(rect.left, window.innerWidth - menuWidth - 12));
  menu.style.top = `${rect.bottom + 8}px`;
  menu.style.left = `${left}px`;
}

async function logout() {
  try {
    await api.post("/auth/logout");
  } catch {
    // Local sign-out should still complete even if the session was already invalid.
  } finally {
    localStorage.removeItem("authToken");
    api.token = null;
    window.location.hash = "";
    window.location.replace("/login.html");
  }
}

async function refresh() {
  if (!api.token) return;
  const admin = isAdminUser();
  const [dashboard, integrations, materials, exportProfiles, videoProductionSkills, productModules] = await Promise.all([
    api.get("/dashboard"),
    api.get("/integrations/status"),
    api.get("/materials"),
    api.get("/video-export-profiles"),
    api.get("/video-production-skills"),
    api.get("/product-modules"),
  ]);
  state.videoProductionSkills = videoProductionSkills;
  state.productModules = productModules;
  renderExportProfileSelects(exportProfiles);
  renderVideoProductionSkills(videoProductionSkills);
  renderProductModules(productModules);
  state.materials = materials;
  renderMetrics(dashboard.counts);
  renderIntegrations(integrations);
  renderMaterials(materials);
  renderReferenceMaterials(materials);
  renderScripts(dashboard.recent_scripts);
  renderTasks(dashboard.recent_tasks);
  if (api.token) {
    const [
      searches,
      videos,
      transcriptions,
      videoAnalyses,
      publishRecords,
      platformAccounts,
      digitalHumans,
      scripts,
      videoTasks,
    ] = await Promise.all([
      api.get("/trending/searches"),
      api.get("/trending/videos"),
      api.get("/transcriptions"),
      api.get("/video-analyses"),
      api.get("/publish-records"),
      api.get("/platform-accounts"),
      api.get("/digital-humans"),
      api.get("/scripts"),
      api.get("/video-tasks"),
    ]);
    const [
      models,
      platformCredentials,
      modelUsage,
      modelDiagnostics,
      videoStorage,
      remoteUpload,
      users,
      wechatLoginConfig,
      wechatLoginRequests,
      wechatIdentities,
    ] = admin
      ? await Promise.all([
          api.get("/settings/models"),
          api.get("/settings/platform-credentials"),
          api.get("/settings/model-usage"),
          api.get("/settings/model-diagnostics"),
          api.get("/settings/video-storage"),
          api.get("/settings/remote-upload"),
          api.get("/settings/users").catch(() => []),
          api.get("/settings/wechat-login/config"),
          api.get("/settings/wechat-login/requests"),
          api.get("/settings/wechat-login/identities"),
        ])
      : [[], [], null, null, null, null, [], null, [], []];
    state.platformCredentials = platformCredentials;
    state.platformAccounts = platformAccounts;
    state.publishRecords = publishRecords;
    state.digitalHumans = digitalHumans;
    state.modelConfigs = models;
    state.modelUsage = modelUsage;
    state.modelDiagnostics = modelDiagnostics;
    state.videoStorage = videoStorage;
    state.remoteUpload = remoteUpload;
    state.users = users;
    state.wechatLoginConfig = wechatLoginConfig;
    state.wechatLoginRequests = wechatLoginRequests;
    state.wechatIdentities = wechatIdentities;
    if (admin) {
      renderModels(models);
      renderModelDiagnostics(modelDiagnostics);
      renderPlatformCredentials(platformCredentials);
      renderModelUsage(modelUsage);
      renderVideoStorage(videoStorage);
      renderRemoteUpload(remoteUpload);
      renderSystemUsers(users);
      renderWechatLogin(wechatLoginConfig, wechatLoginRequests, wechatIdentities);
    }
    renderTrending(searches, videos);
    renderTranscriptions(transcriptions);
    renderVideoAnalyses(videoAnalyses);
    renderReferenceMaterials(materials);
    renderPublishRecords(publishRecords);
    renderPlatformAccounts(platformAccounts);
    renderScripts(scripts);
    renderDigitalHumans(digitalHumans);
    renderTasks(videoTasks);
  }
  enhanceResponsiveTables();
}

document.querySelector("#refreshBtn").addEventListener("click", () => refresh().then(() => toast("已刷新")));

document.querySelector("#productModuleList")?.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-module-page]");
  if (!button) return;
  switchPage(button.dataset.modulePage || "overview");
});

document.querySelector("#mobileNavToggle")?.addEventListener("click", () => {
  setMobileNavOpen(!document.body.classList.contains("nav-open"));
});

document.querySelector("#mobileNavBackdrop")?.addEventListener("click", closeMobileNav);

document.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-action='list-page-prev'], button[data-action='list-page-next']");
  if (!button || button.disabled) return;
  event.preventDefault();
  event.stopPropagation();
  const key = button.dataset.listKey;
  if (!key) return;
  const direction = button.dataset.action === "list-page-next" ? 1 : -1;
  state.listPages[key] = Math.max(1, Number(state.listPages[key] || 1) + direction);
  if (key === "taskScripts") state.taskScriptPage = state.listPages[key];
  rerenderPagedList(key);
}, true);

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    closeMobileNav();
  }
});

const responsiveTableObserver = new MutationObserver((mutations) => {
  if (mutations.some((mutation) => Array.from(mutation.addedNodes).some((node) => node.nodeType === Node.ELEMENT_NODE))) {
    enhanceResponsiveTables();
  }
});
responsiveTableObserver.observe(document.body, { childList: true, subtree: true });

document.querySelectorAll("[data-overview-tab]").forEach((button) => {
  button.addEventListener("click", () => {
    state.overviewActivityTab = button.dataset.overviewTab || "scripts";
    renderOverviewActivity();
  });
});

document.querySelector("#overviewActivityContent").addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button || button.disabled) return;
  const id = Number(button.dataset.id);
  if (button.dataset.action === "overview-view-script") {
    openTaskScriptDetailDrawer(id);
    return;
  }
  if (button.dataset.action === "overview-view-task") {
    await openTaskDetailDrawer(id);
  }
});

document.querySelectorAll("[data-reference-tab]").forEach((button) => {
  button.addEventListener("click", () => setReferenceTab(button.dataset.referenceTab));
});

document.querySelector("#accountMenuButton").addEventListener("click", (event) => {
  event.stopPropagation();
  const menu = document.querySelector("#accountMenu");
  const button = document.querySelector("#accountMenuButton");
  if (!menu || !button) return;
  const willOpen = menu.classList.contains("hiddenPanel");
  menu.classList.toggle("hiddenPanel", !willOpen);
  button.setAttribute("aria-expanded", String(willOpen));
  if (willOpen) positionAccountMenu();
});

document.querySelector("#accountMenu").addEventListener("click", async (event) => {
  const button = event.target.closest("[data-account-action]");
  if (!button) return;
  hideAccountMenu();
  if (button.dataset.accountAction === "profile") {
    openAccountModal("profile");
    return;
  }
  if (button.dataset.accountAction === "password") {
    openAccountModal("password");
    return;
  }
  if (button.dataset.accountAction === "logout") {
    await logout();
  }
});

document.addEventListener("click", (event) => {
  if (!event.target.closest("#accountMenuWrap") && !event.target.closest("#accountMenu")) {
    hideAccountMenu();
  }
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    hideAccountMenu();
    closeAccountModal();
    closeHumanHelpModal();
    closeAssetDetailDrawer();
  }
});

window.addEventListener("resize", () => {
  if (!document.querySelector("#accountMenu")?.classList.contains("hiddenPanel")) {
    positionAccountMenu();
  }
});

document.querySelector("#accountModalClose").addEventListener("click", closeAccountModal);

document.querySelector("#accountModal").addEventListener("click", (event) => {
  if (event.target.id === "accountModal") closeAccountModal();
});

document.querySelector("#humanHelpBtn").addEventListener("click", openHumanHelpModal);

document.querySelector("#humanHelpModalClose").addEventListener("click", closeHumanHelpModal);

document.querySelector("#humanHelpModal").addEventListener("click", (event) => {
  if (event.target.id === "humanHelpModal") closeHumanHelpModal();
});

document.querySelector("#changePasswordForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const payload = formData(form);
  if (payload.new_password !== payload.confirm_password) {
    toast("两次输入的新密码不一致");
    return;
  }
  const button = form.querySelector("button[type='submit']");
  const originalText = button.textContent;
  button.disabled = true;
  button.textContent = "保存中...";
  try {
    await api.post("/auth/change-password", {
      current_password: payload.current_password,
      new_password: payload.new_password,
    });
    form.reset();
    closeAccountModal();
    toast("密码已更新");
  } catch (err) {
    toast(err.message || "密码修改失败");
  } finally {
    button.disabled = false;
    button.textContent = originalText;
  }
});

document.querySelector("#settings-tab-storage").addEventListener("click", async (event) => {
  const localSaveButton = event.target.closest("button[data-action='save-video-local']");
  if (localSaveButton) {
    const taskId = Number(localSaveButton.dataset.id);
    const video = state.videoStorage?.videos?.find((item) => Number(item.task_id) === taskId);
    if (!video) return;
    const originalText = localSaveButton.textContent;
    localSaveButton.disabled = true;
    localSaveButton.textContent = "保存中...";
    state.localSavingVideoIds.add(taskId);
    renderVideoStorage(state.videoStorage);
    try {
      await saveVideoToLocalFolder(video);
    } catch (error) {
      toast(error.message || "保存到电脑失败");
    } finally {
      state.localSavingVideoIds.delete(taskId);
      localSaveButton.disabled = false;
      localSaveButton.textContent = originalText;
      renderVideoStorage(state.videoStorage);
    }
    return;
  }

  const button = event.target.closest("button[data-action='copy-storage-path']");
  if (!button) return;
  const path = button.dataset.path || "";
  if (!path) return;
  try {
    await navigator.clipboard.writeText(path);
    toast("路径已复制");
  } catch {
    toast(path);
  }
});

document.querySelector("#chooseLocalSaveFolderBtn").addEventListener("click", async () => {
  const button = document.querySelector("#chooseLocalSaveFolderBtn");
  const originalText = button.textContent;
  button.disabled = true;
  button.textContent = "选择中...";
  try {
    const handle = await chooseLocalSaveDirectory();
    if (handle) {
      toast(`已选择电脑文件夹：${handle.name}`);
      if (state.autoSaveToLocalFolder && state.videoStorage?.videos) {
        void autoSaveVideosToLocal(state.videoStorage.videos);
      }
    }
  } catch (error) {
    if (error?.name !== "AbortError") {
      toast(error.message || "选择电脑文件夹失败");
    }
  } finally {
    button.disabled = false;
    button.textContent = originalText;
  }
});

document.querySelector("#autoSaveToLocalFolder").addEventListener("change", async (event) => {
  state.autoSaveToLocalFolder = event.currentTarget.checked;
  persistLocalSaveState();
  renderLocalSaveDirectoryState();
  if (state.autoSaveToLocalFolder && !state.localSaveDirectoryHandle) {
    const handle = await chooseLocalSaveDirectory();
    if (!handle) {
      state.autoSaveToLocalFolder = false;
      persistLocalSaveState();
      renderLocalSaveDirectoryState();
      return;
    }
  }
  if (state.autoSaveToLocalFolder && state.videoStorage?.videos) {
    void autoSaveVideosToLocal(state.videoStorage.videos);
  }
});

document.querySelector("#remoteUploadForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector("button[type='submit']");
  const originalText = button.textContent;
  button.disabled = true;
  button.textContent = "保存中...";
  const payload = formData(form);
  payload.enabled = form.querySelector("[name='enabled']").checked;
  payload.clear_upload_token = form.querySelector("[name='clear_upload_token']").checked;
  if (!payload.upload_token) delete payload.upload_token;
  try {
    const settings = await api.patch("/settings/remote-upload", payload);
    state.remoteUpload = settings;
    renderRemoteUpload(settings);
    toast("素材服务器配置已保存");
  } catch (error) {
    toast("保存失败，请确认上传接口是可访问的 http/https 地址");
  } finally {
    button.disabled = false;
    button.textContent = originalText;
  }
});

document.querySelectorAll(".navItem").forEach((item) => {
  item.addEventListener("click", () => {
    closeMobileNav();
    switchPage(item.dataset.page, item.dataset.settingsSection || null);
  });
});

document.querySelectorAll(".subNavItem").forEach((item) => {
  item.addEventListener("click", () => {
    closeMobileNav();
    switchPage(item.dataset.page, item.dataset.settingsSection);
  });
});

document.querySelector("#humanAssetForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const payload = new FormData(form);
  ["portrait_material_id", "source_video_material_id", "default_voice"].forEach((key) => {
    if (!payload.get(key)) payload.delete(key);
  });
  const button = form.querySelector("button[type='submit']");
  const originalText = button.textContent;
  button.disabled = true;
  button.textContent = "上传创建中...";
  try {
    const res = await fetch("/api/digital-humans/create-with-assets", {
      method: "POST",
      headers: authHeaders(),
      body: payload,
    });
    if (!res.ok) throw new Error(await res.text());
    const human = await res.json();
    state.latestHumanId = human.id;
    const taskHumanSelect = document.querySelector("#taskHumanSelect");
    if (taskHumanSelect) taskHumanSelect.value = human.id;
    toast(`数字人资产已创建 #${human.id}`);
    form.reset();
    await refresh();
  } catch (error) {
    toast(apiErrorMessage(error, "数字人创建失败，请检查头像、视频或素材配置"));
  } finally {
    button.disabled = false;
    button.textContent = originalText;
  }
});

async function generateScriptCandidates(button) {
  const form = document.querySelector("#scriptForm");
  const originalText = button.textContent;
  const payload = formData(form);
  payload.duration_seconds = Number(payload.duration_seconds);
  payload.count = Number(document.querySelector("#batchScriptCount").value || 3);
  button.disabled = true;
  button.textContent = "生成候选中...";
  renderScriptLoading(`AI 正在生成 ${payload.count} 条候选方案，审核人只需选择满意的一版...`);
  try {
    const scripts = await api.post("/scripts/batch-generate", payload);
    state.scripts = [...scripts, ...state.scripts.filter((item) => !scripts.some((script) => script.id === item.id))];
    applyGeneratedScript(scripts[0]);
    renderScriptSelects(state.scripts);
    renderScriptCandidates(state.scripts);
    toast(`已生成 ${scripts.length} 条候选方案`);
    await refresh();
  } catch (error) {
    toast("候选方案生成失败，请检查模型配置或稍后重试");
    renderScripts(state.scripts);
  } finally {
    button.disabled = false;
    button.textContent = originalText;
  }
}

document.querySelector("#scriptForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  await saveCurrentScriptEdits({ silent: true });
  await generateScriptCandidates(event.currentTarget.querySelector("button[type='submit']"));
});

function syncDurationPreset() {
  const input = document.querySelector("#scriptForm [name='duration_seconds']");
  if (!input) return;
  const value = String(Number(input.value || 0));
  const buttons = [...document.querySelectorAll(".durationPreset")];
  const matched = buttons.some((button) => button.dataset.duration === value);
  buttons.forEach((button) => {
    button.classList.toggle(
      "active",
      button.dataset.duration === value || (button.dataset.duration === "custom" && !matched),
    );
  });
}

document.querySelectorAll(".durationPreset").forEach((button) => {
  button.addEventListener("click", () => {
    const input = document.querySelector("#scriptForm [name='duration_seconds']");
    if (!input) return;
    if (button.dataset.duration !== "custom") {
      input.value = button.dataset.duration;
    }
    document.querySelectorAll(".durationPreset").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    input.focus();
  });
});

document.querySelector("#scriptForm [name='duration_seconds']").addEventListener("input", syncDurationPreset);
document.querySelector("#scriptForm [name='target_platform']").addEventListener("change", syncCreationExportProfileHint);

function selectedCreationProductionMode() {
  const select = document.querySelector("#creationProductionModeSelect");
  const humanInput = document.querySelector("#creationHumanSelect");
  const hasHuman = Boolean(humanInput?.value);
  const selected = select?.value || "";
  const recommended = recommendedCreationProductionMode(hasHuman);
  if (["talking_head_template", "digital_human"].includes(selected) && !hasRealDigitalHuman()) {
    return recommended;
  }
  if (["talking_head_template", "digital_human"].includes(selected) && !hasHuman) {
    return recommended;
  }
  if (selected === "seedance_scene" && !hasRealVideoGeneration()) {
    return recommended;
  }
  return selected || recommended;
}

function integrationIsRealReady(key) {
  const item = state.integrations?.[key] || {};
  return Boolean(item.configured && item.real_api);
}

function hasRealVideoGeneration() {
  return integrationIsRealReady("video_generation");
}

function hasRealDigitalHuman() {
  return integrationIsRealReady("digital_human");
}

function recommendedCreationProductionMode(hasHuman = Boolean(document.querySelector("#creationHumanSelect")?.value)) {
  if (hasHuman && hasRealDigitalHuman()) return "talking_head_template";
  if (hasRealVideoGeneration()) return "seedance_scene";
  return "dynamic_explainer";
}

function syncCreationProductionModeWithHuman() {
  const select = document.querySelector("#creationProductionModeSelect");
  const humanInput = document.querySelector("#creationHumanSelect");
  if (!select || !humanInput) return;
  const nextMode = recommendedCreationProductionMode(Boolean(humanInput.value));
  if (
    !select.value
    || ["talking_head_template", "digital_human"].includes(select.value)
    || (select.value === "seedance_scene" && !hasRealVideoGeneration())
  ) {
    select.value = nextMode;
  }
  syncProductionModeHint();
}

function syncProductionModeHint() {
  const select = document.querySelector("#creationProductionModeSelect");
  const hint = document.querySelector("#productionModeHint");
  if (!select || !hint) return;
  const effectiveMode = selectedCreationProductionMode();
  const suffix = effectiveMode !== select.value
    ? ` 当前接口状态下会自动改用「${productionModeLabel(effectiveMode)}」。`
    : "";
  const message = {
    dynamic_explainer: "本地图文讲解预览：不依赖外部视频模型，可生成本地 MP4，并自动烧录字幕，适合先跑通审核和保存流程。",
    digital_human: "需要选择已上传头像或口播源视频的数字人，用于后续真人嘴型驱动。",
    material_mix: "先按分镜匹配素材库素材，可人工修改；缺素材的镜头再用 Seedance 补。",
    seedance_scene: "会把分镜表拆成多个 Seedance 镜头，生成 AI 实景画面后自动拼接。",
    talking_head_template: "需要真实数字人驱动接口，会生成顶部标题、底部身份条、字幕和解释页的口播模板。",
  }[select.value] || "";
  hint.textContent = `${message}${suffix}`;
}

function isDigitalHumanProductionMode(mode) {
  return ["digital_human", "talking_head_template"].includes(mode);
}

function estimatedDigitalHumanCost(script) {
  const seconds = Math.max(15, Number(script?.duration_seconds || 60));
  const amount = seconds * 0.5;
  const amountText = amount % 1 === 0 ? String(amount) : amount.toFixed(1);
  return `预计正式数字人费用约 ${amountText} 元（按阿里 480P 0.5 元/秒估算，实际以账单为准）。`;
}

function renderVoicePreview(url, costText) {
  const panel = document.querySelector("#voicePreviewPanel");
  if (!panel) return;
  panel.classList.remove("hiddenPanel");
  panel.innerHTML = `
    <div class="voicePreviewHeader">
      <strong>口播试听</strong>
      <span class="status">先试听，再正式生成</span>
    </div>
    <audio controls autoplay src="${url}"></audio>
    <p class="resultHint">声音、语速和稿子确认满意后，再继续生成正式数字人成片。</p>
    <p class="resultHint">${escapeHtml(costText)}</p>
  `;
}

async function confirmVoicePreviewBeforeFormalGeneration(script, payload, button) {
  const costText = estimatedDigitalHumanCost(script);
  if (state.voicePreviewUrl) {
    URL.revokeObjectURL(state.voicePreviewUrl);
    state.voicePreviewUrl = "";
  }
  button.textContent = "生成口播试听...";
  const audioBlob = await api.postBlob(`/scripts/${script.id}/voice-preview`, payload);
  state.voicePreviewUrl = URL.createObjectURL(audioBlob);
  renderVoicePreview(state.voicePreviewUrl, costText);
  return window.confirm(`已生成口播试听，请先听声音和节奏。\n\n${costText}\n\n确认口播满意，并继续生成正式数字人视频吗？`);
}

document.querySelector("#creationProductionModeSelect").addEventListener("change", syncProductionModeHint);

document.querySelector("#creationHumanSelect").addEventListener("change", syncCreationProductionModeWithHuman);

async function createVideoFromScript(scriptId, button) {
  if (!scriptId) {
    toast("请先生成脚本");
    return;
  }
  const script = state.scripts.find((item) => item.id === Number(scriptId));
  if (!script) {
    toast("没有找到这条脚本，请刷新后重试");
    return;
  }
  state.latestScriptId = script.id;
  state.highlightedScriptId = script.id;
  renderScriptCandidates(state.scripts);
  const originalText = button.textContent;
  const humanInput = document.querySelector("#creationHumanSelect");
  const platformInput = document.querySelector("#scriptForm [name='target_platform']");
  const productionMode = selectedCreationProductionMode();
  const payload = {
    production_mode: productionMode,
    target_platform: platformInput?.value || script.target_platform || "douyin",
    export_profile: defaultExportProfileForPlatform(platformInput?.value || script.target_platform || "douyin"),
    subtitle_enabled: true,
    subtitle_style: document.querySelector("#creationSubtitleStyleSelect")?.value || "auto",
  };
  if (humanInput.value) {
    payload.digital_human_id = Number(humanInput.value);
  }
  if (["digital_human", "talking_head_template"].includes(productionMode) && !payload.digital_human_id) {
    toast("数字人口播需要先选择有头像或口播源视频的数字人");
    return;
  }
  button.disabled = true;
  try {
    const savedScript = (await saveCurrentScriptEdits({ silent: true })) || script;
    if (isDigitalHumanProductionMode(productionMode)) {
      const confirmed = await confirmVoicePreviewBeforeFormalGeneration(savedScript, payload, button);
      if (!confirmed) {
        toast("已生成口播试听，确认满意后再生成正式视频");
        return;
      }
    }
    button.textContent = productionMode === "material_mix" ? "创建素材方案..." : "进入生成队列...";
    const endpoint = productionMode === "material_mix" ? "video-task" : "auto-video-task";
    const task = await api.post(`/scripts/${savedScript.id}/${endpoint}`, payload);
    state.latestTaskId = task.id;
    document.querySelector("#taskForm [name='script_id']").value = task.script_id;
    const taskHumanInput = document.querySelector("#taskForm [name='digital_human_id']");
    if (task.digital_human_id && taskHumanInput) {
      taskHumanInput.value = task.digital_human_id;
    }
    toast(productionMode === "material_mix" ? `已创建素材方案任务 #${task.id}` : `已进入自动生成队列 #${task.id}`);
    await refresh();
    switchPage("tasks");
    if (productionMode === "material_mix") {
      await openTaskDetailDrawer(task.id);
    }
  } catch (error) {
    toast(apiErrorMessage(error, "自动生成视频失败，请检查视频模型或素材配置"));
  } finally {
    button.disabled = false;
    button.textContent = originalText;
  }
}

document.querySelector("#scriptCandidateList").addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-script-id]");
  if (!button) return;
  const scriptId = Number(button.dataset.scriptId);
  const script = state.scripts.find((item) => item.id === scriptId);
  if (!script) return;
  if (button.dataset.action === "auto-video-script") {
    try {
      await saveCurrentScriptEdits({ silent: true });
    } catch (error) {
      toast(apiErrorMessage(error, "当前脚本保存失败，请先检查内容"));
      return;
    }
    await createVideoFromScript(script.id, button);
    return;
  }
  openScriptDetail(script);
});

document.querySelector("#scriptPreviewCreation").addEventListener("input", (event) => {
  const form = event.target.closest("#scriptEditForm");
  if (!form) return;
  form.dataset.dirty = "true";
  const saveState = form.querySelector("#scriptEditSaveState");
  if (saveState) saveState.textContent = "有未保存修改，生成视频前会自动保存。";
});

document.querySelector("#scriptPreviewCreation").addEventListener("submit", async (event) => {
  if (event.target.id !== "scriptEditForm") return;
  event.preventDefault();
  await saveCurrentScriptEdits();
});

document.querySelector("#taskForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = formData(event.currentTarget);
  payload.script_id = Number(payload.script_id || state.latestScriptId);
  payload.digital_human_id = payload.digital_human_id ? Number(payload.digital_human_id) : null;
  if (!payload.export_profile) delete payload.export_profile;
  payload.subtitle_enabled = true;
  payload.subtitle_style = payload.subtitle_style || "auto";
  const task = await api.post("/video-tasks", payload);
  state.latestTaskId = task.id;
  toast(`视频任务已创建 #${task.id}`);
  await refresh();
});

document.querySelector("#batchCreateTasksBtn").addEventListener("click", async () => {
  const scriptIds = [...document.querySelector("#batchScriptSelect").selectedOptions]
    .map((option) => Number(option.value))
    .filter(Boolean);
  if (!scriptIds.length) {
    toast("请先选择要批量生成视频的脚本");
    return;
  }
  const humanValue = document.querySelector("#batchHumanSelect").value;
  const productionMode = document.querySelector("#batchProductionModeSelect").value;
  const payload = {
    script_ids: scriptIds,
    digital_human_id: humanValue ? Number(humanValue) : null,
    production_mode: productionMode,
    export_profile: document.querySelector("#batchExportProfileSelect").value || null,
    subtitle_enabled: true,
    subtitle_style: document.querySelector("#batchSubtitleStyleSelect").value || "auto",
  };
  if (!payload.export_profile) delete payload.export_profile;
  const tasks = await api.post("/video-tasks/batch-create", payload);
  toast(`已批量创建 ${tasks.length} 个视频任务`);
  await refresh();
  switchPage("tasks");
});

document.querySelector("#createTaskFromScriptBtn").addEventListener("click", async () => {
  const button = document.querySelector("#createTaskFromScriptBtn");
  await createVideoFromScript(state.latestScriptId, button);
});

document.querySelector("#goTaskPageBtn").addEventListener("click", () => switchPage("tasks"));

document.querySelector("#closeScriptDetailBtn").addEventListener("click", async () => {
  try {
    await saveCurrentScriptEdits({ silent: true });
  } catch (error) {
    toast("脚本保存失败，请先检查内容");
    return;
  }
  hideScriptDetail();
});

document.querySelector("#regenerateScriptBtn").addEventListener("click", async () => {
  await saveCurrentScriptEdits({ silent: true });
  document.querySelector("#scriptForm").requestSubmit();
});

document.querySelector("#titleSuggestionList").addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-title]");
  if (!button) return;
  const title = button.dataset.title;
  try {
    await saveCurrentScriptEdits({ silent: true });
  } catch (error) {
    toast("当前脚本保存失败，请先检查内容");
    return;
  }
  document.querySelectorAll(".titleOption").forEach((item) => item.classList.remove("selectedTitle"));
  button.classList.add("selectedTitle");
  const form = document.querySelector("#scriptForm");
  const payload = formData(form);
  payload.topic = `按这个标题重写完整脚本：${title}\n原始创作需求：${payload.topic}`;
  payload.duration_seconds = Number(payload.duration_seconds);
  document.querySelectorAll(".titleOption").forEach((item) => {
    item.disabled = true;
  });
  renderScriptLoading(`正在按标题「${title}」重写口播稿、分镜和视频提示词...`, true);
  try {
    if (navigator.clipboard) {
      try {
        await navigator.clipboard.writeText(title);
      } catch {
        // Copying is a convenience only; script rewriting should still run.
      }
    }
    const script = await api.post("/scripts/generate", payload);
    applyGeneratedScript(script, { openDetail: true });
    toast(`已按所选标题重写脚本 #${script.id}`);
    await refresh();
  } catch (error) {
    toast("按标题重写失败，请稍后重试");
    renderScripts(state.scripts);
  } finally {
    document.querySelectorAll(".titleOption").forEach((item) => {
      item.disabled = false;
    });
  }
});

document.querySelector("#runTaskBtn").addEventListener("click", async () => {
  if (!state.latestTaskId) {
    toast("请先创建视频任务");
    return;
  }
  const currentTask = state.videoTasks.find((item) => item.id === state.latestTaskId);
  if (currentTask && !taskActionState(currentTask).canRun) {
    toast("这个任务当前不能开始生成，请先删除成片或检查任务状态");
    return;
  }
  try {
    const task = await api.post(`/video-tasks/${state.latestTaskId}/run`);
    toast(`任务已运行：${taskStatusLabel(task.status)}`);
  } catch (error) {
    toast("这个任务当前不能开始生成，请先删除成片或检查任务状态");
  } finally {
    await refresh();
  }
});

document.querySelector("#batchRunSelectedTasksBtn").addEventListener("click", async () => {
  const taskIds = [...document.querySelectorAll(".taskSelectCheckbox:checked")]
    .map((input) => Number(input.value))
    .filter(Boolean);
  if (!taskIds.length) {
    toast("请先勾选要运行的视频任务");
    return;
  }
  const button = document.querySelector("#batchRunSelectedTasksBtn");
  const originalText = button.textContent;
  button.disabled = true;
  button.textContent = "批量运行中...";
  try {
    const tasks = await api.post("/video-tasks/batch-run", { task_ids: taskIds });
    toast(`已运行 ${tasks.length} 个视频任务`);
    await refresh();
  } catch (error) {
    toast("批量运行失败，请检查任务状态或视频模型配置");
  } finally {
    button.disabled = false;
    button.textContent = originalText;
  }
});

document.querySelector("#materialList").addEventListener("click", async (event) => {
  const detailButton = event.target.closest("button[data-action='view-material-detail']");
  if (detailButton) {
    openAssetDetailDrawer("material", detailButton.dataset.id);
    return;
  }
  const uploadButton = event.target.closest("button[data-action='remote-upload-material']");
  if (uploadButton) {
    uploadButton.disabled = true;
    const originalText = uploadButton.textContent;
    uploadButton.textContent = "上传中...";
    try {
      await api.post(`/materials/${uploadButton.dataset.id}/remote-upload`);
      toast("素材已上传到服务器");
      await refresh();
    } catch (error) {
      toast("补传失败，请先配置素材服务器上传接口");
    } finally {
      uploadButton.disabled = false;
      uploadButton.textContent = originalText;
    }
    return;
  }
  const copyButton = event.target.closest("button[data-action='copy-material-url']");
  if (copyButton) {
    try {
      await navigator.clipboard.writeText(copyButton.dataset.url || "");
      toast("云端地址已复制");
    } catch {
      toast(copyButton.dataset.url || "");
    }
    return;
  }
  const button = event.target.closest("button[data-action='delete-material']");
  if (!button) return;
  if (!window.confirm("确认删除这个素材吗？相关数字人会自动解除绑定。")) return;
  await api.delete(`/materials/${button.dataset.id}`);
  toast("素材已删除");
  await refresh();
});

document.querySelector("#humanList").addEventListener("click", async (event) => {
  const detailButton = event.target.closest("button[data-action='view-human-detail']");
  if (detailButton) {
    openAssetDetailDrawer("human", detailButton.dataset.id);
    return;
  }
  const button = event.target.closest("button[data-action='delete-human']");
  if (!button) return;
  if (!window.confirm("确认删除这个数字人吗？相关视频任务会改为不露脸。")) return;
  await api.delete(`/digital-humans/${button.dataset.id}`);
  toast("数字人已删除");
  await refresh();
});

document.querySelector("#closeAssetDetailBtn").addEventListener("click", closeAssetDetailDrawer);

document.querySelector("#assetDetailDrawer").addEventListener("click", async (event) => {
  if (event.target.id === "assetDetailDrawer") {
    closeAssetDetailDrawer();
    return;
  }
  const copyButton = event.target.closest("button[data-action='copy-material-url']");
  if (copyButton) {
    try {
      await navigator.clipboard.writeText(copyButton.dataset.url || "");
      toast("云端地址已复制");
    } catch {
      toast(copyButton.dataset.url || "");
    }
    return;
  }
  const uploadButton = event.target.closest("button[data-action='remote-upload-material']");
  if (uploadButton) {
    uploadButton.disabled = true;
    const originalText = uploadButton.textContent;
    uploadButton.textContent = "上传中...";
    try {
      await api.post(`/materials/${uploadButton.dataset.id}/remote-upload`);
      toast("素材已上传到服务器");
      closeAssetDetailDrawer();
      await refresh();
    } catch (error) {
      toast(apiErrorMessage(error, "补传失败，请先配置素材服务器上传接口"));
    } finally {
      uploadButton.disabled = false;
      uploadButton.textContent = originalText;
    }
    return;
  }
  const createAuthButton = event.target.closest("button[data-action='create-volcengine-auth']");
  if (createAuthButton) {
    createAuthButton.disabled = true;
    const originalText = createAuthButton.textContent;
    createAuthButton.textContent = "创建中...";
    const humanId = createAuthButton.dataset.id;
    try {
      const result = await api.post(`/digital-humans/${humanId}/volcengine-auth/session`, {
        callback_url: volcengineCallbackUrl(),
      });
      toast("火山真人认证链接已创建");
      await refresh();
      openAssetDetailDrawer("human", humanId);
      if (result.auth_url) window.open(result.auth_url, "_blank", "noopener,noreferrer");
    } catch (error) {
      toast(apiErrorMessage(error, "火山认证链接创建失败，请检查服务开通和 AK/SK 权限"));
    } finally {
      createAuthButton.disabled = false;
      createAuthButton.textContent = originalText;
    }
    return;
  }
  const syncAuthButton = event.target.closest("button[data-action='sync-volcengine-auth']");
  if (syncAuthButton) {
    syncAuthButton.disabled = true;
    const originalText = syncAuthButton.textContent;
    syncAuthButton.textContent = "同步中...";
    const humanId = syncAuthButton.dataset.id;
    try {
      await api.post(`/digital-humans/${humanId}/volcengine-auth/sync`);
      toast("火山真人认证结果已同步");
      await refresh();
      openAssetDetailDrawer("human", humanId);
    } catch (error) {
      toast(apiErrorMessage(error, "同步失败，完成 H5 认证后再试一次"));
    } finally {
      syncAuthButton.disabled = false;
      syncAuthButton.textContent = originalText;
    }
    return;
  }
  const openAuthButton = event.target.closest("button[data-action='open-volcengine-auth']");
  if (openAuthButton) {
    const url = openAuthButton.dataset.url || "";
    if (url) window.open(url, "_blank", "noopener,noreferrer");
    return;
  }
  const copyAuthButton = event.target.closest("button[data-action='copy-volcengine-auth-url']");
  if (copyAuthButton) {
    try {
      await navigator.clipboard.writeText(copyAuthButton.dataset.url || "");
      toast("认证链接已复制");
    } catch {
      toast(copyAuthButton.dataset.url || "");
    }
    return;
  }
  const deleteHumanButton = event.target.closest("button[data-action='delete-human']");
  if (deleteHumanButton) {
    if (!window.confirm("确认删除这个数字人吗？相关视频任务会改为不露脸。")) return;
    await api.delete(`/digital-humans/${deleteHumanButton.dataset.id}`);
    closeAssetDetailDrawer();
    toast("数字人已删除");
    await refresh();
    return;
  }
  const deleteMaterialButton = event.target.closest("button[data-action='delete-material']");
  if (deleteMaterialButton) {
    if (!window.confirm("确认删除这个素材吗？相关数字人会自动解除绑定。")) return;
    await api.delete(`/materials/${deleteMaterialButton.dataset.id}`);
    closeAssetDetailDrawer();
    toast("素材已删除");
    await refresh();
  }
});

document.querySelector("#taskScriptList").addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button || button.disabled) return;
  if (button.dataset.action === "script-page-prev") {
    state.taskScriptPage = Math.max(1, Number(state.taskScriptPage || 1) - 1);
    renderTaskScriptTable(state.scripts);
    return;
  }
  if (button.dataset.action === "script-page-next") {
    state.taskScriptPage = Number(state.taskScriptPage || 1) + 1;
    renderTaskScriptTable(state.scripts);
    return;
  }
  const scriptId = Number(button.dataset.id);
  const script = state.scripts.find((item) => Number(item.id) === scriptId);
  if (!script) return;
  if (button.dataset.action === "view-task-script") {
    openTaskScriptDetailDrawer(script.id);
    return;
  }
  if (button.dataset.action === "create-task-from-script") {
    await createTaskFromTaskScript(script.id, button);
  }
});

document.querySelectorAll("#taskListTasks, #taskList, #taskDetailDrawer").forEach((list) => list.addEventListener("click", async (event) => {
  if (event.target.id === "taskDetailDrawer") {
    closeTaskDetailDrawer();
    return;
  }
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  if (button.disabled) return;
  const id = button.dataset.id;
  if (button.dataset.action === "view-video-task" || button.dataset.action === "preview-video-task") {
    await openTaskDetailDrawer(id);
    return;
  }
  if (button.dataset.action === "view-task-script") {
    openTaskScriptDetailDrawer(id);
    return;
  }
  if (button.dataset.action === "create-task-from-script") {
    await createTaskFromTaskScript(id, button);
    return;
  }
  if (button.dataset.action === "edit-script-from-task-drawer") {
    const script = state.scripts.find((item) => Number(item.id) === Number(id));
    if (script) {
      closeTaskDetailDrawer();
      switchPage("creation");
      openScriptDetail(script);
    }
    return;
  }
  if (button.dataset.action === "assign-segment-material") {
    const taskId = Number(button.dataset.taskId || 0);
    const segmentId = Number(button.dataset.id || 0);
    const select = document.querySelector(`[data-segment-material-select="${segmentId}"]`);
    const materialId = Number(select?.value || 0);
    const originalText = button.textContent;
    button.disabled = true;
    button.textContent = "保存中";
    try {
      await api.patch(`/video-tasks/${taskId}/segments/${segmentId}/material`, {
        material_id: materialId || null,
      });
      toast(materialId ? "分镜素材已更新" : "已改为 Seedance 补镜头");
      await refresh();
      await openTaskDetailDrawer(taskId);
    } catch (error) {
      toast(apiErrorMessage(error, "素材方案保存失败"));
    } finally {
      button.disabled = false;
      button.textContent = originalText;
    }
    return;
  }
  try {
    if (button.dataset.action === "run-video-task") {
      const taskRecord = state.videoTasks.find((item) => Number(item.id) === Number(id));
      if (taskRecord && isDigitalHumanProductionMode(taskRecord.production_mode)) {
        const scriptRecord = state.scripts.find((item) => Number(item.id) === Number(taskRecord.script_id));
        const costText = estimatedDigitalHumanCost(scriptRecord || { duration_seconds: 60 });
        const confirmed = window.confirm(`这是正式数字人生成，会产生较高费用。\n\n${costText}\n\n确认现在运行任务 #${id} 吗？`);
        if (!confirmed) return;
      }
      const statusCell = button.closest("tr")?.querySelector(".status");
      button.textContent = "生成中";
      button.disabled = true;
      if (statusCell) statusCell.textContent = "生成中";
      const task = await api.post(`/video-tasks/${id}/run`);
      toast(`任务已运行：${taskStatusLabel(task.status)}`);
      closeTaskDetailDrawer();
    }
    if (button.dataset.action === "approve-video-task") {
      const task = await api.post(`/video-tasks/${id}/approve`);
      toast(`任务已审核：${taskStatusLabel(task.status)}`);
      closeTaskDetailDrawer();
    }
    if (button.dataset.action === "prepare-publish") {
      const accounts = await api.get("/platform-accounts");
      const account = accounts.find((item) => item.is_default) || accounts[0] || null;
      const record = await api.post(`/video-tasks/${id}/publish-record`, {
        platform: account ? account.platform : "douyin",
        platform_account_id: account ? account.id : null,
        account_name: account ? account.account_name : "公司官方号",
      });
      closeTaskDetailDrawer();
      toast(`发布记录已创建 #${record.id}`);
      switchPage("publish");
    }
    if (button.dataset.action === "delete-task-output") {
      if (!window.confirm("确认删除这个任务的成片文件吗？任务会保留。")) return;
      await api.delete(`/video-tasks/${id}/output`);
      closeTaskDetailDrawer();
      toast("成片已删除");
    }
    if (button.dataset.action === "delete-video-task") {
      if (!window.confirm("确认删除这个视频任务吗？关联发布记录也会删除。")) return;
      await api.delete(`/video-tasks/${id}`);
      closeTaskDetailDrawer();
      toast("视频任务已删除");
    }
  } catch (error) {
    toast(actionErrorMessage(button.dataset.action));
  }
  await refresh();
}));

document.querySelector("#closeTaskDetailBtn").addEventListener("click", closeTaskDetailDrawer);

document.querySelector("#closeTaskPreviewBtn").addEventListener("click", () => {
  state.previewTaskId = null;
  renderTaskOutputPreview(null);
});

document.querySelector("#platformAccountForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = formData(event.currentTarget);
  payload.is_default = Boolean(event.currentTarget.querySelector("[name='is_default']").checked);
  const account = await api.post("/platform-accounts", payload);
  toast(`平台账号已保存 #${account.id}`);
  event.currentTarget.reset();
  event.currentTarget.querySelector("[name='is_default']").checked = true;
  await refresh();
});

document.querySelector("#platformAccountList").addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  if (button.dataset.action === "set-default-account") {
    const account = await api.post(`/platform-accounts/${button.dataset.id}/set-default`);
    toast(`默认账号已切换为 ${account.account_name}`);
    await refresh();
  }
});

document.querySelector("#publishRecordList").addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const id = button.dataset.id;
  if (button.dataset.action === "save-publish") {
    const form = button.closest(".publishEditForm");
    const payload = formData(form);
    payload.platform_account_id = payload.platform_account_id ? Number(payload.platform_account_id) : null;
    const record = await api.patch(`/publish-records/${id}`, payload);
    toast(`发布记录已保存 #${record.id}`);
  }
  if (button.dataset.action === "mark-published") {
    const record = await api.post(`/publish-records/${id}/mark-published`);
    toast(`已标记发布 #${record.id}`);
  }
  if (button.dataset.action === "fail-publish") {
    const record = await api.post(`/publish-records/${id}/fail`);
    toast(`已标记失败 #${record.id}`);
  }
  if (button.dataset.action === "cancel-publish") {
    const record = await api.post(`/publish-records/${id}/cancel`);
    toast(`已取消发布 #${record.id}`);
  }
  await refresh();
});

document.querySelector("#modelConfigForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const payload = formData(event.currentTarget);
  const modelId = form.dataset.modelId;
  payload.is_active = Boolean(form.querySelector("[name='is_active']").checked);
  if (!payload.api_key) delete payload.api_key;
  const config = modelId ? await api.patch(`/settings/models/${modelId}`, payload) : await api.post("/settings/models", payload);
  toast(`模型配置已保存 #${config.id}`);
  form.dataset.modelId = config.id;
  await refresh();
});

document.querySelector(".modelPresetBar").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-model-preset]");
  if (!button) return;
  const preset = modelPresets[button.dataset.modelPreset];
  if (!preset) return;
  const existing = findModelConfig(preset.purpose, preset.provider);
  fillModelConfigForm(preset, existing);
  toast(existing ? `已载入已有配置：${existing.name}` : `已填入${button.textContent.trim()}配置`);
});

document.querySelector("#modelConfigList").addEventListener("click", async (event) => {
  const editButton = event.target.closest("button[data-action='edit-model-config']");
  if (!editButton) return;
  const model = state.modelConfigs.find((item) => String(item.id) === String(editButton.dataset.id));
  if (!model) return;
  fillModelConfigForm(model, model);
  toast(`已载入 ${model.name}`);
});

document.querySelector("#modelConfigList").addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button || button.disabled || button.dataset.action === "edit-model-config") return;
  const id = button.dataset.id;
  const resultTarget = document.querySelector("#modelTestResult");
  if (button.dataset.action === "activate-model-config") {
    const config = await api.post(`/settings/models/${id}/activate`);
    toast(`${config.name} 已启用`);
    await refresh();
    return;
  }
  if (button.dataset.action === "test-model-config") {
    const originalText = button.textContent;
    button.disabled = true;
    button.textContent = "测试中...";
    if (resultTarget) {
      resultTarget.innerHTML = "正在测试模型连接...";
    }
    try {
      const result = await api.post(`/settings/models/${id}/test`);
      const testTitle = result.test_level === "configuration" ? "配置体检通过" : result.test_level === "local" ? "本地模式可用" : "测试通过";
      if (resultTarget) {
        resultTarget.innerHTML = `
          <strong>${testTitle} · ${escapeHtml(result.provider || "-")} / ${escapeHtml(result.model_name || "-")}</strong>
          <span>评分 ${Number(result.quality_score || 0).toFixed(0)} 分</span>
          <p>${escapeHtml(result.summary || "模型连接可用。")}</p>
        `;
      }
      toast(`${testTitle}：${Number(result.quality_score || 0).toFixed(0)} 分`);
      await refresh();
    } catch (error) {
      const message = error?.message || "模型测试失败";
      if (resultTarget) {
        resultTarget.innerHTML = `<strong>测试失败</strong><p>${escapeHtml(message)}</p>`;
      }
      toast(message);
    } finally {
      button.disabled = false;
      button.textContent = originalText;
    }
  }
});

document.querySelector("#platformCredentialForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = formData(event.currentTarget);
  payload.is_active = Boolean(event.currentTarget.querySelector("[name='is_active']").checked);
  const credential = await api.post("/settings/platform-credentials", payload);
  toast(`平台接入已保存 #${credential.id}`);
  event.currentTarget.reset();
  event.currentTarget.querySelector("[name='is_active']").checked = true;
  await refresh();
});

document.querySelector("#platformCredentialForm").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-action='fill-link-resolver-preset']");
  if (!button) return;
  const preset = linkResolverPresets[button.dataset.preset];
  if (!preset) return;
  const form = event.currentTarget;
  fillForm(form, preset);
  const activeField = form.querySelector("[name='is_active']");
  if (activeField) activeField.checked = true;
  toast(`${preset.display_name} 已填入表单`);
});

document.querySelector("#platformCredentialList").addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  if (button.dataset.action === "activate-platform-credential") {
    const credential = await api.post(`/settings/platform-credentials/${button.dataset.id}/activate`);
    toast(`${credential.display_name} 已启用`);
    await refresh();
  }
});

document.querySelector("#linkResolverTestForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector("button[type='submit']");
  const resultTarget = document.querySelector("#linkResolverTestResult");
  const originalText = button.textContent;
  button.disabled = true;
  button.textContent = "测试中...";
  if (resultTarget) {
    resultTarget.className = "linkResolverTestResult";
    resultTarget.textContent = "正在解析链接...";
  }
  try {
    const result = await api.post("/settings/link-resolver/test", formData(form));
    const statusText = result.can_download ? "可解析并可下载" : result.can_resolve ? "已解析但下载待确认" : "未解析出视频";
    const statusClass = result.can_download ? "ok" : result.can_resolve ? "pending" : "blocked";
    if (resultTarget) {
      const diagnostics = Array.isArray(result.diagnostics) && result.diagnostics.length
        ? `<ul class="diagnosticList">${result.diagnostics
            .slice(0, 4)
            .map((item) => `<li>${escapeHtml(item)}</li>`)
            .join("")}</ul>`
        : "";
      resultTarget.className = `linkResolverTestResult ${statusClass}`;
      resultTarget.innerHTML = `
        <strong>${statusText}</strong>
        <span>平台：${platformLabel(result.platform)} · 解析器：${escapeHtml(result.resolver || "-")} · 已启用解析服务 ${Number(result.configured_resolver_count || 0)} 个</span>
        ${result.title ? `<span>标题：${escapeHtml(result.title)}</span>` : ""}
        ${result.media_url_preview ? `<span>视频地址：${escapeHtml(result.media_url_preview)}</span>` : ""}
        <p>${escapeHtml(result.message || "")}</p>
        ${diagnostics}
      `;
    }
    toast(statusText);
  } catch (error) {
    if (resultTarget) {
      resultTarget.className = "linkResolverTestResult blocked";
      resultTarget.innerHTML = `<strong>测试失败</strong><p>${escapeHtml(error.message || "请检查链接或接口配置")}</p>`;
    }
    toast("链接解析测试失败");
  } finally {
    button.disabled = false;
    button.textContent = originalText;
  }
});

document.querySelector("#userAccountForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = formData(event.currentTarget);
  payload.is_active = Boolean(event.currentTarget.querySelector("[name='is_active']").checked);
  const user = await api.post("/settings/users", payload);
  toast(`账号已新增：${user.username}`);
  event.currentTarget.reset();
  event.currentTarget.querySelector("[name='is_active']").checked = true;
  await refresh();
});

document.querySelector("#userAccountList").addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const id = button.dataset.id;
  const row = button.closest("tr");
  if (button.dataset.action === "save-user") {
    const payload = {
      role: row.querySelector("[data-field='role']").value,
      is_active: row.querySelector("[data-field='is_active']").value === "true",
    };
    const user = await api.patch(`/settings/users/${id}`, payload);
    toast(`账号已保存：${user.username}`);
    await refresh();
  }
  if (button.dataset.action === "reset-user-password") {
    const password = window.prompt("请输入新的临时密码，至少 6 位");
    if (!password) return;
    const user = await api.post(`/settings/users/${id}/reset-password`, { password });
    toast(`已重置密码：${user.username}`);
    await refresh();
  }
});

document.querySelector("#wechatLoginConfigForm")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector("button[type='submit']");
  const originalText = button?.textContent || "";
  if (button) {
    button.disabled = true;
    button.textContent = "保存中...";
  }
  try {
    const payload = formData(form);
    payload.app_id = String(payload.app_id || "").trim();
    payload.redirect_uri = String(payload.redirect_uri || "").trim() || `${window.location.origin}/api/auth/wechat/callback`;
    payload.is_active = Boolean(form.querySelector("[name='is_active']").checked);
    if (!payload.app_id) {
      toast("请填写微信开放平台 AppID");
      return;
    }
    const existingHasSecret = Boolean(state.wechatLoginConfig?.has_app_secret);
    if (!existingHasSecret && !payload.app_secret) {
      toast("首次保存需要填写 AppSecret");
      return;
    }
    if (!payload.app_secret) delete payload.app_secret;
    const config = await api.post("/settings/wechat-login/config", payload);
    toast(config.is_active ? "微信扫码登录已启用" : "微信扫码登录配置已保存");
    await refresh();
  } catch (error) {
    toast(apiErrorMessage(error, "微信登录配置保存失败"));
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = originalText;
    }
  }
});

document.querySelector("#wechatSecretEditBtn")?.addEventListener("click", () => {
  const input = document.querySelector("#wechatLoginConfigForm [name='app_secret']");
  if (!input) return;
  input.disabled = false;
  input.placeholder = "请输入新的 AppSecret，保存后会覆盖旧密钥";
  input.focus();
});

document.querySelector("#wechatLoginRequestList")?.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const row = button.closest("tr");
  const id = button.dataset.id;
  if (button.dataset.action === "approve-wechat-request") {
    const mode = row.querySelector("[data-field='approve_mode']").value;
    const payload = { mode };
    if (mode === "bind_existing") {
      payload.user_id = Number(row.querySelector("[data-field='user_id']").value || 0);
      if (!payload.user_id) {
        toast("请选择要绑定的系统用户");
        return;
      }
    } else {
      payload.username = row.querySelector("[data-field='username']").value.trim();
      payload.role = row.querySelector("[data-field='role']").value;
      if (!payload.username) {
        toast("请填写新用户名");
        return;
      }
    }
    await api.post(`/settings/wechat-login/requests/${id}/approve`, payload);
    toast("微信登录申请已批准");
    await refresh();
  }
  if (button.dataset.action === "reject-wechat-request") {
    const reason = window.prompt("请输入拒绝原因，可留空") || "";
    await api.post(`/settings/wechat-login/requests/${id}/reject`, { reason });
    toast("微信登录申请已拒绝");
    await refresh();
  }
});

document.querySelector("#wechatIdentityList")?.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action='disable-wechat-identity']");
  if (!button) return;
  await api.post(`/settings/wechat-login/identities/${button.dataset.id}/disable`);
  toast("微信绑定已停用");
  await refresh();
});

document.querySelector("#modelConfigForm [name='purpose']").addEventListener("change", () => {
  const model = document.querySelector("#modelConfigForm [name='model_name']");
  model.value = "";
  model.dataset.autofilled = "true";
  syncProviderOptions();
});

document.querySelector("#providerSelect").addEventListener("change", applyProviderDefaultModel);

document.querySelector("#modelConfigForm [name='model_name']").addEventListener("input", (event) => {
  event.currentTarget.dataset.autofilled = "false";
});

document.querySelector("#modelConfigForm [name='api_base']").addEventListener("input", (event) => {
  event.currentTarget.dataset.autofilled = "false";
});

document.querySelector("#referenceLinkPlatformSelect")?.addEventListener("change", syncReferencePlatformHint);

document.querySelector("#trendingPlatformSelect")?.addEventListener("change", syncTrendingPlatformHint);

document.querySelector("#trendingSearchForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = formData(event.currentTarget);
  const search = await api.post("/trending/searches", payload);
  state.latestTrendingSearchId = search.id;
  const platform = payload.platform || search.platform;
  toast(
    hasRealTrendingProviderFor(platform)
      ? `采集任务已创建 #${search.id}`
      : `采集任务已创建 #${search.id}，${platformLabel(platform)}真实采集配置未启用`,
  );
  await refresh();
});

document.querySelector("#runTrendingBtn").addEventListener("click", async () => {
  if (!state.latestTrendingSearchId) {
    toast("请先创建采集任务");
    return;
  }
  const latestSearch = state.trendingSearches.find((item) => Number(item.id) === Number(state.latestTrendingSearchId));
  if (latestSearch && !hasRealTrendingProviderFor(latestSearch.platform)) {
    toast(`${platformLabel(latestSearch.platform)}真实主题采集未配置，请先在短视频采集接入配置服务`);
    return;
  }
  const search = await api.post(`/trending/searches/${state.latestTrendingSearchId}/run`);
  toast(`采集完成：${search.result_count} 条参考`);
  await refresh();
});

document.querySelector("#trendingManualForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const video = await api.post("/trending/videos", formData(event.currentTarget));
  toast(`参考视频已保存 #${video.id}`);
  event.currentTarget.reset();
  await refresh();
});

document.querySelector("#trendingVideoList").addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action='save-trending-reference']");
  if (!button) return;
  const video = state.trendingVideos.find((item) => String(item.id) === String(button.dataset.id));
  if (!video || !video.source_url) {
    toast("这条参考没有可保存的链接");
    return;
  }
  button.disabled = true;
  const originalText = button.textContent;
  button.textContent = "保存中...";
  try {
    const material = await api.post("/reference-materials/from-link", {
      source_url: video.source_url,
      title: video.title,
      platform: video.platform,
      tags: `爆款采集,${video.tags || ""}`,
      download: true,
    });
    toast(`已保存到参考素材 #${material.id}`);
    setPage("analysis");
    setReferenceTab("history");
    await refresh();
  } catch (error) {
    toast(apiErrorMessage(error, "保存参考素材失败"));
  } finally {
    button.disabled = false;
    button.textContent = originalText;
  }
});

async function createAndRunVideoAnalysis(materialId, language = "zh-CN", button = null) {
  const originalText = button ? button.textContent : "";
  if (button) {
    button.disabled = true;
    button.textContent = "拆解中...";
  }
  try {
    const created = await api.post("/video-analyses", {
      material_id: Number(materialId),
      provider: "local",
      language,
    });
    state.latestVideoAnalysisId = created.id;
    const task = await api.post(`/video-analyses/${created.id}/run`);
    state.latestVideoAnalysisId = task.id;
    if (task.status === "failed") {
      throw new Error(task.error_message || "深度拆解失败");
    }
    return task;
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = originalText;
    }
  }
}

async function generateScriptFromAnalysis(analysisId, button = null) {
  if (!analysisId) {
    toast("请先完成深度拆解");
    return;
  }
  const originalText = button ? button.textContent : "";
  if (button) {
    button.disabled = true;
    button.textContent = "生成中...";
  }
  try {
    const script = await api.post(`/video-analyses/${analysisId}/generate-script`);
    state.latestScriptId = script.id;
    state.highlightedScriptId = script.id;
    toast(`已按拆解模板生成原创脚本 #${script.id}`);
    await refresh();
    closeAnalysisDetailDrawer();
    switchPage("creation");
  } catch {
    toast("生成脚本失败，请先采纳拆解结果并检查脚本模型配置");
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = originalText;
    }
  }
}

async function saveReferenceLinkAndMaybeAnalyze(form, options = { analyze: false }) {
  const payload = formData(form);
  const language = payload.language || "zh-CN";
  delete payload.language;
  payload.download = Boolean(options.analyze);
  if (!payload.source_url) {
    toast("请先粘贴视频链接");
    return;
  }
  const button = options.button || null;
  const originalText = button ? button.textContent : "";
  if (button) {
    button.disabled = true;
    button.textContent = options.analyze ? "保存并拆解中..." : "保存中...";
  }
  try {
    const material = await api.post("/reference-materials/from-link", payload);
    state.latestSourceVideoId = material.id;
    const select = document.querySelector("#analysisMaterialSelect");
    if (select) {
      select.value = String(material.id);
      renderAnalysisMaterialPreview();
    }
    if (options.analyze && material.file_path) {
      const task = await createAndRunVideoAnalysis(material.id, language);
      toast(`已保存并完成深度拆解：${analysisStatusLabel(task.status)}`);
      form.reset();
      await refresh();
      renderAnalysisDetailDrawer(task.id);
      return;
    } else if (options.analyze) {
      toast("链接已保存，但还没解析出视频文件；请配置链接解析服务或上传源文件");
    } else {
      toast(`参考素材已保存 #${material.id}`);
    }
    form.reset();
    await refresh();
    setReferenceTab("history");
  } catch (error) {
    toast(error.message || "参考链接保存失败");
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = originalText;
    }
  }
}

document.querySelector("#referenceLinkForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  await saveReferenceLinkAndMaybeAnalyze(event.currentTarget, {
    analyze: true,
    button: event.submitter,
  });
});

document.querySelector("#saveReferenceOnlyBtn").addEventListener("click", async (event) => {
  const form = document.querySelector("#referenceLinkForm");
  await saveReferenceLinkAndMaybeAnalyze(form, {
    analyze: false,
    button: event.currentTarget,
  });
});

document.querySelector("#analysisMaterialSelect").addEventListener("change", () => {
  renderAnalysisMaterialPreview();
  renderReferenceMaterials();
});

document.querySelector("#goAssetPageBtn").addEventListener("click", () => switchPage("humans"));

document.querySelector("#createVideoAnalysisBtn").addEventListener("click", async () => {
  const select = document.querySelector("#analysisMaterialSelect");
  const language = document.querySelector("#transcriptionForm [name='language']").value || "zh-CN";
  if (!select.value) {
    toast("请先选择参考视频素材");
    return;
  }
  const material = state.materials.find((item) => String(item.id) === String(select.value));
  if (material && !material.file_path) {
    toast("这个参考素材只有链接，还没有本地视频文件，请上传源文件或使用可下载直链");
    return;
  }
  const button = document.querySelector("#createVideoAnalysisBtn");
  try {
    const task = await createAndRunVideoAnalysis(Number(select.value), language, button);
    toast(`深度拆解完成：${analysisStatusLabel(task.status)}`);
    await refresh();
    renderAnalysisDetailDrawer(task.id);
  } catch (error) {
    toast(error.message || "深度拆解失败，请确认素材是本地视频文件");
  }
});

document.querySelector("#transcriptionForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = formData(event.currentTarget);
  if (!payload.material_id) {
    toast("请先选择参考素材");
    return;
  }
  const material = state.materials.find((item) => String(item.id) === String(payload.material_id));
  if (material && !material.file_path) {
    toast("这个参考素材只有链接，还没有本地视频或音频文件，不能转写");
    return;
  }
  const button = event.submitter;
  const originalText = button ? button.textContent : "";
  if (button) {
    button.disabled = true;
    button.textContent = "转写中...";
  }
  payload.material_id = Number(payload.material_id);
  try {
    const created = await api.post("/transcriptions", payload);
    state.latestTranscriptionId = created.id;
    const task = await api.post(`/transcriptions/${created.id}/run`);
    state.latestTranscriptionId = task.id;
    toast(`口播转写完成：${transcriptionStatusLabel(task.status)}`);
    await refresh();
  } catch {
    toast("转写失败，请确认 ASR 模型和素材文件可用");
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = originalText;
    }
  }
});

const runTranscriptionBtn = document.querySelector("#runTranscriptionBtn");
if (runTranscriptionBtn) {
  runTranscriptionBtn.addEventListener("click", async () => {
    if (!state.latestTranscriptionId) {
      toast("请先创建转写任务");
      return;
    }
    const task = await api.post(`/transcriptions/${state.latestTranscriptionId}/run`);
    toast(`转写完成：${transcriptionStatusLabel(task.status)}`);
    await refresh();
  });
}

const transcriptionList = document.querySelector("#transcriptionList");
if (transcriptionList) transcriptionList.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const id = button.dataset.id;
  if (button.dataset.action === "topic-from-transcription") {
    const topic = await api.post(`/transcriptions/${id}/create-topic`);
    document.querySelector("#scriptForm textarea[name='topic']").value = topic.title;
    toast(`已生成选题 #${topic.id}`);
    switchPage("creation");
  }
  if (button.dataset.action === "script-from-transcription") {
    const script = await api.post(`/transcriptions/${id}/generate-script`);
    state.latestScriptId = script.id;
    document.querySelector("[name='script_id']").value = script.id;
    toast(`已生成脚本 #${script.id}`);
    await refresh();
    switchPage("creation");
  }
});

document.querySelector("#referenceMaterialList").addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button || button.disabled) return;
  const materialId = Number(button.dataset.id);
  if (button.dataset.action === "view-reference-material") {
    openAssetDetailDrawer("material", materialId);
    return;
  }
  if (button.dataset.action === "open-reference-source") {
    const url = button.dataset.url || "";
    if (url) window.open(url, "_blank", "noopener,noreferrer");
    return;
  }
  if (button.dataset.action === "select-reference-material") {
    const select = document.querySelector("#analysisMaterialSelect");
    if (select) {
      select.value = String(materialId);
      renderAnalysisMaterialPreview();
      renderReferenceMaterials();
    }
    setReferenceTab("current");
    toast(`已选择参考素材 #${materialId}`);
    return;
  }
  if (button.dataset.action === "view-reference-analysis") {
    renderAnalysisDetailDrawer(Number(button.dataset.id));
    return;
  }
  if (button.dataset.action === "resolve-reference-material") {
    const originalText = button.textContent;
    try {
      button.disabled = true;
      button.textContent = "解析中...";
      const material = await api.post(`/reference-materials/${materialId}/resolve-download`);
      toast(material.file_path ? "已解析并下载源视频" : "仍未解析出视频文件，请检查解析服务配置");
      await refresh();
      const select = document.querySelector("#analysisMaterialSelect");
      if (select) {
        select.value = String(material.id);
        renderAnalysisMaterialPreview();
      }
    } catch (error) {
      toast(error.message || "解析下载失败");
    } finally {
      button.disabled = false;
      button.textContent = originalText;
    }
    return;
  }
  if (button.dataset.action === "analyze-reference-material") {
    const language = document.querySelector("#transcriptionForm [name='language']").value || "zh-CN";
    const material = state.materials.find((item) => Number(item.id) === materialId);
    if (!material || !material.file_path) {
      toast("这个素材还没有本地视频文件，不能深度拆解");
      return;
    }
    try {
      const task = await createAndRunVideoAnalysis(materialId, language, button);
      toast(`深度拆解完成：${analysisStatusLabel(task.status)}`);
      await refresh();
      renderAnalysisDetailDrawer(task.id);
    } catch (error) {
      toast(error.message || "深度拆解失败");
    }
    return;
  }
  if (button.dataset.action === "script-from-reference-analysis") {
    await generateScriptFromAnalysis(Number(button.dataset.id), button);
  }
});

document.querySelector("#openSelectedAnalysisDetailBtn").addEventListener("click", () => {
  const materialId = Number(document.querySelector("#analysisMaterialSelect").value || 0);
  if (!materialId) {
    toast("请先选择参考素材");
    return;
  }
  const analysis = latestAnalysisForMaterial(materialId);
  if (!analysis) {
    toast("这个素材还没有拆解结果");
    return;
  }
  renderAnalysisDetailDrawer(analysis.id);
});

document.querySelector("#closeAnalysisDetailBtn").addEventListener("click", closeAnalysisDetailDrawer);

document.querySelector("#analysisDetailDrawer").addEventListener("click", (event) => {
  if (event.target.id === "analysisDetailDrawer") closeAnalysisDetailDrawer();
});

document.querySelector("#analysisDetailContent").addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button || button.disabled) return;
  const analysisId = Number(button.dataset.id);
  const originalText = button.textContent;
  try {
    if (button.dataset.action === "approve-reference-analysis") {
      button.disabled = true;
      button.textContent = "采纳中...";
      const task = await api.post(`/video-analyses/${analysisId}/approve`);
      toast(`已采纳为参考模板：${analysisStatusLabel(task.status)}`);
      await refresh();
      renderAnalysisDetailDrawer(task.id);
      return;
    }
    if (button.dataset.action === "reject-reference-analysis") {
      button.disabled = true;
      button.textContent = "处理中...";
      const task = await api.post(`/video-analyses/${analysisId}/reject`);
      toast(`已标记不采用：${analysisStatusLabel(task.status)}`);
      await refresh();
      renderAnalysisDetailDrawer(task.id);
      return;
    }
    if (button.dataset.action === "script-from-drawer-analysis") {
      await generateScriptFromAnalysis(analysisId, button);
    }
  } catch {
    toast("操作失败，请稍后再试");
  } finally {
    button.disabled = false;
    button.textContent = originalText;
  }
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    closeAnalysisDetailDrawer();
    closeAssetDetailDrawer();
  }
});

const videoAnalysisList = document.querySelector("#videoAnalysisList");
if (videoAnalysisList) videoAnalysisList.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button || button.disabled) return;
  const id = Number(button.dataset.id);
  if (button.dataset.action === "view-video-analysis-detail") {
    renderAnalysisDetailDrawer(id);
    return;
  }
  if (button.dataset.action === "run-video-analysis") {
    const originalText = button.textContent;
    try {
      button.disabled = true;
      button.textContent = "拆解中...";
      const task = await api.post(`/video-analyses/${id}/run`);
      state.latestVideoAnalysisId = task.id;
      toast(`深度拆解完成：${analysisStatusLabel(task.status)}`);
      await refresh();
    } catch {
      toast("深度拆解失败，请确认素材是本地视频文件");
    } finally {
      button.disabled = false;
      button.textContent = originalText;
    }
    return;
  }
  if (button.dataset.action === "script-from-video-analysis") {
    await generateScriptFromAnalysis(id, button);
  }
});

initLocalSaveDirectory().finally(() => {
  if (api.token) {
    api.get("/auth/me")
      .then((user) => {
        setLoginState(user);
        refresh().catch((err) => toast(err.message));
      })
      .catch(() => {
        localStorage.removeItem("authToken");
        api.token = null;
        redirectToLogin();
      });
  } else {
    redirectToLogin();
  }
});

const initialRoute = parseRoute(window.location.hash);
switchPage(initialRoute.page, initialRoute.section, false);

syncProviderOptions();
syncProductionModeHint();

setInterval(() => {
  if (!api.token || !state.autoSaveToLocalFolder || !state.localSaveDirectoryHandle) return;
  if (!["settings", "tasks"].includes(state.currentPage)) return;
  refresh().catch(() => {});
}, 15000);
