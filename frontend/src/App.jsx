import { useEffect, useRef, useState } from 'react';
import { ArrowDownToLine, ArrowRight, BookOpen, Check, CheckCircle2, ChevronRight, CircleHelp,
  Clock3, Coins, FileText, FolderOpen, Leaf, LoaderCircle, LogOut, Network, Plus, Search,
  ShieldCheck, Sparkles, Sprout, Trash2, UploadCloud, X } from 'lucide-react';
import { api, download, hasToken, setToken, requestId } from './api';

const TYPES = [
  { id: 'mcq', label: 'Multiple choice', short: 'MCQ', hint: 'One answer, four options' },
  { id: 'fib', label: 'Fill in the blank', short: 'FIB', hint: 'Recall the missing concept' },
  { id: 'short', label: 'Short answer', short: 'Short answer', hint: 'A focused knowledge check' },
  { id: 'long', label: 'Long answer', short: 'Long answer', hint: 'Connect three or more facts' },
];
const SAMPLE = `Photosynthesis is the process by which plants convert light energy into chemical energy.
Chlorophyll is the green pigment that absorbs light energy in plants.
Chloroplasts are organelles that carry out photosynthesis in plant cells.
Mitochondria are organelles that release energy through cellular respiration.
Ribosomes are structures that synthesize proteins inside cells.
Vacuoles are compartments that store water and nutrients in plant cells.
Photosynthesis requires sunlight, water, and carbon dioxide.
Photosynthesis produces glucose and oxygen.
Photosynthesis occurs in the chloroplasts of plant cells.
The cell membrane is the barrier that regulates movement of substances into and out of cells.
The nucleus is the organelle that contains the genetic material of a cell.
The cell wall is the rigid outer layer that supports and protects plant cells.`;

function Spinner() { return <LoaderCircle size={18} className="spin" aria-hidden="true" />; }

function Graph({ graph }) {
  if (!graph.nodes.length) return <div className="empty"><Network /><h3>No relationships found yet</h3><p>Use clear English statements, such as “Photosynthesis produces glucose and oxygen.”</p></div>;
  const nodes = graph.nodes.slice(0, 24);
  const positions = Object.fromEntries(nodes.map((node, i) => {
    const angle = (i / nodes.length) * Math.PI * 2;
    return [node.id, { x: 350 + Math.cos(angle) * 240, y: 240 + Math.sin(angle) * 170 }];
  }));
  return <div className="graph-wrap"><svg viewBox="0 0 700 480" role="img" aria-label={`Knowledge graph with ${graph.nodes.length} concepts and ${graph.edges.length} relationships`}>
    {graph.edges.filter(e => positions[e.source] && positions[e.target]).map((e, i) => <g key={i}>
      <line x1={positions[e.source].x} y1={positions[e.source].y} x2={positions[e.target].x} y2={positions[e.target].y} stroke="#c6d5c8" strokeWidth="1.5" />
      <title>{`${e.source} ${e.relation} ${e.target}`}</title>
    </g>)}
    {nodes.map(n => <g key={n.id} transform={`translate(${positions[n.id].x},${positions[n.id].y})`}>
      <circle r={n.role === 'concept' ? 13 : 7} fill={n.role === 'concept' ? '#285c46' : '#a6bd87'} stroke="white" strokeWidth="3" />
      <text y={28} textAnchor="middle" fill="#415847" fontSize="10">{n.label.length > 28 ? n.label.slice(0, 26) + '…' : n.label}</text><title>{n.label}</title>
    </g>)}
  </svg><p className="muted small">Showing {nodes.length} of {graph.nodes.length} nodes. Every relationship comes from your source.</p>
  <div className="relation-list">{graph.edges.slice(0, 12).map((e, i) => <div key={i}><span>{graph.nodes.find(n => n.id === e.source)?.label}</span><b>{e.relation}</b><span>{graph.nodes.find(n => n.id === e.target)?.label}</span></div>)}</div></div>;
}

