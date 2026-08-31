// ── Socket.IO Setup ──
const socket = io({ autoConnect: false });

// ── DOM Elements ──
const authScreen = document.getElementById('auth-screen');
const mainApp = document.getElementById('main-app');
const authTabs = document.querySelectorAll('.auth-tab');
const loginForm = document.getElementById('login-form');
const registerForm = document.getElementById('register-form');
const authError = document.getElementById('auth-error');
const noApiKeyCheckbox = document.getElementById('reg-no-apikey');
const apiKeyField = document.getElementById('api-key-field');
const regApiKeyInput = document.getElementById('reg-apikey');

const sidebar = document.getElementById('sidebar');
const toggleSidebarBtn = document.getElementById('toggle-sidebar');
const newChatBtn = document.getElementById('new-chat-btn');
const chatList = document.getElementById('chat-list');
const chatSearch = document.getElementById('chat-search');
const messagesContainer = document.getElementById('messages-container');
const messagesEl = document.getElementById('messages');
const welcomeScreen = document.getElementById('welcome-screen');
const messageInput = document.getElementById('message-input');
const sendBtn = document.getElementById('send-btn');
const stopBtn = document.getElementById('stop-btn');
const typingIndicator = document.getElementById('typing-indicator');
const thinkingLabel = document.getElementById('thinking-label');
const currentChatTitle = document.getElementById('current-chat-title');
const contextBanner = document.getElementById('context-banner');
const userAvatar = document.getElementById('user-avatar');
const userName = document.getElementById('user-name');
const logoutBtn = document.getElementById('logout-btn');
const readmeBtn = document.getElementById('readme-btn');
const changePasswordBtn = document.getElementById('change-password-btn');
const systemPromptBtn = document.getElementById('system-prompt-btn');
const debugToggleBtn = document.getElementById('debug-toggle-btn');
const debugStatusSpan = document.getElementById('debug-status');
const exportBtn = document.getElementById('export-btn');
const imageUploadBtn = document.getElementById('image-upload-btn');
const imageFileInput = document.getElementById('image-file-input');
const modelSelector = document.getElementById('model-selector');
const modelBadge = document.getElementById('model-badge');
const modelSelectorContainer = document.getElementById('model-selector-container');

const readmeModal = document.getElementById('readme-modal');
const readmeContent = document.getElementById('readme-content');
const readmeClose = document.getElementById('readme-close');

const passwordModal = document.getElementById('password-modal');
const passwordError = document.getElementById('password-error');
const currentPasswordInput = document.getElementById('current-password');
const newPasswordInput = document.getElementById('new-password');
const confirmNewPasswordInput = document.getElementById('confirm-new-password');
const passwordConfirmBtn = document.getElementById('password-confirm');
const passwordCancelBtn = document.getElementById('password-cancel');

const promptModal = document.getElementById('prompt-modal');
const promptTextarea = document.getElementById('prompt-textarea');
const promptError = document.getElementById('prompt-error');
const promptSaveBtn = document.getElementById('prompt-save');
const promptCancelBtn = document.getElementById('prompt-cancel');
const promptCloseBtn = document.getElementById('prompt-close');

// ── State ──
let currentChatId = null;
let isTyping = false;
let isStreaming = false;
let autoScroll = true;
let currentUser = null;
let debugEnabled = false;
let currentStreamMsgId = null;
let allChats = [];
let currentModelType = 'local';

// ── Marked Config ──
marked.setOptions({
    breaks: true,
    gfm: true,
    headerIds: false,
    mangle: false,
    sanitize: false
});

// ── "No API Key" checkbox toggle ──
if (noApiKeyCheckbox) {
    noApiKeyCheckbox.addEventListener('change', () => {
        if (noApiKeyCheckbox.checked) {
            apiKeyField.classList.add('hidden');
            regApiKeyInput.removeAttribute('required');
            regApiKeyInput.value = '';
        } else {
            apiKeyField.classList.remove('hidden');
            regApiKeyInput.setAttribute('required', '');
        }
    });
}

// ── Auth Tab Switching ──
authTabs.forEach(tab => {
    tab.addEventListener('click', () => {
        authTabs.forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        authError.classList.add('hidden');
        if (tab.dataset.tab === 'login') {
            loginForm.classList.remove('hidden');
            registerForm.classList.add('hidden');
        } else {
            loginForm.classList.add('hidden');
            registerForm.classList.remove('hidden');
        }
    });
});

// ── Login ──
loginForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const username = document.getElementById('login-username').value.trim();
    const password = document.getElementById('login-password').value;

    try {
        const res = await fetch('/api/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password })
        });
        const data = await res.json();
        if (res.ok) {
            enterApp(data);
        } else {
            showAuthError(data.error || 'Login failed');
        }
    } catch (err) {
        showAuthError('Network error');
    }
});

