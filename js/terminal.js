// The OPS TERMINAL — the orb's second page. The orb is the show; this is the
// receipts. Every wake, every word, every Hermes delegation and every line
// Hermes prints while working streams in here, timestamped, plus a prompt so
// you can type to Donald directly.
//
// Self-contained: builds its own DOM + styles, toggled over the orb scene.

const STYLE = `
  #donald-term {
    position: fixed; inset: 0; z-index: 20; display: flex; flex-direction: column;
    background: rgba(4, 7, 12, 0.96); backdrop-filter: blur(10px);
    font: 13px/1.55 "SFMono-Regular", ui-monospace, "JetBrains Mono", Menlo, Consolas, monospace;
    color: #c9d6e2; opacity: 1; transition: opacity 0.16s ease;
  }
  #donald-term.hidden { opacity: 0; pointer-events: none; }
  #donald-term .t-head {
    display: flex; align-items: center; gap: 14px; padding: 12px 18px;
    border-bottom: 1px solid rgba(255,255,255,0.08); flex: none;
  }
  #donald-term .t-title { font-weight: 700; letter-spacing: 0.12em; color: #ff8a3d; }
  #donald-term .t-chips { display: flex; gap: 8px; margin-left: auto; }
  #donald-term .t-chip {
    padding: 3px 9px; border-radius: 999px; font-size: 11px; letter-spacing: 0.06em;
    border: 1px solid rgba(255,255,255,0.14); color: #9fb3c8; text-transform: uppercase;
  }
  #donald-term .t-chip.ok  { color: #34d399; border-color: rgba(52,211,153,0.5); }
  #donald-term .t-chip.bad { color: #ff6b5e; border-color: rgba(255,107,94,0.5); }
  #donald-term .t-chip.warn{ color: #ffb02e; border-color: rgba(255,176,46,0.5); }
  #donald-term .t-close {
    margin-left: 8px; cursor: pointer; background: none; border: 1px solid rgba(255,255,255,0.16);
    color: #c9d6e2; border-radius: 8px; padding: 4px 10px; font: inherit; font-size: 11px;
  }
  #donald-term .t-close:hover { border-color: #ff8a3d; color: #ff8a3d; }
  #donald-term .t-log { flex: 1; overflow-y: auto; padding: 14px 18px; overscroll-behavior: contain; }
  #donald-term .t-row { display: flex; gap: 10px; padding: 1.5px 0; align-items: baseline; }
  #donald-term .t-time { flex: none; color: #55677a; font-size: 11px; }
  #donald-term .t-tag  { flex: none; width: 74px; text-align: right; font-size: 11px;
    letter-spacing: 0.05em; text-transform: uppercase; opacity: 0.9; }
  #donald-term .t-text { white-space: pre-wrap; word-break: break-word; min-width: 0; }
  #donald-term .k-sys    .t-tag { color: #55677a; }  #donald-term .k-sys    .t-text { color: #8fa2b5; }
  #donald-term .k-wake   .t-tag { color: #ffb02e; }  #donald-term .k-wake   .t-text { color: #ffd27a; }
  #donald-term .k-you    .t-tag { color: #7dd3fc; }  #donald-term .k-you    .t-text { color: #cdeeff; }
  #donald-term .k-donald .t-tag { color: #ff8a3d; }  #donald-term .k-donald .t-text { color: #ffe6d2; }
  #donald-term .k-tool   .t-tag { color: #a78bfa; }  #donald-term .k-tool   .t-text { color: #d6c8ff; }
  #donald-term .k-hermes .t-tag { color: #a3e635; }  #donald-term .k-hermes .t-text { color: #9fb884; }
  #donald-term .k-result .t-tag { color: #34d399; }  #donald-term .k-result .t-text { color: #b7ecd8; }
  #donald-term .k-error  .t-tag { color: #ff6b5e; }  #donald-term .k-error  .t-text { color: #ffb4ad; }
  #donald-term .t-input {
    display: flex; gap: 10px; align-items: center; padding: 12px 18px; flex: none;
    border-top: 1px solid rgba(255,255,255,0.08);
  }
  #donald-term .t-prompt { color: #ff8a3d; font-weight: 700; }
  #donald-term .t-input input {
    flex: 1; background: none; border: none; outline: none; color: #eef6ff;
    font: inherit; caret-color: #ff8a3d;
  }
  #donald-term .t-input input::placeholder { color: #55677a; }
`;

