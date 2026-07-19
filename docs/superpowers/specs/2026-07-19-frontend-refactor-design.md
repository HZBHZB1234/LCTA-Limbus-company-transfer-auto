# Frontend Modernization Design Spec

> 将 LCTA 前端从 vanilla JS（9 文件 + 18 HTML 片段 + 3 CSS）完整重构到 Vue 3 + TypeScript + Vite + Pinia 现代架构。

**Status:** Approved  
**Date:** 2026-07-19  
**Version:** 1.0

---

## 一、目标与成功标准

### 目标

使用 Vue 3 + TypeScript + Vite + Pinia + Vue Router 完整重构 `webui/` 前端部分，保持所有 18 个 section 页面功能对等，同时重构 Python 桥接层为数据驱动模式。

### 成功标准

1. 所有 18 个 section 功能行为与重构前完全一致，无回归 bug
2. TypeScript strict 模式零错误（`vue-tsc --noEmit` 通过）
3. ESLint 零 warning
4. 前端测试覆盖核心流程（工具函数 + Store + 核心组件），行覆盖率 ≥ 60%
5. Vite 构建输出体积 ≤ 当前 webui/ 的 1.5 倍
6. 开发时支持 Vite HMR 实时调试（pywebview 加载 Vite dev server）

### 约束

- 必须运行在 pywebview（Windows WebView2）内
- Python 后端（`webui/app.py`）可同步调整，但不能改变整体架构
- C launcher（`launcher.c`）不改动
- 构建系统（`build.ps1`、`InitCode.py`、`release.yml`）可同步调整

---

## 二、技术栈

| 层 | 技术 | 版本 | 用途 |
|-----|------|------|------|
| 框架 | Vue 3 | 3.4+ | SFC 组件模型 |
| 构建 | Vite | 5.4+ | Dev Server (HMR) + 生产构建 |
| 类型 | TypeScript | 5.4+ | strict 模式全量覆盖 |
| 状态 | Pinia | 2.1+ | 全局状态管理 |
| 路由 | Vue Router | 4.3+ | hash mode SPA 导航 |
| 样式 | Scoped CSS + CSS Custom Properties | — | 组件隔离 + 主题系统 |
| 图标 | @fortawesome/fontawesome-free | 6.4+ | 替代 CDN 加载 |
| Markdown | marked | 12+ | 帮助/更新日志渲染 |
| Lint | ESLint 9 | — | flat config, @typescript-eslint + eslint-plugin-vue |
| 测试 | Vitest + @vue/test-utils | 2+ | 单元测试 + 组件测试 |

---

## 三、目录结构