// ── Register ──
registerForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const fullname = document.getElementById('reg-fullname').value.trim();
    const username = document.getElementById('reg-username').value.trim();
    const password = document.getElementById('reg-password').value;
    const confirm = document.getElementById('reg-confirm').value;
    const api_key = document.getElementById('reg-apikey').value.trim();
    const no_api_key = document.getElementById('reg-no-apikey').checked;

    try {
        const res = await fetch('/api/register', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ fullname, username, password, confirm_password: confirm, api_key, no_api_key })
        });
        const data = await res.json();
        if (res.ok) {
            enterApp(data);
        } else {
            showAuthError(data.error || 'Registration failed');
        }
    } catch (err) {
        showAuthError('Network error');
    }
});

function showAuthError(msg) {
    authError.textContent = msg;
    authError.classList.remove('hidden');
}

// ── Enter App ──
function enterApp(user) {
    currentUser = user;
    authScreen.classList.add('hidden');
    mainApp.classList.remove('hidden');
    userAvatar.textContent = user.fullname.charAt(0).toUpperCase();
    userName.textContent = user.fullname;

    if (user.is_admin) {
        document.querySelectorAll('.admin-only').forEach(el => el.classList.remove('hidden'));
    }

    // Setup model selector based on user permissions
    setupModelSelector(user);

    socket.connect();
    loadChatList();
    messageInput.focus();
}

// ── Model Selector Setup ──
function setupModelSelector(user) {
    if (!modelSelector) return;

    // Clear existing options
    modelSelector.innerHTML = '';

    // Always add local model
    const localOption = document.createElement('option');
    localOption.value = 'local';
    localOption.textContent = 'Local Model';
    modelSelector.appendChild(localOption);

    // Add cloud option if user has API key
    if (user.has_api_key) {
        const cloudOption = document.createElement('option');
        cloudOption.value = 'cloud';
        cloudOption.textContent = 'GPT-OSS Cloud';
        modelSelector.appendChild(cloudOption);
    }

    // Show/hide selector container
    if (!user.has_api_key) {
        modelSelectorContainer.style.display = 'none';
    } else {
        modelSelectorContainer.style.display = 'flex';
    }

    // Update badge on change
    modelSelector.addEventListener('change', () => {
        currentModelType = modelSelector.value;
        updateModelBadge();
        // Start a new chat with the selected model
        socket.emit('new_chat', { model_type: currentModelType });
        resetChatUI();
    });

    updateModelBadge();
}

function updateModelBadge() {
    if (!modelBadge) return;
    if (currentModelType === 'cloud') {
        modelBadge.textContent = 'Cloud';
        modelBadge.className = 'model-badge cloud';
    } else {
        modelBadge.textContent = 'Local';
        modelBadge.className = 'model-badge local';
    }
}

// ── Logout ──
logoutBtn.addEventListener('click', async () => {
    await fetch('/api/logout', { method: 'POST' });
    socket.disconnect();
    location.reload();
});

// ── Sidebar Toggle ──
toggleSidebarBtn.addEventListener('click', () => {
    sidebar.classList.toggle('collapsed');
});

// ── Chat Search ──
chatSearch.addEventListener('input', () => {
    const q = chatSearch.value.toLowerCase().trim();
    if (!q) {
        renderChatList(allChats);
        return;
    }
    const filtered = allChats.filter(c => c.title.toLowerCase().includes(q));
    renderChatList(filtered);
});

// ── Auto-resize textarea ──
messageInput.addEventListener('input', () => {
    messageInput.style.height = 'auto';
    messageInput.style.height = Math.min(messageInput.scrollHeight, 200) + 'px';
    sendBtn.disabled = messageInput.value.trim().length === 0 || isTyping || isStreaming;
});

messageInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

// ── Send / Stop ──
sendBtn.addEventListener('click', sendMessage);
stopBtn.addEventListener('click', () => {
    socket.emit('stop_generation');
    setStreaming(false);
});

// -- Image Upload --
if (imageUploadBtn && imageFileInput) {
    imageUploadBtn.addEventListener('click', () => imageFileInput.click());
    imageFileInput.addEventListener('change', async () => {
        const file = imageFileInput.files[0];
        if (!file) return;
        const formData = new FormData();
        formData.append('image', file);
        try {
            const res = await fetch('/api/upload_image', {
                method: 'POST',
                body: formData
            });
            const data = await res.json();
            if (res.ok) {
                const insertText = `[Uploaded image: ${data.url}]`;
                messageInput.value += (messageInput.value ? '\n' : '') + insertText;
                messageInput.style.height = 'auto';
                messageInput.style.height = Math.min(messageInput.scrollHeight, 200) + 'px';
                sendBtn.disabled = false;
                messageInput.focus();
            } else {
                console.error('Upload failed:', data.error);
            }
        } catch (e) {
            console.error('Upload error:', e);
        }
        imageFileInput.value = '';
    });
}

