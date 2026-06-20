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
  highlightedScriptId: null,
  currentPage: "overview",
  materials: [],
  scripts: [],
  videoTasks: [],
  platformAccounts: [],
  publishRecords: [],
  platformCredentials: [],
  digitalHumans: [],
  modelUsage: null,
  users: [],
  currentUser: null,
  currentSettingsSection: "usage",
};

const settingsSections = {
  usage: { title: "模型用量", eyebrow: "Settings / Usage" },
  models: { title: "AI 模型接入", eyebrow: "Settings / AI Models" },
  collectors: { title: "短视频采集接入", eyebrow: "Settings / Collectors" },
  accounts: { title: "账号管理", eyebrow: "Settings / Accounts" },
};

const pages = {
  overview: { title: "运营总览", eyebrow: "Overview" },
  materials: { title: "数字人素材", eyebrow: "Digital Human Assets" },
  creation: { title: "内容创作", eyebrow: "Creation" },
  analysis: { title: "参考拆解", eyebrow: "Reference Breakdown" },
  humans: { title: "数字人素材", eyebrow: "Digital Human Assets" },
  tasks: { title: "视频任务", eyebrow: "Video Tasks" },
  trending: { title: "爆款采集", eyebrow: "Trending" },
  publish: { title: "发布中心", eyebrow: "Publishing" },
  settings: { title: "系统设置", eyebrow: "Settings" },
};

