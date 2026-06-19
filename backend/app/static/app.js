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
  async patch(path, body = {}) {
    const res = await fetch(`/api${path}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify(body),
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
  latestTrendingSearchId: null,
  latestTranscriptionId: null,
  currentPage: "overview",
  platformAccounts: [],
  publishRecords: [],
};

const pages = {
  overview: { title: "运营总览", eyebrow: "Overview" },
  materials: { title: "素材库", eyebrow: "Assets" },
  creation: { title: "内容创作", eyebrow: "Creation" },
  analysis: { title: "参考解析", eyebrow: "ASR Analysis" },
  humans: { title: "数字人", eyebrow: "Digital Human" },
  tasks: { title: "视频任务", eyebrow: "Video Tasks" },
  trending: { title: "爆款采集", eyebrow: "Trending" },
  publish: { title: "发布中心", eyebrow: "Publishing" },
  settings: { title: "系统设置", eyebrow: "Settings" },
};

const providerOptions = {
  script: [
    { value: "openai-compatible", label: "OpenAI 兼容接口", model: "gpt-4.1-mini" },
    { value: "deepseek", label: "DeepSeek", model: "deepseek-chat" },
    { value: "doubao", label: "豆包 / 火山方舟", model: "doubao-seed-1-6" },
    { value: "tongyi", label: "通义千问", model: "qwen-plus" },
    { value: "qwen-local", label: "Qwen 本地模型", model: "Qwen3-Instruct" },
    { value: "vllm", label: "vLLM 自建服务", model: "Qwen/Qwen3-30B-A3B-Instruct-2507" },
  ],
  tts: [
    { value: "cosyvoice", label: "CosyVoice", model: "cosyvoice-v2" },
    { value: "fish-speech", label: "Fish Speech", model: "fish-speech" },
    { value: "volcengine-tts", label: "火山语音", model: "volcano-tts" },
    { value: "aliyun-tts", label: "阿里云语音", model: "cosyvoice-v1" },
    { value: "mock", label: "Mock 测试", model: "mock-tts" },
  ],
  video: [
    { value: "seedance", label: "Seedance", model: "seedance" },
    { value: "comfyui", label: "ComfyUI", model: "wan2.1-workflow" },
    { value: "wan", label: "Wan2.1", model: "wan2.1-t2v-1.3b" },
    { value: "hunyuan-video", label: "HunyuanVideo", model: "hunyuan-video" },
    { value: "mock", label: "Mock 测试", model: "mock-video" },
  ],
  asr: [
    { value: "volcengine", label: "火山引擎 / 豆包 ASR", model: "volcengine-asr" },
    { value: "openai-compatible", label: "OpenAI 兼容转写", model: "whisper-1" },
    { value: "whisperx", label: "WhisperX 本地服务", model: "whisperx-large-v3" },
    { value: "mock", label: "Mock 测试", model: "mock-asr" },
  ],
  compliance: [
    { value: "openai-compatible", label: "OpenAI 兼容接口", model: "gpt-4.1-mini" },
    { value: "deepseek", label: "DeepSeek", model: "deepseek-chat" },
    { value: "doubao", label: "豆包 / 火山方舟", model: "doubao-seed-1-6" },
    { value: "tongyi", label: "通义千问", model: "qwen-plus" },
  ],
};

function authHeaders() {
  return api.token ? { Authorization: `Bearer ${api.token}` } : {};
}

function formData(form) {
  return Object.fromEntries(new FormData(form).entries());
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
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

function toast(message) {
  const el = document.querySelector("#toast");
  el.textContent = message;
  el.classList.add("show");
  setTimeout(() => el.classList.remove("show"), 2600);
}

function switchPage(page) {
  state.currentPage = page;
  document.querySelectorAll(".page").forEach((el) => el.classList.remove("activePage"));
  document.querySelector(`#page-${page}`)?.classList.add("activePage");
  document.querySelectorAll(".navItem").forEach((el) => el.classList.toggle("active", el.dataset.page === page));
  document.querySelector("#pageTitle").textContent = pages[page].title;
  document.querySelector("#pageEyebrow").textContent = pages[page].eyebrow;
  window.location.hash = page;
}

function syncProviderOptions() {
  const form = document.querySelector("#modelConfigForm");
  const purpose = form.querySelector("[name='purpose']").value;
  const provider = form.querySelector("[name='provider']");
  const model = form.querySelector("[name='model_name']");
  const options = providerOptions[purpose] || providerOptions.script;
  provider.innerHTML = options.map((item) => `<option value="${item.value}">${item.label}</option>`).join("");
  if (!model.value || model.dataset.autofilled === "true") {
    model.value = options[0].model;
    model.dataset.autofilled = "true";
  }
}

function applyProviderDefaultModel() {
  const form = document.querySelector("#modelConfigForm");
  const purpose = form.querySelector("[name='purpose']").value;
  const provider = form.querySelector("[name='provider']").value;
  const model = form.querySelector("[name='model_name']");
  const selected = (providerOptions[purpose] || []).find((item) => item.value === provider);
  if (selected) {
    model.value = selected.model;
    model.dataset.autofilled = "true";
  }
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
  };
  document.querySelector("#overview").innerHTML = Object.entries(labels)
    .map(([key, label]) => `<div class="metric"><strong>${counts[key] ?? 0}</strong><span>${label}</span></div>`)
    .join("");
}