function sendMessage() {
    const text = messageInput.value.trim();
    if (!text || isTyping || isStreaming) return;

    if (!welcomeScreen.classList.contains('hidden')) {
        welcomeScreen.classList.add('hidden');
    }

    addMessage('user', text, null, Date.now());

    messageInput.value = '';
    messageInput.style.height = 'auto';
    sendBtn.disabled = true;

    socket.emit('send_message', { message: text });
    setTyping(true, 'Thinking...');
}

// ── Suggestion Cards ──
document.querySelectorAll('.suggestion-card').forEach(card => {
    card.addEventListener('click', () => {
        messageInput.value = card.dataset.text;
        messageInput.style.height = 'auto';
        messageInput.style.height = Math.min(messageInput.scrollHeight, 200) + 'px';
        sendBtn.disabled = false;
        messageInput.focus();
    });
});

// ── New Chat ──
newChatBtn.addEventListener('click', () => {
    socket.emit('new_chat', { model_type: currentModelType });
    resetChatUI();
});

function resetChatUI() {
    currentChatId = null;
    messagesEl.innerHTML = '';
    welcomeScreen.classList.remove('hidden');
    currentChatTitle.textContent = 'YOLEST';
    contextBanner.classList.add('hidden');
    setTyping(false);
    setStreaming(false);
    highlightActiveChat(null);
    clearDebugPanel();
    messageInput.focus();
}

// ── Preprocess (FIXED: was missing) ──
// -- Image rendering helper --
function renderImagesInText(text) {
    if (!text) return text;
    const imgPattern = /\[Uploaded image: ([^\]]+)\]/g;
    return text.replace(imgPattern, (match, url) => {
        const safeUrl = url.trim();
        return `\n![Uploaded Image](${safeUrl})\n`;
    });
}

function preprocess(text) {
    if (!text) return '';
    text = text.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
    text = renderImagesInText(text);
    text = preprocessMath(text);
    return text;
}

// ── Add Message ──
function addMessage(role, content, thinking = null, timestamp = null, id = null) {
    const msgId = id || 'msg-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);
    const msgDiv = document.createElement('div');
    msgDiv.className = `message ${role}`;
    msgDiv.dataset.id = msgId;
    msgDiv.dataset.role = role;

    const avatar = document.createElement('div');
    avatar.className = `message-avatar ${role}`;
    avatar.textContent = role === 'user' ? 'U' : 'AI';

    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';

    const header = document.createElement('div');
    header.className = 'message-header';

    const author = document.createElement('span');
    author.className = 'message-author';
    author.textContent = role === 'user' ? 'You' : 'YOLEST';
    header.appendChild(author);

    if (timestamp) {
        const time = document.createElement('span');
        time.className = 'message-time';
        time.textContent = formatTime(timestamp);
        time.title = new Date(timestamp).toLocaleString();
        header.appendChild(time);
    }

    contentDiv.appendChild(header);

    if (thinking) {
        const thinkingBox = document.createElement('div');
        thinkingBox.className = 'thinking-box';
        thinkingBox.innerHTML = `
            <div class="thinking-header" onclick="this.parentElement.classList.toggle('expanded')">
                <svg class="thinking-toggle" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <polyline points="9 18 15 12 9 6"/>
                </svg>
                <span class="thinking-label">Thinking</span>
            </div>
            <div class="thinking-body">${escapeHtml(thinking)}</div>
        `;
        contentDiv.appendChild(thinkingBox);
    }

    const body = document.createElement('div');
    body.className = 'message-body';
    body.innerHTML = marked.parse(preprocess(content));
    renderMath(body);
    contentDiv.appendChild(body);

    if (role === 'assistant') {
        const actions = document.createElement('div');
        actions.className = 'message-actions';
        actions.innerHTML = `
            <button class="message-action copy-msg-btn" title="Copy message">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
                    <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
                </svg>
                Copy
            </button>
            <button class="message-action regenerate-btn" title="Regenerate response">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <polyline points="23 4 23 10 17 10"/>
                    <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
                </svg>
                Regenerate
            </button>
        `;
        actions.querySelector('.copy-msg-btn').addEventListener('click', () => {
            navigator.clipboard.writeText(content).then(() => {
                const btn = actions.querySelector('.copy-msg-btn');
                btn.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg> Copied`;
                setTimeout(() => {
                    btn.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg> Copy`;
                }, 1500);
            });
        });
        actions.querySelector('.regenerate-btn').addEventListener('click', () => regenerateResponse(msgDiv));
        contentDiv.appendChild(actions);
    }

    if (role === 'user') {
        const actions = document.createElement('div');
        actions.className = 'message-actions';
        actions.innerHTML = `
            <button class="message-action edit-msg-btn" title="Edit message">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                    <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                </svg>
                Edit
            </button>
        `;
        actions.querySelector('.edit-msg-btn').addEventListener('click', () => startEditMessage(msgDiv));
        contentDiv.appendChild(actions);
    }

    msgDiv.appendChild(avatar);
    msgDiv.appendChild(contentDiv);
    messagesEl.appendChild(msgDiv);

    addCodeCopyButtons(body);
    body.querySelectorAll('pre code').forEach(block => hljs.highlightElement(block));

    scrollToBottom();
    return msgDiv;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatTime(ts) {
    const d = new Date(ts);
    const now = new Date();
    const isToday = d.toDateString() === now.toDateString();
    if (isToday) {
        return d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
    }
    const yesterday = new Date(now);
    yesterday.setDate(yesterday.getDate() - 1);
    if (d.toDateString() === yesterday.toDateString()) {
        return 'Yesterday';
    }
    return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
}

