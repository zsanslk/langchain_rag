// 全局变量
let currentSessionId = null;
let currentChatController = null;

// 主题切换功能
const savedTheme = localStorage.getItem('theme') || 'dark';
document.documentElement.setAttribute('data-theme', savedTheme);

function toggleTheme() {
    const currentTheme = document.documentElement.getAttribute('data-theme') || 'dark';
    const newTheme = currentTheme === 'light' ? 'dark' : 'light';
    document.documentElement.setAttribute('data-theme', newTheme);
    localStorage.setItem('theme', newTheme);
    
    // 通知Echarts需要重新渲染(如果在这页面上)
    if (typeof echartInstances !== 'undefined') {
        setTimeout(() => {
            // Echarts 适配主题的简单思路是重新加载数据或者刷新实例
            if (typeof loadStats === 'function') loadStats();
        }, 100);
    }
}

// 判断当前用户是否为管理员（读取后端注入的 data-role 属性）
function isAdmin() {
    const appContainer = document.querySelector('.app-container');
    console.log(appContainer);
    return appContainer && appContainer.dataset.role && appContainer.dataset.role.trim() === 'admin';
}

/**
 * 统一 API 请求封装：
 * - 自动处理 401（session 过期/未登录）→ 跳转登录页
 * - 自动处理非 JSON 响应 → 抛出可读错误
 * 返回 {ok, status, data} 结构
 */
async function apiFetch(url, options = {}) {
    const response = await fetch(url, options);

    // session 过期或未登录
    if (response.status === 401) {
        alert('登录已过期，请重新登录');
        window.location.href = '/login';
        throw new Error('401 Unauthorized');
    }

    // 尝试解析 JSON；若失败则抛出可读错误
    let data;
    try {
        data = await response.json();
    } catch {
        throw new Error(`服务器返回了非预期的响应（HTTP ${response.status}）`);
    }

    return { ok: response.ok, status: response.status, data };
}

// 页面加载完成后执行
document.addEventListener('DOMContentLoaded', () => {
    // 自动聚焦输入框
    const input = document.getElementById('userInput');
    if (input) input.focus();

    // 加载会话列表
    loadSessions();

    // ===== 权限控制：非管理员隐藏管理专属元素 =====
    if (!isAdmin()) {
        document.querySelectorAll('.admin-only').forEach(el => {
            el.style.display = 'none';
        });
    }
});

// ===== 侧边栏 & 会话管理 =====
function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    const mainContent = document.querySelector('.main-content');

    sidebar.classList.toggle('collapsed');

    if (window.innerWidth <= 768) {
        if (!sidebar.classList.contains('collapsed')) {
            sidebar.style.transform = 'translateX(0)';
        } else {
            sidebar.style.transform = 'translateX(-100%)';
        }
    }
}

async function loadSessions() {
    try {
        const response = await fetch('/api/chat/sessions');
        const data = await response.json();

        if (data.code === 200) {
            _doLoadSessions(data.data);
        }
    } catch (e) {
        console.error("加载会话失败:", e);
    }
}

function _doLoadSessions(sessions) {
    const listEl = document.getElementById('sessionList');
    listEl.innerHTML = '';

    sessions.forEach(s => {
        const li = document.createElement('li');
        li.className = 'session-item';
        li.id = `session-${s.id}`;
        li.onclick = () => loadSession(s.id);

        if (currentSessionId === s.id) {
            li.classList.add('active');
        }

        li.innerHTML = `
            <span class="session-name">${escapeHtml(s.session_name)}</span>
            <div class="session-actions">
                <button class="session-action" onclick="event.stopPropagation(); exportSession(${s.id})" title="导出">
                    <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                </button>
                <button class="session-action delete" onclick="event.stopPropagation(); deleteSession(${s.id})" title="删除">
                    <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>
                </button>
            </div>
        `;
        listEl.appendChild(li);
    });
}

