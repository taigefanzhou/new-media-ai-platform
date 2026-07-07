function toast(message) {
  const el = document.querySelector("#toast");
  el.textContent = message;
  el.classList.add("show");
  setTimeout(() => el.classList.remove("show"), 2600);
}

function formData(form) {
  return Object.fromEntries(new FormData(form).entries());
}

function nextUrl() {
  const params = new URLSearchParams(window.location.search);
  const next = params.get("next");
  return next && next.startsWith("/") && !next.startsWith("//") ? next : "/";
}

function handleWechatCallbackState() {
  const params = new URLSearchParams(window.location.search);
  const token = params.get("wechat_token");
  const status = params.get("wechat_status");
  if (token) {
    localStorage.setItem("authToken", token);
    window.location.replace(nextUrl());
    return true;
  }
  if (status === "pending") {
    toast("微信登录申请已提交，请等待管理员批准");
  } else if (status === "rejected") {
    toast("微信登录申请已被拒绝，请联系管理员");
  } else if (status === "disabled") {
    toast("微信绑定或系统账号已停用，请联系管理员");
  } else if (status === "error") {
    toast("微信登录暂不可用，请联系管理员");
  }
  return false;
}

async function initWechatLogin() {
  const button = document.querySelector("#wechatLoginBtn");
  const status = document.querySelector("#wechatLoginStatus");
  if (!button || !status) return;
  try {
    const res = await fetch("/api/auth/wechat/config");
    if (!res.ok) throw new Error("微信登录配置读取失败");
    const config = await res.json();
    button.disabled = !config.enabled;
    status.textContent = config.enabled ? "使用微信扫码后，首次登录需要管理员批准。" : "微信扫码登录未启用。";
  } catch (err) {
    button.disabled = true;
    status.textContent = err.message || "微信扫码登录暂不可用。";
  }
}

document.querySelector("#loginForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector("button[type='submit']");
  const originalText = button.textContent;
  button.disabled = true;
  button.textContent = "登录中...";
  try {
    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(formData(form)),
    });
    if (!res.ok) throw new Error("账号或密码不正确");
    const login = await res.json();
    localStorage.setItem("authToken", login.token);
    window.location.replace(nextUrl());
  } catch (err) {
    toast(err.message || "登录失败，请检查账号和密码");
  } finally {
    button.disabled = false;
    button.textContent = originalText;
  }
});

document.querySelector("#wechatLoginBtn")?.addEventListener("click", () => {
  window.location.href = "/api/auth/wechat/start";
});

if (!handleWechatCallbackState()) {
  initWechatLogin();
}