function QuestionCard({ question, index, showAnswers }) {
  return <article className="question-card"><div className="question-heading"><span className="question-number">{String(index + 1).padStart(2, '0')}</span><span className="tag">{TYPES.find(t => t.id === question.kind)?.short}</span><span className="grounded"><ShieldCheck size={13} /> Source linked</span></div>
    <h3>{question.prompt}</h3>
    {question.options.length > 0 && <div className="options">{question.options.map((option, i) => <div className={showAnswers && option === question.answer ? 'correct' : ''} key={option}><span>{String.fromCharCode(65 + i)}</span>{option}{showAnswers && option === question.answer && <Check size={16} />}</div>)}</div>}
    {showAnswers && <div className="answer"><b>Answer</b><p>{question.answer}</p></div>}
    <details><summary>View source evidence</summary><blockquote>{question.evidence.join('\n\n')}</blockquote></details>
  </article>;
}

export default function App() {
  const [config, setConfig] = useState(null), [user, setUser] = useState(null);
  const [sessions, setSessions] = useState([]), [active, setActive] = useState(null);
  const [view, setView] = useState('create'), [sourceMode, setSourceMode] = useState('text');
  const [title, setTitle] = useState(''), [text, setText] = useState(''), [file, setFile] = useState(null);
  const [kinds, setKinds] = useState(['mcq', 'fib', 'short']), [count, setCount] = useState(10);
  const [busy, setBusy] = useState(''), [error, setError] = useState(''), [notice, setNotice] = useState('');
  const [modal, setModal] = useState(null), [resultTab, setResultTab] = useState('questions');
  const [showAnswers, setShowAnswers] = useState(true), [search, setSearch] = useState('');
  const [ledger, setLedger] = useState([]), [deleteTarget, setDeleteTarget] = useState(null);
  const [checkoutDone, setCheckoutDone] = useState(false);
  const purchaseId = useRef(null), generationId = useRef(null);
  const [authMode, setAuthMode] = useState('signin');
  const [authEmail, setAuthEmail] = useState(''), [authPassword, setAuthPassword] = useState(''), [authName, setAuthName] = useState('');
  const cost = active ? (active.kind === 'text' ? 1 : 2) : (sourceMode === 'text' ? 1 : 2);

  async function refresh() {
    const [profile, list] = await Promise.all([api('/me'), api('/sessions')]);
    setUser(profile); setSessions(list);
  }
  useEffect(() => {
    api('/config').then(setConfig).catch(() => setError('Cannot connect to the API. Start the backend on port 8000 and reload.'));
    if (hasToken()) refresh().catch(e => setError(e.message));
    const signout = () => { setUser(null); setSessions([]); setActive(null); setLedger([]); setText(''); setTitle(''); setFile(null); setView('create'); };
    window.addEventListener('qg-signout', signout);
    return () => window.removeEventListener('qg-signout', signout);
  }, []);

  useEffect(() => {
    if (!modal && !deleteTarget) return;
    const previous = document.activeElement;
    const dialog = document.querySelector('[role="dialog"]');
    const focusables = () => [...dialog.querySelectorAll('button, a, input, [tabindex="0"]')].filter(e => !e.disabled);
    focusables()[0]?.focus();
    const trap = e => {
      if (e.key === 'Escape' && !busy) { setModal(null); setDeleteTarget(null); }
      if (e.key === 'Tab') {
        const items = focusables(), first = items[0], last = items.at(-1);
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last?.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first?.focus(); }
      }
    };
    document.addEventListener('keydown', trap);
    return () => { document.removeEventListener('keydown', trap); previous?.focus(); };
  }, [modal, deleteTarget, busy]);

  async function run(label, action) {
    setBusy(label); setError(''); setNotice('');
    try { await action(); } catch (e) { setError(e.message); } finally { setBusy(''); }
  }
  function newSession() { if (busy) return; setActive(null); setView('create'); setText(''); setTitle(''); setFile(null); setNotice(''); generationId.current = null; }
  async function openSession(id) { await run('open', async () => { setActive(await api(`/sessions/${id}`)); setView('create'); setResultTab('questions'); generationId.current = null; }); }
  async function generate() {
    if (!user) { setModal('login'); return; }
    if (!kinds.length) { setError('Choose at least one question format.'); return; }
    if (!Number.isInteger(Number(count)) || count < 1 || count > 50) { setError('Choose between 1 and 50 questions.'); return; }
    await run('generate', async () => {
      let source = active;
      if (!source) {
        if (sourceMode === 'text') {
          if (text.trim().length < 20) throw new Error('Add at least 20 characters of source text.');
          source = await api('/sessions', { method: 'POST', body: { title: title.trim() || 'Untitled study session', text } });
        } else {
          if (!file) throw new Error('Choose a PDF or Word (.docx) document first.');
          const form = new FormData(); form.append('file', file);
          source = await api('/sessions/upload', { method: 'POST', body: form });
        }
        setActive(source);
      }
      const signature = JSON.stringify([source.id, Number(count), kinds]);
      if (generationId.current?.signature !== signature) generationId.current = { signature, id: requestId() };
      const result = await api(`/sessions/${source.id}/generate`, { method: 'POST', body: { count: Number(count), kinds, request_id: generationId.current.id } });
      generationId.current = null;
      setActive(await api(`/sessions/${source.id}`)); setResultTab('questions');
      await refresh(); setNotice(result.message);
    });
  }
  async function checkout() {
    await run('checkout', async () => {
      purchaseId.current ||= requestId();
      const result = await api('/credits/demo-purchase', { method: 'POST', body: { request_id: purchaseId.current } });
      await new Promise(resolve => setTimeout(resolve, 900));
      await refresh(); setLedger(await api('/ledger')); setNotice(result.message); setCheckoutDone(true); purchaseId.current = null;
    });
  }
  async function exportQuestions(answers) { await run('export', () => download(`/sessions/${active.id}/export?answers=${answers}`, answers ? 'questions-and-answers.pdf' : 'questions.pdf')); }

  return <div className="app-shell">
    <aside className="sidebar">
      <a className="brand" href="#" onClick={e => { e.preventDefault(); newSession(); }}><span className="brand-icon"><Sprout size={25} /></span><span>question<span className="brand-light">garden</span><small>GROW WHAT YOU KNOW</small></span></a>
      <button className="new-button" onClick={newSession} disabled={!!busy}><Plus size={18} /> New question set</button>
      <div className="nav-label">WORKSPACE</div>
      <nav aria-label="Main navigation"><button className={view === 'create' ? 'selected' : ''} onClick={() => setView('create')}><Sparkles size={18} /> Question studio</button><button className={view === 'sessions' ? 'selected' : ''} onClick={() => setView('sessions')}><FolderOpen size={18} /> My sessions <span className="count">{sessions.length}</span></button><button className={view === 'credits' ? 'selected' : ''} onClick={() => { setView('credits'); if (user) run('ledger', async () => setLedger(await api('/ledger'))); }}><Coins size={18} /> Credits & activity</button></nav>
      <div className="nav-label recent-label">RECENT SESSIONS</div>
      <div className="recent-list">{sessions.slice(0, 5).map(s => <button key={s.id} onClick={() => openSession(s.id)} disabled={!!busy}><FileText size={15} /><span>{s.title}</span></button>)}{!sessions.length && <p>Your ideas will take root here.</p>}</div>
      <div className="sidebar-bottom"><div className="credit-card"><div><span className="tiny-leaf"><Leaf size={16} /></span><b>{user ? user.total_credits.toLocaleString() : '100'} <small>credits {user ? 'available' : 'every day'}</small></b></div><div className="credit-track"><span style={{ width: `${user ? user.free_credits : 100}%` }} /></div><p>{user ? `${user.free_credits} daily · ${user.paid_credits} purchased` : 'A little learning goes a long way.'}</p><button onClick={() => { setCheckoutDone(false); setModal(user ? 'credits' : 'login'); }}>Get more credits <ArrowRight size={14} /></button></div>
      {user ? <div className="profile"><span className="avatar">{user.name[0]?.toUpperCase()}</span><div><b>{user.name}</b><small>{user.email}</small></div><button aria-label="Sign out" title="Sign out" onClick={() => run('logout', async () => { await api('/auth/logout', { method: 'POST' }); setToken(''); window.dispatchEvent(new Event('qg-signout')); })}><LogOut size={17} /></button></div> : <button className="signin-button" onClick={() => setModal('login')}>Sign in / Create account <ArrowRight size={16} /></button>}</div>
    </aside>

    <div className="main-shell"><header className="topbar"><div><span>Workspace</span><ChevronRight size={14} /><b>{view === 'create' ? 'Question studio' : view === 'sessions' ? 'My sessions' : 'Credits & activity'}</b></div><span className="topbar-note"><span className="status-dot" /> {config?.engine || 'Connecting to your workspace'}</span><button className="mobile-auth" disabled={!!busy} onClick={() => user ? run('logout', async () => { await api('/auth/logout', { method: 'POST' }); setToken(''); window.dispatchEvent(new Event('qg-signout')); }) : setModal('login')}>{user ? <><span>{user.total_credits} credits</span><LogOut size={16} /></> : 'Sign in'}</button></header>
    <main id="main-content">
      {error && <div className="alert error" role="alert"><CircleHelp size={19} /><span>{error}</span><button aria-label="Dismiss error" onClick={() => setError('')}><X size={16} /></button></div>}
      {notice && <div className="alert success" role="status"><CheckCircle2 size={19} /><span>{notice}</span><button aria-label="Dismiss message" onClick={() => setNotice('')}><X size={16} /></button></div>}
      {view === 'create' && <>
        <div className="page-heading"><div><div className="eyebrow"><span /> A LITTLE CURIOSITY. A LOT OF POSSIBILITY.</div><h1>{active ? active.title : <>Good questions.<br /><em>Deeper understanding.</em></>}</h1><p>{active ? `${active.question_count} questions · ${active.fact_count} source facts · ${active.kind === 'text' ? 'Text' : 'Document'} session` : 'Turn your notes and documents into questions worth asking.'}</p></div><div className="hero-illustration" aria-hidden="true"><div className="orbit orbit-one" /><div className="orbit orbit-two" /><span className="hero-node node-one">?</span><span className="hero-node node-two"><BookOpen size={19} /></span><div className="plant"><Sprout size={72} strokeWidth={1.3} /></div><span className="hero-node node-three"><Sparkles size={18} /></span><span className="illustration-caption">Ideas, connected.</span></div></div>
        <div className="studio-grid"><div className="studio-main">
          {!active ? <section className="panel source-panel"><div className="panel-heading"><span className="step">01</span><h2>Start with your source</h2><span className="muted small">Make something you know, grow.</span></div>
            <div className="segmented"><button className={sourceMode === 'text' ? 'active' : ''} onClick={() => setSourceMode('text')} disabled={!!busy}><FileText size={17} /> Paste text <span>1 credit / question</span></button><button className={sourceMode === 'document' ? 'active' : ''} onClick={() => setSourceMode('document')} disabled={!!busy}><UploadCloud size={18} /> Upload document <span>2 credits / question</span></button></div>
            {sourceMode === 'text' ? <><label className="field-label" htmlFor="session-title">Session name <span>optional</span></label><input id="session-title" placeholder="e.g. Biology · The world of plants" maxLength={200} value={title} onChange={e => setTitle(e.target.value)} disabled={!!busy} /><div className="text-label"><label className="field-label" htmlFor="source-text">Your source material</label><button className="text-button" onClick={() => { setTitle('Biology · Plant cells & photosynthesis'); setText(SAMPLE); }} disabled={!!busy}>Try a sample <ArrowRight size={13} /></button></div><textarea id="source-text" placeholder={'Paste your study notes, a chapter, or an article here…\n\nThe more clear, factual detail you provide, the better your questions will be.'} value={text} onChange={e => setText(e.target.value)} maxLength={config?.max_text_chars || 60000} disabled={!!busy} /><div className="textarea-footer"><span><ShieldCheck size={13} /> Your material stays in your account</span><span>{text.length.toLocaleString()} / {(config?.max_text_chars || 60000).toLocaleString()}</span></div></> : <label className="upload-zone" onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); if (!busy) setFile(e.dataTransfer.files[0]); }}><input type="file" accept=".pdf,.docx" onChange={e => setFile(e.target.files[0])} disabled={!!busy} /><span className="upload-icon"><UploadCloud size={28} /></span><b>{file ? file.name : 'Drop your document here'}</b><p>{file ? `${(file.size / 1024 / 1024).toFixed(2)} MB · Click to replace` : <>or <u>browse files</u> from your computer</>}</p><small>PDF or DOCX · Up to {config?.max_upload_mb || 10} MB · {config?.max_pages || 30} PDF pages</small><span className="ocr-badge"><Sparkles size={13} /> Built-in OCR for scans and embedded images</span></label>}
            <div className="source-tip"><Leaf size={17} /><p><b>Quality over quantity.</b> We stop when your source runs out of supported facts. You only pay for questions we generate.</p></div>
          </section> : <section className="panel result-panel"><div className="result-tabs" role="tablist" aria-label="Session content">{[['questions', `Questions (${active.questions.length})`], ['graph', 'Knowledge graph'], ['source', 'Source material']].map(([id, label]) => <button key={id} role="tab" aria-selected={resultTab === id} className={resultTab === id ? 'active' : ''} onClick={() => setResultTab(id)}>{label}</button>)}</div>
            {resultTab === 'questions' && <><div className="result-toolbar"><label><input type="checkbox" checked={showAnswers} onChange={e => setShowAnswers(e.target.checked)} /> Show answers</label><span className="small muted">Review before assessment use</span></div>{active.questions.length ? active.questions.map((q, i) => <QuestionCard key={q.id} question={q} index={i} showAnswers={showAnswers} />) : <div className="empty"><Sprout size={36} /><h3>Your questions will grow here</h3><p>Choose your formats and generate a set. MCQs need four suitable concepts; long answers need three facts about one concept.</p></div>}</>}
            {resultTab === 'graph' && <Graph graph={active.graph} />}
            {resultTab === 'source' && <div className="source-preview"><div className="source-meta"><span>{active.extraction.characters?.toLocaleString()} characters · {active.extraction.ocr_images_or_pages || 0} OCR images/pages</span><button className="text-button" onClick={() => run('download', () => download(`/sessions/${active.id}/original`, active.filename || 'source.txt'))}><ArrowDownToLine size={15} /> Download original</button></div><pre>{active.text}</pre></div>}
          </section>}
          <div className="trust-row"><span><Network size={16} /> Knowledge graph powered</span><span><ShieldCheck size={16} /> Answers linked to your source</span><span><FileText size={16} /> Export-ready PDFs</span></div>
        </div><aside className="settings-column"><section className="panel settings-panel"><div className="panel-heading"><span className="step">02</span><h2>Shape your questions</h2></div><label className="field-label">Question formats <span>choose any</span></label><div className="type-options">{TYPES.map(type => <label key={type.id} className={kinds.includes(type.id) ? 'chosen' : ''}><input type="checkbox" checked={kinds.includes(type.id)} disabled={!!busy} onChange={() => setKinds(kinds.includes(type.id) ? kinds.filter(k => k !== type.id) : [...kinds, type.id])} /><div><b>{type.label}</b><small>{type.hint}</small></div></label>)}</div><div className="quantity"><label className="field-label" htmlFor="question-count">Number of questions</label><input id="question-count" type="number" min="1" max="50" value={count} onChange={e => setCount(e.target.value === '' ? '' : Number(e.target.value))} disabled={!!busy} /></div><p className="small muted quantity-note">Up to 50 at a time. Formats depend on the facts available in your source.</p><div className="estimate"><span>Maximum cost</span><b>{(Number(count) || 0) * cost} <small>credits</small></b></div><button className="generate-button" onClick={generate} disabled={!!busy || !config}>{busy === 'generate' ? <><Spinner /> Reading & generating…</> : <><Sparkles size={18} /> {active ? 'Generate more questions' : 'Generate questions'} <ArrowRight size={17} /></>}</button><p className="charge-note">Only generated questions use credits.</p></section>
        {active?.questions.length > 0 && <section className="panel export-panel"><h2><ArrowDownToLine size={17} /> Take your learning with you</h2><button onClick={() => exportQuestions(false)} disabled={!!busy}>Questions only <span>PDF <ArrowDownToLine size={14} /></span></button><button onClick={() => exportQuestions(true)} disabled={!!busy}>Questions & answers <span>PDF <ArrowDownToLine size={14} /></span></button></section>}
        <div className="how-card"><span className="how-icon"><Network size={22} /></span><h3>Connected ideas.<br />Meaningful questions.</h3><p>We extract facts, map their relationships, and build questions with answers you can trace back to your material.</p><span>English sources · Conservative generation</span></div></aside></div>
      </>}

      {view === 'sessions' && <><div className="page-heading compact"><div><div className="eyebrow">YOUR PERSONAL LIBRARY</div><h1>Room for <em>every idea.</em></h1><p>Your sources, questions, and connections. Right where you left them.</p></div><button className="primary" onClick={newSession}><Plus size={17} /> New session</button></div><div className="search-box"><Search size={18} /><input aria-label="Search sessions" placeholder="Find a session…" value={search} onChange={e => setSearch(e.target.value)} /></div><div className="session-grid">{sessions.filter(s => s.title.toLowerCase().includes(search.toLowerCase())).map(s => <article className="panel session-card" key={s.id}><div className="session-top"><span className="document-icon"><FileText size={23} /></span><button aria-label={`Delete ${s.title}`} onClick={() => setDeleteTarget(s)}><Trash2 size={16} /></button></div><span className="tag">{s.kind === 'text' ? 'TEXT SOURCE' : 'DOCUMENT'}</span><h2>{s.title}</h2><p>{s.question_count} questions · {s.fact_count} facts</p><div className="session-bottom"><small>{new Date(s.created_at).toLocaleDateString()}</small><button onClick={() => openSession(s.id)} disabled={!!busy}>Open session <ArrowRight size={16} /></button></div></article>)}</div>{!sessions.length && <div className="empty panel"><FolderOpen size={40} /><h3>A fresh page awaits</h3><p>Create your first question set to start your library.</p><button className="primary" onClick={newSession}>Create a question set</button></div>}</>}

      {view === 'credits' && <><div className="page-heading compact"><div><div className="eyebrow">A LITTLE MORE ROOM TO LEARN</div><h1>Keep your curiosity <em>growing.</em></h1><p>100 free credits every day. No subscription needed.</p></div></div><div className="balance-grid"><div className="panel balance"><span>Daily free credits</span><strong>{user?.free_credits ?? '—'}<small> / 100</small></strong><p><Clock3 size={15} /> Resets at midnight {config?.credit_timezone || 'Asia/Kolkata'}</p></div><div className="panel balance"><span>Purchased credits</span><strong>{user?.paid_credits ?? '—'}</strong><p><Leaf size={15} /> These credits carry over</p></div><div className="panel buy-card"><span className="tag">DEMO PAYMENT</span><h2>1,000 credits <span>₹100</span></h2><p>Try the checkout experience. No actual payment or card details.</p><button className="primary" disabled={config && !config.demo_payments} onClick={() => { setCheckoutDone(false); setModal(user ? 'credits' : 'login'); }}>Add demo credits <ArrowRight size={16} /></button></div></div><section className="panel activity"><h2>Credit activity</h2><p className="muted small">Text questions cost 1 credit. Document questions cost 2. Free credits are used first.</p>{ledger.length ? ledger.map(row => <div className="activity-row" key={row.id}><span className={row.amount > 0 ? 'positive' : ''}>{row.amount > 0 ? '+' : ''}{row.amount}</span><div><b>{row.reason}</b><small>{new Date(row.created_at).toLocaleString()}</small></div></div>) : <div className="empty"><Coins size={28} /><p>{user ? 'Your credit activity will appear here.' : 'Sign in to see your balance and activity.'}</p></div>}</section></>}
      <footer><span><Sprout size={14} /> questiongarden</span><p>Make room for what you could know.</p><span>Built for curious minds</span></footer>
    </main></div>

    {(modal || deleteTarget) && <div className="modal-backdrop"><section className="modal" role="dialog" aria-modal="true" aria-labelledby="modal-title"><button className="modal-close" aria-label="Close dialog" onClick={() => { setModal(null); setDeleteTarget(null); }} disabled={!!busy}><X size={20} /></button>
      {modal === 'login' && <><span className="modal-icon"><Sprout size={32} /></span><h2 id="modal-title">{authMode === 'signup' ? 'Create your account.' : 'Welcome back.'}</h2><p>Save your sources and get 100 free credits every day.</p><form className="auth-form" onSubmit={e => { e.preventDefault(); run('login', async () => { const data = await api(`/auth/${authMode}`, { method: 'POST', body: { email: authEmail, password: authPassword, ...(authMode === 'signup' ? { name: authName } : {}) } }); setToken(data.token); setAuthPassword(''); await refresh(); setModal(null); }); }}>
      {authMode === 'signup' && <label>Name<input required maxLength={100} autoComplete="name" value={authName} onChange={e => setAuthName(e.target.value)} /></label>}
      <label>Email<input type="email" required maxLength={254} autoComplete="email" value={authEmail} onChange={e => setAuthEmail(e.target.value)} /></label><label>Password<input type="password" required minLength={10} maxLength={128} autoComplete={authMode === 'signup' ? 'new-password' : 'current-password'} value={authPassword} onChange={e => setAuthPassword(e.target.value)} /></label><small>Use at least 10 characters. Email verification and password recovery are not enabled for this project demo.</small><button className="primary full-width" disabled={!!busy} type="submit">{busy === 'login' ? <Spinner /> : authMode === 'signup' ? 'Create account' : 'Sign in'}</button></form><button className="text-button auth-switch" onClick={() => { setAuthMode(authMode === 'signup' ? 'signin' : 'signup'); setError(''); }}>{authMode === 'signup' ? 'Already have an account? Sign in' : 'New here? Create an account'}</button></>}
      {modal === 'credits' && <>{checkoutDone ? <><span className="modal-icon"><CheckCircle2 size={35} /></span><h2 id="modal-title">Payment done. More room to grow.</h2><p>1,000 demo credits have been added to your account. No money was charged.</p><button className="primary full-width" onClick={() => setModal(null)}>Back to learning <ArrowRight size={17} /></button></> : <><span className="modal-icon"><Coins size={32} /></span><span className="tag">SIMULATED CHECKOUT</span><h2 id="modal-title">A boost for your next idea.</h2><div className="checkout-price"><strong>1,000</strong><span>credits for ₹100</span></div><p>This is a demo payment for the project. It does not collect payment details or charge real money.</p><button className="primary full-width" disabled={!!busy || !config?.demo_payments} onClick={checkout}>{busy === 'checkout' ? <><Spinner /> Processing demo payment…</> : 'Simulate ₹100 payment'}</button></>}</>}
      {deleteTarget && <><span className="modal-icon"><Trash2 size={28} /></span><h2 id="modal-title">Delete this session?</h2><p>“{deleteTarget.title}”, its uploaded file, and all its questions will be removed. Used credits are not refunded.</p><button className="danger-button full-width" disabled={!!busy} onClick={() => run('delete', async () => { await api(`/sessions/${deleteTarget.id}`, { method: 'DELETE' }); if (active?.id === deleteTarget.id) setActive(null); setDeleteTarget(null); await refresh(); })}>{busy === 'delete' ? <Spinner /> : 'Delete session'}</button></>}
      {error && <p role="alert" className="modal-error">{error}</p>}
    </section></div>}
  </div>;
}