async function createNewSession() {
    try {
        const response = await fetch('/api/chat/sessions?name=新对话', {
            method: 'POST'
        });
        const data = await response.json();

        if (data.code === 200) {
            await loadSessions();
            currentSessionId = data.data.id;

            // 高亮当前会话
            document.querySelectorAll('.session-item').forEach(el => el.classList.remove('active'));
            const currentEl = document.getElementById(`session-${currentSessionId}`);
            if (currentEl) currentEl.classList.add('active');

            // 隐藏初始欢迎页
            const welcomeSec = document.getElementById('welcomeSection');
            if (welcomeSec) welcomeSec.style.display = 'none';

            // 清空列表，准备新的对话
            document.getElementById('chatMessages').innerHTML = `
                <div class="welcome-container" id="welcomeContainer">
                    <div class="welcome-title">有什么可以帮你的吗？</div>
                    <div class="welcome-subtitle">我可以帮你处理文档、回答问题、提供建议...</div>
                </div>
            `;

            // 重置输入框
            const textarea = document.getElementById('userInput');
            textarea.value = '';
            textarea.style.height = 'auto';
            textarea.focus();
        }
    } catch (e) {
        console.error("创建会话失败:", e);
    }
}

async function deleteSession(sessionId) {
    if (!confirm('确定要删除这个会话吗？')) return;

    try {
        const response = await fetch(`/api/chat/sessions/${sessionId}`, {
            method: 'DELETE'
        });
        const data = await response.json();

        if (data.code === 200) {
            if (currentSessionId === sessionId) {
                currentSessionId = null;
                document.getElementById('chatMessages').innerHTML = `
                    <div class="welcome-container">
                        <div class="welcome-title">已删除会话</div>
                        <div class="welcome-subtitle">请点击左侧“新建对话”开启新的旅程</div>
                    </div>
                `;
            }
            loadSessions();
        }
    } catch (e) {
        console.error("删除会话失败:", e);
    }
}

async function loadSession(sessionId) {
    currentSessionId = sessionId;

    // 高亮当前会话
    document.querySelectorAll('.session-item').forEach(el => el.classList.remove('active'));
    const currentEl = document.getElementById(`session-${sessionId}`);
    if (currentEl) currentEl.classList.add('active');

    // 如果正在生成中，先中断
    if (currentChatController) {
        currentChatController.abort();
        currentChatController = null;
    }

    // 清空并显示加载中
    const chatContainer = document.getElementById('chatMessages');
    chatContainer.innerHTML = '<div class="message system"><div class="message-content">加载中...</div></div>';

    // 隐藏主页的欢迎组件
    const welcomeSec = document.getElementById('welcomeSection');
    if (welcomeSec) welcomeSec.style.display = 'none';

    try {
        const response = await fetch(`/api/chat/sessions/${sessionId}`);
        const data = await response.json();

        if (data.code === 200) {
            renderMessages(data.data.messages);
            // 滚动到底部
            chatContainer.scrollTop = chatContainer.scrollHeight;
        } else {
            console.error("加载会话失败:", data.message);
            chatContainer.innerHTML = `<div class="message system error"><div class="message-content">加载失败: ${escapeHtml(data.message || '未知错误')}</div></div>`;
        }
    } catch (e) {
        console.error("加载会话出错:", e);
        chatContainer.innerHTML = '<div class="message system error"><div class="message-content">加载失败</div></div>';
    }
}

// ===== 消息渲染 =====
function renderMessages(messages) {
    const chatContainer = document.getElementById('chatMessages');

    // 隐藏全局欢迎
    const welcomeSec = document.getElementById('welcomeSection');
    if (welcomeSec) welcomeSec.style.display = 'none';

    if (!messages || messages.length === 0) {
        chatContainer.innerHTML = `
            <div class="welcome-container" id="welcomeContainer">
                <div class="welcome-title">有什么可以帮你的吗？</div>
                <div class="welcome-subtitle">我可以帮你处理文档、回答问题、提供建议...</div>
            </div>
        `;
        return;
    }

    chatContainer.innerHTML = '';

    messages.forEach(msg => {
        appendMessage(msg.role, msg.content, msg.sources, msg.id, msg.feedback);
    });
}

