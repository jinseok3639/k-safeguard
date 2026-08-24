const state = {
  ready: false,
  busy: false,
  requestId: 0,
  maxInputLength: 1000,
};

const worker = new Worker("./worker.js");
const elements = {
  form: document.querySelector("#analysis-form"),
  input: document.querySelector("#input-text"),
  count: document.querySelector("#character-count"),
  submit: document.querySelector("#analyze-button"),
  status: document.querySelector("#runtime-status"),
  statusDot: document.querySelector("#status-dot"),
  packageVersion: document.querySelector("#package-version"),
  commit: document.querySelector("#commit-version"),
  resultEmpty: document.querySelector("#result-empty"),
  resultContent: document.querySelector("#result-content"),
  resultError: document.querySelector("#result-error"),
  original: document.querySelector("#original-output"),
  normalized: document.querySelector("#normalized-output"),
  changedBadge: document.querySelector("#changed-badge"),
  duration: document.querySelector("#metric-duration"),
  viewCount: document.querySelector("#metric-views"),
  editCount: document.querySelector("#metric-edits"),
  truncated: document.querySelector("#metric-truncated"),
  rules: document.querySelector("#rules-list"),
  edits: document.querySelector("#edits-list"),
  views: document.querySelector("#views-list"),
  experimentalNote: document.querySelector("#experimental-note"),
};

const ruleNames = {
  remove_hangul_zwsp: "한글 인접 ZWSP 제거",
  compose_modern_jamo: "현대 조합형 자모 결합",
  compose_compat_jamo: "호환 자모 결합",
};

function selectedPreset() {
  return document.querySelector('input[name="preset"]:checked').value;
}

function setStatus(message, mode = "loading") {
  elements.status.textContent = message;
  elements.statusDot.dataset.mode = mode;
}

function setBusy(busy) {
  state.busy = busy;
  elements.submit.disabled = busy || !state.ready;
  elements.submit.querySelector("span").textContent = busy ? "분석 중" : "분석하기";
}

function updateCharacterCount() {
  const length = Array.from(elements.input.value).length;
  elements.count.textContent = `${length.toLocaleString()} / ${state.maxInputLength.toLocaleString()}`;
  elements.count.classList.toggle("over-limit", length > state.maxInputLength);
}

function showError(message) {
  elements.resultEmpty.hidden = true;
  elements.resultContent.hidden = true;
  elements.resultError.hidden = false;
  elements.resultError.querySelector("p").textContent = message;
}

function createText(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  node.textContent = text;
  return node;
}

function renderRules(rules) {
  elements.rules.replaceChildren();
  if (!rules.length) {
    elements.rules.append(createText("span", "muted-copy", "적용된 무손실 규칙이 없습니다."));
    return;
  }
  rules.forEach((rule) => {
    elements.rules.append(createText("span", "rule-chip", ruleNames[rule] || rule));
  });
}

function renderEdits(edits) {
  elements.edits.replaceChildren();
  if (!edits.length) {
    elements.edits.append(createText("p", "muted-copy", "변경 구간이 없습니다."));
    return;
  }
  edits.forEach((edit) => {
    const item = document.createElement("article");
    item.className = "edit-item";
    const heading = document.createElement("div");
    heading.className = "edit-heading";
    heading.append(
      createText("strong", "", ruleNames[edit.rule_id] || edit.rule_id),
      createText("span", "range", `${edit.source_start}:${edit.source_end}`),
    );
    const change = document.createElement("div");
    change.className = "edit-change";
    change.append(
      createText("code", "before", edit.before || "∅"),
      createText("span", "arrow", "→"),
      createText("code", "after", edit.after || "∅"),
    );
    item.append(heading, change);
    elements.edits.append(item);
  });
}

function metadataSummary(metadata) {
  const visible = metadata.filter((item) =>
    ["replacement_count", "tense_ratio", "generator_version", "rules"].includes(item.key),
  );
  return visible.map((item) => `${item.key}: ${item.value}`).join(" · ");
}