function addCodeCopyButtons(container) {
    container.querySelectorAll('pre').forEach(pre => {
        const wrapper = document.createElement('div');
        wrapper.className = 'code-block-wrapper';
        pre.parentNode.insertBefore(wrapper, pre);
        wrapper.appendChild(pre);

        const codeEl = pre.querySelector('code');
        let lang = '';
        if (codeEl) {
            const match = codeEl.className.match(/language-(\w+)/);
            if (match) lang = match[1];
        }

        if (lang) {
            const label = document.createElement('span');
            label.className = 'code-lang-label';
            label.textContent = lang;
            wrapper.appendChild(label);
        }

        const btn = document.createElement('button');
        btn.className = 'code-copy-btn';
        btn.textContent = 'Copy';
        btn.addEventListener('click', () => {
            const code = pre.querySelector('code');
            navigator.clipboard.writeText(code ? code.textContent : pre.textContent).then(() => {
                btn.textContent = 'Copied!';
                setTimeout(() => btn.textContent = 'Copy', 1500);
            });
        });
        wrapper.appendChild(btn);
    });
}

function scrollToBottom() {
    if (autoScroll) {
        messagesContainer.scrollTo({ top: messagesContainer.scrollHeight, behavior: 'smooth' });
    }
}

// ── Typing / Streaming ──
function setTyping(typing, label) {
    isTyping = typing;
    if (typing) {
        // Move indicator right after the last user message bubble
        const userMsgs = messagesEl.querySelectorAll('.message.user');
        const lastUserMsg = userMsgs[userMsgs.length - 1];
        if (lastUserMsg && lastUserMsg.nextElementSibling !== typingIndicator) {
            messagesEl.insertBefore(typingIndicator, lastUserMsg.nextElementSibling);
        }
        if (thinkingLabel) {
            thinkingLabel.textContent = label || 'Thinking...';
            thinkingLabel.classList.add('pulse');
        }
        typingIndicator.classList.remove('hidden');
        sendBtn.disabled = true;
    } else {
        typingIndicator.classList.add('hidden');
        if (thinkingLabel) {
            thinkingLabel.classList.remove('pulse');
        }
        sendBtn.disabled = messageInput.value.trim().length === 0 || isStreaming;
    }
    scrollToBottom();
}

function setThinkingLabel(label) {
    if (thinkingLabel) {
        // Force reflow to ensure text updates immediately
        thinkingLabel.style.animation = 'none';
        thinkingLabel.offsetHeight; // trigger reflow
        thinkingLabel.style.animation = '';
        thinkingLabel.textContent = label || 'Thinking...';
        thinkingLabel.classList.add('pulse');
    }
}

function setStreaming(streaming) {
    isStreaming = streaming;
    if (streaming) {
        sendBtn.classList.add('hidden');
        stopBtn.classList.remove('hidden');
    } else {
        sendBtn.classList.remove('hidden');
        stopBtn.classList.add('hidden');
        sendBtn.disabled = messageInput.value.trim().length === 0;
    }
}

messagesContainer.addEventListener('scroll', () => {
    const nearBottom = messagesContainer.scrollHeight - messagesContainer.scrollTop - messagesContainer.clientHeight < 80;
    autoScroll = nearBottom;
});