function appendMessage(role, content, sources = null, messageId = null, feedback = null) {
    const chatContainer = document.getElementById('chatMessages');

    // 移除欢迎语
    const welcome = document.getElementById('welcomeContainer');
    if (welcome) welcome.remove();
    const globalWelcome = document.getElementById('welcomeSection');
    if (globalWelcome) globalWelcome.style.display = 'none';

    const msgDiv = document.createElement('div');
    msgDiv.className = `message ${role}`;
    if (messageId) msgDiv.id = `msg-${messageId}`;

    let parsedContent = escapeHtml(content);
    try {
        if (typeof marked !== 'undefined') {
            parsedContent = marked.parse ? marked.parse(content) : marked(content);
        }
    } catch (e) {
        console.error("Markdown 解析错误:", e);
    }

    const userAvatarText = document.querySelector('.user-info .user-avatar') ? document.querySelector('.user-info .user-avatar').textContent.trim() : 'U';

    let html = `
        <div class="message-avatar">${role === 'user' ? userAvatarText : '🤖'}</div>
        <div class="message-content">
            <div class="markdown-body">${parsedContent}</div>
    `;

    // 来源
    if (sources && sources.length > 0) {
        html += createSourcesHtml(sources);
    }

    // 反馈按钮 (仅助手消息)
    if (role === 'assistant' && messageId) {
        const upActive = feedback === 'up' ? 'active' : '';
        const downActive = feedback === 'down' ? 'active' : '';
        const disabledAttr = feedback ? 'disabled' : '';

        html += `
            <div class="feedback-actions">
                <button class="feedback-btn up ${upActive}" ${disabledAttr} onclick="submitFeedback(${messageId}, 'up', event.currentTarget)" title="有帮助">
                    <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M14 9V5a3 3 0 00-3-3l-4 9v11h11.28a2 2 0 002-1.7l1.38-9a2 2 0 00-2-2.3zM7 22H4a2 2 0 01-2-2v-7a2 2 0 012-2h3"/></svg>
                </button>
                <button class="feedback-btn down ${downActive}" ${disabledAttr} onclick="submitFeedback(${messageId}, 'down', event.currentTarget)" title="没帮助">
                    <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M10 15v4a3 3 0 003 3l4-9V2H5.72a2 2 0 00-2 1.7l-1.38 9a2 2 0 002 2.3zm7-13h2.67A2.31 2.31 0 0122 4v7a2.31 2.31 0 01-2.33 2H17"/></svg>
                </button>
            </div>
            <div class="feedback-input-container" id="feedback-input-${messageId}">
                <textarea placeholder="为了更好地帮助我们优化，请简单描述一下原因..." class="feedback-textarea" rows="2"></textarea>
                <div class="feedback-actions-row">
                    <span class="feedback-status" id="feedback-status-${messageId}"></span>
                    <button class="btn btn-primary btn-sm" onclick="submitActualFeedback(${messageId}, 'down', this)">提交反馈</button>
                    <button class="btn btn-cancel btn-sm" onclick="cancelFeedback(${messageId})">取消</button>
                </div>
            </div>
        `;
    }

    html += `</div>`; // end message-content
    msgDiv.innerHTML = html;
    chatContainer.appendChild(msgDiv);

    // 自动滚动
    chatContainer.scrollTop = chatContainer.scrollHeight;

    // 高亮代码块
    if (typeof hljs !== 'undefined') {
        msgDiv.querySelectorAll('pre code').forEach((block) => {
            try {
                hljs.highlightElement(block);
            } catch (e) {
                console.error("代码高亮失败:", e);
            }
        });
    }
}

function createSourcesHtml(sources) {
    if (!sources || sources.length === 0) return '';

    const tags = sources.map(s => {
        // 如果已删除，增加样式
        if (s.deleted) {
            return `<span class="source-tag deleted" title="源文件已删除" style="text-decoration: none; cursor: not-allowed; opacity: 0.6;">
                <svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                (已删除) ${escapeHtml(s.file_name)}
            </span>`;
        }
        return `<a href="/api/document/${s.document_id}/file" download="${escapeHtml(s.file_name)}" class="source-tag" title="点击下载文档" target="_blank" style="text-decoration: none; cursor: pointer;">
            <svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
            ${escapeHtml(s.file_name)}
        </a>`;
    }).join('');
    return `<div class="message-sources"><span class="sources-label">来源文档：</span>${tags}</div>`;
}

