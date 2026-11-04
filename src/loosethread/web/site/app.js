// The page: draws the state Python sends, and sends back what the player does. It holds no game logic.
// Everything said in the game is set as text, never as markup. Progress and the language stay in
// browser storage. A player's key is held only by the worker, and only until the page closes.

const TEXT = {
  zh: {
    brand: "破绽", caseNo: "案件", left: "还剩", asks: "问",
    ask: "问", accuse: "指认", notebook: "笔记", sheet: "案情", evidence: "证物", map: "地图", rules: "规则", talk: "审讯",
    goal: "目标：找出犯人，并拿出两条不能同时成立的记录，揭穿犯人的谎。同一时段多问几个人，说法对不上时会亮 ⚠。一次问一个人、一个时段。没听懂的、问过的、闲聊不花次数。问得越少，星越多。",
    placeholder: "比如：{example}", thinking: "正在问……", chooseFirst: "先选要问的人。",
    noted: "说法", conflicts: "矛盾提示", noConflicts: "目前没有发现不能同时成立的两条。", noStatements: "还没有问到任何说法。",
    denials: "否认过的（不能当指认的编号）", gridNote: "时段 21:15 指 21:15–21:30。深色的列是作案时间窗。第二行是自称同处一室的人。",
    alsoOnRecord: "其他说法", useThisPair: "用这对指认", people: "在场的人", client: "失主，不是嫌疑人",
    impression: "印象", motive: "动机", keyRules: "推理要点", allRules: "全部规则",
    accuseTitle: "指认", who: "犯人是谁", because: "哪两条不能同时成立（说法 S 或证物 E）", choose: "选两条。",
    accuseGo: "指认", cancel: "取消", confirmTitle: "只能指认一次",
    confirmPair: "确认指认 {name}，理由是 {a} 与 {b} 不能同时成立？",
    confirmNoConflict: "注意：{a} 与 {b} 并不矛盾。仍要指认 {name} 吗？",
    related: "笔记里和它们有关的矛盾：",
    confirmYes: "确认", result: "结果", share: "分享（不含答案）", copy: "复制", copied: "已复制", truth: "真相（剧透）",
    timelineNote: "* 下手的时段；! 本人在这一格撒了谎", lies: "谎言",
    modelButton: "用模型", modelOn: "模型 · 至多 ¥{cost}", rulesMode: "规则模式",
    modelTitle: "用你自己的 DeepSeek key",
    modelWhy: "现在是规则模式：不联网，问题由规则理解，台词是模板。接上模型后，问题和台词都由模型处理，事实仍由游戏决定，模型拿不到真相。",
    modelPrivacy: "你的问题和这一问允许说的事实会发给 DeepSeek，费用从你的 key 扣；我们测试时每局不到 ¥0.1，价格以 DeepSeek 为准。key 只留在这个页面的内存里，不写入浏览器存储，刷新或关闭后要重新输入。",
    keyLabel: "API key", connect: "连接", connecting: "正在连接……", useRules: "改回规则模式", close: "关闭",
    key_empty: "请输入 key。", key_rejected: "DeepSeek 拒绝了这个 key。", model_missing: "DeepSeek 目前没有提供配置里的模型。",
    model_unreachable: "连不上 DeepSeek，请稍后再试。",
    internal: "出了点问题，请再试一次。", restoreFailed: "这局的进度读不出来，已重新开始。",
    bootFailed: "游戏没能加载。请确认浏览器支持 WebAssembly，再试一次。", retry: "再试一次",
    loading: "正在打开卷宗……首次打开要下载约 6 MB。",
    outOfQuestions: "问题用完了，现在请指认。", over: "这一案已经结束。", newest: "打开今天的案子",
  },
  en: {
    brand: "Loose Thread", caseNo: "Case", left: "", asks: "left",
    ask: "Ask", accuse: "Accuse", notebook: "Notebook", sheet: "The case", evidence: "Evidence", map: "Map", rules: "Rules", talk: "Questions",
    goal: "Goal: name the culprit, with two items that cannot both be true, to expose their lie. Ask several people about the same time; ⚠ shows when their stories clash. One person and one time per question. Unclear questions, repeats and small talk are free. Fewer questions earn more stars.",
    placeholder: "e.g. {example}", thinking: "Asking…", chooseFirst: "Choose someone to ask first.",
    noted: "Statements", conflicts: "Contradiction hints", noConflicts: "No contradictions found yet.", noStatements: "No statements yet.",
    denials: "Denials (not usable as accusation ids)", gridNote: "Slot 21:15 means 21:15–21:30. Shaded columns are the theft window. The second line is who they say was in the room.",
    alsoOnRecord: "Also on record", useThisPair: "Accuse with these", people: "Who was there", client: "the owner, not a suspect",
    impression: "Impression", motive: "Motive", keyRules: "Key rules", allRules: "All the rules",
    accuseTitle: "Accuse", who: "Who is the culprit?", because: "Which two items cannot both be true? (statements S, evidence E)", choose: "Choose two.",
    accuseGo: "Accuse", cancel: "Cancel", confirmTitle: "You get one accusation",
    confirmPair: "Accuse {name}, because {a} and {b} cannot both be true?",
    confirmNoConflict: "Note: {a} and {b} do not contradict each other. Accuse {name} anyway?",
    related: "Contradictions in your notebook that involve them: ",
    confirmYes: "Confirm", result: "Result", share: "Share (no spoilers)", copy: "Copy", copied: "Copied", truth: "The truth (spoilers)",
    timelineNote: "* the theft; ! they lied about this slot", lies: "Lies",
    modelButton: "Use a model", modelOn: "Model · at most ¥{cost}", rulesMode: "Rules mode",
    modelTitle: "Use your own DeepSeek key",
    modelWhy: "You are in rules mode: nothing goes online, rules read your questions, and the lines are templates. With a model, it reads the questions and speaks the lines. The game still decides the facts, and the model never receives the truth.",
    modelPrivacy: "Your questions and the facts each answer may state go to DeepSeek, and your key pays: under ¥0.1 a game in our tests, at DeepSeek's prices. The key stays in this page's memory and is never written to browser storage, so a refresh asks for it again.",
    keyLabel: "API key", connect: "Connect", connecting: "Connecting…", useRules: "Back to rules mode", close: "Close",
    key_empty: "Enter a key.", key_rejected: "DeepSeek refused this key.", model_missing: "DeepSeek does not serve the configured model right now.",
    model_unreachable: "Could not reach DeepSeek. Try again later.",
    internal: "Something went wrong. Please try again.", restoreFailed: "This game's progress could not be read, so it starts afresh.",
    bootFailed: "The game could not load. Check that your browser supports WebAssembly, and try again.", retry: "Try again",
    loading: "Opening the case file… about 6 MB to download the first time.",
    outOfQuestions: "No questions left. Make your accusation.", over: "This case is closed.", newest: "Open today's case",
  },
};

