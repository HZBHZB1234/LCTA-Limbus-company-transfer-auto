// ============================
// 工具函数模块
// ============================

// 确保modal-container存在
function ensureModalContainer() {
    let container = document.getElementById('modal-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'modal-container';
        document.body.appendChild(container);
    }
    return container;
}

// 确保最小化窗口容器存在
function ensureMinimizedContainer() {
    let container = document.getElementById('minimized-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'minimized-container';
        container.style.position = 'fixed';
        container.style.top = '80px';
        container.style.right = '20px';
        container.style.bottom = '20px';
        container.style.width = '300px';
        container.style.display = 'flex';
        container.style.flexDirection = 'column';
        container.style.alignItems = 'flex-end';
        container.style.gap = '10px';
        container.style.zIndex = '999';
        container.style.maxHeight = 'calc(100vh - 100px)';
        container.style.overflowY = 'auto';
        container.style.overflowX = 'hidden';
        container.style.padding = '5px';
        document.body.appendChild(container);
    }
    return container;
}

// 切换侧边栏按钮激活状态
function initNavigation() {
    document.querySelectorAll('.nav-btn').forEach(button => {
        button.addEventListener('click', () => {
            if (button.classList.contains('active')) {
                return;
            }
            
            document.querySelectorAll('.nav-btn').forEach(btn => {
                btn.classList.remove('active');
            });

            button.classList.add('active');
            
            document.querySelectorAll('.content-section').forEach(section => {
                if (section.classList.contains('active')) {
                    AnimationManager.fadeOut(section, 150);
                    setTimeout(() => {
                        section.classList.remove('active');
                    }, 150);
                }
            });
            
            const sectionId = button.id.replace('-btn', '-section');
            const section = document.getElementById(sectionId);
            if (section) {
                setTimeout(() => {
                    section.classList.add('active');
                    AnimationManager.fadeIn(section, 150);
                    
                    if (sectionId === 'log-section') {
                        scrollLogToBottom();
                    }
                    
                    if (sectionId === 'install-section') {
                        refreshInstallPackageList();
                    }

                    if (sectionId === 'manage-section') {
                        refreshInstalledPackageList();
                        refreshInstalledModList();
                        refreshSymlink();
                    }

                    if (sectionId === 'cdn-section' && typeof cdnManager !== 'undefined') {
                        cdnManager.init();
                    }

                    if (sectionId === 'speed-section' && typeof speedPage !== 'undefined') {
                        speedPage.init();
                    } else if (typeof speedPage !== 'undefined') {
                        speedPage.stop();
                    }

                    if (sectionId !== 'test-section') {
                        goTestSection(false);
                    }

                    if (sectionId !== 'clean-section') {
                        goCleanSection(false);
                    }                    
                }, 150);
            }
        });
    });
}

// 滚动日志到底部
function scrollLogToBottom() {
    const logDisplay = document.getElementById('log-display');
    if (logDisplay) {
        setTimeout(() => {
            logDisplay.scrollTop = logDisplay.scrollHeight;
        }, 100);
    }
}

// 密码显示/隐藏切换
function initPasswordToggles() {
    document.querySelectorAll('.toggle-password').forEach(button => {
        button.addEventListener('click', function() {
            const input = this.parentElement.querySelector('input');
            const icon = this.querySelector('i');
            
            if (input.type === 'password') {
                input.type = 'text';
                icon.classList.remove('fa-eye');
                icon.classList.add('fa-eye-slash');
            } else {
                input.type = 'password';
                icon.classList.remove('fa-eye-slash');
                icon.classList.add('fa-eye');
            }
        });
    });
}
/**
 * 使用密码加密文本
 * @param {string} password - 密码字符串
 * @param {string} plaintext - 要加密的文本
 * @returns {Promise<string>} Base64编码的加密结果（包含IV和加密数据）
 */

// === 加密工具 ===