function renderScripts(scripts) {
  const targets = [
    document.querySelector("#scriptPreview"),
    document.querySelector("#scriptPreviewCreation"),
  ].filter(Boolean);
  if (!scripts.length) {
    targets.forEach((target) => {
      target.className = "preview empty";
      target.textContent = "还没有脚本";
    });
    return;
  }
  const script = scripts[0];
  state.latestScriptId = script.id;
  document.querySelector("[name='script_id']").value = script.id;
  const content = [
    `脚本 ID: ${script.id}`,
    `开头: ${script.hook}`,
    "",
    "口播:",
    script.voiceover,
    "",
    "分镜:",
    script.storyboard,
    "",
    "标题:",
    script.title_options,
    "",
    `标签: ${script.hashtags}`,
    `合规: ${script.compliance_notes}`,
  ].join("\n");
  targets.forEach((target) => {
    target.className = "preview";
    target.textContent = content;
  });
}

function renderTasks(tasks) {
  const targets = [
    document.querySelector("#taskList"),
    document.querySelector("#taskListTasks"),
  ].filter(Boolean);
  if (!tasks.length) {
    targets.forEach((target) => {
      target.innerHTML = `<div class="item">还没有视频任务</div>`;
    });
    return;
  }
  state.latestTaskId = tasks[0].id;
  const html = tasks
    .map(
      (task) => `
        <div class="item">
          <strong>任务 #${task.id}</strong>
          <div>脚本 ID: ${task.script_id}</div>
          <div>数字人 ID: ${task.digital_human_id ?? "-"}</div>
          <span class="status">${task.status}</span>
          ${task.output_path ? `<div>${task.output_path}</div>` : ""}
          <div class="itemActions">
            <button type="button" data-action="run-video-task" data-id="${task.id}">运行</button>
            <button type="button" class="secondary" data-action="approve-video-task" data-id="${task.id}">审核通过</button>
            <button type="button" class="secondary" data-action="prepare-publish" data-id="${task.id}">准备发布</button>
          </div>
        </div>
      `,
    )
    .join("");
  targets.forEach((target) => {
    target.innerHTML = html;
  });
}

function renderPublishRecords(records) {
  const target = document.querySelector("#publishRecordList");
  if (!target) return;
  renderPublishStatusBoard(records);
  if (!records.length) {
    target.innerHTML = `<div class="item">还没有发布记录</div>`;
    return;
  }
  target.innerHTML = records
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
    .join("");
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
  target.innerHTML = accounts
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
    .join("");
}

function renderIntegrations(status) {
  const labels = {
    script_model: "脚本模型",
    tts: "语音合成",
    digital_human: "数字人",
    video_generation: "视频生成",
    composition: "视频合成",
    trending_search: "爆款采集",
    asr: "语音识别",
  };
  document.querySelector("#integrationStatus").innerHTML = Object.entries(labels)
    .map(([key, label]) => {
      const item = status[key] || {};
      const configured = item.configured ? "已配置" : "待配置";
      return `<span>${label}: ${item.provider || "-"} · ${configured}</span>`;
    })
    .join("");
}

function renderModels(models) {
  const target = document.querySelector("#modelConfigList");
  if (!models.length) {
    target.innerHTML = `<div class="item">还没有模型配置</div>`;
    return;
  }
  target.innerHTML = models
    .map(
      (model) => `
        <div class="item">
          <strong>${model.name}</strong>
          <div>${providerLabel(model.purpose, model.provider)} · ${purposeLabel(model.purpose)}</div>
          <div>${model.model_name}</div>
          <span class="status">${model.is_active ? "启用" : "停用"}</span>
        </div>
      `,
    )
    .join("");
}

function providerLabel(purpose, value) {
  const option = (providerOptions[purpose] || []).find((item) => item.value === value);
  return option ? option.label : value;
}

function purposeLabel(value) {
  return {
    script: "脚本生成",
    tts: "语音合成",
    video: "视频生成",
    asr: "语音识别",
    compliance: "合规检查",
  }[value] || value;
}