const SAVE_PREFIX = "loosethread.game.";
const LANG_NAME = "loosethread.lang";
const KEEP_SAVES = 14;

const store = {
  get(name) { try { return localStorage.getItem(name) ?? ""; } catch { return ""; } },
  set(name, value) { try { localStorage.setItem(name, value); } catch { /* private window */ } },
  prune() {
    try {
      const names = Object.keys(localStorage).filter((n) => n.startsWith(SAVE_PREFIX)).sort();
      names.slice(0, Math.max(0, names.length - KEEP_SAVES)).forEach((n) => localStorage.removeItem(n));
    } catch { /* private window */ }
  },
};

function pickSeed() {
  const asked = new URLSearchParams(location.search).get("case");
  if (asked && /^\d{1,8}$/.test(asked)) return Number(asked);
  const now = new Date();
  return now.getFullYear() * 10000 + (now.getMonth() + 1) * 100 + now.getDate();
}

function pickLang() {
  const asked = new URLSearchParams(location.search).get("lang");
  if (asked === "zh" || asked === "en") return asked;
  const kept = store.get(LANG_NAME);
  if (kept === "zh" || kept === "en") return kept;
  return (navigator.language || "zh").toLowerCase().startsWith("zh") ? "zh" : "en";
}

const seed = pickSeed();
const saveName = SAVE_PREFIX + seed;
const ui = {
  lang: pickLang(), state: null, busy: false, hint: "", hintBad: false, notice: "", person: "",
  tab: "notes", pane: "talk", draft: "", first: "", second: "", suspect: "",
};
const t = (name, fields = {}) => {
  let text = TEXT[ui.lang][name] ?? name;
  for (const [field, value] of Object.entries(fields)) text = text.replaceAll(`{${field}}`, value);
  return text;
};

