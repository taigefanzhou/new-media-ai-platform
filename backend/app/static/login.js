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
