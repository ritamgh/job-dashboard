const state = { session: null, contacts: [], drafts: [] };

const els = {
  website: document.querySelector('#website'),
  company: document.querySelector('#company'),
  sessionBadge: document.querySelector('#sessionBadge'),
  createSession: document.querySelector('#createSession'),
  researchCompany: document.querySelector('#researchCompany'),
  findContacts: document.querySelector('#findContacts'),
  generateDrafts: document.querySelector('#generateDrafts'),
  newSession: document.querySelector('#newSession'),
  researchSummary: document.querySelector('#researchSummary'),
  contacts: document.querySelector('#contacts'),
  drafts: document.querySelector('#drafts'),
  manualRecipient: document.querySelector('#manualRecipient'),
  toast: document.querySelector('#toast'),
};

function esc(s){ return String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
function toast(message){ els.toast.textContent = message; els.toast.classList.add('show'); setTimeout(()=>els.toast.classList.remove('show'), 3500); }
function setBusy(button, busy){ button.disabled = busy; button.dataset.originalText ||= button.textContent; button.textContent = busy ? 'Working…' : button.dataset.originalText; }

async function request(path, options = {}){
  const res = await fetch(path, {
    ...options,
    headers: {'Content-Type': 'application/json', ...(options.headers || {})},
  });
  const text = await res.text();
  const data = text ? JSON.parse(text) : null;
  if (!res.ok) throw new Error(data?.detail || `Request failed: ${res.status}`);
  return data;
}

function updateButtons(){
  const hasSession = Boolean(state.session?.id);
  els.researchCompany.disabled = !hasSession;
  els.findContacts.disabled = !hasSession;
  els.generateDrafts.disabled = !hasSession;
  els.sessionBadge.textContent = hasSession ? `Session #${state.session.id} · ${state.session.status}` : 'No session';
}

function renderResearch(){
  const r = state.session?.research;
  if (!r) {
    els.researchSummary.className = 'empty-state';
    els.researchSummary.textContent = state.session ? 'No research yet. Click Research company.' : 'Create a session, then research the company.';
    return;
  }
  els.researchSummary.className = 'research-grid';
  els.researchSummary.innerHTML = `
    <div class="metric"><strong>${esc(r.ai_native_score)}/10</strong><span>AI native</span></div>
    <div class="metric"><strong>${esc(r.resume_fit_score)}/10</strong><span>Resume fit</span></div>
    <div class="metric"><strong>${esc(r.hiring_status)}</strong><span>Hiring</span></div>
    <div class="metric"><strong>${esc(r.research_confidence)}/10</strong><span>Confidence</span></div>
    <div class="summary-block">
      <h3>${esc(state.session.company || state.session.website)}</h3>
      <p>${esc(r.product_summary || 'No summary available.')}</p>
      <p><strong>Hiring evidence:</strong> ${esc(r.hiring_evidence || 'No hiring evidence yet.')}</p>
      <p><strong>Remote/India fit:</strong> ${esc(r.remote_india_fit || 'Unknown')}</p>
      <div>${(r.tags || []).map(t => `<span class="pill">${esc(t)}</span>`).join('')}</div>
      ${(r.evidence_urls || []).map(u => `<div><a href="${esc(u)}" target="_blank" rel="noreferrer">${esc(u)}</a></div>`).join('')}
    </div>`;
}

function renderContacts(){
  if (!state.contacts.length) {
    els.contacts.className = 'empty-state';
    els.contacts.textContent = 'No contacts found yet. Use Serper or type a recipient manually.';
    return;
  }
  els.contacts.className = 'contact-list';
  els.contacts.innerHTML = state.contacts.map(c => `
    <label class="contact-option">
      <input type="radio" name="contact" value="${esc(c.email || '')}" ${c.email ? '' : 'disabled'} />
      <span>
        <strong>${esc(c.email || c.linkedin_url || 'Contact candidate')}</strong>
        <small>${esc(c.name || '')} ${esc(c.role || '')} · confidence ${esc(c.confidence || 0)}/100</small>
        ${c.source_url ? `<a href="${esc(c.source_url)}" target="_blank" rel="noreferrer">source ↗</a>` : ''}
        ${c.source_snippet ? `<em>${esc(c.source_snippet)}</em>` : ''}
      </span>
    </label>`).join('');
}

function selectedRecipient(){
  const selected = document.querySelector('input[name="contact"]:checked');
  return els.manualRecipient.value.trim() || selected?.value || '';
}

function draftText(draft, key){
  return draft[`edited_${key}`] ?? draft[key] ?? '';
}

function renderDrafts(){
  if (!state.drafts.length) {
    els.drafts.className = 'empty-state';
    els.drafts.textContent = 'Generate drafts after research. Cold email, LinkedIn DM, and follow-up will appear here.';
    return;
  }
  els.drafts.className = 'draft-list';
  els.drafts.innerHTML = state.drafts.map(d => `
    <article class="draft" data-draft-id="${esc(d.id)}">
      <div class="section-heading compact">
        <h3>${esc(d.channel)}</h3>
        <span class="pill ${esc(d.send_status)}">${esc(d.send_status)}</span>
      </div>
      ${d.channel === 'email' || d.subject ? `<label>Subject<input data-field="subject" value="${esc(draftText(d, 'subject'))}" /></label>` : ''}
      <label>Body<textarea data-field="body" rows="${d.channel === 'linkedin' ? 7 : 12}">${esc(draftText(d, 'body'))}</textarea></label>
      <div class="actions">
        <button class="button secondary" data-action="save">Save edits</button>
        ${d.channel === 'email' ? '<button class="button" data-action="send">Send email</button>' : '<button class="button secondary" data-action="copy">Copy</button>'}
      </div>
      ${d.last_error ? `<p class="error">${esc(d.last_error)}</p>` : ''}
    </article>`).join('');
}

function render(){
  updateButtons();
  renderResearch();
  renderContacts();
  renderDrafts();
}

async function refreshSession(){
  if (!state.session?.id) return;
  const session = await request(`/api/outreach/sessions/${state.session.id}`);
  state.session = session;
  state.contacts = session.contacts || [];
  state.drafts = session.drafts || [];
  els.website.value = session.website || '';
  els.company.value = session.company || '';
  render();
}

async function loadSessionFromQuery(){
  const sessionId = new URLSearchParams(window.location.search).get('session');
  if (!sessionId) return;
  try {
    state.session = {id: Number(sessionId)};
    await refreshSession();
    toast('Loaded dashboard email draft. Review/edit before sending.');
  } catch (err) { toast(err.message); }
}

els.createSession.addEventListener('click', async () => {
  const website = els.website.value.trim();
  if (!website) return toast('Website URL is required.');
  setBusy(els.createSession, true);
  try {
    state.session = await request('/api/outreach/sessions', {method: 'POST', body: JSON.stringify({website, company: els.company.value.trim() || null})});
    state.contacts = [];
    state.drafts = [];
    toast('Outreach session created.');
    render();
  } catch (err) { toast(err.message); }
  finally { setBusy(els.createSession, false); }
});

els.researchCompany.addEventListener('click', async () => {
  setBusy(els.researchCompany, true);
  try {
    state.session = await request(`/api/outreach/sessions/${state.session.id}/research`, {method: 'POST'});
    toast('Company research complete.');
    await refreshSession();
  } catch (err) { toast(err.message); }
  finally { setBusy(els.researchCompany, false); }
});

els.findContacts.addEventListener('click', async () => {
  setBusy(els.findContacts, true);
  try {
    state.contacts = await request(`/api/outreach/sessions/${state.session.id}/contacts`, {method: 'POST'});
    toast(state.contacts.length ? 'Contact candidates updated.' : 'No contacts found. Add one manually.');
    renderContacts();
  } catch (err) { toast(err.message); }
  finally { setBusy(els.findContacts, false); }
});

els.generateDrafts.addEventListener('click', async () => {
  setBusy(els.generateDrafts, true);
  try {
    state.drafts = await request(`/api/outreach/sessions/${state.session.id}/drafts`, {method: 'POST'});
    toast('Draft pack generated. Review and edit before sending.');
    renderDrafts();
  } catch (err) { toast(err.message); }
  finally { setBusy(els.generateDrafts, false); }
});

els.newSession.addEventListener('click', () => {
  state.session = null; state.contacts = []; state.drafts = [];
  els.website.value = ''; els.company.value = ''; els.manualRecipient.value = '';
  render();
});

els.drafts.addEventListener('click', async (event) => {
  const button = event.target.closest('button[data-action]');
  if (!button) return;
  const card = button.closest('.draft');
  const draftId = Number(card.dataset.draftId);
  const draft = state.drafts.find(d => Number(d.id) === draftId);
  const subject = card.querySelector('[data-field="subject"]')?.value || null;
  const body = card.querySelector('[data-field="body"]')?.value || '';
  const action = button.dataset.action;
  setBusy(button, true);
  try {
    if (action === 'copy') {
      await navigator.clipboard.writeText(body);
      toast('Copied draft.');
    } else if (action === 'save') {
      await request(`/api/outreach/drafts/${draftId}`, {method: 'PATCH', body: JSON.stringify({edited_subject: subject, edited_body: body})});
      toast('Draft saved.');
      await refreshSession();
    } else if (action === 'send') {
      const to = selectedRecipient();
      if (!to) throw new Error('Select or type a recipient email before sending.');
      const ok = window.confirm(`Send this email to ${to}? This uses the edited text currently shown.`);
      if (!ok) return;
      await request(`/api/outreach/drafts/${draftId}`, {method: 'PATCH', body: JSON.stringify({edited_subject: subject, edited_body: body})});
      const result = await request(`/api/outreach/drafts/${draftId}/send`, {method: 'POST', body: JSON.stringify({to, subject, body, confirm_send: true})});
      toast(result.sent ? 'Email sent.' : (result.error || 'Send failed.'));
      await refreshSession();
    }
  } catch (err) { toast(err.message); }
  finally { setBusy(button, false); }
});

render();
loadSessionFromQuery();