```
webui/
├── index.html                # Vite 入口（仅 <div id="app"> + <script type="module">）
├── package.json
├── tsconfig.json             # strict: true
├── vite.config.ts            # base: './', vue plugin, strictPort: 5173
├── eslint.config.js          # ES9 flat config
│
├── src/
│   ├── main.ts               # 等待 pywebviewready → initApi → createApp → mount
│   ├── App.vue               # 根布局: AppSidebar + <router-view> + ModalContainer + HelpDrawer
│   ├── router.ts             # 18 条 lazy route
│   │
│   ├── types/
│   │   ├── api.d.ts          # PyWebViewApi 接口（约 80 个方法完整类型声明）
│   │   ├── config.d.ts       # ConfigModel 完整类型
│   │   └── events.d.ts       # CustomEvent detail payload 类型
│   │
│   ├── utils/
│   │   ├── api.ts            # initApi() → Promise<PyWebViewApi>; getApi() → 类型安全调用
│   │   ├── events.ts         # listenEvent(name, handler) / dispatchEvent(name, detail) 封装
│   │   └── crypto.ts         # AES-256-GCM 加密（从 utils.js 迁移）
│   │
│   ├── stores/
│   │   ├── config.ts         # 全局配置（替代 ConfigManager.configCache + window.config）
│   │   ├── modal.ts          # 模态状态（替代 modalWindows 全局数组 + Event 监听）
│   │   ├── log.ts            # 日志缓冲（替代全局 addLogMessage）
│   │   ├── update.ts         # 自更新状态
│   │   └── theme.ts          # 主题切换状态
│   │
│   ├── composables/
│   │   ├── useModal.ts       # ModalWindow 创建/销毁逻辑
│   │   ├── useProgress.ts    # 进度推送封装
│   │   ├── useLog.ts         # 日志输出
│   │   ├── useTooltip.ts     # tooltip 注册
│   │   └── useElder.ts       # Elder 向导逻辑
│   │
│   ├── components/
│   │   ├── AppSidebar.vue        # 侧边栏（导航 + 搜索 + 最小化模态列表）
│   │   ├── ThemeToggle.vue       # 主题切换按钮组
│   │   ├── HelpDrawer.vue        # 帮助抽屉（3 tab）
│   │   ├── ModalContainer.vue    # 模态容器（v-for modalStore.modals）
│   │   ├── ModalWindow.vue       # 基础模态（标题 + 进度 + 日志 + 操作按钮 + 最小化）
│   │   ├── ProgressBar.vue       # 进度条子组件
│   │   ├── LogPanel.vue          # 滚动日志面板
│   │   ├── TooltipWrapper.vue    # 悬停 tooltip
│   │   └── DragOverlay.vue       # 拖拽蒙层
│   │
│   └── views/                # 18 个路由页面
│       ├── Dashboard.vue
│       ├── Translate.vue
│       ├── Download.vue
│       ├── Install.vue
│       ├── Fancy.vue
│       ├── Cdn.vue
│       ├── Speed.vue
│       ├── Manage.vue
│       ├── LauncherConfig.vue
│       ├── ApiConfig.vue
│       ├── Proper.vue
│       ├── Log.vue
│       ├── Settings.vue
│       ├── About.vue
│       ├── Welcome.vue
│       ├── Elder.vue
│       ├── Test.vue
│       └── Clean.vue
│
└── dist/                     # Vite 构建输出（gitignore，生产包包含）
```

---

## 四、Python ↔ Vue Bridge（Event Bridge）

### 4.1 JS → Python（不变）

前端通过 `pywebview.api.xxx()` 调用 Python，方法签名不变。改进是 TypeScript 类型声明（`types/api.d.ts` 定义约 80 个方法的完整接口），所有调用通过 `getApi()` 获得类型安全。

```ts
// src/utils/api.ts
import type { PyWebViewApi } from '../types/api'

let _api: PyWebViewApi | null = null

export function initApi(): Promise<PyWebViewApi> {
  return new Promise((resolve) => {
    if ((window as any).pywebview?.api) {
      _api = (window as any).pywebview.api as PyWebViewApi
      resolve(_api)
    } else {
      window.addEventListener('pywebviewready', () => {
        _api = (window as any).pywebview.api as PyWebViewApi
        resolve(_api)
      })
    }
  })
}

export function getApi(): PyWebViewApi {
  if (!_api) throw new Error('API not initialized. Call initApi() first.')
  return _api
}
```

### 4.2 Python → Vue（Event Bridge）

Python 不再直接操作 DOM 或调用全局 JS 函数，改为 dispatch CustomEvent：

```python
# webui/app.py — LCTA_API 类新增方法
def _emit(self, event_name: str, detail: dict):
    """将事件推送到 Vue 前端"""
    import json
    payload = json.dumps(detail, ensure_ascii=False)
    self._window.evaluate_js(
        f"window.dispatchEvent(new CustomEvent('{event_name}', {{ detail: {payload} }}))"
    )
```

### 4.3 事件分类

| 事件名 | Payload | 触发场景 |
|--------|---------|---------|
| `lcta:log` | `{message: string, level: 'info'|'warn'|'error'}` | 全局日志 |
| `lcta:modal-log` | `{modalId: string, message: string}` | 模态内日志 |
| `lcta:modal-progress` | `{modalId: string, percent: number, text: string}` | 模态进度 |
| `lcta:modal-status` | `{modalId: string, status: string, text?: string}` | 模态状态变更 |
| `lcta:file-picked` | `{inputId: string, path: string}` | 文件/文件夹选择 |
| `lcta:file-dropped` | `{files: string[]}` | 拖拽文件 |
| `lcta:config-reloaded` | `{}` | 配置重载通知 |