const providerOptions = {
  script: [
    { value: "volcengine-ark", label: "火山方舟 / Doubao Seed 2.0 Pro", model: "doubao-seed-2-0-pro-260215", base: "https://ark.cn-beijing.volces.com/api/v3" },
    { value: "volcengine-ark-lite", label: "火山方舟 / Doubao Seed 2.0 Lite", model: "doubao-seed-2-0-lite-260215", base: "https://ark.cn-beijing.volces.com/api/v3" },
    { value: "aliyun-bailian", label: "阿里云百炼 / Qwen3.7 Plus", model: "qwen3.7-plus", base: "https://dashscope.aliyuncs.com/compatible-mode/v1" },
    { value: "aliyun-bailian-max", label: "阿里云百炼 / Qwen3.7 Max", model: "qwen3.7-max", base: "https://dashscope.aliyuncs.com/compatible-mode/v1" },
    { value: "aliyun-bailian-latest", label: "阿里云百炼 / Qwen Plus Latest", model: "qwen-plus-latest", base: "https://dashscope.aliyuncs.com/compatible-mode/v1" },
    { value: "deepseek", label: "DeepSeek", model: "deepseek-chat", base: "https://api.deepseek.com/v1" },
    { value: "openai-compatible", label: "其他 OpenAI 兼容接口", model: "gpt-4.1-mini", base: "https://api.openai.com/v1" },
    { value: "vllm", label: "vLLM 自建服务", model: "Qwen/Qwen3-30B-A3B-Instruct-2507", base: "http://localhost:8000/v1" },
  ],
  tts: [
    { value: "volcengine-tts", label: "火山语音", model: "volcano-tts" },
    { value: "cosyvoice", label: "CosyVoice", model: "cosyvoice-v2" },
    { value: "fish-speech", label: "Fish Speech", model: "fish-speech" },
    { value: "aliyun-tts", label: "阿里云语音", model: "cosyvoice-v1" },
    { value: "mock", label: "Mock 测试", model: "mock-tts" },
  ],
  voice_clone: [
    { value: "volcengine-voice-clone", label: "火山引擎 / 声音复刻", model: "volcengine-voice-clone" },
    { value: "cosyvoice-clone", label: "CosyVoice 声音克隆服务", model: "cosyvoice-clone" },
    { value: "openvoice", label: "OpenVoice 本地服务", model: "openvoice-v2" },
    { value: "f5-tts", label: "F5-TTS 本地服务", model: "f5-tts" },
    { value: "openai-compatible", label: "其他声音复刻接口", model: "voice-clone" },
  ],
  video: [
    { value: "seedance", label: "火山方舟 / Seedance 2.0", model: "doubao-seedance-2-0-260128" },
    { value: "comfyui", label: "ComfyUI", model: "wan2.1-workflow" },
    { value: "wan", label: "Wan2.1", model: "wan2.1-t2v-1.3b" },
    { value: "hunyuan-video", label: "HunyuanVideo", model: "hunyuan-video" },
    { value: "mock", label: "Mock 测试", model: "mock-video" },
  ],
  asr: [
    { value: "volcengine", label: "火山引擎 / 豆包 ASR", model: "volcengine-asr" },
    { value: "aliyun-bailian", label: "阿里云百炼 / Qwen Audio", model: "qwen-audio-asr" },
    { value: "openai-compatible", label: "OpenAI 兼容转写", model: "whisper-1" },
    { value: "whisperx", label: "WhisperX 本地服务", model: "whisperx-large-v3" },
    { value: "mock", label: "Mock 测试", model: "mock-asr" },
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

function formatNumber(value) {
  return Number(value || 0).toLocaleString("zh-CN");
}

function formatDateTime(value) {
  if (!value) return "-";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "-" : date.toLocaleString("zh-CN", { hour12: false });
}

function toast(message) {
  const el = document.querySelector("#toast");
  el.textContent = message;
  el.classList.add("show");
  setTimeout(() => el.classList.remove("show"), 2600);
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
  state.scripts = scripts;
  renderScriptSelects(scripts);
  const overviewTarget = document.querySelector("#scriptPreview");
  const creationTarget = document.querySelector("#scriptPreviewCreation");
  const resultStatus = document.querySelector("#scriptResultStatus");
  if (!scripts.length) {
    renderTitleSuggestions(null);
    [overviewTarget, creationTarget].filter(Boolean).forEach((target) => {
      target.className = "preview empty";
      target.textContent = "还没有脚本";
    });
    if (resultStatus) {
      resultStatus.textContent = "点击标题会按该方向重写";
      resultStatus.classList.remove("isGenerating");
    }
    return;
  }
  const script = scripts[0];
  state.latestScriptId = script.id;
  const taskScriptSelect = document.querySelector("[name='script_id']");
  if (taskScriptSelect) taskScriptSelect.value = script.id;
  renderTitleSuggestions(script);
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
  if (overviewTarget) {
    overviewTarget.className = "preview";
    overviewTarget.textContent = content;
  }
  renderScriptDetail(script, state.highlightedScriptId === script.id);
}

function renderScriptDetail(script, isFresh = false) {
  const creationTarget = document.querySelector("#scriptPreviewCreation");
  const resultStatus = document.querySelector("#scriptResultStatus");
  if (!creationTarget) return;

  const tags = String(script.hashtags || "")
    .split(/\s+/)
    .map((tag) => tag.trim())
    .filter(Boolean);
  const tagHtml = tags.length
    ? tags.map((tag) => `<span>${escapeHtml(tag)}</span>`).join("")
    : `<span>暂无标签</span>`;

  creationTarget.className = `scriptResult${isFresh ? " scriptResultFresh" : ""}`;
  creationTarget.innerHTML = `
    <div class="scriptBlock compactScriptBlock">
      <span>开头钩子</span>
      <strong>${escapeHtml(script.hook)}</strong>
    </div>
    <div class="scriptBlock primaryScriptBlock">
      <span>口播稿</span>
      <p>${escapeHtml(script.voiceover)}</p>
    </div>
    <div class="scriptBlock compactScriptBlock">
      <span>分镜/画面</span>
      <p>${escapeHtml(script.storyboard)}</p>
    </div>
    <div class="scriptUtilityGrid">
      <details>
        <summary>视频提示词</summary>
        <p>${escapeHtml(script.seedance_prompt)}</p>
      </details>
      <details>
        <summary>标签</summary>
        <div class="tagChips">${tagHtml}</div>
      </details>
      <details>
        <summary>合规提醒</summary>
        <p>${escapeHtml(script.compliance_notes)}</p>
      </details>
    </div>
  `;
  if (resultStatus) {
    resultStatus.textContent = isFresh ? `脚本 #${script.id} · 刚刚生成` : `脚本 #${script.id}`;
    resultStatus.classList.remove("isGenerating");
  }
}

function renderScriptLoading(message = "AI 正在生成标题、口播稿、分镜和视频提示词...", keepTitles = false) {
  const titleTarget = document.querySelector("#titleSuggestionList");
  const creationTarget = document.querySelector("#scriptPreviewCreation");
  const resultStatus = document.querySelector("#scriptResultStatus");
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

function applyGeneratedScript(script) {
  state.latestScriptId = script.id;
  state.highlightedScriptId = script.id;
  state.scripts = [script, ...state.scripts.filter((item) => item.id !== script.id)];
  const scriptInput = document.querySelector("[name='script_id']");
  if (scriptInput) scriptInput.value = script.id;
  renderScriptSelects(state.scripts);
  renderTitleSuggestions(script);
  renderScriptDetail(script, true);
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

function taskProgress(status) {
  return {
    draft: 8,
    queued: 25,
    running: 60,
    needs_review: 85,
    approved: 100,
    rejected: 100,
    failed: 100,
  }[status] || 0;
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
  if (!task.output_path || task.output_path.startsWith("mock://")) return "";
  if (task.output_path.startsWith("http")) return task.output_path;
  return `/api/video-tasks/${task.id}/output`;
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
          <span class="status">${taskStatusLabel(task.status)}</span>
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
  target.innerHTML = `
    <table class="taskTable">
      <thead>
        <tr>
          <th>选择</th>
          <th>任务</th>
          <th>脚本</th>
          <th>数字人</th>
          <th>进度</th>
          <th>成片预览</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        ${tasks
          .map((task) => {
            const progress = taskProgress(task.status);
            const videoSrc = taskVideoSrc(task);
            return `
              <tr>
                <td><input type="checkbox" class="taskSelectCheckbox" value="${task.id}" /></td>
                <td>
                  <strong>#${task.id}</strong>
                  <span class="status">${taskStatusLabel(task.status)}</span>
                </td>
                <td>${escapeHtml(scriptName(task.script_id)).slice(0, 72)}</td>
                <td>${escapeHtml(humanName(task.digital_human_id))}</td>
                <td>
                  <div class="progressBar"><span style="width:${progress}%"></span></div>
                  <div class="recordMeta">${progress}% · ${taskStatusLabel(task.status)}</div>
                  ${task.error_message ? `<div class="errorText">${escapeHtml(task.error_message)}</div>` : ""}
                </td>
                <td>
                  ${videoSrc ? `<video class="taskVideoPreview" src="${videoSrc}" controls preload="metadata"></video>` : `<span class="recordMeta">生成后显示视频</span>`}
                </td>
                <td>
                  <div class="tableActions">
                    <button type="button" data-action="run-video-task" data-id="${task.id}">${task.status === "running" ? "生成中" : "开始生成"}</button>
                    <button type="button" class="secondary" data-action="approve-video-task" data-id="${task.id}">审核通过</button>
                    <button type="button" class="secondary" data-action="prepare-publish" data-id="${task.id}">准备发布</button>
                    <button type="button" class="secondary" data-action="delete-task-output" data-id="${task.id}">删除成片</button>
                    <button type="button" class="danger" data-action="delete-video-task" data-id="${task.id}">删除任务</button>
                  </div>
                </td>
              </tr>
            `;
          })
          .join("")}
      </tbody>
    </table>
  `;
}

function renderTasks(tasks) {
  state.videoTasks = tasks;
  if (tasks.length) {
    state.latestTaskId = tasks[0].id;
  }
  renderTaskCompact(tasks);
  renderTaskTable(tasks);
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

function isImageMaterial(material) {
  return ["portrait", "product", "image"].includes(material.kind);
}

function isVideoMaterial(material) {
  return ["avatar_source", "video"].includes(material.kind);
}

function renderMaterialPreview(material, className = "materialThumb") {
  const src = `/api/materials/${material.id}/preview`;
  if (isImageMaterial(material)) {
    return `<img class="${className}" src="${src}" alt="${escapeHtml(material.name)}" />`;
  }
  if (isVideoMaterial(material)) {
    return `<video class="${className}" src="${src}" controls preload="metadata"></video>`;
  }
  return `<div class="${className} materialFile">文件</div>`;
}

function renderMaterials(materials) {
  const target = document.querySelector("#materialList");
  if (!target) return;
  renderMaterialSelects(materials);
  if (!materials.length) {
    target.innerHTML = `<div class="item">还没有上传素材</div>`;
    return;
  }
  target.innerHTML = materials
    .map((material) => `
      <div class="materialCard">
        ${renderMaterialPreview(material)}
        <div class="materialBody">
          <strong>#${material.id} ${escapeHtml(material.name)}</strong>
          <span class="status">${materialKindLabel(material.kind)}</span>
          <div class="recordMeta">${escapeHtml(material.copyright_status)} · ${escapeHtml(material.tags || "未打标签")}</div>
          <div class="itemActions accountActions">
            <button type="button" class="danger" data-action="delete-material" data-id="${material.id}">删除素材</button>
          </div>
        </div>
      </div>
    `)
    .join("");
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
    const references = materials.filter((item) => ["avatar_source", "video", "reference"].includes(item.kind));
    analysisSelect.innerHTML = `<option value="">先上传或选择参考素材</option>${references
      .map((item) => `<option value="${item.id}">#${item.id} ${escapeHtml(item.name)} · ${materialKindLabel(item.kind)}</option>`)
      .join("")}`;
    const latestReference = materials.find((item) => ["avatar_source", "video", "reference"].includes(item.kind));
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
      </div>
    </div>
  `;
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
}

function renderDigitalHumans(humans) {
  const target = document.querySelector("#humanList");
  if (!target) return;
  renderHumanSelects(humans);
  if (!humans.length) {
    target.innerHTML = `<div class="item">还没有数字人形象</div>`;
    return;
  }
  target.innerHTML = humans
    .map((human) => {
      const preview = human.portrait_material_id
        ? `<img src="/api/materials/${human.portrait_material_id}/preview" alt="${escapeHtml(human.name)}" />`
        : `<div class="portraitPlaceholder">无头像</div>`;
      const sourceVideo = human.source_video_material_id
        ? `<video class="humanSourceVideo" src="/api/materials/${human.source_video_material_id}/preview" controls preload="metadata"></video>`
        : `<div class="recordMeta">未绑定口播视频源</div>`;
      return `
        <div class="humanCard">
          <div class="portraitPreview">${preview}</div>
          <div>
            <strong>${escapeHtml(human.name)}</strong>
            <div>${escapeHtml(human.role || "未设置角色")}</div>
            <span class="status">${escapeHtml(human.style)}</span>
            <div class="recordMeta">头像素材 ID：${human.portrait_material_id || "-"}</div>
            <div class="recordMeta">口播源视频 ID：${human.source_video_material_id || "-"}</div>
            <div class="recordMeta">声音 ID：${escapeHtml(human.default_voice || "未复刻")}</div>
            ${sourceVideo}
            <div class="itemActions accountActions">
              <button type="button" class="danger" data-action="delete-human" data-id="${human.id}">删除数字人</button>
            </div>
          </div>
        </div>
      `;
    })
    .join("");
}

function renderVoiceCloneStatus(status) {
  const target = document.querySelector("#voiceCloneStatus");
  if (!target) return;
  const configured = Boolean(status.configured);
  target.innerHTML = `
    <div class="voiceCloneCard ${configured ? "ready" : "pending"}">
      <strong>${configured ? "声音复刻已接入" : "声音复刻未接入"}</strong>
      <span>${escapeHtml(status.provider || "未配置")} · ${configured ? "上传源视频后可生成本人 voice_id" : "当前只能使用默认语音，需在系统设置里配置声音复刻接口"}</span>
    </div>
  `;
}

function renderIntegrations(status) {
  const labels = {
    script_model: "脚本模型",
    tts: "语音合成",
    voice_clone: "声音复刻",
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
  renderVoiceCloneStatus(status.voice_clone || {});
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

function renderModelUsage(report) {
  const summaryTarget = document.querySelector("#modelUsageSummary");
  const listTarget = document.querySelector("#modelUsageList");
  if (!summaryTarget || !listTarget) return;
  const totals = report?.totals || {};
  const cards = [
    ["调用次数", totals.call_count],
    ["总 Token", totals.total_tokens],
    ["输入 Token", totals.prompt_tokens],
    ["输出 Token", totals.completion_tokens],
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
  if (!items.length) {
    listTarget.innerHTML = `<div class="item">还没有模型调用记录。生成一次脚本后，这里会自动出现用量。</div>`;
    return;
  }
  listTarget.innerHTML = `
    <table class="settingsTable">
      <thead>
        <tr>
          <th>用途</th>
          <th>供应商</th>
          <th>模型</th>
          <th>调用次数</th>
          <th>输入 Token</th>
          <th>输出 Token</th>
          <th>总 Token</th>
          <th>最近调用</th>
        </tr>
      </thead>
      <tbody>
        ${items
          .map(
            (item) => `
              <tr>
                <td>${purposeLabel(item.purpose)}</td>
                <td>${escapeHtml(providerLabel(item.purpose, item.provider))}</td>
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
  `;
}

function renderSystemUsers(users) {
  const target = document.querySelector("#userAccountList");
  if (!target) return;
  if (!users.length) {
    target.innerHTML = `<div class="item">还没有可维护账号，或当前账号没有管理员权限。</div>`;
    return;
  }
  target.innerHTML = `
    <table class="settingsTable userTable">
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
        ${users
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
  `;
}

function renderPlatformCredentials(credentials) {
  const target = document.querySelector("#platformCredentialList");
  if (!target) return;
  if (!credentials.length) {
    target.innerHTML = `<div class="item">还没有平台接入配置</div>`;
    return;
  }
  target.innerHTML = credentials
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
    .join("");
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
    manual: "手动",
  }[value] || value;
}

function credentialPurposeLabel(value) {
  return {
    trending: "爆款采集",
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
    asr: "语音识别",
    compliance: "合规检查",
    knowledge: "知识库/文档/长文本",
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
            <button type="button" data-action="topic-from-transcription" data-id="${task.id}">带到内容创作</button>
            <button type="button" class="secondary" data-action="script-from-transcription" data-id="${task.id}">生成原创脚本</button>
          </div>
        </div>
      `,
    )
    .join("");
}

function setLoginState(user) {
  state.currentUser = user;
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
  const [dashboard, integrations, materials] = await Promise.all([
    api.get("/dashboard"),
    api.get("/integrations/status"),
    api.get("/materials"),
  ]);
  state.materials = materials;
  renderMetrics(dashboard.counts);
  renderIntegrations(integrations);
  renderMaterials(materials);
  renderScripts(dashboard.recent_scripts);
  renderTasks(dashboard.recent_tasks);
  if (api.token) {
    const [
      models,
      platformCredentials,
      searches,
      videos,
      transcriptions,
      publishRecords,
      platformAccounts,
      digitalHumans,
      scripts,
      videoTasks,
      modelUsage,
      users,
    ] = await Promise.all([
      api.get("/settings/models"),
      api.get("/settings/platform-credentials"),
      api.get("/trending/searches"),
      api.get("/trending/videos"),
      api.get("/transcriptions"),
      api.get("/publish-records"),
      api.get("/platform-accounts"),
      api.get("/digital-humans"),
      api.get("/scripts"),
      api.get("/video-tasks"),
      api.get("/settings/model-usage"),
      api.get("/settings/users").catch(() => []),
    ]);
    state.platformCredentials = platformCredentials;
    state.platformAccounts = platformAccounts;
    state.publishRecords = publishRecords;
    state.digitalHumans = digitalHumans;
    state.modelUsage = modelUsage;
    state.users = users;
    renderModels(models);
    renderPlatformCredentials(platformCredentials);
    renderModelUsage(modelUsage);
    renderSystemUsers(users);
    renderTrending(searches, videos);
    renderTranscriptions(transcriptions);
    renderPublishRecords(publishRecords);
    renderPlatformAccounts(platformAccounts);
    renderScripts(scripts);
    renderDigitalHumans(digitalHumans);
    renderTasks(videoTasks);
  }
}

document.querySelector("#refreshBtn").addEventListener("click", () => refresh().then(() => toast("已刷新")));

document.querySelectorAll(".navItem").forEach((item) => {
  item.addEventListener("click", () => switchPage(item.dataset.page, item.dataset.settingsSection || null));
});

document.querySelectorAll(".subNavItem").forEach((item) => {
  item.addEventListener("click", () => switchPage(item.dataset.page, item.dataset.settingsSection));
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

document.querySelector("#humanAssetForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const payload = new FormData(form);
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
});

document.querySelector("#scriptForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const submitButton = form.querySelector("button[type='submit']");
  const originalText = submitButton.textContent;
  const payload = formData(form);
  payload.duration_seconds = Number(payload.duration_seconds);
  submitButton.disabled = true;
  submitButton.textContent = "生成中...";
  renderScriptLoading();
  try {
    const script = await api.post("/scripts/generate", payload);
    applyGeneratedScript(script);
    toast(`脚本已生成 #${script.id}`);
    await refresh();
  } catch (error) {
    toast("脚本生成失败，请检查模型配置或稍后重试");
    renderScripts(state.scripts);
  } finally {
    submitButton.disabled = false;
    submitButton.textContent = originalText;
  }
});

document.querySelector("#batchScriptBtn").addEventListener("click", async () => {
  const form = document.querySelector("#scriptForm");
  const button = document.querySelector("#batchScriptBtn");
  const originalText = button.textContent;
  const payload = formData(form);
  payload.duration_seconds = Number(payload.duration_seconds);
  payload.count = Number(document.querySelector("#batchScriptCount").value || 5);
  button.disabled = true;
  button.textContent = "生成候选中...";
  renderScriptLoading(`AI 正在生成 ${payload.count} 条候选脚本，审核人只需选择满意的一版...`);
  try {
    const scripts = await api.post("/scripts/batch-generate", payload);
    state.scripts = [...scripts, ...state.scripts.filter((item) => !scripts.some((script) => script.id === item.id))];
    applyGeneratedScript(scripts[0]);
    renderScriptSelects(state.scripts);
    toast(`已生成 ${scripts.length} 条候选脚本`);
    await refresh();
  } catch (error) {
    toast("候选脚本生成失败，请检查模型配置或稍后重试");
    renderScripts(state.scripts);
  } finally {
    button.disabled = false;
    button.textContent = originalText;
  }
});

document.querySelector("#taskForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = formData(event.currentTarget);
  payload.script_id = Number(payload.script_id || state.latestScriptId);
  payload.digital_human_id = payload.digital_human_id ? Number(payload.digital_human_id) : null;
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
  const payload = {
    script_ids: scriptIds,
    digital_human_id: humanValue ? Number(humanValue) : null,
  };
  const tasks = await api.post("/video-tasks/batch-create", payload);
  toast(`已批量创建 ${tasks.length} 个视频任务`);
  await refresh();
  switchPage("tasks");
});

document.querySelector("#createTaskFromScriptBtn").addEventListener("click", async () => {
  if (!state.latestScriptId) {
    toast("请先生成脚本");
    return;
  }
  const button = document.querySelector("#createTaskFromScriptBtn");
  const originalText = button.textContent;
  const humanInput = document.querySelector("#creationHumanSelect");
  const payload = {};
  if (humanInput.value) {
    payload.digital_human_id = Number(humanInput.value);
  }
  button.disabled = true;
  button.textContent = "进入生成队列...";
  try {
    const task = await api.post(`/scripts/${state.latestScriptId}/auto-video-task`, payload);
    state.latestTaskId = task.id;
    document.querySelector("#taskForm [name='script_id']").value = task.script_id;
    const taskHumanInput = document.querySelector("#taskForm [name='digital_human_id']");
    if (task.digital_human_id && taskHumanInput) {
      taskHumanInput.value = task.digital_human_id;
    }
    toast(`已进入自动生成队列 #${task.id}`);
    await refresh();
    switchPage("tasks");
  } catch (error) {
    toast("自动生成视频失败，请检查视频模型或素材配置");
  } finally {
    button.disabled = false;
    button.textContent = originalText;
  }
});

document.querySelector("#goTaskPageBtn").addEventListener("click", () => switchPage("tasks"));

document.querySelector("#regenerateScriptBtn").addEventListener("click", () => {
  document.querySelector("#scriptForm").requestSubmit();
});

document.querySelector("#titleSuggestionList").addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-title]");
  if (!button) return;
  const title = button.dataset.title;
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
    applyGeneratedScript(script);
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
  const task = await api.post(`/video-tasks/${state.latestTaskId}/run`);
  toast(`任务已运行：${task.status}`);
  await refresh();
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
  const button = event.target.closest("button[data-action='delete-material']");
  if (!button) return;
  if (!window.confirm("确认删除这个素材吗？相关数字人会自动解除绑定。")) return;
  await api.delete(`/materials/${button.dataset.id}`);
  toast("素材已删除");
  await refresh();
});

document.querySelector("#humanList").addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action='delete-human']");
  if (!button) return;
  if (!window.confirm("确认删除这个数字人吗？相关视频任务会改为不露脸。")) return;
  await api.delete(`/digital-humans/${button.dataset.id}`);
  toast("数字人已删除");
  await refresh();
});