// ===== 发送消息 =====
async function sendMessage() {
    if (currentChatController) return;
    const textarea = document.getElementById('userInput');
    const message = textarea.value.trim();
    if (!message) return;

    // 如果没有当前会话，先创建
    if (!currentSessionId) {
        await createNewSession();
    }

    // 清空输入框
    textarea.value = '';
    textarea.style.height = 'auto';

    // 显示用户消息
    appendMessage('user', message);

    // 创建助手消息占位
    const chatContainer = document.getElementById('chatMessages');
    const assistantMsgId = `assistant-loading-${Date.now()}`;
    const assistantMsgDiv = document.createElement('div');
    assistantMsgDiv.className = 'message assistant';
    assistantMsgDiv.id = assistantMsgId;
    assistantMsgDiv.innerHTML = `
        <div class="message-avatar">🤖</div>
        <div class="message-content">
            <div class="markdown-body typing">...</div>
        </div>
    `;
    chatContainer.appendChild(assistantMsgDiv);
    chatContainer.scrollTop = chatContainer.scrollHeight;

    // 发起流式请求
    currentChatController = new AbortController();

    try {
        const response = await fetch('/api/chat/completions', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: message,
                session_id: currentSessionId
            }),
            signal: currentChatController.signal
        });

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let assistantContent = '';
        let assistantSources = [];
        let realMessageId = null;

        const contentDiv = assistantMsgDiv.querySelector('.markdown-body');
        contentDiv.classList.remove('typing');
        contentDiv.innerHTML = ''; // 清空 loading

        let buffer = '';
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n\n');
            buffer = lines.pop(); // 将最后一个不完整的块留在 buffer 中

            for (const line of lines) {
                const trimmedLine = line.trim();
                if (!trimmedLine) continue;

                if (trimmedLine.startsWith('data: ')) {
                    const dataStr = trimmedLine.replace('data: ', '');
                    if (dataStr === '[DONE]') break;

                    try {
                        const data = JSON.parse(dataStr);
                        if (data.type === 'content') {
                            assistantContent += data.content;
                            let parsedContent = escapeHtml(assistantContent);
                            try {
                                if (typeof marked !== 'undefined') {
                                    parsedContent = marked.parse ? marked.parse(assistantContent) : marked(assistantContent);
                                }
                            } catch (marE) {
                                console.error("Markdown 解析出错:", marE);
                            }
                            contentDiv.innerHTML = parsedContent;
                            // 实时滚动
                            chatContainer.scrollTop = chatContainer.scrollHeight;
                        } else if (data.type === 'sources') {
                            console.log("收到来源信息:", data.sources);
                            assistantSources = data.sources;
                        } else if (data.type === 'done') {
                            realMessageId = data.message_id;
                        } else if (data.type === 'session') {
                            // 确保 session ID 一致
                            if (!currentSessionId) {
                                currentSessionId = data.session_id;
                                // 刷新列表以显示新标题
                                loadSessions();
                            }
                        }
                    } catch (e) {
                        console.error("JSON 解析错误:", e, "数据内容:", dataStr);
                    }
                }
            }
        }

        // 渲染来源和反馈按钮
        if (assistantSources.length > 0) {
            const sourcesHtml = createSourcesHtml(assistantSources);
            assistantMsgDiv.querySelector('.message-content').insertAdjacentHTML('beforeend', sourcesHtml);
        }

        if (realMessageId) {
            assistantMsgDiv.id = `msg-${realMessageId}`;
            // 添加反馈按钮
            const feedbackHtml = `
                <div class="feedback-actions">
                    <button class="feedback-btn up" onclick="submitFeedback(${realMessageId}, 'up', event.currentTarget)" title="有帮助">
                        <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M14 9V5a3 3 0 00-3-3l-4 9v11h11.28a2 2 0 002-1.7l1.38-9a2 2 0 00-2-2.3zM7 22H4a2 2 0 01-2-2v-7a2 2 0 012-2h3"/></svg>
                    </button>
                    <button class="feedback-btn down" onclick="submitFeedback(${realMessageId}, 'down', event.currentTarget)" title="没帮助">
                        <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M10 15v4a3 3 0 003 3l4-9V2H5.72a2 2 0 00-2 1.7l-1.38 9a2 2 0 002 2.3zm7-13h2.67A2.31 2.31 0 0122 4v7a2.31 2.31 0 01-2.33 2H17"/></svg>
                    </button>
                </div>
                <div class="feedback-input-container" id="feedback-input-${realMessageId}">
                    <textarea placeholder="为了更好地帮助我们优化，请简单描述一下原因..." class="feedback-textarea" rows="2"></textarea>
                    <div class="feedback-actions-row">
                        <span class="feedback-status" id="feedback-status-${realMessageId}"></span>
                        <button class="btn btn-primary btn-sm" onclick="submitActualFeedback(${realMessageId}, 'down', this)">提交反馈</button>
                        <button class="btn btn-cancel btn-sm" onclick="cancelFeedback(${realMessageId})">取消</button>
                    </div>
                </div>
            `;
            assistantMsgDiv.querySelector('.message-content').insertAdjacentHTML('beforeend', feedbackHtml);
        }

    } catch (e) {
        if (e.name === 'AbortError') {
            console.log("请求已取消");
        } else {
            console.error("对话失败:", e);
            assistantMsgDiv.querySelector('.markdown-body').textContent = "⚠️ 发生错误，请稍后重试。";
        }
    } finally {
        currentChatController = null;
        // 高亮代码
        if (typeof hljs !== 'undefined' && assistantMsgDiv) {
            assistantMsgDiv.querySelectorAll('pre code').forEach((block) => {
                try {
                    hljs.highlightElement(block);
                } catch (e) {
                    console.error("代码高亮失败:", e);
                }
            });
        }
    }
}