// --- Worker ---------------------------------------------------------------------------------------

let worker;
let nextId = 1;
const waiting = new Map();

function startWorker(onBooted) {
  worker = new Worker("./worker.mjs", { type: "module" });
  worker.onerror = () => onBooted(false);
  worker.onmessage = ({ data }) => {
    if ("booted" in data) { onBooted(data.booted); return; }
    const done = waiting.get(data.id);
    waiting.delete(data.id);
    done(JSON.parse(data.reply));
  };
}

function call(op, ...args) {
  return new Promise((resolve) => {
    const id = nextId++;
    waiting.set(id, resolve);
    worker.postMessage({ id, op, args });
  });
}

function errorText(reply) {
  if (reply.message) return reply.message;
  const code = reply.error.startsWith("internal") ? "internal" : reply.error;
  return t(code);
}

function take(reply) {
  if (reply.error) return false;
  ui.state = reply.state;
  ui.person = reply.state.current || ui.person;
  if (reply.save) store.set(saveName, reply.save);
  return true;
}

// --- Elements -------------------------------------------------------------------------------------

function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [name, value] of Object.entries(props)) {
    if (name === "class") node.className = value;
    else if (name.startsWith("on")) node.addEventListener(name.slice(2), value);
    else if (name === "text") node.textContent = value;
    else if (value === true) node.setAttribute(name, "");
    else if (value !== false && value !== null && value !== undefined) node.setAttribute(name, value);
  }
  for (const child of children.flat(Infinity)) if (child !== null && child !== undefined && child !== false) node.append(child);
  return node;
}

function section(title, ...children) {
  return el("section", { class: "section" }, el("h3", { text: title }), ...children);
}

function gridTable(grid, withCompany) {
  const inWindow = (i) => i >= grid.first && i <= grid.last;
  const head = el("tr", {}, el("th", { class: "who", scope: "col" }), grid.slots.map((slot, i) =>
    el("th", { scope: "col", class: inWindow(i) ? "inwindow" : "", text: slot })));
  const rows = grid.names.map((name, r) => el("tr", {}, el("th", { class: "who", scope: "row", text: name }),
    grid.slots.map((_, i) => el("td", { class: inWindow(i) ? "inwindow" : "" }, grid.places[r][i],
      withCompany && grid.company[r][i] ? el("span", { class: "with", text: grid.company[r][i] }) : null))));
  return el("div", { class: "gridwrap", tabindex: "0" },
    el("table", { class: "grid" }, el("thead", {}, head), el("tbody", {}, rows)));
}

// --- Notebook and case panes ----------------------------------------------------------------------

