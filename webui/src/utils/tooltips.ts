import type { Directive, App } from 'vue'

const TOOLTIP_DATA: Record<string, string> = {
  // ===== Translate =====
  'enable-proper': '翻译时参考专有名词表，提高人名、地名等术语的翻译一致性。LLM翻译专用，默认开启。若出现大量匹配错误可关闭。',
  'auto-fetch-proper': '翻译过程中自动重新提取专有词汇。如需使用自定义专有名词文件，请关闭此选项并在下方手动指定文件路径。',
  'proper-path': '关闭"自动抓取专有词汇"后，可手动指定自定义的专有名词 JSON 文件路径。',
  'enable-role': '为 LLM 翻译添加上下文标记，帮助模型理解当前文本属于哪个角色，提升角色对话的翻译准确性。',
  'enable-skill': '为 LLM 翻译添加状态效果标记，帮助模型理解技能描述中的游戏机制术语，提高技能翻译质量。',
  'enable-dev-settings': '开启后可手动指定各语言的源文本路径。通常情况下无需手动设置，程序会自动检测。',
  'kr-path-text': '原始韩文游戏文本所在的文件夹路径。仅在自动检测失败或需要特殊处理时手动配置。',
  'jp-path-text': '日文游戏文本所在的文件夹路径。仅在自动检测失败或需要特殊处理时手动配置。',
  'en-path-text': '英文游戏文本所在的文件夹路径。仅在自动检测失败或需要特殊处理时手动配置。',
  'llc-path-text': '参考中文文本（零协会汉化）所在的文件夹路径。如果未安装零协会汉化，需手动指定。',
  'has-prefix': '按带前缀的文件名格式处理源文件。如果源文件按特定前缀命名规则组织，请开启此选项。',
  'dump-translation': '将请求文本与响应文本输出至日志文件，方便调试和排查翻译问题。',
  'fallback': '当 LLM 返回格式无法解析时，自动按 xml_json→json_json→xml_xml 顺序切换格式重试。建议开启以减少格式错误导致的翻译失败。',
  'prompt-format': '选择提示词与响应的格式。"XML请求→JSON响应"为推荐选项，平衡了结构化与解析可靠性。"JSON请求→JSON响应"适合偏好纯 JSON 的场景。"XML请求→XML响应"在某些模型上格式遵循度更高。',
  'from-lang': '选择要翻译的源语言。LLM 翻译无需选择此项，程序会自动检测语言。',
  'max-workers': '并发翻译的最大线程数。数值越大翻译越快，但过高可能导致 API 限流或被暂时封禁。建议保持默认值 4。',
  'enable-concurrent': '开启后多个文件将并行翻译，大幅提升整体速度。关闭则逐个文件串行处理，速度较慢但更稳定。',
  'translation-mode': '多阶段翻译（推荐）：消歧→翻译→自检三阶段管线，质量更高但耗时更长。单阶段翻译：直接翻译，速度更快但可能遗漏上下文匹配。',
  'enable-self-check': '翻译完成后由 LLM 自行检查翻译质量并修正明显错误。可提升质量但会增加 API 调用次数和耗时。',
  'enable-thinking': '启用后 LLM 将在翻译前进行深度思考（chain-of-thought），提高翻译质量但会增加 API 响应时间和 token 消耗。DeepSeek 使用原生思考模式，其他 LLM 使用 OpenAI 通用 reasoning_effort 参数。',
  'disambiguation-mode': '混合模式（推荐）：相似度匹配优先，必要时使用 LLM 消歧。相似度匹配：仅用 Jaccard 相似度进行 JP/EN 交叉验证。LLM 消歧：完全由 LLM 判断专有名词归属。',
  'min-confidence': '专有名词匹配的最低置信度阈值。高：只采纳最确定的匹配，漏翻可能增加。低：采纳更多匹配但可能引入错误。推荐使用"中"。',

  // ===== Install =====
  'install-package-directory': '存放汉化包的目录路径。留空则使用程序所在目录。修改后会自动扫描目录下的汉化包。',
  'clean-progress': '清理游戏存档中的进度文件，可解决因进度数据导致的游戏异常问题。',
  'clean-notice': '清理游戏中的通知缓存文件，可解决通知显示异常或重复提示的问题。',
  'clean-mods': '清理默认 MOD 资源文件，适用于因 MOD 残留文件导致的启动或运行问题。',

  // ===== Download =====
  'ourplay-font-option': 'OurPlay 汉化包携带两份相同字体文件。"保留原字体"不做处理；"精简字体"去除冗余文件节省空间；"使用本地字体缓存"使用已缓存的字体避免重复下载。',
  'ourplay-check-hash': '下载完成后校验文件完整性。如果文件不完整，程序会提出警告。建议开启以确保下载文件正确。',
  'ourplay-use-api': '通过 Webnote API 获取下载链接。具有延迟，不建议开启。关闭后使用直连下载，速度更快。',
  'ourplay-source': '选择 OurPlay 汉化包的 API 来源。"PC API"使用 PC 端接口，较为稳定；"Android API"使用移动端接口，需基板包辅助转换文件结构，可能有一些问题，支持神人汉化。',
  'ourplay-official': '下载 OurPlay 正经版汉化，反之下载神人汉化。仅 Android API 源有效。',
  'ourplay-refer-package': '基板包（参考包）的路径，用于将 Android API 下载的汉化包文件转换为可被游戏理解的格式。支持目录或 zip 文件。留空则自动从游戏安装目录的 LLC 汉化包检测。仅 Android API 源有效。',
  'llc-zip-type': '零协会汉化包的压缩格式。ZIP 格式兼容性更好无需额外软件；7Z 格式压缩率更高文件更小，但需 7-Zip 支持。',
  'llc-download-source': '零协会汉化包的下载来源。GitHub 更新最及时；公益镜像通过 API 代理下载，适合 GitHub 访问不稳定的情况。',
  'llc-use-proxy': '通过代理服务器加速 GitHub 下载请求。建议开启，解决国内访问 GitHub 不稳定、下载慢的问题。',
  'llc-use-cache': '使用本地已缓存的字体文件而非重新下载。缓存路径可在"设置"页面配置。',
  'llc-dump-default': '下载的汉化包将被解压并保留原始文件结构，而非保存为压缩包格式。此为历史遗留选项，一般无需开启。',
  'machine-download-source': 'LCTA-AU 汉化包的下载来源。LCTA-AU 翻译延迟仅 1-3 小时且翻译质量高于 OurPlay，建议优先使用。',
  'machine-use-proxy': '通过代理服务器加速 LCTA-AU 汉化包的 GitHub 下载。建议开启。',
  'bubble-color': '下载彩色气泡文本模组，使游戏中的对话气泡显示不同颜色。效果参考相关视频链接。',
  'bubble-llc': '下载包含随机加载文本的气泡文本版本，在战斗加载页面显示零协会曾使用的加载文本。',
  'bubble-install': '下载完成后自动安装气泡文本到当前汉化包。建议开启，省去手动安装步骤。',

  // ===== Settings =====
  'game-path': '游戏 Limbus Company 的安装根目录。选择正确的游戏路径后，程序才能自动定位游戏文件和汉化包安装位置。',
  'debug-mode': '开启调试模式后，程序会输出更详细的日志信息，方便排查问题。一般用户无需开启。',
  'auto-check-update': '程序启动时自动检查 LCTA 工具箱是否有新版本。建议开启以保持工具为最新状态。',
  'delete-updating': '更新时自动删除已被弃用的旧版本文件，保持程序目录整洁。',
  'update-use-proxy': '通过镜像源加速程序更新下载。建议开启以解决国内访问 GitHub 不稳定的问题。',
  'update-only-stable': '仅更新到经过测试的稳定版本，跳过预览版和测试版。建议开启以确保工具运行稳定。',
  'api-crypto': '对 API 配置信息（密钥、地址等）进行加密存储，防止敏感信息以明文形式保存。修改后需在 API 配置界面保存。',
  'github-max-workers': 'GitHub 代理下载时的最大并发线程数。数值越大下载越快，但过高可能导致被限制访问。建议保持默认值。',
  'github-timeout': 'GitHub 代理请求的超时等待时间（秒）。若网络状况较差，可适当增大此值。',
  'enable-cache': '启用资源文件（如字体）的本地缓存，避免每次操作都重新下载，加快后续操作速度。',
  'enable-storage': '启用数据持久化存储，保存用户配置和运行状态。关闭后部分设置可能在重启后丢失。',

  // ===== Launcher Config =====
  'launcher-zero-zip-type': '零协会汉化包的压缩格式。ZIP 兼容性更好；7Z 压缩率更高但需 7-Zip 支持。',
  'launcher-zero-download-source': '零协会汉化包的下载来源。GitHub 更新最及时；公益镜像通过 API 代理，适合网络不稳时使用。',
  'launcher-zero-use-proxy': '通过代理服务器加速零协会汉化包的 GitHub 下载。建议开启。',
  'launcher-zero-use-cache': '使用本地已有的字体文件，跳过字体下载步骤，加快更新速度。',
  'launcher-ourplay-font-option': 'OurPlay 汉化包的字体处理方式。"保留原字体"不做处理；"精简字体"去除冗余；"使用本地缓存"复用已下载的字体。',
  'launcher-ourplay-use-api': '通过 Webnote API 获取 OurPlay 版本信息。具有延迟，适合直连获取版本信息失败时使用。',
  'launcher-ourplay-source': '启动器自动更新时使用的 OurPlay API 来源。PC API 为原版接口；Android API 为新版接口，需基板包辅助。',
  'launcher-ourplay-official': '下载 OurPlay 官方权威汉化版本。关闭后下载社区修改版。仅 Android API 源有效。',
  'launcher-ourplay-refer-package': '基板包的路径，用于 Android API 源的文件结构转换。留空则自动检测。仅 Android API 源有效。',
  'launcher-machine-download-source': 'LCTA-AU 汉化包的下载来源。建议优先使用 LCTA-AU 源，翻译质量更高。',
  'launcher-machine-use-proxy': '通过代理服务器加速 LCTA-AU 汉化包的 GitHub 下载。建议开启。',
  'launcher-work-update': '启动器自动更新模式。可选择不更新、仅更新指定汉化源，或组合更新多个汉化源。',
  'launcher-work-mod': '启动游戏时自动加载 MOD 支持。启用后可使用各类游戏模组。',
  'launcher-work-fancy': '更新汉化包后自动进行文本美化处理。相关美化选项请在"文本美化"页面配置。',
  'launcher-work-bubble': '自动更新气泡文本模组，使游戏中的对话气泡显示特效。相关设置请在"汉化包下载"页面配置。',
  'launcher-work-cdn-optimize': '启动游戏前自动测试Cloudflare和CloudFront CDN节点速度，选择最快的IP用于游戏下载和API连接。',
  'launcher-work-cdn-auto-apply': 'CDN优选完成后自动将选出的最优IP写入系统hosts文件。需要管理员权限，如权限不足会尝试UAC提权。',
  'launcher-work-cdn-cache-ttl': 'CDN优选结果的有效时间（小时）。缓存有效期内跳过测速直接使用已有hosts。设为0表示每次启动都重新测速。',
  'launcher-work-gui-mode': '在Launcher模式下显示图形化进度窗口，实时展示更新、CDN优选和游戏启动的状态与日志。关闭则使用传统的控制台模式。',
  'steam-command': '用于通过 Steam 启动游戏的命令行参数。复制后可粘贴到 Steam 游戏属性中的启动选项。',

  // ===== Proper Nouns =====
  'proper-output': '专有名词的输出格式。"JSON格式"输出标准 JSON 文件；"单文件格式"将所有词汇合并在一个文件中；"双文件格式"将词汇分为两个文件输出。',
  'proper-skip-space': '跳过包含空格的词汇，避免将多词短语错误识别为专有名词。',
  'proper-max-count': '限制最多提取的专有名词数量。留空表示不限制。数值越大结果越多但可能包含更多噪声。',
  'proper-min-count': '专有名词的最小字符长度。增大此值可减少短词汇的错误匹配，提高提取精度。',
  'proper-join-char': '单文件格式输出时的词汇分隔符，默认使用逗号。仅在输出格式为"单文件格式"时生效。',
}