async function encryptText(password, plaintext) {
    try {
        // 1. 准备密钥材料
        const encoder = new TextEncoder();
        const passwordBuffer = encoder.encode(password);
        
        // 2. 创建密钥
        const keyMaterial = await crypto.subtle.importKey(
            'raw',
            passwordBuffer,
            { name: 'PBKDF2' },
            false,
            ['deriveKey']
        );
        
        // 3. 派生加密密钥
        const salt = crypto.getRandomValues(new Uint8Array(16));
        const iv = crypto.getRandomValues(new Uint8Array(12)); // GCM推荐12字节IV
        
        const key = await crypto.subtle.deriveKey(
            {
                name: 'PBKDF2',
                salt: salt,
                iterations: 100000,
                hash: 'SHA-256'
            },
            keyMaterial,
            { name: 'AES-GCM', length: 256 },
            false,
            ['encrypt']
        );
        
        // 4. 加密数据
        const plaintextBuffer = encoder.encode(plaintext);
        const encryptedBuffer = await crypto.subtle.encrypt(
            {
                name: 'AES-GCM',
                iv: iv
            },
            key,
            plaintextBuffer
        );
        
        // 5. 组合结果：salt + iv + 加密数据
        const combinedBuffer = new Uint8Array(
            salt.length + iv.length + encryptedBuffer.byteLength
        );
        combinedBuffer.set(salt, 0);
        combinedBuffer.set(iv, salt.length);
        combinedBuffer.set(new Uint8Array(encryptedBuffer), salt.length + iv.length);
        
        // 6. 转换为Base64字符串
        return btoa(String.fromCharCode(...combinedBuffer));
        
    } catch (error) {
        console.error('加密失败:', error);
        throw new Error('加密失败: ' + error.message);
    }
}

/**
 * 使用密码解密文本
 * @param {string} password - 密码字符串
 * @param {string} encryptedBase64 - Base64编码的加密数据
 * @returns {Promise<string>} 解密后的文本
 */
async function decryptText(password, encryptedBase64) {
    try {
        // 1. 解码Base64数据
        const combinedBuffer = Uint8Array.from(atob(encryptedBase64), c => c.charCodeAt(0));
        
        // 2. 提取各部分数据
        const salt = combinedBuffer.slice(0, 16);
        const iv = combinedBuffer.slice(16, 28); // 12字节IV
        const encryptedData = combinedBuffer.slice(28);
        
        // 3. 准备密钥材料
        const encoder = new TextEncoder();
        const passwordBuffer = encoder.encode(password);
        
        const keyMaterial = await crypto.subtle.importKey(
            'raw',
            passwordBuffer,
            { name: 'PBKDF2' },
            false,
            ['deriveKey']
        );
        
        // 4. 派生解密密钥
        const key = await crypto.subtle.deriveKey(
            {
                name: 'PBKDF2',
                salt: salt,
                iterations: 100000,
                hash: 'SHA-256'
            },
            keyMaterial,
            { name: 'AES-GCM', length: 256 },
            false,
            ['decrypt']
        );
        
        // 5. 解密数据
        const decryptedBuffer = await crypto.subtle.decrypt(
            {
                name: 'AES-GCM',
                iv: iv
            },
            key,
            encryptedData
        );
        
        // 6. 转换为字符串
        const decoder = new TextDecoder();
        return decoder.decode(decryptedBuffer);
        
    } catch (error) {
        console.error('解密失败:', error);
        throw new Error('解密失败: ' + error.message);
    }
}

// === 进度与日志 ===

function updateProgress(percent, text) {
    const progressFill = document.getElementById('progress-fill');
    const progressPercent = document.getElementById('progress-percent');
    const progressText = document.getElementById('progress-text');
    const progressContainer = document.getElementById('translation-progress');
    
    if (progressFill) {
        progressFill.style.width = percent + '%';
    }
    
    if (progressPercent) {
        progressPercent.textContent = percent + '%';
    }
    
    if (progressText && text) {
        progressText.textContent = text;
    }
    
    if (progressContainer) {
        progressContainer.style.display = 'block';
    }
}