function notesView(state) {
  const notes = state.notes;
  const denied = state.turns.filter((turn) => turn.denial);
  if (!notes.statements.length && !denied.length) return el("p", { class: "empty", text: t("noStatements") });
  return [
    section(t("conflicts"), notes.conflicts.length
      ? notes.conflicts.map((c) => el("div", { class: "conflict" }, conflictView(c),
          state.ending ? null : el("button", {
            class: "plain", text: t("useThisPair"),
            onclick: () => openAccuse(c.first, c.second),
          })))
      : el("p", { class: "empty", text: t("noConflicts") })),
    notes.statements.length ? section(t("noted"),
      gridTable(notes.grid, true),
      el("p", { class: "gridnote", text: t("gridNote") }),
      el("ul", { class: "items", style: "margin-top:.6rem" }, notes.statements.map((s) =>
        el("li", {}, el("span", { class: "id", text: s.id }), el("span", { text: s.text }))))) : null,
    notes.extras.length ? section(t("alsoOnRecord"),
      el("ul", { class: "items" }, notes.extras.map((x) => el("li", { text: x })))) : null,
    denied.length ? section(t("denials"),
      el("ul", { class: "items" }, denied.map((d) => el("li", { text: `${d.speaker}: ${d.line}` })))) : null,
  ];
}

function sheetView(state) {
  const sheet = state.sheet;
  return [
    section(t("sheet"), el("dl", { class: "facts" }, sheet.facts.map(([label, value]) =>
      [el("dt", { text: label }), el("dd", { text: value })]))),
    section(t("people"), sheet.people.map((p) => el("div", { class: "person" },
      el("h4", {}, p.name, el("span", { class: "role", text: p.suspect ? p.role : `${p.role} · ${t("client")}` })),
      el("p", {}, el("span", { class: "label", text: `${t("impression")}: ` }), p.persona),
      p.motive ? el("p", {}, el("span", { class: "label", text: `${t("motive")}: ` }), p.motive) : null))),
  ];
}

function evidenceView(state) {
  return el("ul", { class: "items" }, state.sheet.evidence.map((e) => el("li", {},
    el("span", { class: "id", text: e.id }),
    el("span", {}, el("span", { class: "tag", text: `[${e.time}] ` }), e.text))));
}

function rulesView(state) {
  return [
    section(t("keyRules"), el("ul", { class: "rules" }, state.sheet.key_rules.map((r) => el("li", { text: r })))),
    section(t("allRules"), el("ol", { class: "rules" }, state.sheet.rules.map((r) => el("li", { text: r })))),
  ];
}

const TABS = [
  ["notes", "notebook", notesView],
  ["sheet", "sheet", sheetView],
  ["evidence", "evidence", evidenceView],
  ["map", "map", (state) => el("pre", { class: "map", text: state.sheet.map_picture })],
  ["rules", "rules", rulesView],
];

function bookPane(state) {
  const [, , view] = TABS.find(([name]) => name === ui.tab);
  return el("div", { class: "pane", "data-hidden": String(ui.pane !== "book") },
    el("div", { class: "tabs", role: "tablist" }, TABS.map(([name, label]) => el("button", {
      role: "tab", "aria-selected": String(ui.tab === name), text: t(label),
      onclick: () => { ui.tab = name; draw(); },
    }))),
    el("div", { class: "scroll" }, view(state)));
}

// --- Interrogation pane ---------------------------------------------------------------------------

function endingView(state) {
  const ending = state.ending;
  const card = el("textarea", { class: "card", readonly: true, rows: String(ending.share.split("\n").length), "aria-label": t("share") });
  card.value = ending.share;
  const copied = el("span", { class: "small", role: "status" });
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(ending.share);
    } catch {
      card.select();
      document.execCommand("copy");
    }
    copied.textContent = ` ${t("copied")}`;
  };
  return el("div", { class: "ending" },
    el("h2", { class: "mark", text: ending.lines[0] }),
    ending.lines.slice(1).map((line) => el("p", { class: "small", text: line })),
    section(t("share"), card, el("button", { class: "plain", text: t("copy"), onclick: copy }), copied),
    section(t("truth"),
      el("p", { class: "truthline", text: ending.truth.culprit }),
      gridTable(ending.truth.grid, false),
      el("p", { class: "gridnote", text: t("timelineNote") }),
      el("h3", { text: t("lies"), style: "margin-top:.75rem" }),
      el("ul", { class: "lies" }, ending.truth.lies.map((lie) => el("li", { text: lie })))));
}