let tooltipEl: HTMLDivElement | null = null
let hideTimer: ReturnType<typeof setTimeout> | null = null

function getTooltipEl(): HTMLDivElement {
  if (!tooltipEl) {
    tooltipEl = document.createElement('div')
    tooltipEl.className = 'tooltip-popup'
    tooltipEl.style.cssText = `
      position: fixed; z-index: 9999; pointer-events: none;
      max-width: 320px; padding: 8px 12px; font-size: 13px;
      line-height: 1.5; color: #fff; background: rgba(0,0,0,0.85);
      border-radius: 6px; opacity: 0; transition: opacity 0.15s ease;
      word-break: break-word;
    `
    document.body.appendChild(tooltipEl)
  }
  return tooltipEl
}

function showTooltip(el: HTMLElement, text: string): void {
  if (hideTimer) { clearTimeout(hideTimer); hideTimer = null }
  const tip = getTooltipEl()
  tip.textContent = text
  const rect = el.getBoundingClientRect()
  let left = rect.left + rect.width / 2
  let top = rect.top - 8
  tip.style.opacity = '1'
  tip.style.left = `${left}px`
  tip.style.bottom = 'auto'
  tip.style.top = `${top}px`
  tip.style.transform = 'translate(-50%, -100%)'
  const tipRect = tip.getBoundingClientRect()
  if (tipRect.top < 4) {
    top = rect.bottom + 8
    tip.style.top = `${top}px`
    tip.style.bottom = 'auto'
    tip.style.transform = 'translate(-50%, 0)'
  }
}