// ── Edit Message ──
function startEditMessage(msgDiv) {
    const contentDiv = msgDiv.querySelector('.message-content');
    const body = contentDiv.querySelector('.message-body');
    const actions = contentDiv.querySelector('.message-actions');
    const originalText = body.textContent.trim();

    msgDiv.classList.add('editing');

    const editBox = document.createElement('div');
    editBox.className = 'message-edit-box';
    editBox.innerHTML = `
        <textarea>${escapeHtml(originalText)}</textarea>
        <div class="message-edit-actions">
            <button class="btn btn-ghost edit-cancel">Cancel</button>
            <button class="btn btn-primary edit-save">Send</button>
        </div>
    `;

    contentDiv.appendChild(editBox);
    if (actions) actions.style.display = 'none';

    const textarea = editBox.querySelector('textarea');
    textarea.focus();
    textarea.select();

    editBox.querySelector('.edit-cancel').addEventListener('click', () => {
        editBox.remove();
        msgDiv.classList.remove('editing');
        if (actions) actions.style.display = '';
    });

    editBox.querySelector('.edit-save').addEventListener('click', () => {
        const newText = textarea.value.trim();
        if (!newText || newText === originalText) {
            editBox.remove();
            msgDiv.classList.remove('editing');
            if (actions) actions.style.display = '';
            return;
        }

        const msgIndex = Array.from(messagesEl.children).indexOf(msgDiv);
        const toRemove = Array.from(messagesEl.children).slice(msgIndex);
        toRemove.forEach(el => el.remove());

        const history = [];
        messagesEl.querySelectorAll('.message').forEach(el => {
            const role = el.dataset.role;
            const bodyText = el.querySelector('.message-body').textContent.trim();
            const ts = el.querySelector('.message-time');
            history.push({
                role: role,
                content: bodyText,
                timestamp: ts ? ts.title : new Date().toISOString()
            });
        });

        editBox.remove();
        msgDiv.classList.remove('editing');

        addMessage('user', newText, null, Date.now());

        socket.emit('send_message', { message: newText, history: history });
        setTyping(true);
    });
}

// ── Regenerate Response ──
function regenerateResponse(assistantMsgDiv) {
    const allMsgs = Array.from(messagesEl.children);
    const idx = allMsgs.indexOf(assistantMsgDiv);
    if (idx <= 0) return;

    const userMsgDiv = allMsgs[idx - 1];
    if (userMsgDiv.dataset.role !== 'user') return;

    const userText = userMsgDiv.querySelector('.message-body').textContent.trim();

    const toRemove = allMsgs.slice(idx);
    toRemove.forEach(el => el.remove());

    const history = [];
    allMsgs.slice(0, idx).forEach(el => {
        const role = el.dataset.role;
        const bodyText = el.querySelector('.message-body').textContent.trim();
        const ts = el.querySelector('.message-time');
        history.push({
            role: role,
            content: bodyText,
            timestamp: ts ? ts.title : new Date().toISOString()
        });
    });

    socket.emit('send_message', { message: userText, history: history });
    setTyping(true);
}

// ── Debug Panel ──
function getDebugPanel() {
    let panel = document.getElementById('debug-panel');
    if (!panel) {
        panel = document.createElement('div');
        panel.id = 'debug-panel';
        panel.className = 'debug-panel hidden';
        messagesContainer.insertBefore(panel, typingIndicator);
    }
    return panel;
}

function clearDebugPanel() {
    const panel = getDebugPanel();
    panel.innerHTML = '';
    panel.classList.add('hidden');
}

function addDebugEntry(type, content, extra = {}) {
    if (!debugEnabled) return;
    const panel = getDebugPanel();
    panel.classList.remove('hidden');

    const entry = document.createElement('div');
    entry.className = 'debug-entry';

    let label = type;
    let body = '';

    if (type === 'tool_call') {
        label = 'Tool Call';
        body = `<span class="debug-content">${escapeHtml(extra.name)}(${JSON.stringify(extra.arguments)})</span>`;
    } else if (type === 'tool_result') {
        label = extra.duplicate ? 'Tool Result (Duplicate Blocked)' : 'Tool Result';
        body = `<span class="debug-content">${escapeHtml(content.substring(0, 500))}${content.length > 500 ? '...' : ''}</span>`;
    } else if (type === 'thinking') {
        label = 'Thinking';
        body = `<span class="debug-content">${escapeHtml(content)}</span>`;
    } else if (type === 'trim') {
        label = 'Context Trim';
        body = `<span class="debug-content">${escapeHtml(content)}</span>`;
    } else {
        body = `<span class="debug-content">${escapeHtml(content)}</span>`;
    }

    entry.innerHTML = `<span class="debug-label">${label}</span>${body}`;
    panel.appendChild(entry);
    scrollToBottom();
}

// ─ Debug Toggle ──
debugToggleBtn.addEventListener('click', () => {
    socket.emit('toggle_debug');
});

// ── Chat List ──
async function loadChatList() {
    try {
        const res = await fetch('/api/chats');
        const chats = await res.json();
        if (Array.isArray(chats)) {
            allChats = chats;
            renderChatList(chats);
        }
    } catch (e) {
        console.error('Failed to load chats:', e);
    }
}

