/* ═══════════════════════════════════════════════════════════════════════════
   HR-Bot Frontend — Application Logic
   ═══════════════════════════════════════════════════════════════════════════ */

const API_BASE = 'http://localhost:8000';

// ── State ─────────────────────────────────────────────────────────────────
let currentUser = null;      // { id, username, name, email, role, candidate_id? }
let sessionId = null;
let questionCount = 0;
const MAX_Q = 10;

// ── Helpers ───────────────────────────────────────────────────────────────

function ts() {
  return new Date().toLocaleTimeString('en-IN', {
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true
  });
}

function showToast(msg, type = 'error') {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = 'toast ' + type;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 4000);
}

function escapeHtml(text) {
  return String(text)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/\n/g, '<br>');
}

// ═══════════════ AUTH ═══════════════

function switchAuthTab(tab) {
  document.getElementById('tab-login').classList.toggle('active', tab === 'login');
  document.getElementById('tab-signup').classList.toggle('active', tab === 'signup');
  document.getElementById('login-form').style.display = tab === 'login' ? 'flex' : 'none';
  document.getElementById('signup-form').style.display = tab === 'signup' ? 'flex' : 'none';
  // Clear errors
  document.getElementById('login-error').textContent = '';
  document.getElementById('signup-error').textContent = '';
  document.getElementById('signup-success').textContent = '';
}