// 添加日志消息
function addLogMessage(message, level = 'info') {
    const logDisplay = document.getElementById('log-display');
    if (logDisplay) {
        const now = new Date();
        const timestamp = `[${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')} ${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}:${String(now.getSeconds()).padStart(2, '0')}]`;
        
        const logEntry = document.createElement('div');
        logEntry.className = `log-entry ${level}`;
        logEntry.innerHTML = `
            <div class="log-timestamp">${timestamp}</div>
            <div class="log-level">[${level.toUpperCase()}]</div>
            <div class="log-message">${message}</div>
        `;
        
        logDisplay.appendChild(logEntry);
        logDisplay.scrollTop = logDisplay.scrollHeight;
    };
    if (window.apiReady) {
        pywebview.api.log(message).catch(
            function(error) { console.log(error); })
    };
}

const renderer = new marked.Renderer();

// 重写 link 方法
renderer.link = function (href, title, text) {
  // 生成原始的链接 HTML
  const link = marked.Renderer.prototype.link.call(this, href, title, text);
  // 如果已经是 <a> 标签，则添加 target 和 rel
  return link.replace('<a', '<a target="_blank" rel="noopener noreferrer"');
};

// 使用自定义渲染器
marked.setOptions({ renderer });
// 简单Markdown转HTML
function simpleMarkdownToHtml(text) {
    const html = marked.parse(text);
    return html;
}

// === 悬停提示 ===

// 配置项悬停提示映射
const TOOLTIP_DATA = {
    // ===== 翻译工具 =====
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

    // ===== 安装已有汉化 =====
    'install-package-directory': '存放汉化包的目录路径。留空则使用程序所在目录。修改后会自动扫描目录下的汉化包。',
    'clean-progress': '清理游戏存档中的进度文件，可解决因进度数据导致的游戏异常问题。',
    'clean-notice': '清理游戏中的通知缓存文件，可解决通知显示异常或重复提示的问题。',
    'clean-mods': '清理默认 MOD 资源文件，适用于因 MOD 残留文件导致的启动或运行问题。',

    // ===== 汉化包下载 =====
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

    // ===== 设置 =====
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

    // ===== Launcher配置 =====
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
    'steam-command': '用于通过 Steam 启动游戏的命令行参数。复制后可粘贴到 Steam 游戏属性中的启动选项。',

    // ===== 抓取专有词汇 =====
    'proper-output': '专有名词的输出格式。"JSON格式"输出标准 JSON 文件；"单文件格式"将所有词汇合并在一个文件中；"双文件格式"将词汇分为两个文件输出。',
    'proper-skip-space': '跳过包含空格的词汇，避免将多词短语错误识别为专有名词。',
    'proper-max-count': '限制最多提取的专有名词数量。留空表示不限制。数值越大结果越多但可能包含更多噪声。',
    'proper-min-count': '专有名词的最小字符长度。增大此值可减少短词汇的错误匹配，提高提取精度。',
    'proper-join-char': '单文件格式输出时的词汇分隔符，默认使用逗号。仅在输出格式为"单文件格式"时生效。',
};

// 初始化所有静态配置项的悬停提示
function initTooltips() {
    // 为 form-group 中已知 ID 的元素添加 tooltip
    Object.entries(TOOLTIP_DATA).forEach(([id, description]) => {
        const element = document.getElementById(id);
        if (!element) return;

        // 查找最合适的父级元素来放置 tooltip
        let tooltipTarget = null;

        if (element.tagName === 'INPUT' && element.type === 'checkbox') {
            // 复选框：使用 .checkbox-container 作为 tooltip 目标
            tooltipTarget = element.closest('.checkbox-container');
        } else if (element.tagName === 'INPUT' || element.tagName === 'SELECT' || element.tagName === 'TEXTAREA') {
            // 普通输入框/下拉框：优先使用关联的 label
            const formGroup = element.closest('.form-group');
            if (formGroup) {
                const label = formGroup.querySelector('label:not(.checkbox-container)');
                if (label && label.getAttribute('for') === id) {
                    tooltipTarget = label;
                } else {
                    tooltipTarget = formGroup;
                }
            }
        } else {
            // 其他元素（如 DIV 容器）：使用元素本身或其 form-group
            tooltipTarget = element.closest('.form-group') || element;
        }

        if (tooltipTarget) {
            tooltipTarget.setAttribute('data-tooltip', description);
        }
    });
}