function turnView(turn) {
  const colon = ui.lang === "zh" ? "：" : ": ";
  return el("article", { class: "turn" },
    el("p", { class: "asked", text: `${turn.speaker} ← ${turn.question}` }),
    el("p", { class: "said" }, el("b", { text: turn.speaker + colon }), turn.line),
    el("p", { class: "status", text: turn.status }),
    turn.conflicts.map(conflictView));
}

function conflictView(c) {
  return el("div", {},
    el("p", { class: "alarm", text: c.text }),
    c.said.map((text) => el("p", { class: "status", text })));
}

function askForm(state) {
  const closed = Boolean(state.ending);
  const spent = state.left <= 0;
  if (closed) return null;
  const suspects = state.sheet.people;
  const input = el("input", {
    id: "question", type: "text", maxlength: "200", autocomplete: "off", enterkeyhint: "send",
    "aria-label": t("ask"),
    placeholder: spent ? t("outOfQuestions") : t("placeholder", { example: state.example }),
    disabled: ui.busy || spent,
    oninput: (event) => { ui.draft = event.target.value; },
  });
  input.value = ui.draft;
  return el("form", {
    class: "asking",
    onsubmit: (event) => { event.preventDefault(); ask(); },
  },
    el("div", { class: "people", role: "group", "aria-label": t("ask") }, suspects.map((p) => el("button", {
      type: "button", "aria-pressed": String(ui.person === p.id), text: p.name,
      onclick: () => { ui.person = p.id; ui.hint = ""; draw(); document.getElementById("question")?.focus(); },
    }))),
    el("div", { class: "line" }, input,
      el("button", { class: "primary", disabled: ui.busy || spent, text: t("ask") }),
      el("button", {
        class: "plain", type: "button", disabled: ui.busy, text: t("accuse"),
        onclick: () => openAccuse(ui.first, ui.second),
      })),
    el("p", { class: `hint${ui.hintBad ? " bad" : ""}`, role: "status", text: ui.hint }));
}

function talkPane(state) {
  return el("div", { class: "pane", "data-hidden": String(ui.pane !== "talk") },
    el("div", { class: "scroll", id: "talk", "aria-live": "polite" },
      ui.notice ? el("p", { class: "notice", text: ui.notice }) : null,
      state.ending ? endingView(state) : null,
      el("div", { class: "briefing" },
        el("h2", { text: state.sheet.title }),
        el("p", { text: state.sheet.intro }),
        state.ending ? null : el("p", { class: "goal", text: t("goal") })),
      state.turns.map(turnView)),
    askForm(state));
}

// --- Top bar and whole page -----------------------------------------------------------------------

function topBar(state) {
  return el("header", { class: "top" },
    el("h1", { class: "brand" }, t("brand"), el("small", { text: `${t("caseNo")} #${state.seed}` })),
    el("button", {
      class: "plain only-narrow", "aria-pressed": String(ui.pane === "book"),
      text: ui.pane === "book" ? t("talk") : t("notebook"),
      onclick: () => { ui.pane = ui.pane === "book" ? "talk" : "book"; draw(); },
    }),
    el("span", { class: "count" }, t("left"), " ", el("strong", { text: String(state.left) }), " ", t("asks")),
    el("button", {
      class: "plain", "aria-pressed": String(state.mode === "model"),
      text: state.mode === "model" ? t("modelOn", { cost: state.spent_cny.toFixed(2) }) : t("modelButton"),
      onclick: openModel,
    }),
    el("button", {
      class: "plain", lang: ui.lang === "zh" ? "en" : "zh", text: ui.lang === "zh" ? "EN" : "中文",
      onclick: switchLang,
    }));
}