document.querySelectorAll("#taskListTasks, #taskList").forEach((list) => list.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const id = button.dataset.id;
  if (button.dataset.action === "run-video-task") {
    button.textContent = "生成中";
    button.disabled = true;
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
  if (button.dataset.action === "delete-task-output") {
    if (!window.confirm("确认删除这个任务的成片文件吗？任务会保留。")) return;
    await api.delete(`/video-tasks/${id}/output`);
    toast("成片已删除");
  }
  if (button.dataset.action === "delete-video-task") {
    if (!window.confirm("确认删除这个视频任务吗？关联发布记录也会删除。")) return;
    await api.delete(`/video-tasks/${id}`);
    toast("视频任务已删除");
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

document.querySelector("#platformCredentialList").addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  if (button.dataset.action === "activate-platform-credential") {
    const credential = await api.post(`/settings/platform-credentials/${button.dataset.id}/activate`);
    toast(`${credential.display_name} 已启用`);
    await refresh();
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

document.querySelector("#analysisMaterialSelect").addEventListener("change", renderAnalysisMaterialPreview);

document.querySelector("#goAssetPageBtn").addEventListener("click", () => switchPage("humans"));

document.querySelector("#transcriptionForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = formData(event.currentTarget);
  if (!payload.material_id) {
    toast("请先选择参考素材");
    return;
  }
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

const initialRoute = parseRoute(window.location.hash);
switchPage(initialRoute.page, initialRoute.section, false);

syncProviderOptions();