async function handleLogin(e) {
  e.preventDefault();
  const username = document.getElementById('login-username').value.trim();
  const password = document.getElementById('login-password').value;
  const errEl = document.getElementById('login-error');
  errEl.textContent = '';

  if (!username || !password) {
    errEl.textContent = 'Please fill in all fields.';
    return;
  }

  try {
    const res = await fetch(`${API_BASE}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });
    const data = await res.json();

    if (!res.ok) {
      errEl.textContent = data.detail || 'Login failed.';
      return;
    }

    currentUser = data.user;
    localStorage.setItem('hrbot_user', JSON.stringify(currentUser));

    if (currentUser.role === 'hr') {
      showHRDashboard();
    } else {
      showCandidateDashboard();
    }
  } catch (err) {
    errEl.textContent = 'Connection error. Is the server running?';
  }
}

async function handleSignup(e) {
  e.preventDefault();
  const name = document.getElementById('signup-name').value.trim();
  const email = document.getElementById('signup-email').value.trim();
  const password = document.getElementById('signup-password').value;
  const age = parseInt(document.getElementById('signup-age').value);
  const role = document.getElementById('signup-role').value;

  const errEl = document.getElementById('signup-error');
  const successEl = document.getElementById('signup-success');
  errEl.textContent = '';
  successEl.textContent = '';

  if (!name || !email || !password || !age) {
    errEl.textContent = 'Please fill in all fields.';
    return;
  }

  try {
    const res = await fetch(`${API_BASE}/auth/signup`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, email, password, age, role }),
    });
    const data = await res.json();

    if (!res.ok) {
      errEl.textContent = data.detail || 'Sign-up failed.';
      return;
    }

    successEl.textContent = `Account created! Your username is: ${data.user.username}. Switch to Login.`;
    // Clear form
    document.getElementById('signup-form').reset();
  } catch (err) {
    errEl.textContent = 'Connection error. Is the server running?';
  }
}

function logout() {
  currentUser = null;
  sessionId = null;
  localStorage.removeItem('hrbot_user');
  document.getElementById('hr-dashboard').style.display = 'none';
  document.getElementById('candidate-dashboard').style.display = 'none';
  document.getElementById('auth-screen').style.display = 'flex';
  // Clear forms
  document.getElementById('login-form').reset();
  document.getElementById('signup-form').reset();
}

// ═══════════════ HR DASHBOARD ═══════════════

function showHRDashboard() {
  document.getElementById('auth-screen').style.display = 'none';
  document.getElementById('candidate-dashboard').style.display = 'none';
  document.getElementById('hr-dashboard').style.display = 'flex';

  // Set user info
  document.getElementById('hr-name').textContent = currentUser.name;
  document.getElementById('hr-avatar').textContent = currentUser.name.charAt(0).toUpperCase();
  document.getElementById('welcome-msg').textContent = `Hello, ${currentUser.name}! Let's streamline your hiring process.`;

  // Start live time
  updateLiveTime();
  setInterval(updateLiveTime, 1000);
}

function updateLiveTime() {
  const el = document.getElementById('live-time');
  if (el) {
    el.textContent = new Date().toLocaleString('en-IN', {
      weekday: 'short', year: 'numeric', month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true
    });
  }
}

function switchHRTab(tab) {
  // Update nav
  document.querySelectorAll('.sidebar-nav .nav-item').forEach(el => el.classList.remove('active'));
  document.getElementById('nav-' + tab).classList.add('active');

  // Show/hide content
  document.querySelectorAll('.tab-content').forEach(el => {
    el.style.display = 'none';
    el.classList.remove('active');
  });
  const target = document.getElementById('tab-content-' + tab);
  if (target) {
    target.style.display = 'block';
    target.classList.add('active');
  }
}

// ── File Handling ─────────────────────────────────────────────────────────

function handleFileSelect(type) {
  const input = document.getElementById(type + '-file');
  const nameEl = document.getElementById(type + '-file-name');
  const zone = document.getElementById(type + '-drop-zone');

  if (input.files.length > 0) {
    nameEl.textContent = '✅ ' + input.files[0].name;
    zone.classList.add('has-file');
  } else {
    nameEl.textContent = '';
    zone.classList.remove('has-file');
  }

  // Enable generate button if both files selected
  const resumeReady = document.getElementById('resume-file').files.length > 0;
  const jdReady = document.getElementById('jd-file').files.length > 0;
  document.getElementById('generate-score-btn').disabled = !(resumeReady && jdReady);
}

// ── Generate Score ────────────────────────────────────────────────────────

async function generateScore() {
  const resumeFile = document.getElementById('resume-file').files[0];
  const jdFile = document.getElementById('jd-file').files[0];

  if (!resumeFile || !jdFile) {
    showToast('Please select both files first.', 'error');
    return;
  }

  // Show loading state
  const btn = document.getElementById('generate-score-btn');
  btn.disabled = true;
  document.getElementById('generate-btn-text').style.display = 'none';
  document.getElementById('generate-btn-loader').style.display = 'inline-flex';

  const formData = new FormData();
  formData.append('resume_file', resumeFile);
  formData.append('jd_file', jdFile);

  try {
    const res = await fetch(`${API_BASE}/upload/resume-and-jd`, {
      method: 'POST',
      body: formData,
    });
    const data = await res.json();

    if (!res.ok) {
      showToast(data.detail || 'Screening failed.', 'error');
      return;
    }

    displayScreeningResults(data);
    showToast('Screening completed successfully!', 'success');
  } catch (err) {
    showToast('Connection error: ' + err.message, 'error');
  } finally {
    btn.disabled = false;
    document.getElementById('generate-btn-text').style.display = 'inline';
    document.getElementById('generate-btn-loader').style.display = 'none';
  }
}

function displayScreeningResults(data) {
  const panel = document.getElementById('results-panel');
  const content = document.getElementById('results-content');
  panel.style.display = 'block';

  // Extract screening result from the nested response
  const screeningResult = data.results?.screening || data.results?.extraction?.screening_result || {};
  const extractionResult = data.results?.extraction || {};

  const scores = screeningResult.scores || {};
  const overallFit = scores.overall_fit || 0;
  const recommendation = screeningResult.recommendation || 'N/A';
  const jdTitle = screeningResult.jd_title || 'Position';
  const candidateId = data.candidate_id;

  // Determine pass/fail
  const passed = overallFit >= 90;

  let html = `
    <div class="score-hero">
      <div class="score-circle" style="background: ${passed ? 'var(--gradient-green)' : 'var(--gradient-danger)'};">
        ${overallFit}
      </div>
      <div class="score-label">Overall Fit Score</div>
      <div class="score-status ${passed ? 'pass' : 'fail'}">
        ${passed ? '✅ SHORTLISTED' : '❌ NOT QUALIFIED'}
      </div>
    </div>
  `;

  // Score breakdown
  if (Object.keys(scores).length > 0) {
    html += '<div class="scores-breakdown">';
    for (const [key, value] of Object.entries(scores)) {
      if (key === 'overall_fit') continue;
      const label = key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
      html += `
        <div class="score-bar-item">
          <span class="score-bar-label">${label}</span>
          <div class="score-bar-track">
            <div class="score-bar-fill" style="width: ${value}%;"></div>
          </div>
          <span class="score-bar-value">${value}</span>
        </div>
      `;
    }
    html += '</div>';
  }

  // Recommendation
  html += `
    <div class="result-section">
      <h3>Recommendation</h3>
      <p class="result-text">${escapeHtml(recommendation)}</p>
    </div>
  `;

  // Strengths/Weaknesses
  if (screeningResult.strengths && screeningResult.strengths.length > 0) {
    html += `
      <div class="result-section">
        <h3>Strengths</h3>
        ${screeningResult.strengths.map(s => `<span class="result-tag">${escapeHtml(s)}</span>`).join('')}
      </div>
    `;
  }

  if (screeningResult.weaknesses && screeningResult.weaknesses.length > 0) {
    html += `
      <div class="result-section">
        <h3>Areas for Improvement</h3>
        ${screeningResult.weaknesses.map(w => `<span class="result-tag">${escapeHtml(w)}</span>`).join('')}
      </div>
    `;
  }

  // Gmail result
  const gmailResult = data.results?.gmail;
  if (gmailResult) {
    const emailType = gmailResult.email_type || gmailResult.status;
    html += `
      <div class="result-section">
        <h3>📧 Email Notification</h3>
        <p class="result-text">
          ${gmailResult.status === 'sent'
            ? `✅ ${emailType === 'shortlisting' ? 'Shortlisting' : 'Rejection'} email sent to ${gmailResult.to}`
            : `⚠ Email: ${gmailResult.status} — ${gmailResult.reason || ''}`
          }
        </p>
      </div>
    `;
  }

  // If candidate passed, show generate credentials button
  if (passed && candidateId) {
    html += `
      <div class="cred-card" id="cred-card-${candidateId}">
        <h3>🔐 Generate Candidate Credentials</h3>
        <p style="font-size: 0.82rem; color: var(--text-secondary); margin-bottom: 12px;">
          Generate login credentials for the candidate to access the interview portal.
        </p>
        <button class="btn btn-success" onclick="generateCandidateCredentials(${candidateId})" id="cred-btn-${candidateId}">
          🔑 Generate & Send Credentials
        </button>
        <div id="cred-result-${candidateId}" style="margin-top: 12px;"></div>
      </div>
    `;
  }

  content.innerHTML = html;

  // Animate score bars with delay
  setTimeout(() => {
    document.querySelectorAll('.score-bar-fill').forEach(fill => {
      fill.style.width = fill.style.width; // trigger reflow
    });
  }, 100);
}

async function generateCandidateCredentials(candidateId) {
  const btn = document.getElementById(`cred-btn-${candidateId}`);
  const resultEl = document.getElementById(`cred-result-${candidateId}`);
  btn.disabled = true;
  btn.textContent = '⏳ Generating...';

  try {
    const res = await fetch(`${API_BASE}/auth/generate-candidate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ candidate_id: candidateId }),
    });
    const data = await res.json();

    if (!res.ok) {
      resultEl.innerHTML = `<p style="color: var(--red);">❌ ${data.detail}</p>`;
      btn.disabled = false;
      btn.textContent = '🔑 Generate & Send Credentials';
      return;
    }

    resultEl.innerHTML = `
      <div style="margin-top: 6px;">
        <div class="cred-row"><span class="cred-label">Username:</span><span class="cred-value">${data.username}</span></div>
        ${data.password ? `<div class="cred-row"><span class="cred-label">Password:</span><span class="cred-value">${data.password}</span></div>` : ''}
        <div class="cred-row"><span class="cred-label">Email sent:</span><span class="cred-value">${data.email_sent ? '✅ Yes' : '❌ No'}</span></div>
      </div>
    `;
    btn.textContent = '✅ Credentials Generated';
    showToast('Credentials generated and emailed!', 'success');
  } catch (err) {
    resultEl.innerHTML = `<p style="color: var(--red);">❌ Connection error</p>`;
    btn.disabled = false;
    btn.textContent = '🔑 Generate & Send Credentials';
  }
}


// ═══════════════ CANDIDATE DASHBOARD ═══════════════

function showCandidateDashboard() {
  document.getElementById('auth-screen').style.display = 'none';
  document.getElementById('hr-dashboard').style.display = 'none';
  document.getElementById('candidate-dashboard').style.display = 'flex';

  // Set user info
  document.getElementById('cand-name-display').textContent = currentUser.name;
  document.getElementById('cand-avatar').textContent = currentUser.name.charAt(0).toUpperCase();

  // Load chat history
  loadChatHistory();
}

async function loadChatHistory() {
  if (!currentUser || !currentUser.candidate_id) return;

  const listEl = document.getElementById('chat-history-list');
  listEl.innerHTML = '<div class="chat-history-empty"><span>Loading...</span></div>';

  try {
    const res = await fetch(`${API_BASE}/interview/sessions?candidate_id=${currentUser.candidate_id}`);
    const data = await res.json();

    if (!res.ok || !data.sessions || data.sessions.length === 0) {
      listEl.innerHTML = `
        <div class="chat-history-empty">
          <span>No chat history yet</span>
          <p>Start an interview to see your history here.</p>
        </div>
      `;
      return;
    }

    listEl.innerHTML = data.sessions.map(s => `
      <div class="history-session-item" onclick="loadSessionHistory(${s.session_id})">
        <div class="history-session-id">Session #${s.session_id}</div>
        <div class="history-session-time">${s.started_at ? new Date(s.started_at).toLocaleString() : 'N/A'}</div>
        <span class="history-session-status ${s.status === 'completed' ? 'status-completed' : 'status-active'}">
          ${s.status}
        </span>
      </div>
    `).join('');
  } catch (err) {
    listEl.innerHTML = `
      <div class="chat-history-empty">
        <span>Failed to load</span>
        <p>${err.message}</p>
      </div>
    `;
  }
}

async function loadSessionHistory(sid) {
  // Highlight active session
  document.querySelectorAll('.history-session-item').forEach(el => el.classList.remove('active'));
  event.currentTarget.classList.add('active');

  try {
    const res = await fetch(`${API_BASE}/interview/history/${sid}`);
    const data = await res.json();

    if (!res.ok) {
      showToast(data.detail || 'Failed to load history', 'error');
      return;
    }

    // Display history in chat area
    const messagesEl = document.getElementById('cand-messages');
    const setupEl = document.getElementById('cand-setup');
    const inputEl = document.getElementById('cand-input-area');

    setupEl.style.display = 'none';
    messagesEl.style.display = 'flex';
    messagesEl.innerHTML = '';
    
    sessionId = sid;
    if (data.status === 'completed') {
      inputEl.style.display = 'none';
      setCandidateInputEnabled(false, 'Interview completed.');
    } else {
      inputEl.style.display = 'flex';
      setCandidateInputEnabled(true, 'Type your answer… (Enter to send)');
    }

    // Status pill
    const statusPill = document.getElementById('cand-status-pill');
    statusPill.textContent = data.status;
    statusPill.className = `status-pill pill-${data.status === 'completed' ? 'completed' : 'active'}`;

    document.getElementById('chat-status').textContent = `Session #${sid} — ${data.status}`;

    // Render history
    if (data.interview_history && data.interview_history.length > 0) {
      data.interview_history.forEach(turn => {
        // Bot question
        addCandidateMsg('bot', turn.question, turn.question_number);
        // User answer
        if (turn.answer) {
          addCandidateMsg('user', turn.answer);
        }
      });
    }
    if (data.post_interview_qna && data.post_interview_qna.length > 0) {
      data.post_interview_qna.forEach(turn => {
        // User question
        addCandidateMsg('user', turn.question);
        // Bot answer
        if (turn.answer) {
          addCandidateMsg('bot', turn.answer);
        }
      });
    }
  } catch (err) {
    showToast('Error loading session: ' + err.message, 'error');
  }
}

// ── Candidate Interview ───────────────────────────────────────────────────

async function startCandidateInterview() {
  if (!currentUser || !currentUser.candidate_id) {
    showToast('No candidate ID linked to your account.', 'error');
    return;
  }

  const btn = document.getElementById('start-interview-btn');
  btn.disabled = true;
  btn.textContent = '⏳ Starting...';

  try {
    const res = await fetch(`${API_BASE}/interview/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ candidate_id: currentUser.candidate_id }),
    });
    const data = await res.json();

    if (!res.ok) {
      showToast(data.detail || 'Failed to start interview.', 'error');
      btn.disabled = false;
      btn.textContent = '▶ Start Interview';
      return;
    }

    sessionId = data.session_id;

    // Switch to chat view
    document.getElementById('cand-setup').style.display = 'none';
    document.getElementById('cand-messages').style.display = 'flex';
    document.getElementById('cand-input-area').style.display = 'flex';

    document.getElementById('chat-status').textContent = `Session #${sessionId} — Live`;
    const statusPill = document.getElementById('cand-status-pill');
    statusPill.textContent = 'Greeting';
    statusPill.className = 'status-pill pill-greeting';

    // Show first message
    addCandidateMsg('bot', data.bot_message);
    setCandidateInputEnabled(true, 'Say hello to get started…');

    // Refresh chat history
    loadChatHistory();
  } catch (err) {
    showToast('Connection error: ' + err.message, 'error');
    btn.disabled = false;
    btn.textContent = '▶ Start Interview';
  }
}

async function sendCandidateAnswer() {
  const input = document.getElementById('cand-answer-input');
  const answer = input.value.trim();
  if (!answer || !sessionId) return;

  setCandidateInputEnabled(false);
  input.value = '';
  addCandidateMsg('user', answer);
  showCandidateTyping();

  try {
    const res = await fetch(`${API_BASE}/interview/respond`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, answer }),
    });
    const data = await res.json();
    removeCandidateTyping();

    if (!res.ok) {
      showToast(data.detail || 'Error', 'error');
      setCandidateInputEnabled(true);
      return;
    }

    handleCandidateBotResponse(data);
  } catch (err) {
    removeCandidateTyping();
    showToast('Error: ' + err.message, 'error');
    setCandidateInputEnabled(true);
  }
}

function handleCandidateBotResponse(data) {
  const status = data.status;
  const botMsg = data.bot_message;
  const qNum = data.is_interview_question ? data.question_number : null;

  // Update status pill
  const pill = document.getElementById('cand-status-pill');
  const statusMap = {
    greeting: ['pill-greeting', 'Greeting'],
    active: ['pill-active', 'Live'],
    post_interview: ['pill-active', 'Q&A'],
    completed: ['pill-completed', 'Completed'],
  };
  const [pillClass, pillLabel] = statusMap[status] || ['pill-idle', status];
  pill.className = 'status-pill ' + pillClass;
  pill.textContent = pillLabel;

  if (data.is_interview_question && data.question_number > 0) {
    questionCount = data.question_number;
  }

  if (status === 'completed') {
    showCandidateDone(botMsg);
    loadChatHistory();
    return;
  }

  addCandidateMsg('bot', botMsg, qNum);

  if (status === 'post_interview') {
    setCandidateInputEnabled(true, 'Ask a question, or type "No more questions" to end…');
  } else {
    setCandidateInputEnabled(true, status === 'greeting'
      ? 'Say hello to get started…'
      : 'Type your answer… (Enter to send)');
  }
}

// ── Chat UI Helpers ───────────────────────────────────────────────────────

function addCandidateMsg(role, text, qNum = null) {
  if (!text) return;
  const msgs = document.getElementById('cand-messages');
  const div = document.createElement('div');
  div.className = 'msg ' + role;

  if (role === 'bot') {
    div.innerHTML = `
      <div class="msg-label">🤖 HR-Bot</div>
      ${qNum ? `<div class="q-badge">Question ${qNum}</div>` : ''}
      <div class="bubble">${escapeHtml(text)}</div>
      <div class="msg-time">${ts()}</div>
    `;
  } else {
    div.innerHTML = `
      <div class="msg-label">You</div>
      <div class="bubble">${escapeHtml(text)}</div>
      <div class="msg-time">${ts()}</div>
    `;
  }
  msgs.appendChild(div);
  msgs.scrollTop = msgs.scrollHeight;
}

function showCandidateTyping() {
  const msgs = document.getElementById('cand-messages');
  const div = document.createElement('div');
  div.className = 'msg bot';
  div.id = 'cand-typing';
  div.innerHTML = `
    <div class="msg-label">🤖 HR-Bot</div>
    <div class="bubble"><div class="typing"><span></span><span></span><span></span></div></div>
  `;
  msgs.appendChild(div);
  msgs.scrollTop = msgs.scrollHeight;
}

function removeCandidateTyping() {
  const el = document.getElementById('cand-typing');
  if (el) el.remove();
}

function showCandidateDone(message) {
  const msgs = document.getElementById('cand-messages');
  const div = document.createElement('div');
  div.className = 'done-banner';
  div.innerHTML = `<div class="done-icon">🌟</div><p>${escapeHtml(message)}</p>`;
  msgs.appendChild(div);
  msgs.scrollTop = msgs.scrollHeight;

  // Disable input
  setCandidateInputEnabled(false, 'Interview completed.');
}

function setCandidateInputEnabled(enabled, placeholder) {
  const inp = document.getElementById('cand-answer-input');
  const btn = document.getElementById('cand-send-btn');
  const micBtn = document.getElementById('cand-mic-btn');
  inp.disabled = !enabled;
  btn.disabled = !enabled;
  if (micBtn) micBtn.disabled = !enabled;
  if (placeholder) inp.placeholder = placeholder;
  if (enabled) inp.focus();
}

function handleCandidateKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendCandidateAnswer();
  }
}