function draw() {
  const state = ui.state;
  const app = document.getElementById("app");
  const talk = document.getElementById("talk");
  const keepTalk = talk ? talk.scrollTop : 0;
  const hadFocus = document.activeElement?.id === "question";
  document.documentElement.lang = ui.lang === "zh" ? "zh" : "en";
  document.title = TEXT[ui.lang].brand === "破绽" ? "破绽 · Loose Thread" : "Loose Thread · 破绽";
  app.replaceChildren(topBar(state), el("main", { class: "panes" }, talkPane(state), bookPane(state)));
  const fresh = document.getElementById("talk");
  if (fresh) fresh.scrollTop = ui.scrollDown ? fresh.scrollHeight : keepTalk;
  ui.scrollDown = false;
  if (hadFocus && !ui.busy) document.getElementById("question")?.focus();
  // A narrow grid opens at the theft window, not at the evening's first slot.
  for (const wrap of document.querySelectorAll(".gridwrap")) {
    const column = wrap.querySelector("thead .inwindow");
    if (column) wrap.scrollLeft = column.offsetLeft - wrap.querySelector("th.who").offsetWidth;
  }
}

// --- What the player does -------------------------------------------------------------------------

async function ask() {
  const text = ui.draft.trim();
  if (!text || ui.busy) return;
  ui.busy = true; ui.hint = t("thinking"); ui.hintBad = false;
  draw();
  const reply = await call("ask", ui.person, text);
  ui.busy = false;
  if (take(reply)) {
    ui.draft = ""; ui.hint = ""; ui.scrollDown = true; ui.notice = "";
    if (reply.state.left <= 0) ui.hint = t("outOfQuestions");
  } else {
    ui.hint = errorText(reply); ui.hintBad = true;
  }
  draw();
  document.getElementById("question")?.focus();
}

async function switchLang() {
  if (ui.busy) return;
  const lang = ui.lang === "zh" ? "en" : "zh";
  const reply = await call("set_lang", lang);
  if (take(reply)) {
    ui.lang = lang; ui.hint = ""; ui.notice = "";
    store.set(LANG_NAME, lang);
    draw();
  }
}

function dialog(...children) {
  const box = el("dialog", {}, ...children);
  box.addEventListener("close", () => box.remove());
  document.body.append(box);
  box.showModal();
  return box;
}

function openAccuse(first = "", second = "") {
  const state = ui.state;
  ui.first = first; ui.second = second;
  const suspects = state.sheet.people.filter((p) => p.suspect);
  const items = [
    ...state.notes.statements.map((s) => ({ id: s.id, text: s.text })),
    ...state.sheet.evidence.map((e) => ({ id: e.id, text: `[${e.time}] ${e.text}` })),
  ];
  const problem = el("p", { class: "hint bad", role: "status" });
  const fill = () => {
    box.replaceChildren(
      el("h2", { text: t("accuseTitle") }),
      el("label", { text: t("who") }),
      el("div", { class: "pick" }, suspects.map((p) => el("button", {
        type: "button", "aria-pressed": String(ui.suspect === p.id), text: p.name,
        onclick: () => { ui.suspect = p.id; fill(); },
      }))),
      el("label", { text: t("because") }),
      el("ul", { class: "pickitems" }, items.map((item) => el("li", {}, el("button", {
        type: "button", "aria-pressed": String(ui.first === item.id || ui.second === item.id),
        onclick: () => { toggleItem(item.id); fill(); },
      }, el("span", { class: "id", text: item.id }), el("span", { text: item.text }))))),
      problem,
      el("div", { class: "row" },
        el("button", { class: "plain", type: "button", text: t("cancel"), onclick: () => box.close() }),
        el("button", {
          class: "primary", type: "button", text: t("accuseGo"),
          disabled: !(ui.suspect && ui.first && ui.second),
          onclick: () => precheck(box, problem),
        })));
  };
  const box = dialog();
  fill();
}