function renderChatList(chats) {
    chatList.innerHTML = '';
    if (chats.length === 0) {
        const empty = document.createElement('div');
        empty.style.cssText = 'padding: 16px; text-align: center; color: var(--text-muted); font-size: 12px;';
        empty.textContent = 'No chats yet';
        chatList.appendChild(empty);
        return;
    }

    chats.forEach(chat => {
        const item = document.createElement('div');
        item.className = 'chat-item';
        item.dataset.id = chat.id;
        if (chat.id === currentChatId) item.classList.add('active');

        item.innerHTML = `
            <svg class="chat-item-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
            </svg>
            <span class="chat-item-title">${escapeHtml(chat.title)}</span>
            <div class="chat-item-actions">
                <button class="chat-item-action rename-action" title="Rename">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                        <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                    </svg>
                </button>
                <button class="chat-item-action delete-action" title="Delete">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <polyline points="3 6 5 6 21 6"/>
                        <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                    </svg>
                </button>
            </div>
        `;

        item.addEventListener('click', (e) => {
            if (e.target.closest('.rename-action') || e.target.closest('.delete-action')) return;
            loadChat(chat.id);
        });

        item.querySelector('.rename-action').addEventListener('click', (e) => {
            e.stopPropagation();
            openRenameModal(chat.id, chat.title);
        });

        item.querySelector('.delete-action').addEventListener('click', (e) => {
            e.stopPropagation();
            deleteChat(chat.id);
        });

        chatList.appendChild(item);
    });
}

function highlightActiveChat(chatId) {
    document.querySelectorAll('.chat-item').forEach(item => {
        item.classList.toggle('active', item.dataset.id === chatId);
    });
}

function loadChat(chatId) {
    socket.emit('load_chat', { chat_id: chatId });
}

async function deleteChat(chatId) {
    if (!confirm('Delete this chat?')) return;
    try {
        const res = await fetch(`/api/chats/${chatId}`, { method: 'DELETE' });
        if (res.ok) {
            if (currentChatId === chatId) resetChatUI();
            loadChatList();
        }
    } catch (e) {
        console.error('Failed to delete chat:', e);
    }
}

// ── Rename ──
const renameModal = document.createElement('div');
renameModal.className = 'modal hidden';
renameModal.innerHTML = `
    <div class="modal-backdrop"></div>
    <div class="modal-panel">
        <h3>Rename Chat</h3>
        <input type="text" id="rename-input" placeholder="Chat title...">
        <div class="modal-actions">
            <button id="rename-cancel" class="btn btn-ghost">Cancel</button>
            <button id="rename-confirm" class="btn btn-primary">Rename</button>
        </div>
    </div>
`;
document.body.appendChild(renameModal);

const renameInput = document.getElementById('rename-input');
let renamingChatId = null;

function openRenameModal(chatId, title) {
    renamingChatId = chatId;
    renameInput.value = title === 'YOLEST' || title === 'New Chat' ? '' : title;
    renameModal.classList.remove('hidden');
    renameInput.focus();
    renameInput.select();
}

function closeRenameModal() {
    renameModal.classList.add('hidden');
    renamingChatId = null;
}

renameModal.querySelector('#rename-confirm').addEventListener('click', async () => {
    const title = renameInput.value.trim();
    if (!title || !renamingChatId) return;
    try {
        const res = await fetch(`/api/chats/${renamingChatId}/rename`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title })
        });
        if (res.ok) {
            if (currentChatId === renamingChatId) currentChatTitle.textContent = title;
            loadChatList();
        }
    } catch (e) {
        console.error('Failed to rename chat:', e);
    }
    closeRenameModal();
});

renameModal.querySelector('#rename-cancel').addEventListener('click', closeRenameModal);
renameModal.querySelector('.modal-backdrop').addEventListener('click', closeRenameModal);
renameInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') renameModal.querySelector('#rename-confirm').click();
    if (e.key === 'Escape') closeRenameModal();
});

// ── README ──
readmeBtn.addEventListener('click', async () => {
    try {
        const res = await fetch('/api/readme');
        const data = await res.json();
        readmeContent.innerHTML = marked.parse(data.content);
        readmeContent.querySelectorAll('pre code').forEach(block => hljs.highlightElement(block));
        readmeModal.classList.remove('hidden');
    } catch (e) {
        readmeContent.innerHTML = '<p style="color:var(--text-muted)">Failed to load README.</p>';
        readmeModal.classList.remove('hidden');
    }
});

function closeReadmeModal() {
    readmeModal.classList.add('hidden');
}

readmeClose.addEventListener('click', closeReadmeModal);
readmeModal.querySelector('.modal-backdrop').addEventListener('click', closeReadmeModal);

// ── Change Password ──
changePasswordBtn.addEventListener('click', () => {
    passwordError.classList.add('hidden');
    currentPasswordInput.value = '';
    newPasswordInput.value = '';
    confirmNewPasswordInput.value = '';
    passwordModal.classList.remove('hidden');
    currentPasswordInput.focus();
});

function closePasswordModal() {
    passwordModal.classList.add('hidden');
}