// ── Voice Bot Integration ───────────────────────────────────────────────

let voiceWs = null;
let voiceAudioCtx = null;
let voiceMicStream = null;
let voiceWorkletNode = null;
let voiceNextPlayTime = 0;
let isVoiceRecording = false;

const WORKLET_CODE = `
class PCMProcessor extends AudioWorkletProcessor {
  process(inputs) {
    const ch = inputs[0][0];
    if (ch) {
      const buf = new Int16Array(ch.length);
      for (let i = 0; i < ch.length; i++) {
        const s = Math.max(-1, Math.min(1, ch[i]));
        buf[i] = s < 0 ? s * 32768 : s * 32767;
      }
      this.port.postMessage(buf.buffer, [buf.buffer]);
    }
    return true;
  }
}
registerProcessor('pcm-processor', PCMProcessor);
`;

async function toggleVoiceBot() {
  if (isVoiceRecording) stopVoiceBot();
  else startVoiceBot();
}

async function startVoiceBot() {
  const btn = document.getElementById('cand-mic-btn');
  isVoiceRecording = true;
  btn.classList.add('connecting');
  btn.textContent = '⌛';
  showToast('Connecting to voice...', 'info');

  try {
    voiceMicStream = await navigator.mediaDevices.getUserMedia({
      audio: { sampleRate: 48000, channelCount: 1, echoCancellation: true, noiseSuppression: true }
    });
  } catch (err) {
    showToast('Microphone error: ' + err.message, 'error');
    stopVoiceBot();
    return;
  }

  voiceAudioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 48000 });
  await voiceAudioCtx.resume();

  const blob = new Blob([WORKLET_CODE], { type: 'application/javascript' });
  const blobURL = URL.createObjectURL(blob);
  await voiceAudioCtx.audioWorklet.addModule(blobURL);

  const micSource = voiceAudioCtx.createMediaStreamSource(voiceMicStream);
  voiceWorkletNode = new AudioWorkletNode(voiceAudioCtx, 'pcm-processor');
  micSource.connect(voiceWorkletNode);

  const wsUrl = API_BASE.replace('http:', 'ws:').replace('https:', 'wss:') + '/voice-interview/ws?session_id=' + sessionId;
  voiceWs = new WebSocket(wsUrl);
  voiceWs.binaryType = 'arraybuffer';

  voiceWs.onopen = () => {
    btn.classList.remove('connecting');
    btn.classList.add('recording');
    btn.textContent = '🔴';
    showToast('Voice agent connected! Start speaking.', 'success');

    voiceWorkletNode.port.onmessage = (e) => {
      if (voiceWs && voiceWs.readyState === WebSocket.OPEN) {
        voiceWs.send(e.data);
      }
    };
  };

  voiceWs.onmessage = (e) => {
    if (e.data instanceof ArrayBuffer) {
      const int16 = new Int16Array(e.data);
      const float32 = new Float32Array(int16.length);
      for (let i = 0; i < int16.length; i++) {
        float32[i] = int16[i] / 32768;
      }
      const audioBuf = voiceAudioCtx.createBuffer(1, float32.length, 24000);
      audioBuf.copyToChannel(float32, 0);

      const src = voiceAudioCtx.createBufferSource();
      src.buffer = audioBuf;
      src.connect(voiceAudioCtx.destination);

      const now = voiceAudioCtx.currentTime;
      if (voiceNextPlayTime < now) voiceNextPlayTime = now + 0.05;
      src.start(voiceNextPlayTime);
      voiceNextPlayTime += audioBuf.duration;
    } else {
      try {
        const msg = JSON.parse(e.data);
        if (msg.type === 'ConversationText') {
          if (msg.role === 'assistant') addCandidateMsg('bot', msg.content);
          else if (msg.role === 'user') addCandidateMsg('user', msg.content);
        } else if (msg.type === 'UserStartedSpeaking') {
          voiceNextPlayTime = 0;
        } else if (msg.error) {
          showToast('Voice Error: ' + msg.error, 'error');
        }
      } catch (err) {
        console.error('Error parsing WS message', err);
      }
    }
  };

  voiceWs.onclose = () => stopVoiceBot();
  voiceWs.onerror = () => {
    showToast('Voice connection error', 'error');
    stopVoiceBot();
  };
}