async function submitFeedback(messageId, rating, btn) {
    if (rating === 'down') {
        const inputContainer = document.getElementById(`feedback-input-${messageId}`);
        if (inputContainer) {
            inputContainer.style.display = 'block';
            inputContainer.querySelector('textarea').focus();
        }
    } else {
        await submitActualFeedback(messageId, 'up', btn);
    }
}

function cancelFeedback(messageId) {
    const inputContainer = document.getElementById(`feedback-input-${messageId}`);
    if (inputContainer) {
        inputContainer.classList.add('closing');
        setTimeout(() => {
            inputContainer.style.display = 'none';
            inputContainer.classList.remove('closing');
            inputContainer.querySelector('textarea').value = '';
            const statusEl = document.getElementById(`feedback-status-${messageId}`);
            if(statusEl) {
                statusEl.textContent = '';
                statusEl.className = 'feedback-status';
            }
        }, 280);
    }
}

async function submitActualFeedback(messageId, rating, btn) {
    let comment = '';
    let statusEl = null;

    if (rating === 'down') {
        const inputContainer = document.getElementById(`feedback-input-${messageId}`);
        if (inputContainer) {
            comment = inputContainer.querySelector('textarea').value.trim();
            statusEl = document.getElementById(`feedback-status-${messageId}`);

            if (!comment) {
                if(statusEl) {
                    statusEl.textContent = '请填写反馈原因！';
                    statusEl.className = 'feedback-status error';
                }
                return;
            }
            if(statusEl) {
                statusEl.textContent = '提交中...';
                statusEl.className = 'feedback-status';
            }
            if(btn) btn.disabled = true;
        }
    }

    try {
        const response = await fetch('/api/chat/feedback', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message_id: messageId, rating: rating, comment: comment })
        });
        const data = await response.json();

        if (data.code === 200) {
            if(statusEl) {
                statusEl.textContent = '反馈成功！感谢您的建议。';
                statusEl.className = 'feedback-status success';
            }
            // 更新 UI 状态
            let targetBtn = btn;
            if (rating === 'down') {
                targetBtn = document.querySelector(`#msg-${messageId} .feedback-btn.down`);
                setTimeout(() => {
                    cancelFeedback(messageId); // 隐藏输入框
                    if(btn) btn.disabled = false;
                }, 1200);
            }

            if (targetBtn) {
                const parent = targetBtn.parentElement;
                parent.querySelectorAll('.feedback-btn').forEach(b => {
                    b.classList.remove('active');
                    b.disabled = true;
                });
                targetBtn.classList.add('active');
            }
        } else {
            if(statusEl) {
                statusEl.textContent = data.message || '反馈失败';
                statusEl.className = 'feedback-status error';
            }
            if (btn) btn.disabled = false;
        }
    } catch (e) {
        console.error("提交反馈失败:", e);
        if(statusEl) {
            statusEl.textContent = '网络错误，请重试';
            statusEl.className = 'feedback-status error';
        }
        if (btn) btn.disabled = false;
    }
}

