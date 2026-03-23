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

  // Auto-fetch candidate data
  if (tab === 'candidates') {
    loadCandidatesList();
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
  
  // Automatically start a new interview session
  autoStartInterview();
}

// ── Candidate Interview ───────────────────────────────────────────────────

async function autoStartInterview() {
  if (!currentUser || !currentUser.candidate_id) {
    showToast('No candidate ID linked to your account.', 'error');
    return;
  }

  // Hide setup, show loading state
  document.getElementById('cand-setup').style.display = 'none';
  document.getElementById('cand-messages').style.display = 'flex';
  document.getElementById('cand-input-area').style.display = 'none';
  
  // Show loading message
  const messagesEl = document.getElementById('cand-messages');
  messagesEl.innerHTML = `
    <div style="display: flex; align-items: center; justify-content: center; height: 100%; flex-direction: column; gap: 16px;">
      <div style="font-size: 3rem;">🤖</div>
      <div style="font-size: 1.2rem; font-weight: 600;">Starting your interview...</div>
      <div style="color: var(--text-2);">Please wait while we prepare your session</div>
    </div>
  `;

  try {
    const res = await fetch(`${API_BASE}/interview/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ candidate_id: currentUser.candidate_id }),
    });
    const data = await res.json();

    if (!res.ok) {
      showToast(data.detail || 'Failed to start interview.', 'error');
      // Show setup screen again on error
      document.getElementById('cand-setup').style.display = 'flex';
      document.getElementById('cand-messages').style.display = 'none';
      return;
    }

    sessionId = data.session_id;

    // Clear loading message and show chat
    messagesEl.innerHTML = '';
    document.getElementById('cand-input-area').style.display = 'flex';

    document.getElementById('chat-status').textContent = `Session #${sessionId} — Live`;
    const statusPill = document.getElementById('cand-status-pill');
    statusPill.textContent = 'Greeting';
    statusPill.className = 'status-pill pill-greeting';

    // Show first message
    addCandidateMsg('bot', data.bot_message);
    setCandidateInputEnabled(true, 'Say hello to get started…');
  } catch (err) {
    showToast('Connection error: ' + err.message, 'error');
    // Show setup screen again on error
    document.getElementById('cand-setup').style.display = 'flex';
    document.getElementById('cand-messages').style.display = 'none';
  }
}

async function startCandidateInterview() {
  // This function is now just a wrapper for autoStartInterview
  // Kept for backward compatibility if called from setup button
  autoStartInterview();
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
    const payload = { 
      session_id: sessionId, 
      answer 
    };
    
    // Add candidate_id for authorization if available
    if (currentUser && currentUser.candidate_id) {
      payload.candidate_id = currentUser.candidate_id;
    }
    
    const res = await fetch(`${API_BASE}/interview/respond`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
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

    window.currentCandidatesList = candidates;

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
          <button class="btn btn-sm" style="background:var(--bg-surface-3)" onclick="viewCandidateEvaluation(${c.id})">
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

window.viewCandidateEvaluation = function(cid) {
  const c = window.currentCandidatesList.find(x => x.id === cid);
  if (!c) return;
  const panel = document.getElementById('candidate-vis-panel');
  document.getElementById('vis-candidate-name').textContent = c.name;
  panel.style.display = 'block';

  const rbadge = document.getElementById('vis-report-badge');
  if (c.report_path) {
    rbadge.style.display = 'inline-block';
  } else {
    rbadge.style.display = 'none';
  }

  // Destroy previous charts to avoid canvas overlaps
  if (typeof window.botChartInstance !== 'undefined' && window.botChartInstance) { window.botChartInstance.destroy(); }
  if (typeof window.candChartInstance !== 'undefined' && window.candChartInstance) { window.candChartInstance.destroy(); }
  if (typeof window.sysChartInstance !== 'undefined' && window.sysChartInstance) { window.sysChartInstance.destroy(); }

  if (!c.eval_result) {
    document.getElementById('botMetricsChart').style.display = 'none';
    document.getElementById('candidateMetricsChart').style.display = 'none';
    document.getElementById('systemMetricsChart').style.display = 'none';
    document.getElementById('vis-full-report-content').style.display = 'none';
    return;
  }
  document.getElementById('botMetricsChart').style.display = 'block';
  document.getElementById('candidateMetricsChart').style.display = 'block';
  document.getElementById('systemMetricsChart').style.display = 'block';

  // --- Display Full Report Content ---
  document.getElementById('vis-full-report-content').style.display = 'block';
  
  if (c.eval_result.overall_analysis) {
    document.getElementById('vis-overall-summary').textContent = c.eval_result.overall_analysis;
  }
  
  // SHRM Summary as text
  const shrmChecks = c.eval_result.shrm_compliance_summary;
  const shrmSummaryEl = document.getElementById('vis-shrm-summary');
  if (shrmChecks) {
    const verdict = shrmChecks.overall_shrm_verdict || 'N/A';
    let verdictColor = verdict.includes('Fully') ? 'var(--primary)' : (verdict.includes('Partially') ? '#f59e0b' : 'var(--red)');
    let verdictIcon = verdict.includes('Fully') ? '✅' : (verdict.includes('Partially') ? '⚠️' : '❌');
    
    shrmSummaryEl.innerHTML = `
      <div style="background:var(--bg-surface-3); padding:16px; border-radius:8px; border-left: 4px solid ${verdictColor}">
        <div style="font-size: 1rem; font-weight: 600; margin-bottom: 8px; color: ${verdictColor}">
          ${verdictIcon} SHRM Compliance: ${verdict}
        </div>
        <div style="font-size: 0.9rem; color: var(--text-2); line-height: 1.5;">
          ${Object.entries(shrmChecks)
            .filter(([key]) => key !== 'overall_shrm_verdict')
            .map(([key, value]) => {
              let icon = value.includes('Non-Compliant') ? '❌' : (value.includes('Partially Compliant') ? '⚠️' : '✅');
              let niceKey = key.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
              return `<div style="margin-bottom: 6px;"><strong>${icon} ${niceKey}:</strong> ${escapeHtml(value)}</div>`;
            }).join('')}
        </div>
      </div>
    `;
  }

  const biasFlags = c.eval_result.bias_flags || [];
  const warnEl = document.getElementById('vis-bias-warnings');
  const warnList = document.getElementById('vis-bias-warnings-list');
  if (biasFlags.length > 0) {
    warnEl.style.display = 'block';
    warnList.innerHTML = biasFlags.map(f => `<li><strong>[${f.severity.toUpperCase()}] ${f.flag_type.replace('_', ' ')}:</strong> ${escapeHtml(f.description)} ${f.question_number ? '(Q' + f.question_number + ')' : ''}</li>`).join('');
  } else {
    warnEl.style.display = 'none';
    warnList.innerHTML = '';
  }

  window.currentActiveCandidate = c;
  renderCharts();
}

let chartTypes = {
  bot: 'bar',
  cand: 'pie',
  sys: 'line'
};

window.updateChartType = function(section, type) {
  chartTypes[section] = type;
  if (window.currentActiveCandidate) {
    renderCharts();
  }
};

function renderCharts() {
  const c = window.currentActiveCandidate;
  if (!c || !c.eval_result) return;
  
  if (typeof window.botChartInstance !== 'undefined' && window.botChartInstance) { window.botChartInstance.destroy(); }
  if (typeof window.candChartInstance !== 'undefined' && window.candChartInstance) { window.candChartInstance.destroy(); }
  if (typeof window.sysChartInstance !== 'undefined' && window.sysChartInstance) { window.sysChartInstance.destroy(); }

  const bm = c.eval_result.bot_metrics || {};
  const cm = c.eval_result.candidate_metrics || {};
  const sys = c.eval_result.system_evaluation || {};
  const graphData = c.eval_result.graph_data;
  
  const commonColors = [
    'rgba(108,99,255,0.6)', 'rgba(52,211,153,0.6)', 'rgba(245,158,11,0.6)',
    'rgba(239,68,68,0.6)', 'rgba(59,130,246,0.6)', 'rgba(147,51,234,0.6)', 'rgba(16,185,129,0.6)'
  ];

  function getBaseConfig(type, labels, data, defaultColor) {
    let bgColors = defaultColor;
    if (['pie', 'doughnut', 'polarArea'].includes(type)) {
      bgColors = commonColors.slice(0, data.length);
    }
    const config = {
      type: type,
      data: {
        labels: labels,
        datasets: [{
          label: 'Score',
          data: data,
          backgroundColor: bgColors,
          borderColor: bgColors,
          borderWidth: 1,
          fill: type === 'line' ? true : false,
          tension: 0.3
        }]
      },
      options: {}
    };
    if (['bar', 'line'].includes(type)) {
      config.options.scales = { y: { beginAtZero: true, max: 100 } };
    } else if (type === 'radar' || type === 'polarArea') {
      config.options.scales = { r: { beginAtZero: true, max: 100 } };
    }
    return config;
  }

  // 1. Bot Metrics Chart
  let bmVis = graphData ? graphData.bot_metrics : null;
  let bLabels = bmVis && bmVis.x_values ? bmVis.x_values : ['Question Quality', 'Adaptability', 'Topic Coverage', 'Consistency'];
  let bData = bmVis && bmVis.y_values ? bmVis.y_values : [bm.question_quality_score||0, bm.adaptability_score||0, bm.topic_coverage_score||0, bm.consistency_score||0];
  window.botChartInstance = new Chart(document.getElementById('botMetricsChart'), getBaseConfig(chartTypes.bot, bLabels, bData, 'rgba(108,99,255,0.6)'));

  // 2. Candidate Metrics Chart
  let cmVis = graphData ? graphData.candidate_metrics : null;
  let cLabels = cmVis && cmVis.x_values ? cmVis.x_values : ['Clarity', 'Relevance', 'Technical', 'Confidence', 'Engagement'];
  let cData = cmVis && cmVis.y_values ? cmVis.y_values : [cm.communication_clarity_score||0, cm.relevance_score||0, cm.technical_competency_score||0, cm.confidence_conviction_score||0, cm.engagement_depth_score||0];
  window.candChartInstance = new Chart(document.getElementById('candidateMetricsChart'), getBaseConfig(chartTypes.cand, cLabels, cData, 'rgba(52,211,153,0.6)'));

  // 3. System Metrics Chart
  let smVis = graphData ? graphData.system_evaluation : null;
  let sLabels = smVis && smVis.x_values ? smVis.x_values : ['Screening Accuracy', 'Interview Quality', 'Fairness/Transp.', 'Cand. Experience', 'Report Quality', 'Practicality'];
  let sData = smVis && smVis.y_values ? smVis.y_values : [sys.screening_accuracy_score||0, sys.interview_quality_score||0, sys.fairness_transparency_score||0, sys.candidate_experience_score||0, sys.report_quality_score||0, sys.practicality_score||0];
  window.sysChartInstance = new Chart(document.getElementById('systemMetricsChart'), getBaseConfig(chartTypes.sys, sLabels, sData, 'rgba(245,158,11,0.4)'));
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
