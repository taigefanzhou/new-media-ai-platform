const api = {
  async get(path) {
    const res = await fetch(`/api${path}`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },
  async post(path, body = {}) {
    const res = await fetch(`/api${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
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
};

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

async function refresh() {
  const [dashboard, integrations] = await Promise.all([
    api.get("/dashboard"),
    api.get("/integrations/status"),
  ]);
  renderMetrics(dashboard.counts);
  renderIntegrations(integrations);
  renderScripts(dashboard.recent_scripts);
  renderTasks(dashboard.recent_tasks);
}

document.querySelector("#refreshBtn").addEventListener("click", () => refresh().then(() => toast("已刷新")));

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
  const human = await api.post("/digital-humans", formData(event.currentTarget));
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

refresh().catch((err) => toast(err.message));
