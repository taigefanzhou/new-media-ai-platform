const token = localStorage.getItem("authToken");
const api = async (path, method = "GET", body) => {
  const response = await fetch(`/api${path}`, {
    method,
    headers: { Authorization: `Bearer ${token}`, ...(body ? { "Content-Type": "application/json" } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || "操作失败");
  return response.json();
};
const state = { projects: [], project: null, materials: [], humans: [] };
const $ = (selector) => document.querySelector(selector);
const escapeHtml = (value = "") => String(value).replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[char]));
const message = (text = "") => { $("#status").textContent = text; };

function referenceOptions(selected) {
  return [`<option value="">自动使用角色/场景参考图</option>`, ...state.materials
    .filter((item) => ["image", "portrait", "product", "video"].includes(item.kind))
    .map((item) => `<option value="${item.id}" ${item.id === selected ? "selected" : ""}>#${item.id} ${escapeHtml(item.name)}</option>`)].join("");
}

function renderProjects() {
  $("#projectList").innerHTML = state.projects.length ? state.projects.map((item) => `<button class="project-card ${state.project?.project?.id === item.id ? "active" : ""}" data-project-id="${item.id}"><strong>${escapeHtml(item.title)}</strong><br><small>第 ${item.episode_number} 集 · ${escapeHtml(item.status)}</small></button>`).join("") : "<p class=\"muted\">还没有项目。</p>";
  document.querySelectorAll("[data-project-id]").forEach((button) => button.addEventListener("click", () => loadProject(button.dataset.projectId)));
}

function renderProject() {
  const data = state.project;
  if (!data) return;
  const { project, characters, scenes, shots } = data;
  const characterName = (ids) => JSON.parse(ids || "[]").map((id) => characters.find((item) => item.id === id)?.name).filter(Boolean).join("、") || "未指定";
  $("#projectDetail").innerHTML = `
    <div class="project-head"><div><h2>${escapeHtml(project.title)}</h2><p class="muted">${escapeHtml(project.premise || "请补充剧情简介")}</p></div><div><span class="pill">${shots.length} 个镜头</span> <button id="buildTaskBtn">生成视频任务</button></div></div>
    <div class="cards"><div class="card"><strong>统一美术</strong><p>${escapeHtml(project.visual_style || "待设置")}</p></div><div class="card"><strong>角色参考图</strong><p>请先在素材库上传角色/场景首帧，再在镜头中绑定。生成时会将它作为参考素材。</p></div></div>
    <h3>角色卡</h3><div class="cards">${characters.map((item) => `<div class="card"><strong>${escapeHtml(item.name)}</strong><p>${escapeHtml(item.role)}</p><small>${escapeHtml(item.visual_prompt)}</small></div>`).join("") || "<p class=\"muted\">暂无角色。</p>"}</div>
    <h3>场景卡</h3><div class="cards">${scenes.map((item) => `<div class="card"><strong>${escapeHtml(item.name)}</strong><p>${escapeHtml(item.visual_prompt)}</p></div>`).join("") || "<p class=\"muted\">暂无场景。</p>"}</div>
    <h3>镜头表</h3><p class="muted">先修改台词、画面和参考图；“生成视频任务”后，到视频任务页启动生成。</p>
    <table><thead><tr><th>镜头</th><th>时长</th><th>剧情/台词</th><th>画面提示词</th><th>参考图</th><th></th></tr></thead><tbody>
      ${shots.map((item) => `<tr data-shot-id="${item.id}"><td>${item.order_index}<br><small>${escapeHtml(item.beat)}</small><br><small>${escapeHtml(characterName(item.character_ids_json))}</small></td><td><input class="duration" type="number" min="3" max="10" value="${item.duration_seconds}" /></td><td><textarea class="dialogue">${escapeHtml(item.dialogue)}</textarea></td><td><textarea class="visual">${escapeHtml(item.visual_prompt)}</textarea></td><td><select class="reference">${referenceOptions(item.reference_material_id)}</select></td><td><button class="secondary save-shot">保存</button></td></tr>`).join("")}
    </tbody></table>`;
  $("#buildTaskBtn").addEventListener("click", buildTask);
  document.querySelectorAll(".save-shot").forEach((button) => button.addEventListener("click", async () => {
    const row = button.closest("tr");
    button.disabled = true;
    try {
      await api(`/drama-shots/${row.dataset.shotId}`, "PATCH", { duration_seconds: Number(row.querySelector(".duration").value), dialogue: row.querySelector(".dialogue").value, visual_prompt: row.querySelector(".visual").value, reference_material_id: row.querySelector(".reference").value ? Number(row.querySelector(".reference").value) : null });
      message("镜头已保存。"); await loadProject(project.id);
    } catch (error) { message(error.message); } finally { button.disabled = false; }
  }));
}

async function loadProject(id) { try { state.project = await api(`/drama-projects/${id}`); renderProjects(); renderProject(); } catch (error) { message(error.message); } }
async function buildTask() { const button = $("#buildTaskBtn"); button.disabled = true; try { const result = await api(`/drama-projects/${state.project.project.id}/build-video-task`, "POST"); message(`视频任务 #${result.video_task.id} 已创建。请回到“视频任务”确认后运行。`); await loadProject(state.project.project.id); } catch (error) { message(error.message); } finally { button.disabled = false; } }

$("#projectForm").addEventListener("submit", async (event) => { event.preventDefault(); const form = new FormData(event.currentTarget); try { const project = await api("/drama-projects", "POST", { title: form.get("title"), premise: form.get("premise"), visual_style: form.get("visual_style"), narrator_human_id: form.get("narrator_human_id") ? Number(form.get("narrator_human_id")) : null }); event.currentTarget.reset(); await reload(); await loadProject(project.id); } catch (error) { message(error.message); } });
$("#cloudHotelBtn").addEventListener("click", async (event) => { event.currentTarget.disabled = true; try { const project = await api("/drama-projects", "POST", { title: "未来云端酒店：悬浮套房异常" }); await api(`/drama-projects/${project.id}/bootstrap-cloud-hotel`, "POST"); await reload(); await loadProject(project.id); message("示例已创建：请为角色和场景绑定自有参考图，再生成视频任务。"); } catch (error) { message(error.message); } finally { event.currentTarget.disabled = false; } });
async function reload() { [state.projects, state.materials, state.humans] = await Promise.all([api("/drama-projects"), api("/materials"), api("/digital-humans")]); $("#narratorHuman").innerHTML = `<option value="">暂不绑定</option>${state.humans.map((item) => `<option value="${item.id}">${escapeHtml(item.name)}${item.default_voice ? "（已绑定音色）" : ""}</option>`).join("")}`; renderProjects(); }
reload().catch((error) => message(error.message));
