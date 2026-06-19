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
};

function authHeaders() {
  return api.token ? { Authorization: `Bearer ${api.token}` } : {};
}

function formData(form) {
  return Object.fromEntries(new FormData(form).entries());
}

function toast(message) {
  const el = document.querySelector("#toast");
  el.textContent = message;
  el.classList.add("show");
  setTimeout(() => el.classList.remove("show"), 2600);
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
  };
  document.querySelector("#overview").innerHTML = Object.entries(labels)
    .map(([key, label]) => `<div class="metric"><strong>${counts[key] ?? 0}</strong><span>${label}</span></div>`)
    .join("");
}

function renderScripts(scripts) {
  const target = document.querySelector("#scriptPreview");
  if (!scripts.length) {
    target.className = "preview empty";
    target.textContent = "还没有脚本";
    return;
  }
  const script = scripts[0];
  state.latestScriptId = script.id;
  document.querySelector("[name='script_id']").value = script.id;
  target.className = "preview";
  target.textContent = [
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
}

function renderTasks(tasks) {
  const target = document.querySelector("#taskList");
  if (!tasks.length) {
    target.innerHTML = `<div class="item">还没有视频任务</div>`;
    return;
  }
  state.latestTaskId = tasks[0].id;
  target.innerHTML = tasks
    .map(
      (task) => `
        <div class="item">
          <strong>任务 #${task.id}</strong>
          <div>脚本 ID: ${task.script_id}</div>
          <div>数字人 ID: ${task.digital_human_id ?? "-"}</div>
          <span class="status">${task.status}</span>
          ${task.output_path ? `<div>${task.output_path}</div>` : ""}
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
          <div>${model.provider} · ${model.purpose}</div>
          <div>${model.model_name}</div>
          <span class="status">${model.is_active ? "启用" : "停用"}</span>
        </div>
      `,
    )
    .join("");
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
    const [models, searches, videos] = await Promise.all([
      api.get("/settings/models"),
      api.get("/trending/searches"),
      api.get("/trending/videos"),
    ]);
    renderModels(models);
    renderTrending(searches, videos);
  }
}

document.querySelector("#refreshBtn").addEventListener("click", () => refresh().then(() => toast("已刷新")));

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

document.querySelector("#runTaskBtn").addEventListener("click", async () => {
  if (!state.latestTaskId) {
    toast("请先创建视频任务");
    return;
  }
  const task = await api.post(`/video-tasks/${state.latestTaskId}/run`);
  toast(`任务已运行：${task.status}`);
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