// 创建连接遮罩层

// === 连接状态 ===

function createConnectionMask() {
    const mask = document.createElement('div');
    mask.id = 'connection-mask';
    mask.className = 'connection-mask';
    
    mask.innerHTML = `
        <div class="mask-content">
            <div class="spinner"></div>
            <div class="mask-text">正在连接到API...</div>
        </div>
    `;
    
    document.body.appendChild(mask);
    
    const statusIndicator = document.querySelector('.status-indicator');
    if (statusIndicator) {
        const statusDot = statusIndicator.querySelector('.status-dot');
        const statusText = statusIndicator.querySelector('span');
        
        if (statusDot) {
            statusDot.className = 'status-dot connecting';
        }
        
        if (statusText) {
            statusText.textContent = '连接中';
        }
    }
}

// 移除连接遮罩层
function removeConnectionMask() {
    const mask = document.getElementById('connection-mask');
    if (mask) {
        mask.style.opacity = '0';
        setTimeout(() => {
            if (mask.parentNode) {
                mask.parentNode.removeChild(mask);
            }
        }, 300);
    }
    
    const statusIndicator = document.querySelector('.status-indicator');
    if (statusIndicator) {
        const statusDot = statusIndicator.querySelector('.status-dot');
        const statusText = statusIndicator.querySelector('span');
        
        if (statusDot) {
            statusDot.className = 'status-dot connected';
        }
        
        if (statusText) {
            statusText.textContent = '已连接';
        }
    }
}

function goAndShow(name) {
    const targetButton = document.getElementById(`${name}-btn`);
    if (!targetButton) return;
    targetButton.style.display = 'block';
    targetButton.click();
    // 如果切换到首页，刷新仪表盘
    if (name === 'dashboard') {
        refreshDashboard();
    }
}

function setupGlobalErrorHandling() {
    window.preApiErrors = [];
    window.preApiRejections = [];
    window.apiReady = false;
    
    window.addEventListener('error', function(event) {
        const errorMessage = `[全局错误] ${event.message} at ${event.filename}:${event.lineno}:${event.colno}`;
        const stack = event.error && event.error.stack ? event.error.stack : '无堆栈信息';
        
        addLogMessage(errorMessage, 'error');
        addLogMessage(stack, 'error');
        console.log('已捕捉到异常',errorMessage);
        
        if (typeof pywebview !== 'undefined' && pywebview.api && pywebview.api.log && window.apiReady) {
            pywebview.api.log(`[前端错误] ${errorMessage}\n堆栈: ${stack}`)
                .catch(function(error) {
                    console.error('无法将错误发送到后端:', error);
                });
        } else {
            window.preApiErrors.push({
                message: errorMessage,
                stack: stack,
                timestamp: new Date().toISOString()
            });
        }
    });
    
    window.addEventListener('unhandledrejection', function(event) {
        const errorMessage = `[未处理的Promise拒绝] ${event.reason}`;
        
        addLogMessage(errorMessage, 'error');
        console.log('已捕捉到异常',errorMessage);
        
        if (typeof pywebview !== 'undefined' && pywebview.api && pywebview.api.log && window.apiReady) {
            pywebview.api.log(`[前端Promise错误] ${errorMessage}`)
                .catch(function(error) {
                    console.error('无法将Promise错误发送到后端:', error);
                });
        } else {
            window.preApiRejections.push({
                message: errorMessage,
                timestamp: new Date().toISOString()
            });
        }
    });
}


// === 侧边栏 ===

// 侧边栏折叠切换
function toggleSidebar() {
    const sidebar = document.querySelector('.sidebar');
    const isCollapsed = sidebar.classList.toggle('collapsed');
    try {
        localStorage.setItem('lcta-sidebar-collapsed', isCollapsed ? '1' : '0');
    } catch (e) { /* ignore */ }
}