function hideTooltip(): void {
  hideTimer = setTimeout(() => {
    const tip = tooltipEl
    if (tip) tip.style.opacity = '0'
  }, 100)
}

const tooltipHandlers = new WeakMap<HTMLElement, {
  show: () => void
  hide: () => void
  focusShow: () => void
  focusHide: () => void
}>()

export const vTooltip: Directive<HTMLElement, string> = {
  mounted(el: HTMLElement, binding) {
    const id = el.id || binding.arg
    const text = binding.value || (id ? TOOLTIP_DATA[id] : undefined)
    if (!text) return
    const show = () => showTooltip(el, text)
    const focusShow = () => showTooltip(el, text)
    const handlers = { show, hide: hideTooltip, focusShow, focusHide: hideTooltip }
    tooltipHandlers.set(el, handlers)
    el.addEventListener('mouseenter', show)
    el.addEventListener('mouseleave', hideTooltip)
    el.addEventListener('focus', focusShow)
    el.addEventListener('blur', hideTooltip)
  },
  unmounted(el: HTMLElement) {
    const handlers = tooltipHandlers.get(el)
    if (handlers) {
      el.removeEventListener('mouseenter', handlers.show)
      el.removeEventListener('mouseleave', handlers.hide)
      el.removeEventListener('focus', handlers.focusShow)
      el.removeEventListener('blur', handlers.focusHide)
      tooltipHandlers.delete(el)
    } else {
      // Fallback: remove global hideTooltip at least
      el.removeEventListener('mouseleave', hideTooltip)
      el.removeEventListener('blur', hideTooltip)
    }
  },
}

export function installTooltipDirective(app: App): void {
  app.directive('tooltip', vTooltip)
}

export { TOOLTIP_DATA }
