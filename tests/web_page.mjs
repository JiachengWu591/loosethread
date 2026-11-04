// Runs the page's real code on a small stand-in for the DOM, through a whole game, with the worker
// replaced by replies the game gave in Python. It reports what a real DOM would swallow: a real
// `append` turns an array or null into text on the screen, and this stand-in records it instead.
// node tests/web_page.mjs <path to app.js> <replies.json>
// It cannot see layout, CSS, a real worker, or anything a browser does differently from this.
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";

const [appPath, repliesPath] = process.argv.slice(2);
const { replies, key } = JSON.parse(readFileSync(repliesPath, "utf8"));
const problems = [];
const sent = [];

class Node {
  constructor(tag) {
    Object.assign(this, { tag, kids: [], attrs: {}, listeners: {}, className: "", value: "", scrollTop: 0, scrollHeight: 0, parent: null });
  }
  append(...items) {
    for (const item of items) {
      if (item instanceof Node) { item.parent = this; this.kids.push(item); }
      else if (typeof item === "string") this.kids.push(item);
      else problems.push(`${this.tag} was given ${Array.isArray(item) ? "an array" : String(item)}`);
    }
  }
  replaceChildren(...items) { this.kids = []; this.append(...items); }
  set textContent(value) { this.kids = [String(value)]; }
  get textContent() { return this.kids.map((k) => (k instanceof Node ? k.textContent : k)).join(" "); }
  setAttribute(name, value) { this.attrs[name] = value; }
  addEventListener(name, fn) { (this.listeners[name] ??= []).push(fn); }
  fire(name, extra = {}) { for (const fn of this.listeners[name] ?? []) fn({ preventDefault() {}, target: this, ...extra }); }
  walk() { return [this, ...this.kids.filter((k) => k instanceof Node).flatMap((k) => k.walk())]; }
  querySelector() { return null; }
  focus() {} select() {} showModal() { this.attrs.open = true; } scrollTo() {}
  close() { this.fire("close"); }
  remove() { if (this.parent) this.parent.kids = this.parent.kids.filter((k) => k !== this); }
}

const body = new Node("body");
const app = new Node("div");
app.attrs.id = "app";
const boot = new Node("p");
boot.attrs.id = "boot";
app.append(boot);
body.append(app);
const storage = {};

globalThis.document = {
  body, title: "", activeElement: null, documentElement: { lang: "" },
  createElement: (tag) => new Node(tag),
  getElementById: (id) => body.walk().find((n) => n.attrs.id === id) ?? null,
  querySelectorAll: () => [],
  execCommand() {},
};
globalThis.localStorage = new Proxy(storage, {
  get: (target, name) => ({
    getItem: (n) => target[n] ?? null,
    setItem: (n, v) => { target[n] = String(v); },
    removeItem: (n) => { delete target[n]; },
  })[name] ?? target[name],
});
globalThis.location = { search: "", reload() {} };
Object.defineProperty(globalThis, "navigator", {
  value: { language: "zh-CN", clipboard: { writeText: async () => {} } },
  configurable: true,
});
globalThis.Worker = class {
  constructor() { setTimeout(() => this.onmessage({ data: { booted: true } }), 0); }
  postMessage({ id, op, args }) {
    sent.push({ op, args });
    const reply = replies[op].shift();
    if (reply === undefined) throw new Error(`no reply left for ${op}`);
    setTimeout(() => this.onmessage({ data: { id, reply } }), 0);
  }
};

await import(pathToFileURL(appPath).href);

const settle = async () => { for (let i = 0; i < 6; i++) await new Promise((r) => setTimeout(r, 0)); };
const scope = () => body.walk().filter((n) => n.tag === "dialog").at(-1) ?? body;  // an open dialog is on top
const clickOn = async (text) => {
  const found = scope().walk().find((n) => n.tag === "button" && n.textContent === text);
  if (!found) throw new Error(`no button ${text}`);
  found.fire("click");
  await settle();
};
const everyTab = async () => {
  for (const tab of ["笔记", "案情", "证物", "地图", "规则"]) await clickOn(tab);
};
const onScreen = [];
const look = () => {
  onScreen.push(body.textContent);
  for (const match of body.textContent.matchAll(/\[object[^\]]*\]|\bundefined\b|\bnull\b|\bNaN\b/g)) problems.push(`on screen: ${match[0]}`);
};

await settle();
look();
await everyTab();
look();

// The language, both ways.
await clickOn("EN");
look();
await clickOn("中文");

// A question, by the form.
const input = document.getElementById("question");
input.value = "一个问题";
input.fire("input");
body.walk().find((n) => n.tag === "form").fire("submit");
await settle();
look();
await everyTab();
look();

// An accusation that is not a contradiction, cancelled, then one that is, confirmed.
await clickOn("指认");
await clickOn(replies.suspect[0]);
for (const item of replies.items[0]) {
  scope().walk().find((n) => n.tag === "button" && n.textContent.startsWith(`${item} `)).fire("click");
}
await settle();
await clickOn("指认");
look();
await clickOn("取消");
await clickOn("笔记");
await clickOn("用这对指认");
await clickOn(replies.suspect[0]);
await clickOn("指认");
look();
await clickOn("确认");
look();
await everyTab();
look();
await clickOn("复制");

// A key: refused, then accepted, then given up.
const openModel = () => body.walk().find((n) => n.tag === "button" && n.attrs["aria-pressed"] !== undefined && /模型/.test(n.textContent));
openModel().fire("click");
await settle();
const field = document.getElementById("key");
const form = body.walk().filter((n) => n.tag === "form").at(-1);
field.value = key;
form.fire("submit");
await settle();
look();
const clearedAfterRefusal = field.value === "";
field.value = key;
form.fire("submit");
await settle();
look();
openModel().fire("click");
await settle();
await clickOn("改回规则模式");
look();

const stored = JSON.stringify(storage);
process.stdout.write(JSON.stringify({
  problems,
  sawEnding: onScreen.some((text) => text.includes(replies.ending[0])),
  keyInStorage: stored.includes(key),
  keyOnScreen: onScreen.some((text) => text.includes(key)),
  clearedAfterRefusal,
  clearedAfterConnect: field.value === "",
  keySentOnlyToConnect: sent.filter((m) => JSON.stringify(m.args).includes(key)).every((m) => m.op === "connect"),
  ops: [...new Set(sent.map((m) => m.op))].sort(),
}));