// 恢复侧边栏折叠状态
function restoreSidebarState() {
    try {
        if (localStorage.getItem('lcta-sidebar-collapsed') === '1') {
            document.querySelector('.sidebar').classList.add('collapsed');
        }
    } catch (e) { /* ignore */ }
}

// 侧边栏搜索
function onSidebarSearch(query) {
    const navBtns = document.querySelectorAll('.sidebar-menu .nav-btn');
    const groups = document.querySelectorAll('.sidebar-menu .nav-group');
    const lower = query.toLowerCase().trim();

    if (!lower) {
        // 显示全部
        navBtns.forEach(b => b.style.display = '');
        groups.forEach(g => g.style.display = '');
        return;
    }

    groups.forEach(g => {
        let hasVisible = false;
        g.querySelectorAll('.nav-btn').forEach(btn => {
            const text = btn.textContent.toLowerCase();
            if (text.includes(lower)) {
                btn.style.display = '';
                hasVisible = true;
            } else {
                btn.style.display = 'none';
            }
        });
        // 隐藏空分组
        g.style.display = hasVisible ? '' : 'none';
    });
}

// 动态注入帮助按钮到导航栏和页面标题
function injectHelpButtons() {
    // 为每个导航按钮添加 ? 帮助图标
    document.querySelectorAll('.nav-btn').forEach(btn => {
        // 避免重复添加
        if (btn.querySelector('.nav-help-btn')) return;
        const helpBtn = document.createElement('button');
        helpBtn.className = 'nav-help-btn';
        helpBtn.innerHTML = '<i class="fas fa-question"></i>';
        helpBtn.title = '打开页面帮助';
        helpBtn.onclick = (e) => {
            e.stopPropagation();
            const page = btn.id.replace('-btn', '');
            helpDrawer.open(page);
        };
        btn.appendChild(helpBtn);
    });

    // 为每个导航按钮添加绿色指示点（预留空间）
    document.querySelectorAll('.nav-btn').forEach(btn => {
        if (btn.querySelector('.nav-indicator')) return;
        const indicator = document.createElement('div');
        indicator.className = 'nav-indicator';
        btn.appendChild(indicator);
    });

}

async function showGuide(page) {
    await helpDrawer.open(page);
}

async function showMarkdownModal(link, title= '指导', pre='正在加载数据内容') {

    const modal = showMessage(title, pre)

    const response = await fetch(link);

    let markdownText

    if (!response.ok) {
        markdownText = `加载内容失败: ${response.status} ${response.statusText}`;
    } else {
        markdownText = await response.text();
    };

    const bodyHtml = simpleMarkdownToHtml(markdownText);
    const showing = `<div class="markdown-body" id="update-markdown">${bodyHtml}</div>`

    setTimeout(() => {
        const statusElement = document.getElementById(`modal-status-${modal.id}`);
        if (statusElement) {
            statusElement.innerHTML = showing;
        }
    }, 100);
}


