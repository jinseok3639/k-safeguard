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
  inputInspector: document.querySelector("#input-inspector"),
  inputKindSummary: document.querySelector("#input-kind-summary"),
  inputVisual: document.querySelector("#input-visual"),
  spacedJamo: document.querySelector("#spaced-jamo-toggle"),
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
  candidateSection: document.querySelector("#candidate-section"),
  candidate: document.querySelector("#candidate-output"),
  changedBadge: document.querySelector("#changed-badge"),
  duration: document.querySelector("#metric-duration"),
  editCount: document.querySelector("#metric-edits"),
  truncated: document.querySelector("#metric-truncated"),
  rules: document.querySelector("#rules-list"),
  edits: document.querySelector("#edits-list"),
};

const ruleNames = {
  remove_hangul_zwsp: "한글 인접 ZWSP 제거",
  compose_modern_jamo: "현대 조합형 자모 결합",
  compose_compat_jamo: "호환 자모 결합",
  normalize_halfwidth_hangul: "반각 한글 정규화",
};

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

function isModernJamo(codePoint) {
  return (
    (codePoint >= 0x1100 && codePoint <= 0x11ff) ||
    (codePoint >= 0xa960 && codePoint <= 0xa97f) ||
    (codePoint >= 0xd7b0 && codePoint <= 0xd7ff)
  );
}

function isCompatibilityJamo(codePoint) {
  return codePoint >= 0x3130 && codePoint <= 0x318f;
}

function updateInputInspector() {
  const characters = Array.from(elements.input.value);
  let zwspCount = 0;
  let modernJamoCount = 0;
  let compatibilityJamoCount = 0;

  const visual = characters.map((character) => {
    const codePoint = character.codePointAt(0);
    if (codePoint === 0x200b) {
      zwspCount += 1;
      return "⟦ZWSP⟧";
    }
    if (isModernJamo(codePoint)) {
      modernJamoCount += 1;
      return `⟦U+${codePoint.toString(16).toUpperCase().padStart(4, "0")}⟧`;
    }
    if (isCompatibilityJamo(codePoint)) compatibilityJamoCount += 1;
    return character;
  }).join("");

  const summary = [];
  if (zwspCount) summary.push(`ZWSP ${zwspCount}개`);
  if (modernJamoCount) summary.push(`조합형 자모 ${modernJamoCount}개`);
  if (compatibilityJamoCount) summary.push(`호환 자모 ${compatibilityJamoCount}개`);

  elements.inputInspector.hidden = summary.length === 0;
  elements.inputKindSummary.textContent = summary.join(" · ");
  elements.inputVisual.textContent = visual;
}

function updateInputDetails() {
  updateCharacterCount();
  updateInputInspector();
}

function showError(message) {
  elements.resultEmpty.hidden = true;
  elements.resultContent.hidden = true;
  elements.resultError.hidden = false;
  elements.resultError.querySelector("p").textContent = message;
  elements.candidateSection.hidden = true;
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

function renderResult(result, roundTripMs) {
  elements.resultEmpty.hidden = true;
  elements.resultError.hidden = true;
  elements.resultContent.hidden = false;
  elements.original.textContent = result.original || "(빈 문자열)";
  elements.normalized.textContent = result.normalized || "(빈 문자열)";
  elements.candidateSection.hidden = !result.candidate;
  elements.candidate.textContent = result.candidate?.text || "";
  elements.changedBadge.textContent = result.changed ? "변경됨" : "변경 없음";
  elements.changedBadge.dataset.changed = String(result.changed);
  elements.duration.textContent = `${result.duration_ms.toFixed(3)} ms`;
  elements.duration.title = `Worker 왕복 ${roundTripMs.toFixed(1)} ms`;
  elements.editCount.textContent = result.normalization.edits.length.toLocaleString();
  elements.truncated.textContent = result.truncated ? "예" : "아니요";
  elements.truncated.dataset.warning = String(result.truncated);
  renderRules(result.normalization.applied_rules);
  renderEdits(result.normalization.edits);
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
    updateInputDetails();
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
    payload: { text, spaced_jamo: elements.spacedJamo.checked },
  });
});

elements.input.addEventListener("input", updateInputDetails);

document.querySelectorAll("[data-example]").forEach((button) => {
  button.addEventListener("click", () => {
    elements.input.value = button.dataset.example;
    elements.spacedJamo.checked = button.dataset.spacedJamo === "true";
    elements.input.focus();
    updateInputDetails();
  });
});

updateInputDetails();
worker.postMessage({ type: "init" });