Vue 端通过 `listenEvent()` 注册监听，在 Pinia store 中处理：

```ts
// src/utils/events.ts
export function listenEvent<T>(name: string, handler: (detail: T) => void): () => void {
  const listener = (e: Event) => handler((e as CustomEvent<T>).detail)
  window.addEventListener(name, listener)
  return () => window.removeEventListener(name, listener)
}
```

### 4.4 启动时序

```
index.html 加载
  └─ <script type="module" src="/src/main.ts">
       └─ await initApi()                           # 等待 pywebviewready
            └─ const startup = await getApi().get_startup_data()
                 └─ configStore.init(startup)
                      └─ createApp(App).use(pinia).use(router).mount('#app')
```

Vue 在 `pywebview.api` 可用后才 mount，所有组件内 `getApi()` 调用安全。

---

## 五、状态管理（Pinia Stores）

### 5.1 configStore

```ts
interface ConfigStore {
  config: Ref<ConfigModel>
  dirty: Ref<boolean>
  init(startupData: StartupData): void
  get<T>(path: string): T
  set(path: string, value: any): void
  save(): Promise<void>
  reload(): Promise<void>
}
```

- 单一数据源，消除当前 `configCache` + `window.config` 双源问题
- 取消 `configKeyMap`（约 90 条 DOM id → 路径映射），改为 TypeScript 类型推导
- `save()` 调用 `getApi().update_config_batch()` + `getApi().save_config_to_file()`
- `reload()` 重新调用 `getApi().get_startup_data()`

### 5.2 modalStore

```ts
interface ModalStore {
  modals: Ref<ModalState[]>
  create(type: ModalType, options: ModalOptions): string  // 返回 modalId
  remove(id: string): void
  updateProgress(id: string, percent: number, text: string): void
  addLog(id: string, message: string): void
  setStatus(id: string, status: ModalStatus): void
  minimize(id: string): void
  restore(id: string): void
  setupEventListeners(): void  // 在 App.vue onMounted 中调用
}
```

- `create()` 生成 modalId 并自动调用 `getApi().add_modal_id(id)` 通知 Python
- `setupEventListeners()` 注册 `lcta:modal-log`、`lcta:modal-progress`、`lcta:modal-status` 事件
- 模态组件通过 `v-for="m in modalStore.modals"` 自动渲染

### 5.3 logStore

```ts
interface LogStore {
  messages: Ref<LogEntry[]>
  add(message: string, level: LogLevel): void
  clear(): void
}
```

- 最多保留 500 条，超出自动移出旧条目
- `lcta:log` 事件自动追加

### 5.4 themeStore

```ts
interface ThemeStore {
  current: Ref<'light' | 'dark' | 'purple'>
  switch(theme: string): void
}
```

- 切换时在 `document.body` 上设置 class（`.theme-light` / `.theme-dark` / `.theme-purple`）
- 持久化到 `configStore`

### 5.5 updateStore

```ts
interface UpdateStore {
  latestVersion: Ref<string | null>
  updating: Ref<boolean>
  check(): Promise<void>
  perform(): Promise<void>
}
```

---

## 六、模态系统设计

### 6.1 组件层级

```
App.vue
├── AppSidebar.vue
│   └── 最小化模态按钮（v-for minimizedModals）
├── <router-view>
└── ModalContainer.vue（Teleport to body）
    └── ModalWindow.vue（v-for modalStore.modals）
        ├── 标题 + 状态标签 + 最小化/关闭
        ├── ProgressBar.vue
        ├── LogPanel.vue
        └── 操作按钮（取消/暂停/继续/确认/取消）
```

### 6.2 ModalState

```ts
interface ModalState {
  id: string
  type: 'progress' | 'confirm' | 'message'
  title: string
  status: 'running' | 'paused' | 'canceled' | 'completed'
  percent: number
  progressText: string
  logs: LogEntry[]
  minimized: boolean
  confirmText?: string
  cancelText?: string
  onConfirm?: () => void
  onCancel?: () => void
}
```