function renderTrending(searches, videos) {
  const searchTarget = document.querySelector("#trendingSearchList");
  const videoTarget = document.querySelector("#trendingVideoList");
  if (searches.length) {
    state.latestTrendingSearchId = searches[0].id;
  }
  searchTarget.innerHTML = searches.length
    ? searches
        .map(
          (item) => `
            <div class="item">
              <strong>#${item.id} ${item.keyword}</strong>
              <div>${item.platform} · ${item.category || "-"}</div>
              <span class="status">${item.status}</span>
              <div>结果：${item.result_count}</div>
            </div>
          `,
        )
        .join("")
    : `<div class="item">还没有采集任务</div>`;

  videoTarget.innerHTML = videos.length
    ? videos
        .map(
          (item) => `
            <div class="item">
              <strong>${item.title}</strong>
              <div>${item.platform} · ${item.author || "-"}</div>
              <div>${item.summary || item.hook || ""}</div>
              <div>${item.source_url}</div>
              <span class="status">参考，不搬运</span>
            </div>
          `,
        )
        .join("")
    : `<div class="item">还没有爆款参考</div>`;
}

function renderTranscriptions(tasks) {
  const target = document.querySelector("#transcriptionList");
  if (!target) return;
  if (!tasks.length) {
    target.innerHTML = `<div class="item">还没有转写任务</div>`;
    return;
  }
  state.latestTranscriptionId = tasks[0].id;
  target.innerHTML = tasks
    .map(
      (task) => `
        <div class="item">
          <strong>转写 #${task.id} · 素材 #${task.material_id}</strong>
          <span class="status">${task.status}</span>
          <div>${task.summary || ""}</div>
          <div>${task.hook_analysis || ""}</div>
          <div class="transcript">${task.transcript || task.error_message || ""}</div>
          <div class="itemActions">
            <button type="button" data-action="topic-from-transcription" data-id="${task.id}">生成选题</button>
            <button type="button" class="secondary" data-action="script-from-transcription" data-id="${task.id}">生成脚本</button>
          </div>
        </div>
      `,
    )
    .join("");
}

function setLoginState(user) {
  const label = document.querySelector("#loginState");
  if (user) {
    label.textContent = `${user.username} · ${user.role}`;
    document.querySelector("#loginPanel").classList.add("compactLogin");
  } else {
    label.textContent = "未登录";
    document.querySelector("#loginPanel").classList.remove("compactLogin");
  }
}

async function refresh() {
  const [dashboard, integrations] = await Promise.all([
    api.get("/dashboard"),
    api.get("/integrations/status"),
  ]);
  renderMetrics(dashboard.counts);
  renderIntegrations(integrations);
  renderScripts(dashboard.recent_scripts);
  renderTasks(dashboard.recent_tasks);
  if (api.token) {
    const [models, searches, videos, transcriptions, publishRecords, platformAccounts] = await Promise.all([
      api.get("/settings/models"),
      api.get("/trending/searches"),
      api.get("/trending/videos"),
      api.get("/transcriptions"),
      api.get("/publish-records"),
      api.get("/platform-accounts"),
    ]);
    state.platformAccounts = platformAccounts;
    state.publishRecords = publishRecords;
    renderModels(models);
    renderTrending(searches, videos);
    renderTranscriptions(transcriptions);
    renderPublishRecords(publishRecords);
    renderPlatformAccounts(platformAccounts);
  }
}

document.querySelector("#refreshBtn").addEventListener("click", () => refresh().then(() => toast("已刷新")));

document.querySelectorAll(".navItem").forEach((item) => {
  item.addEventListener("click", () => switchPage(item.dataset.page));
});

document.querySelector("#loginForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const login = await api.post("/auth/login", formData(event.currentTarget));
  api.token = login.token;
  localStorage.setItem("authToken", login.token);
  setLoginState(login.user);
  toast("登录成功");
  await refresh();
});

document.querySelector("#uploadForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const payload = new FormData(form);
  const res = await fetch("/api/materials/upload", {
    method: "POST",
    body: payload,
  });
  if (!res.ok) throw new Error(await res.text());
  const material = await res.json();
  if (material.kind === "portrait") {
    state.latestPortraitId = material.id;
    document.querySelector("[name='portrait_material_id']").value = material.id;
  }
  toast(`素材已上传 #${material.id}`);
  form.reset();
  await refresh();
});

document.querySelector("#topicForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = formData(event.currentTarget);
  const topic = await api.post("/topics", payload);
  document.querySelector("#scriptForm textarea[name='topic']").value = topic.title;
  toast(`选题已创建 #${topic.id}`);
  await refresh();
});

document.querySelector("#scriptForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = formData(event.currentTarget);
  payload.duration_seconds = Number(payload.duration_seconds);
  const script = await api.post("/scripts/generate", payload);
  state.latestScriptId = script.id;
  document.querySelector("[name='script_id']").value = script.id;
  toast(`脚本已生成 #${script.id}`);
  await refresh();
});