function stopVoiceBot() {
  if (voiceWs) { try { voiceWs.close(); } catch {} voiceWs = null; }
  if (voiceMicStream) { voiceMicStream.getTracks().forEach(t => t.stop()); voiceMicStream = null; }
  if (voiceAudioCtx) { voiceAudioCtx.close(); voiceAudioCtx = null; }
  voiceNextPlayTime = 0;
  isVoiceRecording = false;

  const btn = document.getElementById('cand-mic-btn');
  if (btn) {
    btn.classList.remove('connecting', 'recording');
    btn.textContent = '🎙️';
  }
}

// ── Candidates & Visualisations ──────────────────────────────────────────

let botChartInstance = null;
let candChartInstance = null;

async function loadCandidatesList() {
  const tbody = document.getElementById('candidates-table-body');
  tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; padding: 20px;">Fetching...</td></tr>';
  document.getElementById('candidate-vis-panel').style.display = 'none';

  try {
    const res = await fetch(`${API_BASE}/interview/candidates`);
    if (!res.ok) throw new Error('Failed to load candidates');
    const candidates = await res.json();
    
    tbody.innerHTML = '';
    if (candidates.length === 0) {
      tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; padding: 20px;">No candidates found</td></tr>';
      return;
    }

    candidates.forEach(c => {
      const tr = document.createElement('tr');
      
      let badgeClass = 'badge-pending';
      if (c.status === 'Shortlisted') badgeClass = 'badge-shortlisted';
      else if (c.status === 'Rejected') badgeClass = 'badge-rejected';
      else if (c.status === 'Completed') badgeClass = 'badge-completed';
      else if (c.status === 'Active') badgeClass = 'badge-active';

      let scoreMarkup = '-';
      if (c.score !== null) {
        let scClass = 'high';
        if (c.score < 60) scClass = 'low';
        else if (c.score < 80) scClass = 'med';
        scoreMarkup = `<span class="score-badge ${scClass}">${c.score}/100</span>`;
      }

      tr.innerHTML = `
        <td>#${c.id}</td>
        <td style="font-weight:600;">${c.name}</td>
        <td>${c.email}</td>
        <td>${scoreMarkup}</td>
        <td><span class="status-badge ${badgeClass}">${c.status}</span></td>
        <td>
          <button class="btn btn-sm" style="background:var(--bg-surface-3)" onclick='viewCandidateEvaluation(${JSON.stringify(c).replace(/'/g, "&apos;")})'>
            View Eval
          </button>
        </td>
      `;
      tbody.appendChild(tr);
    });

  } catch(err) {
    tbody.innerHTML = `<tr><td colspan="6" style="color:var(--red); text-align:center;">${err.message}</td></tr>`;
  }
}