### 6.3 生命周期

```
1. View 组件: modalStore.create('progress', { title: '正在下载...' })
   → 返回 modalId，ModalContainer 自动渲染
2. View 组件: getApi().download_xxx(modalId)
   → Python 注册 modalId
3. Python 操作中: self._emit('lcta:modal-progress', { modalId, percent, text })
   → modalStore 接收 → 响应式更新 ModalWindow
4. 用户取消: getApi().set_modal_running(modalId, 'cancel')
   → Python check_modal_running() 抛出 CancelRunning → 操作停止
5. 操作完成: Python 返回 { success: true, ... }
   → View 组件接收 → modalStore.setStatus(id, 'completed')
```

---

## 七、CSS 策略

### 7.1 技术选择：Scoped CSS + CSS Custom Properties

- Vue SFC `<style scoped>` 提供组件级样式隔离
- CSS Custom Properties 实现三主题切换
- 不引入 SCSS/Tailwind，保持最小依赖

### 7.2 主题变量

```css
:root {
  --bg-primary: #ffffff;
  --bg-secondary: #f5f5f5;
  --text-primary: #333333;
  --text-secondary: #666666;
  --border-color: #e0e0e0;
  --accent-color: #4a90d9;
}

.theme-dark {
  --bg-primary: #1a1a2e;
  --bg-secondary: #16213e;
  --text-primary: #e0e0e0;
  --text-secondary: #a0a0a0;
  --border-color: #2a2a4e;
  --accent-color: #6ea8fe;
}

.theme-purple {
  --bg-primary: #2d1b69;
  --bg-secondary: #1a0f3c;
  --text-primary: #e8dff5;
  --text-secondary: #b8a9d4;
  --border-color: #3d2b79;
  --accent-color: #b794f4;
}
```

### 7.3 全局样式与组件样式分界

- App.vue 的 `<style>`（非 scoped）放 CSS reset + 主题变量定义
- 所有组件使用 `<style scoped>`，引用 `var(--xxx)` 变量
- 组件间样式不互相泄漏

---

## 八、路由设计

### 8.1 Hash Mode

```ts
// src/router.ts
import { createRouter, createWebHashHistory } from 'vue-router'

const routes = [
  { path: '/',             name: 'dashboard',       component: () => import('./views/Dashboard.vue') },
  { path: '/translate',    name: 'translate',       component: () => import('./views/Translate.vue') },
  { path: '/download',     name: 'download',        component: () => import('./views/Download.vue') },
  { path: '/install',      name: 'install',         component: () => import('./views/Install.vue') },
  { path: '/fancy',        name: 'fancy',           component: () => import('./views/Fancy.vue') },
  { path: '/cdn',          name: 'cdn',             component: () => import('./views/Cdn.vue') },
  { path: '/speed',        name: 'speed',           component: () => import('./views/Speed.vue') },
  { path: '/manage',       name: 'manage',          component: () => import('./views/Manage.vue') },
  { path: '/launcher',     name: 'launcher-config', component: () => import('./views/LauncherConfig.vue') },
  { path: '/config',       name: 'api-config',      component: () => import('./views/ApiConfig.vue') },
  { path: '/proper',       name: 'proper',          component: () => import('./views/Proper.vue') },
  { path: '/log',          name: 'log',             component: () => import('./views/Log.vue') },
  { path: '/settings',     name: 'settings',        component: () => import('./views/Settings.vue') },
  { path: '/about',        name: 'about',           component: () => import('./views/About.vue') },
  { path: '/welcome',      name: 'welcome',         component: () => import('./views/Welcome.vue') },
  { path: '/elder',        name: 'elder',           component: () => import('./views/Elder.vue') },
  { path: '/test',         name: 'test',            component: () => import('./views/Test.vue') },
  { path: '/clean',        name: 'clean',           component: () => import('./views/Clean.vue') },
]

export default createRouter({ history: createWebHashHistory(), routes })
```

URL 示例：`http://localhost:5173/#/translate`（hash mode，pywebview 兼容）。

### 8.2 路由守卫

- 全局前置守卫：`speed` 路由离开时停止轮询
- 无认证/权限守卫