function renderViews(views) {
  elements.views.replaceChildren();
  views.forEach((view) => {
    const item = document.createElement("article");
    item.className = "view-item";
    const header = document.createElement("div");
    header.className = "view-heading";
    const badges = document.createElement("div");
    badges.className = "view-badges";
    badges.append(
      createText("span", `view-index ${view.kind}`, `VIEW ${view.index}`),
      createText("span", "provider-name", view.provider),
    );
    if (view.lossy) badges.append(createText("span", "lossy-badge", "LOSSY"));
    header.append(badges, createText("span", "view-kind", view.kind));
    item.append(header, createText("pre", "view-text", view.text || "(빈 문자열)"));
    const summary = metadataSummary(view.metadata);
    if (summary) item.append(createText("p", "metadata", summary));
    elements.views.append(item);
  });
}

function renderResult(result, roundTripMs) {
  elements.resultEmpty.hidden = true;
  elements.resultError.hidden = true;
  elements.resultContent.hidden = false;
  elements.original.textContent = result.original || "(빈 문자열)";
  elements.normalized.textContent = result.normalized || "(빈 문자열)";
  elements.changedBadge.textContent = result.changed ? "변경됨" : "변경 없음";
  elements.changedBadge.dataset.changed = String(result.changed);
  elements.duration.textContent = `${result.duration_ms.toFixed(3)} ms`;
  elements.duration.title = `Worker 왕복 ${roundTripMs.toFixed(1)} ms`;
  elements.viewCount.textContent = result.views.length.toLocaleString();
  elements.editCount.textContent = result.normalization.edits.length.toLocaleString();
  elements.truncated.textContent = result.truncated ? "예" : "아니요";
  elements.truncated.dataset.warning = String(result.truncated);
  renderRules(result.normalization.applied_rules);
  renderEdits(result.normalization.edits);
  renderViews(result.views);
}

let requestStartedAt = 0;
worker.onmessage = (event) => {
  const { type, message, manifest, runtime, result, requestId } = event.data || {};
  if (type === "status") {
    setStatus(message, "loading");
    return;
  }
  if (type === "ready") {
    state.ready = true;
    state.maxInputLength = runtime.max_input_length;
    elements.input.maxLength = runtime.max_input_length;
    elements.packageVersion.textContent = `v${runtime.package_version}`;
    elements.commit.textContent = manifest.commit.slice(0, 7);
    setStatus("브라우저에서 실행 준비 완료", "ready");
    setBusy(false);
    updateCharacterCount();
    return;
  }
  if (type === "result" && requestId === state.requestId) {
    renderResult(result, performance.now() - requestStartedAt);
    setBusy(false);
    setStatus("분석 완료", "ready");
    return;
  }
  if (type === "error" && (!requestId || requestId === state.requestId)) {
    state.ready = Boolean(requestId);
    setBusy(false);
    setStatus("실행 오류", "error");
    showError(message || "알 수 없는 오류가 발생했습니다.");
  }
};

worker.onerror = () => {
  state.ready = false;
  setBusy(false);
  setStatus("Worker를 시작하지 못했습니다", "error");
  showError("브라우저가 데모 Worker를 시작하지 못했습니다. 페이지를 새로고침해 주세요.");
};

elements.form.addEventListener("submit", (event) => {
  event.preventDefault();
  if (!state.ready || state.busy) return;
  const text = elements.input.value;
  if (Array.from(text).length > state.maxInputLength) {
    showError(`입력은 ${state.maxInputLength.toLocaleString()}자 이하여야 합니다.`);
    return;
  }
  state.requestId += 1;
  requestStartedAt = performance.now();
  setBusy(true);
  setStatus("입력을 분석하고 있습니다", "loading");
  worker.postMessage({
    type: "analyze",
    requestId: state.requestId,
    payload: { text, preset: selectedPreset() },
  });
});

elements.input.addEventListener("input", updateCharacterCount);

document.querySelectorAll("[data-example]").forEach((button) => {
  button.addEventListener("click", () => {
    elements.input.value = button.dataset.example;
    elements.input.focus();
    updateCharacterCount();
  });
});

document.querySelectorAll('input[name="preset"]').forEach((input) => {
  input.addEventListener("change", () => {
    elements.experimentalNote.hidden = selectedPreset() !== "experimental";
  });
});

updateCharacterCount();
worker.postMessage({ type: "init" });