const TAGS = {
  sys: 'sys', wake: 'wake', you: 'you', donald: 'donald',
  tool: 'dispatch', hermes: 'hermes', result: 'result', error: 'error',
};

const MAX_ROWS = 2000;

export class Terminal {
  constructor({ onSubmit = null } = {}) {
    this.onSubmit = onSubmit;
    this._autoScroll = true;
    this._build();
  }

  _build() {
    const style = document.createElement('style');
    style.textContent = STYLE;
    document.head.appendChild(style);

    this.el = document.createElement('div');
    this.el.id = 'donald-term';
    this.el.className = 'hidden';
    this.el.innerHTML = `
      <div class="t-head">
        <div class="t-title">DONALD ▸ OPS TERMINAL</div>
        <div class="t-chips">
          <span class="t-chip" data-chip="gateway">gateway: …</span>
          <span class="t-chip" data-chip="hermes">hermes: …</span>
          <span class="t-chip" data-chip="ears">ears: off</span>
        </div>
        <button class="t-close" title="Back to the orb (\` or Esc)">◉ orb</button>
      </div>
      <div class="t-log"></div>
      <form class="t-input">
        <span class="t-prompt">❯</span>
        <input type="text" autocomplete="off" spellcheck="false"
               placeholder="type to Donald — or just clap and speak" />
      </form>`;
    document.body.appendChild(this.el);

    this.log = this.el.querySelector('.t-log');
    this.input = this.el.querySelector('input');
    this.el.querySelector('.t-close').addEventListener('click', () => this.hide());
    this.el.querySelector('.t-input').addEventListener('submit', (e) => {
      e.preventDefault();
      const text = this.input.value.trim();
      if (!text) return;
      this.input.value = '';
      if (this.onSubmit) this.onSubmit(text);
    });
    // Stick to the bottom unless the user has scrolled up to read history.
    this.log.addEventListener('scroll', () => {
      this._autoScroll =
        this.log.scrollTop + this.log.clientHeight >= this.log.scrollHeight - 40;
    });
  }

  // One log line. kind: sys|wake|you|donald|tool|hermes|result|error
  line(kind, text) {
    const row = document.createElement('div');
    row.className = `t-row k-${kind in TAGS ? kind : 'sys'}`;
    const t = new Date();
    const hh = String(t.getHours()).padStart(2, '0');
    const mm = String(t.getMinutes()).padStart(2, '0');
    const ss = String(t.getSeconds()).padStart(2, '0');
    const time = document.createElement('span');
    time.className = 't-time';
    time.textContent = `${hh}:${mm}:${ss}`;
    const tag = document.createElement('span');
    tag.className = 't-tag';
    tag.textContent = TAGS[kind] || kind;
    const body = document.createElement('span');
    body.className = 't-text';
    body.textContent = text;
    row.append(time, tag, body);
    this.log.appendChild(row);
    while (this.log.childElementCount > MAX_ROWS) this.log.firstElementChild.remove();
    if (this._autoScroll) this.log.scrollTop = this.log.scrollHeight;
  }

  // Header status chips: setChip('hermes', 'reachable', 'ok')
  setChip(name, text, tone = '') {
    const chip = this.el.querySelector(`[data-chip="${name}"]`);
    if (!chip) return;
    chip.textContent = `${name}: ${text}`;
    chip.className = `t-chip${tone ? ' ' + tone : ''}`;
  }

  get visible() { return !this.el.classList.contains('hidden'); }
  show() { this.el.classList.remove('hidden'); this.input.focus(); }
  hide() { this.el.classList.add('hidden'); this.input.blur(); }
  toggle() { this.visible ? this.hide() : this.show(); }
}
