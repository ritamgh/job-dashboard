const rowsEl = document.querySelector('#rows');
const statsEl = document.querySelector('#stats');
const toastEl = document.querySelector('#toast');
const queryEl = document.querySelector('#query');
const hiringFilterEl = document.querySelector('#hiringFilter');
const minAiEl = document.querySelector('#minAi');
const queueStatusEl = document.querySelector('#queueStatus');
let startups = [];
let sortKey = 'overall_score';
let sortDir = -1;
let latestRunId = null;
const messageStyles = JSON.parse(localStorage.getItem('messageStyles') || '{}');

function toast(message){ toastEl.textContent = message; toastEl.classList.add('show'); setTimeout(()=>toastEl.classList.remove('show'), 3500); }
function esc(s){ return String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
function hiringClass(s){ return String(s || '').toLowerCase(); }
function bestHiringUrl(s){
  const urls = s.evidence_urls || [];
  return urls.find(u => /careers|jobs|join-us|join/i.test(u)) || (s.hiring_status === 'Yes' ? urls[0] : '');
}
function preferredMessage(s){
  const selected = messageStyles[s.id];
  if (selected === 'short') return s.message_short || s.message_founder || '';
  if (selected === 'founder') return s.message_founder || s.message_short || '';
  return s.message_founder || s.message_short || '';
}
function founderLinkedIn(s){
  return s.founder_linkedin || s.raw?.['Founder LinkedIn'] || s.raw?.['Founder Linkedin'] || s.raw?.['Founders LinkedIn'] || s.raw?.['Founders Linkedin'] || s.raw?.Linkedin || s.raw?.LinkedIn || '';
}
function hiringEvidenceHtml(s){
  const url = bestHiringUrl(s);
  return `
    <span class="pill ${hiringClass(s.hiring_status)}">${esc(s.hiring_status)}</span>
    <br><small>${esc(s.hiring_evidence || '')}</small>
    ${url ? `<br><a class="evidence-link" href="${esc(url)}" target="_blank" rel="noreferrer">hiring evidence ↗</a>` : ''}
  `;
}

async function load(){
  const q = queryEl.value.trim();
  const res = await fetch(`/api/startups?limit=5000${q ? `&q=${encodeURIComponent(q)}` : ''}`);
  startups = await res.json();
  render();
  await loadQueueStatus();
}

function renderQueue(run){
  if (!run || !run.id) {
    queueStatusEl.textContent = 'No research run yet.';
    return;
  }
  latestRunId = run.id;
  const done = Number(run.completed || 0) + Number(run.failed || 0) + Number(run.needs_browser || 0);
  const total = Number(run.total || 0);
  const pct = total ? Math.round((done / total) * 100) : 0;
  queueStatusEl.innerHTML = `
    <strong>Run #${esc(run.id)}</strong> · ${esc(run.status)} · ${done}/${total} (${pct}%)
    <br><small>${esc(run.pending || 0)} pending · ${esc(run.running || 0)} running · ${esc(run.completed || 0)} completed · ${esc(run.failed || 0)} failed · ${esc(run.needs_browser || 0)} need browser fallback</small>
  `;
}

async function loadQueueStatus(){
  const res = await fetch('/api/research-runs/latest');
  if (!res.ok) return;
  renderQueue(await res.json());
}

function renderStats(){
  const total = startups.length;
  const researched = startups.filter(s => s.research_confidence > 0).length;
  const yes = startups.filter(s => s.hiring_status === 'Yes').length;
  const aiStrong = startups.filter(s => s.ai_native_score >= 7).length;
  statsEl.innerHTML = [
    ['Companies', total], ['Researched', researched], ['Active hiring', yes], ['Strong AI-native', aiStrong]
  ].map(([label, value]) => `<div class="stat"><strong>${value}</strong><span>${label}</span></div>`).join('');
}

function visibleStartups(){
  const hiring = hiringFilterEl.value;
  const minAi = Number(minAiEl.value || 0);
  return startups
    .filter(s => !hiring || s.hiring_status === hiring)
    .filter(s => Number(s.ai_native_score || 0) >= minAi)
    .sort((a,b) => {
      const av = a[sortKey] ?? '';
      const bv = b[sortKey] ?? '';
      if (typeof av === 'number' && typeof bv === 'number') return (av - bv) * sortDir;
      return String(av).localeCompare(String(bv)) * sortDir;
    });
}

function sortBy(key){
  if (sortKey === key) sortDir *= -1;
  else { sortKey = key; sortDir = key === 'company' ? 1 : -1; }
  render();
}

function render(){
  renderStats();
  const visible = visibleStartups();
  if (!visible.length) {
    rowsEl.innerHTML = '<tr><td colspan="9" class="empty">No companies match the current filters. Try lowering the AI score or clearing search.</td></tr>';
    return;
  }
  rowsEl.innerHTML = visible.map(s => `
    <tr>
      <td class="company"><strong>${esc(s.company)}</strong><br>${s.website ? `<a href="${esc(s.website)}" target="_blank" rel="noreferrer">website</a>` : ''} ${s.linkedin ? `<a href="${esc(s.linkedin)}" target="_blank" rel="noreferrer">linkedin</a>` : ''}</td>
      <td>${founderLinkedIn(s) ? `<a href="${esc(founderLinkedIn(s))}" target="_blank" rel="noreferrer">founder ↗</a>` : '<span class="subtle">—</span>'}</td>
      <td><span class="score">${esc(s.overall_score)}</span></td>
      <td>${esc(s.ai_native_score)}/10<br><small>${(s.tags || []).includes('Website-confirmed AI-native') ? 'website confirmed' : (Number(s.ai_native_score || 0) > 0 ? 'needs website confirmation' : 'no signal yet')}</small></td>
      <td>${esc(s.resume_fit_score)}/10</td>
      <td>${hiringEvidenceHtml(s)}</td>
      <td>${esc(s.research_confidence)}/10</td>
      <td class="summary">${esc(s.product_summary || 'Not researched yet.')}<div>${(s.tags || []).map(t => `<span class="pill">${esc(t)}</span>`).join('')}</div>${(s.evidence_urls || []).slice(0,3).map(u => `<div><a href="${esc(u)}" target="_blank" rel="noreferrer">${esc(u)}</a></div>`).join('')}</td>
      <td>
        <button class="button secondary" onclick="researchOne(${s.id})">Research</button>
        <button class="button secondary" onclick="message(${s.id}, 'short')">Short</button>
        <button class="button secondary" onclick="message(${s.id}, 'founder')">Founder DM</button>
        <button class="button" onclick="message(${s.id}, 'founder', true)" title="Ignore cached text and generate a fresh founder DM">Regenerate Founder</button>
        <div id="msg-${s.id}" class="message-box">${esc(preferredMessage(s))}</div>
      </td>
    </tr>`).join('');
}

async function researchOne(id){
  const button = event?.target;
  if (button) button.disabled = true;
  toast('Researching company...');
  await fetch(`/api/startups/${id}/research`, {method:'POST'});
  await load();
  toast('Research complete');
}

async function message(id, style, force=false){
  const button = event?.target;
  if (button) button.disabled = true;
  messageStyles[id] = style;
  localStorage.setItem('messageStyles', JSON.stringify(messageStyles));
  toast(`${force ? 'Regenerating' : 'Generating'} ${style} message...`);
  const res = await fetch(`/api/startups/${id}/message`, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({style, force})});
  const data = await res.json();
  document.querySelector(`#msg-${id}`).textContent = data.message;
  await navigator.clipboard?.writeText(data.message).catch(()=>{});
  toast(data.cached ? 'Copied cached message' : 'Generated fresh message and copied it');
  await load();
}

