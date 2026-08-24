const BRIDGE_URL = new URL("./py/bridge.py", self.location.href).href;
const MANIFEST_URL = new URL("./assets/demo-manifest.json", self.location.href).href;

let runtimePromise = null;

function postStatus(message) {
  self.postMessage({ type: "status", message });
}

async function initializeRuntime() {
  if (runtimePromise) {
    return runtimePromise;
  }

  runtimePromise = (async () => {
    postStatus("배포 정보를 확인하고 있습니다");
    const manifestResponse = await fetch(MANIFEST_URL, { cache: "no-cache" });
    if (!manifestResponse.ok) {
      throw new Error("데모 manifest를 불러오지 못했습니다.");
    }
    const manifest = await manifestResponse.json();
    const indexURL = `https://cdn.jsdelivr.net/pyodide/v${manifest.pyodide_version}/full/`;

    postStatus("브라우저용 Python을 준비하고 있습니다");
    importScripts(`${indexURL}pyodide.js`);
    const pyodide = await loadPyodide({ indexURL });

    postStatus("k-safeguard wheel을 불러오고 있습니다");
    await pyodide.loadPackage("micropip");
    const micropip = pyodide.pyimport("micropip");
    const wheelURL = new URL(manifest.wheel, self.location.href).href;
    try {
      await micropip.install(wheelURL);
    } finally {
      micropip.destroy();
    }

    const bridgeResponse = await fetch(BRIDGE_URL, { cache: "no-cache" });
    if (!bridgeResponse.ok) {
      throw new Error("Python bridge를 불러오지 못했습니다.");
    }
    pyodide.runPython(await bridgeResponse.text());
    const runtime = JSON.parse(pyodide.runPython("runtime_metadata_json()"));
    return { pyodide, manifest, runtime };
  })();

  return runtimePromise;
}

async function analyze(requestId, payload) {
  const { pyodide } = await initializeRuntime();
  pyodide.globals.set("web_demo_payload_json", JSON.stringify(payload));
  try {
    const serialized = pyodide.runPython("analyze_json(web_demo_payload_json)");
    return JSON.parse(serialized);
  } finally {
    pyodide.runPython("del web_demo_payload_json");
  }
}

self.onmessage = async (event) => {
  const { type, requestId, payload } = event.data || {};
  try {
    if (type === "init") {
      const { manifest, runtime } = await initializeRuntime();
      self.postMessage({ type: "ready", manifest, runtime });
      return;
    }
    if (type === "analyze") {
      const result = await analyze(requestId, payload);
      self.postMessage({ type: "result", requestId, result });
      return;
    }
    throw new Error("지원하지 않는 worker 요청입니다.");
  } catch (error) {
    self.postMessage({
      type: "error",
      requestId,
      message: error instanceof Error ? error.message : String(error),
    });
  }
};