passwordConfirmBtn.addEventListener('click', async () => {
    const current = currentPasswordInput.value;
    const newPass = newPasswordInput.value;
    const confirm = confirmNewPasswordInput.value;

    if (!current || !newPass || !confirm) {
        passwordError.textContent = 'All fields are required';
        passwordError.classList.remove('hidden');
        return;
    }

    try {
        const res = await fetch('/api/change_password', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ current_password: current, new_password: newPass, confirm_password: confirm })
        });
        const data = await res.json();
        if (res.ok) {
            closePasswordModal();
        } else {
            passwordError.textContent = data.error || 'Failed to change password';
            passwordError.classList.remove('hidden');
        }
    } catch (e) {
        passwordError.textContent = 'Network error';
        passwordError.classList.remove('hidden');
    }
});

passwordCancelBtn.addEventListener('click', closePasswordModal);
passwordModal.querySelector('.modal-backdrop').addEventListener('click', closePasswordModal);

// ── Admin: System Prompt ──
systemPromptBtn.addEventListener('click', async () => {
    try {
        const res = await fetch('/api/admin/system_prompt');
        const data = await res.json();
        promptTextarea.value = data.prompt;
        promptError.classList.add('hidden');
        promptModal.classList.remove('hidden');
    } catch (e) {
        promptError.textContent = 'Failed to load system prompt';
        promptError.classList.remove('hidden');
    }
});

function closePromptModal() {
    promptModal.classList.add('hidden');
}

promptSaveBtn.addEventListener('click', async () => {
    const prompt = promptTextarea.value.trim();
    if (!prompt) {
        promptError.textContent = 'Prompt cannot be empty';
        promptError.classList.remove('hidden');
        return;
    }
    try {
        const res = await fetch('/api/admin/system_prompt', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ prompt })
        });
        const data = await res.json();
        if (res.ok) {
            closePromptModal();
        } else {
            promptError.textContent = data.error || 'Failed to save';
            promptError.classList.remove('hidden');
        }
    } catch (e) {
        promptError.textContent = 'Network error';
        promptError.classList.remove('hidden');
    }
});

promptCancelBtn.addEventListener('click', closePromptModal);
promptCloseBtn.addEventListener('click', closePromptModal);
promptModal.querySelector('.modal-backdrop').addEventListener('click', closePromptModal);