function toggleItem(id) {
  if (ui.first === id) { ui.first = ui.second; ui.second = ""; return; }
  if (ui.second === id) { ui.second = ""; return; }
  if (!ui.first) ui.first = id;
  else if (!ui.second) ui.second = id;
  else { ui.first = ui.second; ui.second = id; }
}

async function precheck(box, problem) {
  const reply = await call("check", ui.suspect, ui.first, ui.second);
  if (reply.error) { problem.textContent = errorText(reply); return; }
  const { check } = reply;
  const fields = { name: check.name, a: check.first, b: check.second };
  const related = !check.conflicts && check.related.length
    ? [el("p", { class: "small", text: t("related") + check.related.join(ui.lang === "zh" ? "；" : "; ") })] : [];
  box.replaceChildren(
    el("h2", { text: t("confirmTitle") }),
    el("p", { text: t(check.conflicts ? "confirmPair" : "confirmNoConflict", fields) }),
    ...related,
    el("div", { class: "row" },
      el("button", { class: "plain", type: "button", text: t("cancel"), onclick: () => box.close() }),
      el("button", { class: "primary", type: "button", text: t("confirmYes"), onclick: () => accuse(box) })));
}

async function accuse(box) {
  box.close();
  ui.busy = true;
  draw();
  const reply = await call("accuse", ui.suspect, ui.first, ui.second);
  ui.busy = false;
  if (take(reply)) { ui.pane = "talk"; ui.hint = ""; }
  else { ui.hint = errorText(reply); ui.hintBad = true; }
  draw();
  document.getElementById("talk")?.scrollTo(0, 0);
}

function openModel() {
  const state = ui.state;
  const problem = el("p", { class: "hint bad", role: "status" });
  const field = el("input", { type: "password", id: "key", autocomplete: "off", spellcheck: "false" });
  const go = el("button", { class: "primary", text: t("connect") });
  const form = el("form", {
    onsubmit: async (event) => {
      event.preventDefault();
      go.disabled = true;
      problem.textContent = t("connecting");
      const reply = await call("connect", field.value);
      field.value = "";
      go.disabled = false;
      if (take(reply)) { box.close(); draw(); }
      else problem.textContent = errorText(reply);
    },
  },
    el("label", { for: "key", text: t("keyLabel") }), field, problem,
    el("div", { class: "row" },
      el("button", { class: "plain", type: "button", text: t("close"), onclick: () => box.close() }),
      go));
  const leave = async () => {
    const reply = await call("disconnect");
    if (take(reply)) { box.close(); draw(); }
  };
  const box = dialog(
    el("h2", { text: t("modelTitle") }),
    el("p", { class: "small", text: t("modelWhy") }),
    el("p", { class: "small", text: t("modelPrivacy") }),
    state.mode === "model"
      ? el("div", { class: "row" },
          el("button", { class: "plain", text: t("close"), onclick: () => box.close() }),
          el("button", { class: "primary", text: t("useRules"), onclick: leave }))
      : form);
}

// --- Start ----------------------------------------------------------------------------------------

function bootFailed() {
  const app = document.getElementById("app");
  app.replaceChildren(el("div", { class: "boot" }, el("p", { text: t("bootFailed") }),
    el("button", { class: "plain", text: t("retry"), onclick: () => location.reload() })));
}

async function open() {
  document.getElementById("boot").textContent = t("loading");
  store.prune();
  startWorker(async (booted) => {
    if (!booted) { bootFailed(); return; }
    const reply = await call("start", seed, ui.lang, store.get(saveName));
    if (!take(reply)) { bootFailed(); return; }
    if (reply.restore_failed) ui.notice = t("restoreFailed");
    ui.scrollDown = !reply.state.ending;  // a finished game opens at its ending, on top
    draw();
  });
}

open();