(function() {
  // 按键状态管理
  let wPressed = false;         // W 键是否正在被按下
  let wTimer = null;            // 长按计时器 ID
  let wProgressInterval = null; // 进度环更新间隔
  let wStartTime = 0;           // 长按开始时间
  const LONG_PRESS_TIME = 2000; // 长按阈值（毫秒）- 与文档统一为2秒
  const PROGRESS_STEP = 50;     // 进度更新间隔（毫秒）

  // 创建进度指示器 DOM
  function createWProgressIndicator() {
    const existing = document.getElementById('w-press-indicator');
    if (existing) return existing;

    const indicator = document.createElement('div');
    indicator.id = 'w-press-indicator';
    indicator.className = 'w-press-indicator';
    indicator.innerHTML = `
      <div class="w-press-ring">
        <svg viewBox="0 0 60 60" width="60" height="60">
          <circle class="w-press-track" cx="30" cy="30" r="25" fill="none"
                  stroke="var(--color-border)" stroke-width="3"/>
          <circle class="w-press-fill" cx="30" cy="30" r="25" fill="none"
                  stroke="var(--color-primary)" stroke-width="3"
                  stroke-dasharray="157" stroke-dashoffset="157" stroke-linecap="round"
                  transform="rotate(-90 30 30)"/>
        </svg>
        <div class="w-press-icon">?</div>
      </div>
      <div class="w-press-label">按住 <kbd>W</kbd> 键打开帮助</div>
    `;
    document.body.appendChild(indicator);
    // 触发进场动画
    requestAnimationFrame(() => indicator.classList.add('visible'));
    return indicator;
  }

  // 移除进度指示器
  function removeWProgressIndicator() {
    const indicator = document.getElementById('w-press-indicator');
    if (indicator) {
      indicator.classList.remove('visible');
      setTimeout(() => indicator.remove(), 200);
    }
  }

  // 更新进度环
  function updateWProgress(elapsed) {
    const progress = Math.min(elapsed / LONG_PRESS_TIME, 1);
    const indicator = document.getElementById('w-press-indicator');
    if (!indicator) return;
    const fill = indicator.querySelector('.w-press-fill');
    if (fill) {
      const circumference = 2 * Math.PI * 25; // ~157
      fill.style.strokeDashoffset = circumference * (1 - progress);
    }
    // 快完成时脉冲动画
    if (progress > 0.75) {
      indicator.classList.add('nearly-done');
    }
  }

  // 用户自定义的回调函数
  async function onLongPressW() {
    removeWProgressIndicator();
    const activeNav = document.querySelector('.nav-btn.active');
    if (!activeNav) {
      return;
    }
    const page = activeNav.id.replace('-btn', '');
    try {
      await showGuide(page);
    } catch (e) {
      // silently fail — guide is non-critical
    }
  }

  // 重置与 W 键相关的所有状态
  function resetWState() {
    if (wTimer) {
      clearTimeout(wTimer);
      wTimer = null;
    }
    if (wProgressInterval) {
      clearInterval(wProgressInterval);
      wProgressInterval = null;
    }
    removeWProgressIndicator();
    wPressed = false;
    wStartTime = 0;
  }

  // 键盘按下事件
  function handleKeyDown(e) {
    if (e.code !== 'KeyW') return;

    // 排除输入框、文本域、下拉框、可编辑元素内的长按
    const tag = e.target.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || e.target.isContentEditable) {
      return;
    }

    if (wPressed) return;
    wPressed = true;
    wStartTime = Date.now();

    // 显示进度指示器
    createWProgressIndicator();
    updateWProgress(0);

    // 定期更新进度环
    wProgressInterval = setInterval(() => {
      updateWProgress(Date.now() - wStartTime);
    }, PROGRESS_STEP);

    // 设置长按计时器
    wTimer = setTimeout(() => {
      wTimer = null;
      onLongPressW();
    }, LONG_PRESS_TIME);
  }

  // 键盘松开事件
  function handleKeyUp(e) {
    if (e.code === 'KeyW') {
      resetWState();
    }
  }

  // 窗口失去焦点时重置
  function handleBlur() {
    resetWState();
  }

  // 添加全局事件监听
  window.addEventListener('keydown', handleKeyDown);
  window.addEventListener('keyup', handleKeyUp);
  window.addEventListener('blur', handleBlur);

  // 清理函数
  window.removeLongPressW = function() {
    window.removeEventListener('keydown', handleKeyDown);
    window.removeEventListener('keyup', handleKeyUp);
    window.removeEventListener('blur', handleBlur);
    resetWState();
  };
})();

// Ctrl+K / Cmd+K 聚焦侧边栏搜索
(function() {
  document.addEventListener('keydown', function(e) {
    // Ctrl+K 或 Cmd+K
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
      e.preventDefault();
      const searchInput = document.getElementById('sidebar-search-input');
      if (searchInput) {
        // 如果侧边栏折叠，先展开
        const sidebar = document.querySelector('.sidebar');
        if (sidebar && sidebar.classList.contains('collapsed')) {
          toggleSidebar();
        }
        searchInput.focus();
        searchInput.select();
      }
    }
  });
})();