// 自动调整输入框高度
// 自动调整输入框高度
function adjustTextareaHeight(el) {
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = (el.scrollHeight) + 'px';
}

// 监听回车发送
const userInput = document.getElementById('userInput');
if (userInput) {
    userInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    // 监听输入框高度变化
    userInput.addEventListener('input', function () {
        adjustTextareaHeight(this);
    });
}


// ===== 用户头像 & 个人中心 =====
function toggleUserMenu() {
    const menu = document.getElementById('userMenu');
    menu.classList.toggle('show');
}

function askSample(text, label) {
    const input = document.getElementById('userInput');
    if (input) {
        input.value = text;
        adjustTextareaHeight(input);
        sendMessage();
    }
}

// 点击外部关闭用户菜单
document.addEventListener('click', (e) => {
    const menu = document.getElementById('userMenu');
    const avatar = document.querySelector('.user-avatar-container');
    if (menu && menu.classList.contains('show') && !avatar.contains(e.target)) {
        menu.classList.remove('show');
    }
});

// 显示个人信息模态框，并从 API 加载当前用户数据
async function showProfileModal() {
    const modal = document.getElementById('profileModal');
    modal.classList.add('active');

    // 清空旧数据
    document.getElementById('profileEmployeeId').value = '';
    document.getElementById('profileUsername').value = '';
    document.getElementById('profileEmail').value = '';
    document.getElementById('profilePhone').value = '';
    document.getElementById('profileOldPassword').value = '';
    document.getElementById('profileNewPassword').value = '';
    const msgEl = document.getElementById('profileMessage');
    if (msgEl) { msgEl.textContent = ''; msgEl.className = 'auth-message'; }

    try {
        const response = await fetch('/api/auth/profile');
        const data = await response.json();
        if (data.code === 200) {
            const u = data.data;
            document.getElementById('profileEmployeeId').value = u.employee_id || '';
            document.getElementById('profileUsername').value = u.username || '';
            document.getElementById('profileEmail').value = u.email || '';
            document.getElementById('profilePhone').value = u.phone || '';
        }
    } catch (e) {
        console.error('加载个人信息失败:', e);
    }
}

function hideProfileModal() {
    document.getElementById('profileModal').classList.remove('active');
}