document.querySelector("#humanForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = formData(event.currentTarget);
  payload.portrait_material_id = payload.portrait_material_id
    ? Number(payload.portrait_material_id)
    : state.latestPortraitId;
  const human = await api.post("/digital-humans", payload);
  state.latestHumanId = human.id;
  document.querySelector("[name='digital_human_id']").value = human.id;
  toast(`数字人已创建 #${human.id}`);
  await refresh();
});

document.querySelector("#taskForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = formData(event.currentTarget);
  payload.script_id = Number(payload.script_id || state.latestScriptId);
  payload.digital_human_id = payload.digital_human_id ? Number(payload.digital_human_id) : state.latestHumanId;
  const task = await api.post("/video-tasks", payload);
  state.latestTaskId = task.id;
  toast(`视频任务已创建 #${task.id}`);
  await refresh();
});

document.querySelector("#createTaskFromScriptBtn").addEventListener("click", async () => {
  if (!state.latestScriptId) {
    toast("请先生成脚本");
    return;
  }
  const humanInput = document.querySelector("#taskForm [name='digital_human_id']");
  const payload = {
    digital_human_id: humanInput.value ? Number(humanInput.value) : state.latestHumanId,
  };
  const task = await api.post(`/scripts/${state.latestScriptId}/video-task`, payload);
  state.latestTaskId = task.id;
  document.querySelector("#taskForm [name='script_id']").value = task.script_id;
  if (task.digital_human_id) {
    humanInput.value = task.digital_human_id;
  }
  toast(`视频任务已创建 #${task.id}`);
  await refresh();
  switchPage("tasks");
});

document.querySelector("#goTaskPageBtn").addEventListener("click", () => switchPage("tasks"));

document.querySelector("#runTaskBtn").addEventListener("click", async () => {
  if (!state.latestTaskId) {
    toast("请先创建视频任务");
    return;
  }
  const task = await api.post(`/video-tasks/${state.latestTaskId}/run`);
  toast(`任务已运行：${task.status}`);
  await refresh();
});

document.querySelectorAll("#taskListTasks, #taskList").forEach((list) => list.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const id = button.dataset.id;
  if (button.dataset.action === "run-video-task") {
    const task = await api.post(`/video-tasks/${id}/run`);
    toast(`任务已运行：${task.status}`);
  }
  if (button.dataset.action === "approve-video-task") {
    const task = await api.post(`/video-tasks/${id}/approve`);
    toast(`任务已审核：${task.status}`);
  }
  if (button.dataset.action === "prepare-publish") {
    const accounts = await api.get("/platform-accounts");
    const account = accounts.find((item) => item.is_default) || accounts[0] || null;
    const record = await api.post(`/video-tasks/${id}/publish-record`, {
      platform: account ? account.platform : "douyin",
      platform_account_id: account ? account.id : null,
      account_name: account ? account.account_name : "公司官方号",
    });
    toast(`发布记录已创建 #${record.id}`);
    switchPage("publish");
  }
  await refresh();
}));

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
  const payload = formData(event.currentTarget);
  payload.is_active = Boolean(event.currentTarget.querySelector("[name='is_active']").checked);
  const config = await api.post("/settings/models", payload);
  toast(`模型配置已保存 #${config.id}`);
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

document.querySelector("#trendingSearchForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const search = await api.post("/trending/searches", formData(event.currentTarget));
  state.latestTrendingSearchId = search.id;
  toast(`采集任务已创建 #${search.id}`);
  await refresh();
});

document.querySelector("#runTrendingBtn").addEventListener("click", async () => {
  if (!state.latestTrendingSearchId) {
    toast("请先创建采集任务");
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

document.querySelector("#transcriptionForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = formData(event.currentTarget);
  payload.material_id = Number(payload.material_id);
  const task = await api.post("/transcriptions", payload);
  state.latestTranscriptionId = task.id;
  toast(`转写任务已创建 #${task.id}`);
  await refresh();
});

document.querySelector("#runTranscriptionBtn").addEventListener("click", async () => {
  if (!state.latestTranscriptionId) {
    toast("请先创建转写任务");
    return;
  }
  const task = await api.post(`/transcriptions/${state.latestTranscriptionId}/run`);
  toast(`转写完成：${task.status}`);
  await refresh();
});

document.querySelector("#transcriptionList").addEventListener("click", async (event) => {
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

if (api.token) {
  api.get("/auth/me")
    .then(setLoginState)
    .catch(() => {
      localStorage.removeItem("authToken");
      api.token = null;
      setLoginState(null);
    })
    .finally(() => refresh().catch((err) => toast(err.message)));
} else {
  setLoginState(null);
  refresh().catch((err) => toast(err.message));
}

const initialPage = window.location.hash.replace("#", "") || "overview";
if (pages[initialPage]) {
  switchPage(initialPage);
}

syncProviderOptions();
