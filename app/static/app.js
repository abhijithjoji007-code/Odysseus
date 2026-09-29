const $ = (id) => document.getElementById(id);
const chat = $('chat');
const input = $('commandInput');
const form = $('commandForm');
const orb = $('voiceOrb');
let speakEnabled = true;
let missionPoll = null;
let lastMissionPrompt = '';
const sessionId = (() => {
  const existing = sessionStorage.getItem('odysseusSessionId');
  if (existing) return existing;
  const created = crypto.randomUUID().replaceAll('-', '');
  sessionStorage.setItem('odysseusSessionId', created);
  return created;
})();

function addMessage(role, text) {
  const box = document.createElement('div');
  box.className = `message ${role}`;
  box.innerHTML = `<b>${role === 'user' ? 'YOU' : 'ODYSSEUS'}</b><p></p>`;
  box.querySelector('p').textContent = text;
  chat.appendChild(box);
  chat.scrollTop = chat.scrollHeight;
}

function renderMission(mission) {
  if (!mission) return;
  $('missionEmpty').classList.add('hidden');
  $('missionView').classList.remove('hidden');
  $('missionTitle').textContent = mission.title;
  $('missionObjective').textContent = mission.objective;
  $('missionProgress').textContent = `${mission.progress}%`;
  $('progressBar').style.width = `${mission.progress}%`;
  $('missionSteps').innerHTML = '';
  mission.steps.forEach((step) => {
    const row = document.createElement('div');
    row.className = `step ${step.status}`;
    const label = step.agent ? `${step.agent} — ${step.title}` : step.title;
    const detail = step.detail || step.error || (step.tool ? `Secure tool: ${step.tool}` : '');
    row.innerHTML = `<span class="step-icon">${step.status === 'completed' ? '✓' : '•'}</span><div><b>${label}</b><small>${detail}</small></div>`;
    $('missionSteps').appendChild(row);
  });
}

function watchMission(id) {
  if (missionPoll) clearInterval(missionPoll);
  const refresh = async () => {
    try {
      const response = await fetch(`/api/missions/${id}?session_id=${sessionId}`);
      if (!response.ok) throw new Error(`status check returned ${response.status}`);
      const mission = await response.json();
      if (mission.error) throw new Error(mission.error);
      renderMission(mission);
      if (mission.prompt && mission.prompt !== lastMissionPrompt) { addMessage('assistant', mission.prompt); lastMissionPrompt = mission.prompt; }
      if (['completed','failed','cancelled'].includes(mission.status)) {
        clearInterval(missionPoll); missionPoll = null;
        addMessage('assistant', mission.final_report || `Mission ${mission.status}. Check the mission steps for details.`);
      }
    } catch (error) {
      clearInterval(missionPoll); missionPoll = null;
      addMessage('assistant', `Mission status could not be updated: ${error.message}.`);
    }
  };
  refresh(); missionPoll = setInterval(refresh, 800);
}

function speak(text) {
  if (!speakEnabled || !('speechSynthesis' in window)) return;
  speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text.replace(/[#*]/g, ' ').slice(0, 1200));
  utterance.rate = 1.02;
  speechSynthesis.speak(utterance);
}

async function execute(message) {
  const clean = message.trim();
  if (!clean) return;
  addMessage('user', clean);
  input.value = '';
  input.disabled = true;
  try {
    const response = await fetch('/api/assistant', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({message:clean, session_id:sessionId})});
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Request failed');
    addMessage('assistant', data.reply);
    renderMission(data.mission);
    if (data.data?.mission_id && data.action.startsWith('mission')) watchMission(data.data.mission_id);
    speak(data.reply);
  } catch (error) {
    addMessage('assistant', `Request failed: ${error.message}`);
  } finally {
    input.disabled = false;
    input.focus();
  }
}

form.addEventListener('submit', (event) => { event.preventDefault(); execute(input.value); });
document.querySelectorAll('[data-command]').forEach((button) => button.addEventListener('click', () => execute(button.dataset.command)));

async function refreshHealth() {
  try {
    const data = await fetch('/api/health').then(r => r.json());
    $('aiStatus').textContent = data.ai.ready ? 'Gemini ready' : (data.ai.configured ? 'Gemini needs attention' : 'Local mode');
    $('aiModel').textContent = data.ai.model || data.ai.message;
    $('aiDot').classList.toggle('ready', data.ai.ready);
  } catch { $('aiStatus').textContent = 'Offline'; }
}

async function refreshSystem() {
  try {
    const data = await fetch('/api/system').then(r => r.json());
    [['cpu',data.cpu_percent],['ram',data.ram_percent],['disk',data.disk_percent],['battery',data.battery_percent]].forEach(([name,value]) => {
      const unavailable = value === null || value === undefined || value < 0;
      const display = unavailable ? '--' : `${Math.round(value)}%`;
      $(name).textContent = display;
      $(`${name}Bar`).style.width = unavailable ? '0%' : `${Math.min(100,value)}%`;
    });
  } catch {}
}

$('diagnostics').addEventListener('click', async () => {
  $('diagnostics').disabled = true;
  try {
    const data = await fetch('/api/ai/test', {method:'POST'}).then(r => r.json());
    addMessage('assistant', data.message);
    refreshHealth();
  } finally { $('diagnostics').disabled = false; }
});

const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
if (SpeechRecognition) {
  const recognition = new SpeechRecognition();
  recognition.lang = 'en-IN';
  recognition.interimResults = false;
  recognition.onstart = () => { orb.classList.add('listening'); $('voiceState').textContent = 'Listening…'; };
  recognition.onend = () => { orb.classList.remove('listening'); $('voiceState').textContent = 'Ready'; };
  recognition.onerror = (e) => addMessage('assistant', `Voice input error: ${e.error}`);
  recognition.onresult = (e) => execute(e.results[0][0].transcript);
  orb.addEventListener('click', () => recognition.start());
} else {
  orb.addEventListener('click', () => addMessage('assistant', 'Voice recognition is not supported in this browser. Use Chrome or type the command.'));
}

function tick(){ $('clock').textContent = new Date().toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'}); }
tick(); setInterval(tick,1000); refreshHealth(); refreshSystem(); setInterval(refreshSystem,4000);