// 保存个人信息（邮箱、手机号、修改密码）
async function saveProfile() {
    const msgEl = document.getElementById('profileMessage');
    const email = document.getElementById('profileEmail').value.trim();
    const phone = document.getElementById('profilePhone').value.trim();
    const oldPassword = document.getElementById('profileOldPassword').value;
    const newPassword = document.getElementById('profileNewPassword').value;

    const payload = { email, phone };
    if (newPassword) {
        payload.old_password = oldPassword;
        payload.new_password = newPassword;
    }

    try {
        const response = await fetch('/api/auth/profile', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await response.json();

        if (data.code === 200) {
            msgEl.textContent = '保存成功';
            msgEl.className = 'auth-message success';
            setTimeout(() => hideProfileModal(), 1200);
        } else {
            msgEl.textContent = data.message || '保存失败';
            msgEl.className = 'auth-message error';
        }
    } catch (e) {
        msgEl.textContent = '网络错误，请重试';
        msgEl.className = 'auth-message error';
    }
}

// 退出登录（调用后端 POST /api/auth/logout）
async function doLogout() {
    try {
        await fetch('/api/auth/logout', { method: 'POST' });
    } catch (e) {
        // 忽略网络错误，直接跳转
    }
    window.location.href = '/login';
}


// ===== 文档管理 =====
function showDocPanel() {
    document.getElementById('docModalOverlay').classList.add('active');
    document.getElementById('docPanel').classList.add('show');
    loadDocuments();
}

function hideDocPanel() {
    const panel = document.getElementById('docPanel');
    const overlay = document.getElementById('docModalOverlay');

    panel.classList.add('closing');

    // 等待动画结束
    setTimeout(() => {
        panel.classList.remove('show');
        panel.classList.remove('closing');
        overlay.classList.remove('active');
    }, 280); // 略小于动画时长(300ms)以避免闪烁
}

async function loadDocuments() {
    const listEl = document.getElementById('docList');
    listEl.innerHTML = '<div class="doc-empty">加载中...</div>';

    try {
        const response = await fetch('/api/document/list');
        const data = await response.json();

        if (data.code === 200) {
            renderDocList(data.data);
        } else {
            listEl.innerHTML = '<div class="doc-empty">加载失败</div>';
        }
    } catch (e) {
        listEl.innerHTML = '<div class="doc-empty">网络错误</div>';
    }
}

function renderDocList(docs) {
    const listEl = document.getElementById('docList');
    if (!docs || docs.length === 0) {
        // 根据角色显示不同提示
        const emptyMsg = isAdmin()
            ? `<div class="doc-empty-state">
                <svg width="48" height="48" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24" style="opacity:.4">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>
                </svg>
                <p>知识库暂无文档</p>
                <span>点击上方按钮上传第一个文档</span>
               </div>`
            : `<div class="doc-empty-state">
                <svg width="48" height="48" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24" style="opacity:.4">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>
                </svg>
                <p>暂无文档，等待管理员上传</p>
                <span>文档上传后即可在对话中检索</span>
               </div>`;
        listEl.innerHTML = emptyMsg;
        return;
    }

    listEl.innerHTML = '';
    docs.forEach(doc => {
        const item = document.createElement('div');
        item.className = 'doc-item';

        const sizeStr = doc.file_size >= 1024 * 1024
            ? (doc.file_size / 1024 / 1024).toFixed(1) + ' MB'
            : (doc.file_size / 1024).toFixed(1) + ' KB';

        const statusMap = {
            completed: { label: '已就绪', cls: 'completed' },
            processing: { label: '处理中', cls: 'processing' },
            failed: { label: '失败', cls: 'failed' },
            pending: { label: '待处理', cls: 'pending' }
        };
        const st = statusMap[doc.status] || { label: doc.status, cls: 'pending' };

        const extIconMap = {
            pdf: '#f87171', docx: '#60a5fa', doc: '#60a5fa', txt: '#a3e635'
        };
        const iconColor = extIconMap[doc.file_type] || '#a0a0c0';

        const deleteBtn = isAdmin() ? `
            <button class="doc-btn delete" onclick="deleteDocument(${doc.id})" title="删除">
                <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                    <path d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/>
                </svg>
            </button>` : '';

        item.innerHTML = `
            <div class="doc-icon" style="color:${iconColor}">
                <svg width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                    <polyline points="14 2 14 8 20 8"/>
                    <text x="6" y="19" font-size="5" fill="currentColor" stroke="none" font-weight="bold">${doc.file_type.toUpperCase()}</text>
                </svg>
            </div>
            <div class="doc-info">
                <div class="doc-name" title="${escapeHtml(doc.file_name)}">${escapeHtml(doc.file_name)}</div>
                <div class="doc-meta">
                    <span class="doc-status ${st.cls}">${st.label}</span>
                    ${sizeStr}
                    ${doc.chunk_count > 0 ? `· <strong>${doc.chunk_count}</strong> 个切片` : ''}
                    · ${doc.created_at}
                </div>
            </div>
            <div class="doc-actions">${deleteBtn}</div>
        `;
        listEl.appendChild(item);
    });
}

async function uploadFile() {
    const fileInput = document.getElementById('fileInput');
    const file = fileInput.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);

    // 显示上传进度区域
    const progressEl = document.getElementById('uploadProgress');
    const progressFill = document.getElementById('progressFill');
    const uploadStatus = document.getElementById('uploadStatus');
    const uploadBtn = document.querySelector('.btn-upload');

    progressEl.style.display = 'block';
    uploadBtn.disabled = true;
    uploadStatus.textContent = `正在上传 ${file.name}...`;

    // 模拟进度动画（真实进度需 XHR，此处用平滑动画替代）
    let fakeProgress = 0;
    progressFill.style.width = '0%';
    const progressTimer = setInterval(() => {
        // 快速到 85%，然后等待服务器响应
        const step = fakeProgress < 60 ? 4 : fakeProgress < 80 ? 1.5 : 0.3;
        fakeProgress = Math.min(fakeProgress + step, 88);
        progressFill.style.width = fakeProgress + '%';
    }, 120);

    try {
        const response = await fetch('/api/document/upload', {
            method: 'POST',
            body: formData
        });
        const data = await response.json();

        clearInterval(progressTimer);

        if (data.code === 200) {
            // 进度条完成动画
            progressFill.style.width = '100%';
            uploadStatus.textContent = `✅ 上传成功！共生成 ${data.data.chunk_count} 个切片`;
            fileInput.value = '';

            // 刷新文档列表
            await loadDocuments();

            setTimeout(() => {
                progressEl.style.display = 'none';
                progressFill.style.width = '0%';
                uploadBtn.disabled = false;
            }, 1200);
        } else {
            progressFill.style.width = '0%';
            uploadStatus.textContent = `❌ ${data.message || '上传失败'}`;
            setTimeout(() => {
                progressEl.style.display = 'none';
                uploadBtn.disabled = false;
            }, 2500);
        }
    } catch (e) {
        clearInterval(progressTimer);
        progressFill.style.width = '0%';
        uploadStatus.textContent = `❌ 网络错误：${e.message}`;
        setTimeout(() => {
            progressEl.style.display = 'none';
            uploadBtn.disabled = false;
        }, 2500);
    }
}