---

## 九、Python 后端改动

### 9.1 改动方法清单（约 15-20 个方法）

| 方法 | 当前实现 | 新实现 |
|------|---------|--------|
| `log_ui(message)` | `run_js("addLogMessage(...)")` | `self._emit('lcta:log', {message})` |
| `update_progress(pct, text)` | `run_js("updateProgress(...)")` | `self._emit('lcta:progress', {percent, text})` |
| `progress_callback(pct)` | 调 `update_progress` | 改调 `self._emit(...)` |
| `browse_file(id)` | `run_js("document.getElementById(...).value=...")` | `self._emit('lcta:file-picked', {inputId, path})` |
| `browse_folder(id)` | 同上 | 同上 |
| `set_modal_status(status, mid)` | `evaluate_js("modalWindows.find(...).setStatus(...)")` | `self._emit('lcta:modal-status', {modalId, status})` |
| `add_modal_log(msg, mid)` | `evaluate_js("modalWindows.find(...).addLog(...)")` | `self._emit('lcta:modal-log', {modalId, message})` |
| `update_modal_progress(pct, text, mid)` | `evaluate_js("modalWindows.find(...).updateProgress(...)")` | `self._emit('lcta:modal-progress', {modalId, percent, text})` |
| `on_drop(e)` | `evaluate_js("dragDropManager.onFileDropCallback(...)")` | `self._emit('lcta:file-dropped', {files})` |
| `save_setting_from()` | `run_js("...collect config from DOM...")` | **删除** — Vue 端 `beforeunload` 直接调 `configStore.save()` |
| `main()` | `webview.start(func=start_func, ...)` | 添加 `--dev` URL 切换逻辑 |

### 9.2 不需要改动的方法（约 50+ 个）

所有只返回数据或操作文件的方法零改动：
- 配置 CRUD：`get_startup_data()`、`get_config_value()`、`update_config_batch()`、`get_attr()`、`set_attr()` 等
- 长操作调度：`start_translation()`、`download_llc_translation()`、`download_ourplay_translation()` 等
- CDN/加速：`cdn_*()`、`speed_*()` 系列
- 文件操作：`get_translation_packages()`、`get_installed_packages()`、`find_installed_mod()` 等
- 更新：`auto_check_update()`、`manual_check_update()`、`perform_update_in_modal()` 等

### 9.3 `_emit()` 辅助方法

```python
def _emit(self, event_name: str, detail: dict):
    import json
    payload = json.dumps(detail, ensure_ascii=False)
    self._window.evaluate_js(
        f"window.dispatchEvent(new CustomEvent('{event_name}', {{ detail: {payload} }}))"
    )
```

### 9.4 LogManager 回调适配

当前 `main()` 中的 LogManager 回调设置保持不变，但 `set_modal_status`、`add_modal_log`、`update_modal_progress` 三个方法内部改为 `self._emit()`。

---

## 十、构建流水线改动

### 10.1 InitCode.py 简化

移除 CDN 下载和 index.html 链接替换逻辑（约 170 行 → 80 行）。保留：
- C 变体源文件生成
- favicon.ico / README.md 复制

### 10.2 build.ps1 改动

在 Step 1（InitCode）和 Step 4（复制源文件）之间插入 **Step 1.5: Vite 构建**：

```powershell
# Step 1.5: Vite 构建前端
Write-Host "`n构建 Vue 前端..." -ForegroundColor Yellow
Push-Location "$ProjectRoot\webui"

if (-not (Test-Path "node_modules")) {
    Write-Host "  安装 npm 依赖..."
    npm install
    if ($LASTEXITCODE -ne 0) { Pop-Location; exit 1 }
}

npm run build
if ($LASTEXITCODE -ne 0) {
    Write-Host "  ERROR: Vite 构建失败" -ForegroundColor Red
    Pop-Location; exit 1
}
Pop-Location
```

Step 4 中 webui 复制逻辑改为仅复制 `webui/dist/` 到目标路径的 `webui/` 目录。

### 10.3 release.yml 改动

在 checkout 和 Python setup 之间添加：

```yaml
- name: Setup Node.js
  uses: actions/setup-node@v4
  with:
    node-version: '20'

