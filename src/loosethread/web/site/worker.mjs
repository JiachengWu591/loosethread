// Runs the game in Python, off the page's thread. A model call blocks here and not the page.
// A key arrives in one message, goes to Python, and is held nowhere in this file.
import { loadPyodide } from "./pyodide/pyodide.mjs";

async function boot() {
  const pyodide = await loadPyodide({ indexURL: new URL("./pyodide/", import.meta.url).href });
  const bundle = await (await fetch("./loosethread.zip")).arrayBuffer();
  pyodide.unpackArchive(bundle, "zip");
  return pyodide.pyimport("loosethread.web.bridge");
}

const ready = boot();
ready.then(
  () => postMessage({ booted: true }),
  (err) => postMessage({ booted: false, reason: err.name }),
);

self.onmessage = async ({ data: { id, op, args } }) => {
  try {
    const bridge = await ready;
    postMessage({ id, reply: bridge[op](...args) });
  } catch (err) {
    postMessage({ id, reply: JSON.stringify({ error: `internal:${err.name}` }) });
  }
};