async function deleteDocument(docId) {
    if (!confirm('确定要删除该文档吗？删除后不仅无法检索，之前的引用也可能失效。')) return;

    try {
        const response = await fetch(`/api/document/${docId}/delete`, {
            method: 'DELETE'
        });
        const data = await response.json();

        if (data.code === 200) {
            loadDocuments();
        } else {
            alert(data.message || '删除失败');
        }
    } catch (e) {
        alert('删除出错');
    }
}

// 文档预览
async function showDocumentPreview(docId, fileName) {
    const modal = document.getElementById('documentModal');
    const container = document.getElementById('documentPreviewContent');
    const title = document.getElementById('documentPreviewTitle');

    title.textContent = fileName;
    container.innerHTML = '<div class="preview-loading">加载中...</div>';
    modal.classList.add('active');

    try {
        const response = await fetch(`/api/document/${docId}/preview`);
        const data = await response.json();

        if (data.code === 200) {
            // 简单处理：如果是纯文本直接显示，pdf 暂不支持预览或用 iframe
            // 这里后端返回的是 text_content
            // 为了安全，转义 html
            const safeContent = escapeHtml(data.data.content);
            container.innerHTML = `<pre class="preview-text">${safeContent}</pre>`;
        } else {
            container.innerHTML = '<div class="preview-error">预览失败: ' + data.message + '</div>';
        }
    } catch (e) {
        container.innerHTML = '<div class="preview-error">加载错误</div>';
    }
}

function hideDocumentModal() {
    document.getElementById('documentModal').classList.remove('active');
}


// 工具函数
function escapeHtml(unsafe) {
    if (typeof unsafe !== 'string') return unsafe;
    return unsafe
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

async function exportSession(sessionId) {
    if (!sessionId) return;
    // 直接导出 markdown
    window.location.href = `/api/chat/sessions/${sessionId}/export?format=md`;
}


function page2admin() {
    if (isAdmin()) {
        window.location.href = '/admin';
    } else {
        alert('你没有权限访问管理后台');
    }
}