- name: Build Vue frontend
  run: |
    cd webui
    npm ci
    npm run build
```

### 10.4 Dev/Prod 入口切换

```python
# webui/app.py
dev_mode = '--dev' in sys.argv

if dev_mode:
    url = "http://localhost:5173"
else:
    url = os.path.join(os.getenv('path_'), "webui/dist/index.html")
```

---

## 十一、测试策略

### 11.1 测试工具

- **Vitest** — 单元测试 + 组件测试
- **@vue/test-utils** — Vue 组件 mount + 交互
- **happy-dom** — 轻量 DOM 模拟

### 11.2 测试分层

| 层 | 覆盖目标 | 文件 |
|-----|---------|------|
| 工具函数 | `api.ts`、`events.ts`、`crypto.ts` | `src/utils/__tests__/` |
| Pinia Store | config、modal、log、theme、update | `src/stores/__tests__/` |
| 核心组件 | ModalWindow、ConfirmModal、ThemeToggle | `src/components/__tests__/` |

### 11.3 Mock 策略

```ts
// vitest.setup.ts — 全局 mock pywebview
beforeEach(() => {
  vi.stubGlobal('pywebview', {
    api: {
      get_startup_data: vi.fn().mockResolvedValue(mockStartup),
      update_config_batch: vi.fn().mockResolvedValue({ updated: 1 }),
      //
    }
  })
})
```

### 11.4 不做的事

- 不写视图级快照测试（18 个 View 维护成本高）
- 不写 E2E 测试（pywebview 环境无法在 CI 中自动化）
- ESLint 和 TypeScript 编译作为构建的前置步骤（`npm run build` = `vue-tsc --noEmit` + `eslint src/` + `vite build`）

---

## 十二、迁移阶段

| 阶段 | 内容 | 涉及文件 | 可独立测试 |
|------|------|---------|----------|
| 1 | 基础设施：package.json、Vite、TS、ESLint 配置 + `types/api.d.ts` + `utils/*.ts` | 新建 10+ 文件 | `npm run build` 成功输出 dist/ |
| 2 | 框架层：App.vue、router.ts、4 个 Store、共享组件（Modal/Sidebar/Theme/Help） | 新建 15+ 文件 | 启动 Vite dev server → pywebview 加载，Sidebar + 主题切换可用 |
| 3 | Python 适配：`_emit()` 方法 + 15-20 个方法改写 + `--dev` 参数 | `webui/app.py` | 启动 dev 模式 → 前端能收到 Python 推送的 Event |
| 4 | 页面迁移（四批）：Dashboard→Settings→About→Welcome→Log → Install→Manage→Download→Fancy→Proper → Translate→CDN→Speed→Config→Clean → Elder→LauncherConfig→Test | 新建 18 个 View | 每批迁移后功能对等验证 |
| 5 | 构建流水线：InitCode.py 简化 + build.ps1 插入 Vite + release.yml 加 Node.js | 3 个文件 | `build.ps1` 从头运行到生成 .zip |
| 6 | 测试 + 清理：编写单元测试 + TS/ESLint 通过 + 删除旧文件 | 新建 5+ 测试文件，删除 15+ 旧文件 | `npm run build` 全通过 |

---

## 十三、风险与缓解

| 风险 | 缓解 |
|------|------|
| WebView2 对 Vue 3 兼容性 | 阶段 1 即用 Vite dev server + pywebview 验证 shell 渲染 |
| `pywebview.api` 在 HMR 后丢失 | `getApi()` 每次检查 `window.pywebview.api`，失效则重新 `await initApi()` |
| 18 页面迁移遗漏功能 | 分批迁移，每批与旧版对照核验 |
| TypeScript 类型与 Python API 不同步 | 类型以 `app.py` 方法签名为唯一真源，与阶段 3 同步编写 |
| npm install 在 CI 中慢 | CI 可用 `actions/setup-node` 内置缓存 |
| 构建体积超标 | Vite tree-shaking 后预计更小，若溢出则排查依赖 |
