# WeChat Scan Login Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add WeChat Open Platform scan login with admin approval and keep ordinary users isolated to their own content.

**Architecture:** Keep the current FastAPI + SQLModel + static frontend structure. Add focused WeChat identity/config/request tables, a small OAuth service, public callback/start endpoints, admin approval endpoints, and a compact frontend section in login/settings.

**Tech Stack:** FastAPI, SQLModel, SQLite compatibility migrations, httpx, static HTML/CSS/JavaScript, existing token-based `AuthSession`.

---

### Task 1: Failing Smoke Test

**Files:**
- Create: `backend/tests/wechat_login_smoke.py`

- [ ] Write a smoke script that creates a temp SQLite DB, starts `TestClient`, verifies `/api/auth/wechat/config` is public, verifies unconfigured `/api/auth/wechat/start` is blocked, configures WeChat as admin, simulates a callback through a fake OAuth client, approves the pending request, and verifies the same WeChat identity logs in.
- [ ] Run: `cd backend && python tests/wechat_login_smoke.py`
- [ ] Expected before implementation: fails because `/api/auth/wechat/config` or `/api/settings/wechat-login/config` does not exist.

### Task 2: Models, Schemas, and Migrations

**Files:**
- Modify: `backend/app/models/entities.py`
- Modify: `backend/app/schemas/requests.py`
- Modify: `backend/app/core/db.py`

- [ ] Add `WechatLoginConfig`, `WechatIdentity`, `WechatLoginRequest`, and `WechatLoginStatus`.
- [ ] Add request/public schemas for config save, config public view, request approval/rejection, request list item, and identity list item.
- [ ] Add SQLite compatibility creation/indexes through `SQLModel.metadata.create_all(engine)` plus explicit safe migrations for existing DBs.
- [ ] Run the smoke script and confirm it now fails at missing routes or service behavior, not model import errors.

### Task 3: OAuth Service

**Files:**
- Create: `backend/app/services/wechat_login.py`

- [ ] Implement a `WechatOAuthClient` protocol-shaped class using httpx to call `sns/oauth2/access_token` and `sns/userinfo`.
- [ ] Implement helpers to build the QR URL, sign/verify `state`, mask identifiers, reuse pending requests, create sessions for bound identities, and generate a random temporary password for approved new users.
- [ ] Keep `AppSecret` server-side only.
- [ ] Run the smoke script and confirm it now fails at route wiring only.

### Task 4: Public and Admin Routes

**Files:**
- Modify: `backend/app/api/routes.py`
- Modify: `backend/app/main.py`

- [ ] Add public `/api/auth/wechat/config`, `/api/auth/wechat/start`, and `/api/auth/wechat/callback`.
- [ ] Add admin `/api/settings/wechat-login/config`, `/api/settings/wechat-login/requests`, `/approve`, `/reject`, `/identities`, and `/disable`.
- [ ] Add public API paths to auth middleware.
- [ ] Wire approval to either existing user binding or new user creation.
- [ ] Run the smoke script and confirm WeChat approval/login passes.

### Task 5: Frontend Login and Admin UI

**Files:**
- Modify: `backend/app/static/login.html`
- Modify: `backend/app/static/login.js`
- Modify: `backend/app/static/index.html`
- Modify: `backend/app/static/app.js`
- Modify: `backend/app/static/styles.css`

- [ ] Add a WeChat login button to the login page, only enabled when config says WeChat login is active.
- [ ] Add callback status handling for `wechat_token`, `wechat_status=pending`, `wechat_status=rejected`, and `wechat_status=error`.
- [ ] Add a System Settings panel for WeChat config, pending requests, and bound identities.
- [ ] Keep the style aligned with the current clean table/card direction.

### Task 6: Data Isolation Audit

**Files:**
- Modify: `backend/app/api/routes.py`
- Modify if needed: `backend/app/models/entities.py`
- Modify if needed: `backend/app/core/db.py`

- [ ] Audit list/detail/update/delete/media endpoints for core owned models.
- [ ] Ensure ordinary users use `_owned_statement` for lists and `_ensure_record_access` for details/files/mutations.
- [ ] Ensure admin sees all.
- [ ] Add smoke assertions that a second operator cannot see or mutate the first operator's material.

### Task 7: Verification and Commit

**Files:**
- Test: `backend/tests/wechat_login_smoke.py`
- Existing: `backend/tests/release_smoke.py`

- [ ] Run: `cd backend && python tests/wechat_login_smoke.py`
- [ ] Run: `cd backend && python tests/release_smoke.py`
- [ ] Run: `python -m compileall backend/app`
- [ ] Run: `git diff --check`
- [ ] Commit all implementation changes with a focused message.