// ── Export Chat ──
exportBtn.addEventListener('click', () => {
    const msgs = [];
    messagesEl.querySelectorAll('.message').forEach(el => {
        const role = el.dataset.role;
        const bodyText = el.querySelector('.message-body').textContent.trim();
        const timeEl = el.querySelector('.message-time');
        msgs.push({
            role: role,
            content: bodyText,
            time: timeEl ? timeEl.title : ''
        });
    });

    if (msgs.length === 0) {
        alert('No messages to export');
        return;
    }

    let md = `# ${currentChatTitle.textContent}\n\n`;
    msgs.forEach(m => {
        const label = m.role === 'user' ? 'You' : 'YOLEST';
        md += `## ${label}${m.time ? ' - ' + m.time : ''}\n\n${m.content}\n\n---\n\n`;
    });

    const blob = new Blob([md], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${currentChatTitle.textContent.replace(/[^a-z0-9]/gi, '_').toLowerCase()}_chat.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
});

// ── Auto-save draft ──
const DRAFT_KEY = 'yolest_draft';

function saveDraft() {
    const text = messageInput.value.trim();
    if (text) {
        localStorage.setItem(DRAFT_KEY, text);
    } else {
        localStorage.removeItem(DRAFT_KEY);
    }
}

function loadDraft() {
    const draft = localStorage.getItem(DRAFT_KEY);
    if (draft) {
        messageInput.value = draft;
        messageInput.style.height = 'auto';
        messageInput.style.height = Math.min(messageInput.scrollHeight, 200) + 'px';
        sendBtn.disabled = false;
    }
}

messageInput.addEventListener('input', () => {
    saveDraft();
});

loadDraft();

// ── Socket Events ──
socket.on('connect', () => {
    console.log('[YOLEST] Connected');
    loadChatList();
});

socket.on('chat_started', (data) => {
    currentChatId = data.chat_id;
    currentChatTitle.textContent = data.title;
    if (data.model_type) {
        currentModelType = data.model_type;
        if (modelSelector) modelSelector.value = currentModelType;
        updateModelBadge();
    }
    clearDebugPanel();
});

socket.on('chat_created', (data) => {
    currentChatId = data.chat_id;
    currentChatTitle.textContent = data.title;
    if (data.model_type) {
        currentModelType = data.model_type;
        if (modelSelector) modelSelector.value = currentModelType;
        updateModelBadge();
    }
    loadChatList().then(() => highlightActiveChat(data.chat_id));
});

socket.on('chat_loaded', (data) => {
    currentChatId = data.id;
    currentChatTitle.textContent = data.title;
    if (data.model_type) {
        currentModelType = data.model_type;
        if (modelSelector) modelSelector.value = currentModelType;
        updateModelBadge();
    }
    welcomeScreen.classList.add('hidden');
    messagesEl.innerHTML = '';
    clearDebugPanel();
    contextBanner.classList.add('hidden');

    data.messages.forEach(msg => {
        if (msg.role === 'system') return;
        if (msg.role === 'user' || msg.role === 'assistant') {
            const thinking = msg.role === 'assistant' ? extractThinking(msg.content) : null;
            const content = preprocessMath(thinking ? stripThinking(msg.content) : msg.content);
            const ts = msg.timestamp ? new Date(msg.timestamp).getTime() : null;
            addMessage(msg.role, content, thinking, ts);
        }
    });

    highlightActiveChat(data.id);
    scrollToBottom();
});

socket.on('message_received', (data) => {
    if (data.role === 'user') return;
    if (data.role === 'assistant') {
        setTyping(false);
        const thinking = data.thinking || extractThinking(data.content);
        const content = thinking ? stripThinking(data.content) : data.content;
        const ts = data.timestamp ? new Date(data.timestamp).getTime() : Date.now();
        addMessage('assistant', content, thinking, ts);
    }
});

socket.on('stream_start', (data) => {
    setTyping(false);
    setStreaming(true);
    currentStreamMsgId = 'msg-' + Date.now();
    addMessage('assistant', '', null, Date.now(), currentStreamMsgId);
    const msgDiv = messagesEl.querySelector(`[data-id="${currentStreamMsgId}"]`);
    if (msgDiv) {
        const body = msgDiv.querySelector('.message-body');
        body.innerHTML = '';
        body.dataset.rawText = '';
    }
});

socket.on('stream_token', (data) => {
    if (!currentStreamMsgId) return;
    const msgDiv = messagesEl.querySelector(`[data-id="${currentStreamMsgId}"]`);
    if (!msgDiv) return;
    const body = msgDiv.querySelector('.message-body');
    let rawText = (body.dataset.rawText || '') + data.token;
    body.dataset.rawText = rawText;
    const lastNode = body.lastChild;
    if (lastNode && lastNode.nodeType === Node.TEXT_NODE) {
        lastNode.textContent += data.token;
    } else {
        body.appendChild(document.createTextNode(data.token));
    }
    scrollToBottom();
});

socket.on('stream_end', (data) => {
    setStreaming(false);
    if (!currentStreamMsgId) return;
    const msgDiv = messagesEl.querySelector(`[data-id="${currentStreamMsgId}"]`);
    if (msgDiv) {
        const body = msgDiv.querySelector('.message-body');
        const rawText = body.dataset.rawText || '';
        body.innerHTML = marked.parse(preprocess(rawText));
        renderMath(body);
        addCodeCopyButtons(body);
        body.querySelectorAll('pre code').forEach(block => hljs.highlightElement(block));
    }
    currentStreamMsgId = null;
});

socket.on('status', (data) => {
    if (data.status === 'idle') {
        setTyping(false);
    } else if (data.status === 'thinking') {
        setThinkingLabel(data.message || 'Thinking...');
    } else if (data.status === 'tool') {
        setThinkingLabel(data.message || `Using ${data.tool}...`);
    }
});

socket.on('debug', (data) => {
    addDebugEntry(data.type, data.message || data.content || '', data);
});

socket.on('debug_toggled', (data) => {
    debugEnabled = data.enabled;
    debugStatusSpan.textContent = debugEnabled ? 'On' : 'Off';
    debugToggleBtn.classList.toggle('active-debug', debugEnabled);
    if (!debugEnabled) {
        clearDebugPanel();
    }
});

socket.on('context_trimmed', (data) => {
    contextBanner.classList.remove('hidden');
    contextBanner.querySelector('span').textContent = `Older messages were hidden to save space (trim #${data.count}).`;
});

socket.on('refresh_chats', () => {
    loadChatList();
});

socket.on('error', (data) => {
    setTyping(false);
    setStreaming(false);
    currentStreamMsgId = null;
    console.error('[YOLEST Error]', data.message);
    addMessage('assistant', `**Error:** ${escapeHtml(data.message)}`, null, Date.now());
});

// ── Helpers ──
function extractThinking(text) {
    if (!text) return null;
    const match = text.match(/<thinking>([\s\S]*?)<\/thinking>/);
    return match ? match[1].trim() : null;
}

function stripThinking(text) {
    if (!text) return '';
    return text.replace(/<thinking>[\s\S]*?<\/thinking>/g, '').trim();
}

function renderMath(element) {
    if (window.renderMathInElement) {
        renderMathInElement(element, {
            delimiters: [
                {left: '$$$$', right: '$$$$', display: true},
                {left: '$$', right: '$$', display: true},
                {left: '\\[', right: '\\]', display: true},
                {left: '\\(', right: '\\)', display: false}
            ],
            throwOnError: false
        });
    }
}

function preprocessMath(text) {
    return text.replace(/\[([\s\S]*?)\]/g, (match, content) => {
        if (/\\[a-zA-Z]+/.test(content)) {
            return '$$' + content + '$$';
        }
        return match;
    });
}
