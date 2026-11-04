// Runs tests/web_digests.py in the built site's Pyodide and package, and prints what it returns.
// node tests/web_node.mjs <site folder> <path to web_digests.py>
import { readFileSync } from "node:fs";
import { resolve, join } from "node:path";
import { pathToFileURL } from "node:url";

const [site, script] = process.argv.slice(2).map((path) => resolve(path));
const runtime = join(site, "pyodide");
const { loadPyodide } = await import(pathToFileURL(join(runtime, "pyodide.mjs")).href);
const pyodide = await loadPyodide({ indexURL: runtime });
pyodide.unpackArchive(new Uint8Array(readFileSync(join(site, "loosethread.zip"))), "zip");
pyodide.FS.writeFile("web_digests.py", readFileSync(script, "utf8"));
process.stdout.write(pyodide.runPython("import web_digests; web_digests.digests()"));