async function importSheet(){
  document.querySelector('#importSheet').disabled = true;
  const url = document.querySelector('#sheetUrl').value.trim();
  toast('Scraping rendered sheet. This can take a while for 1.5k rows...');
  const res = await fetch('/api/import/google-sheet', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({url, max_scrolls: 160})});
  const data = await res.json();
  toast(`Imported ${data.imported} rows`);
  document.querySelector('#importSheet').disabled = false;
  await load();
}

async function importCsv(file){
  const form = new FormData();
  form.append('file', file);
  const res = await fetch('/api/import/csv', {method:'POST', body: form});
  const data = await res.json();
  toast(`Imported ${data.imported} CSV rows`);
  await load();
}

async function researchBatch(){
  const res = await fetch('/api/research-runs', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({limit:100, only_unresearched:true, max_confidence:6, start_worker:true})});
  const data = await res.json();
  renderQueue(data.run);
  toast(`Queued Scrapy research run #${data.run.id} for ${data.run.total} companies.`);
}

async function researchAll(){
  const button = event?.target;
  if (button) button.disabled = true;
  const res = await fetch('/api/research-runs', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({limit:5000, only_unresearched:true, max_confidence:6, start_worker:true})});
  const data = await res.json();
  renderQueue(data.run);
  toast(`Queued Scrapy research run #${data.run.id} for ${data.run.total} companies.`);
  if (button) button.disabled = false;
}

async function cancelRun(){
  if (!latestRunId) return toast('No run to cancel.');
  const res = await fetch(`/api/research-runs/${latestRunId}/cancel`, {method:'POST'});
  if (res.ok) renderQueue(await res.json());
  toast('Marked pending/running jobs as skipped.');
}

document.querySelector('#refresh').addEventListener('click', load);
document.querySelector('#importSheet').addEventListener('click', importSheet);
document.querySelector('#research').addEventListener('click', researchBatch);
document.querySelector('#researchAll').addEventListener('click', researchAll);
document.querySelector('#cancelRun').addEventListener('click', cancelRun);
document.querySelector('#csvFile').addEventListener('change', e => e.target.files[0] && importCsv(e.target.files[0]));
queryEl.addEventListener('input', () => { clearTimeout(window.__q); window.__q = setTimeout(load, 250); });
hiringFilterEl.addEventListener('change', render);
minAiEl.addEventListener('input', render);
window.sortBy = sortBy;
load();
setInterval(loadQueueStatus, 5000);