window.viewCandidateEvaluation = function(c) {
  const panel = document.getElementById('candidate-vis-panel');
  document.getElementById('vis-candidate-name').textContent = c.name;
  panel.style.display = 'block';

  const rbtn = document.getElementById('download-report-btn');
  const rbadge = document.getElementById('vis-report-badge');
  if (c.report_path) {
    rbtn.style.display = 'inline-block';
    rbadge.style.display = 'inline-block';
    rbtn.onclick = () => {
      let relativePath = c.report_path;
      if (relativePath.includes('/tmp')) {
        relativePath = relativePath.split('/tmp').pop(); 
      }
      window.open(relativePath, '_blank');
    };
  } else {
    rbtn.style.display = 'none';
    rbadge.style.display = 'none';
  }

  // Destroy previous charts to avoid canvas overlaps
  if (botChartInstance) { botChartInstance.destroy(); }
  if (candChartInstance) { candChartInstance.destroy(); }

  if (!c.eval_result) {
    document.getElementById('botMetricsChart').style.display = 'none';
    document.getElementById('candidateMetricsChart').style.display = 'none';
    return;
  }
  document.getElementById('botMetricsChart').style.display = 'block';
  document.getElementById('candidateMetricsChart').style.display = 'block';

  const bm = c.eval_result.bot_metrics || {};
  const cm = c.eval_result.candidate_metrics || {};
  const vis = c.eval_result.visualisation_data;

  // Render Bot Metrics Chart
  if (vis && vis.x_values && vis.y_values) {
    botChartInstance = new Chart(document.getElementById('botMetricsChart'), {
      type: 'bar',
      data: {
        labels: vis.x_values,
        datasets: [{
          label: vis.y_column || 'Scores',
          data: vis.y_values,
          backgroundColor: 'rgba(108,99,255,0.5)',
          borderColor: 'rgba(108,99,255,1)',
          borderWidth: 1
        }]
      },
      options: { scales: { y: { beginAtZero: true, max: 100 } } }
    });
  } else {
    // Fallback based on known keys
    botChartInstance = new Chart(document.getElementById('botMetricsChart'), {
      type: 'bar',
      data: {
        labels: ['Question Quality', 'Adaptability', 'Topic Coverage', 'Consistency'],
        datasets: [{
          label: 'Bot Score / 100',
          data: [bm.question_quality_score, bm.adaptability_score, bm.topic_coverage_score, bm.consistency_score],
          backgroundColor: 'rgba(108,99,255,0.5)',
          borderColor: 'rgba(108,99,255,1)',
          borderWidth: 1
        }]
      },
      options: { scales: { y: { beginAtZero: true, max: 100 } } }
    });
  }

  candChartInstance = new Chart(document.getElementById('candidateMetricsChart'), {
    type: 'pie',
    data: {
      labels: ['Clarity', 'Relevance', 'Technical', 'Confidence', 'Engagement'],
      datasets: [{
        label: 'Candidate Score / 100',
        data: [cm.communication_clarity_score, cm.relevance_score, cm.technical_competency_score, cm.confidence_conviction_score, cm.engagement_depth_score],
        backgroundColor: [
          'rgba(52,211,153,0.5)',
          'rgba(59,130,246,0.5)',
          'rgba(147,51,234,0.5)',
          'rgba(245,158,11,0.5)',
          'rgba(239,68,68,0.5)'
        ],
        borderWidth: 1
      }]
    }
  });
}

// ═══════════════ AUTO-LOGIN ON PAGE LOAD ═══════════════

(function init() {
  const saved = localStorage.getItem('hrbot_user');
  if (saved) {
    try {
      currentUser = JSON.parse(saved);
      if (currentUser.role === 'hr') {
        showHRDashboard();
      } else {
        showCandidateDashboard();
      }
    } catch {
      localStorage.removeItem('hrbot_user');
    }
  }
})();
