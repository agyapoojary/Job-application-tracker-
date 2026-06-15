document.addEventListener("DOMContentLoaded", () => {
  if (window.lucide) window.lucide.createIcons();

  bindThemeToggle();
  bindCounters();
  bindResumeUpload();
  bindResumeAnalysis();
  bindCoverLetter();
  bindKanban();
  bindTrackerForm();
});

function bindThemeToggle() {
  const themeToggle = document.querySelector("#themeToggle");
  if (localStorage.getItem("careerai-theme") === "dark") document.body.classList.add("dark");
  themeToggle?.addEventListener("click", () => {
    document.body.classList.toggle("dark");
    localStorage.setItem("careerai-theme", document.body.classList.contains("dark") ? "dark" : "light");
  });
}

function bindCounters() {
  document.querySelectorAll(".counter").forEach((counter) => {
    const raw = Number(counter.dataset.target || "0");
    if (!Number.isFinite(raw)) return;
    const hasPercent = counter.textContent.includes("%");
    let current = 0;
    const step = Math.max(1, Math.ceil(raw / 28));
    const timer = window.setInterval(() => {
      current = Math.min(raw, current + step);
      counter.textContent = `${current}${hasPercent ? "%" : ""}`;
      if (current >= raw) window.clearInterval(timer);
    }, 22);
  });
}

function bindResumeUpload() {
  const input = document.querySelector("#resumeFileInput");
  const dropZone = document.querySelector("#resumeDropZone");
  const label = document.querySelector("#resumeFileName");
  input?.addEventListener("change", () => {
    const file = input.files?.[0];
    if (file && label) label.textContent = `Selected: ${file.name}`;
  });
  if (!dropZone || !input) return;
  ["dragenter", "dragover"].forEach((eventName) => {
    dropZone.addEventListener(eventName, (event) => {
      event.preventDefault();
      dropZone.classList.add("drag-over");
    });
  });
  ["dragleave", "drop"].forEach((eventName) => {
    dropZone.addEventListener(eventName, (event) => {
      event.preventDefault();
      dropZone.classList.remove("drag-over");
    });
  });
  dropZone.addEventListener("drop", (event) => {
    const file = event.dataTransfer?.files?.[0];
    if (!file) return;
    const transfer = new DataTransfer();
    transfer.items.add(file);
    input.files = transfer.files;
    if (label) label.textContent = `Selected: ${file.name}`;
  });
}

function bindResumeAnalysis() {
  const form = document.querySelector("#resumeAnalysisForm");
  if (!form) return;
  const progress = document.querySelector("#analysisProgress");
  const button = document.querySelector("#analyzeResumeBtn");
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const formData = new FormData(form);
    button.disabled = true;
    showProgress(progress);
    try {
      const response = await fetch("/api/resume/analyze", { method: "POST", body: formData });
      const payload = await response.json();
      await setProgressStep(4);
      if (!response.ok || !payload.ok) throw new Error(payload.error || "Resume analysis failed.");
      renderAnalysis(payload.analysis);
      renderHistory(payload.history || []);
    } catch (error) {
      alert(error.message);
    } finally {
      button.disabled = false;
      progress?.classList.add("hidden");
      if (window.lucide) window.lucide.createIcons();
    }
  });
}

async function showProgress(progress) {
  progress?.classList.remove("hidden");
  document.querySelectorAll(".progress-steps li").forEach((item) => item.classList.remove("active"));
  await setProgressStep(1);
  await delay(350);
  await setProgressStep(2);
  await delay(350);
  await setProgressStep(3);
}

function setProgressStep(step) {
  document.querySelectorAll(".progress-steps li").forEach((item) => {
    item.classList.toggle("active", Number(item.dataset.step) <= step);
  });
  return Promise.resolve();
}

function delay(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function renderAnalysis(analysis) {
  window.latestResumeAnalysis = analysis;
  const results = document.querySelector("#analysisResults");
  results?.classList.remove("hidden");
  setText("#analysisFilename", analysis.filename || "Typed resume text");
  setText("#atsScore", `${analysis.ats_score}%`);
  const gauge = document.querySelector("#scoreGauge");
  if (gauge) {
    gauge.style.setProperty("--value", analysis.resume_score || 0);
    const span = gauge.querySelector("span");
    if (span) span.textContent = `${analysis.resume_score || 0}%`;
  }
  setBar("#atsBar", analysis.ats_score);
  renderChips("#missingSkills", analysis.missing_skills, "No missing skills returned.");
  renderChips("#recommendedRoles", analysis.recommended_roles, "No recommended roles returned.");
  renderList("#strengthsList", analysis.strengths);
  renderList("#weaknessesList", analysis.weaknesses);
  renderList("#suggestionsList", analysis.suggestions);
  document.querySelector("#downloadAnalysisBtn")?.addEventListener("click", downloadAnalysis, { once: true });
  results?.scrollIntoView({ behavior: "smooth", block: "start" });
}

function setText(selector, value) {
  const element = document.querySelector(selector);
  if (element) element.textContent = value;
}

function setBar(selector, value) {
  const element = document.querySelector(selector);
  if (element) element.style.width = `${Math.max(0, Math.min(100, Number(value) || 0))}%`;
}

function renderChips(selector, values, emptyText) {
  const container = document.querySelector(selector);
  if (!container) return;
  const list = Array.isArray(values) && values.length ? values : [emptyText];
  container.innerHTML = list.map((value) => `<span>${escapeHtml(value)}</span>`).join("");
}

function renderList(selector, values) {
  const container = document.querySelector(selector);
  if (!container) return;
  const list = Array.isArray(values) && values.length ? values : ["No details returned."];
  container.innerHTML = list.map((value) => `<li>${escapeHtml(value)}</li>`).join("");
}

function renderHistory(history) {
  const tbody = document.querySelector("#analysisHistoryTable tbody");
  if (!tbody) return;
  tbody.innerHTML = history.map((item) => `
    <tr data-strengths="${escapeAttr((item.strengths || []).join(", "))}" data-weaknesses="${escapeAttr((item.weaknesses || []).join(", "))}" data-missing="${escapeAttr((item.missing_skills || []).join(", "))}" data-suggestions="${escapeAttr((item.suggestions || []).join(", "))}" data-roles="${escapeAttr((item.recommended_roles || []).join(", "))}">
      <td>${escapeHtml(item.analysis_date || "")}</td>
      <td>${escapeHtml(item.filename || "Uploaded resume")}</td>
      <td><strong>${escapeHtml(String(item.resume_score || 0))}%</strong></td>
      <td>${escapeHtml(String(item.ats_score || 0))}%</td>
      <td><button class="small-btn view-history-btn" type="button">View Details</button></td>
    </tr>
  `).join("");
  bindHistoryButtons();
}

function bindHistoryButtons() {
  document.querySelectorAll(".view-history-btn").forEach((button) => {
    button.addEventListener("click", () => {
      const row = button.closest("tr");
      const strengths = row?.dataset.strengths || "None";
      const weaknesses = row?.dataset.weaknesses || "None";
      const missing = row?.dataset.missing || "None";
      const suggestions = row?.dataset.suggestions || "None";
      const roles = row?.dataset.roles || "None";
      alert(`Strengths: ${strengths}\nWeaknesses: ${weaknesses}\nMissing Skills: ${missing}\nSuggestions: ${suggestions}\nRecommended Roles: ${roles}`);
    });
  });
}

function downloadAnalysis() {
  const analysis = window.latestResumeAnalysis;
  if (!analysis) return;
  const blob = new Blob([JSON.stringify(analysis, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "careerai-resume-analysis.json";
  link.click();
  URL.revokeObjectURL(url);
}

function bindCoverLetter() {
  const form = document.querySelector("#coverLetterForm");
  const regenerate = document.querySelector("#regenerateLetterBtn");
  const copy = document.querySelector(".copy-letter");
  form?.addEventListener("submit", generateCoverLetter);
  regenerate?.addEventListener("click", () => form?.requestSubmit());
  copy?.addEventListener("click", async () => {
    const letter = document.querySelector("#letterText")?.textContent || "";
    if (letter) await navigator.clipboard.writeText(letter);
  });
}

async function generateCoverLetter(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const button = document.querySelector("#generateLetterBtn");
  const loading = document.querySelector("#letterLoading");
  const warning = document.querySelector("#letterWarning");
  button.disabled = true;
  loading?.classList.remove("hidden");
  warning?.classList.add("hidden");
  try {
    const response = await fetch("/api/cover-letter", { method: "POST", body: new FormData(form) });
    const payload = await response.json();
    if (!response.ok || !payload.ok) throw new Error(payload.error || "Cover letter generation failed.");
    document.querySelector("#letterEmpty")?.classList.add("hidden");
    const letter = document.querySelector("#letterText");
    if (letter) {
      letter.classList.remove("hidden");
      letter.textContent = payload.letter;
    }
    if (payload.warning && warning) {
      warning.textContent = `Fallback used: ${payload.warning}`;
      warning.classList.remove("hidden");
    }
  } catch (error) {
    if (warning) {
      warning.textContent = error.message;
      warning.classList.remove("hidden");
    }
  } finally {
    button.disabled = false;
    loading?.classList.add("hidden");
  }
}

function bindKanban() {
  if (!window.Sortable) return;
  document.querySelectorAll(".sortable-list").forEach((list) => {
    new Sortable(list, {
      group: "applications",
      animation: 160,
      ghostClass: "sortable-ghost",
      onEnd: async (event) => {
        const card = event.item;
        const status = card.closest(".kanban-col")?.dataset.status;
        const id = card.dataset.id;
        updateKanbanCounts();
        if (!id || !status) return;
        const response = await fetch(`/applications/${id}/status`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ status }),
        });
        if (!response.ok) window.location.reload();
      },
    });
  });
}

function bindTrackerForm() {
  document.querySelector("#addCardBtn")?.addEventListener("click", () => {
    document.querySelector("#addApplicationForm")?.classList.remove("hidden");
  });
  document.querySelector("#cancelAddBtn")?.addEventListener("click", () => {
    document.querySelector("#addApplicationForm")?.classList.add("hidden");
  });
  bindHistoryButtons();
}

function updateKanbanCounts() {
  document.querySelectorAll(".kanban-col").forEach((column) => {
    const count = column.querySelectorAll(".kanban-card").length;
    const badge = column.querySelector("header b");
    if (badge) badge.textContent = count;
  });
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttr(value) {
  return escapeHtml(value).replaceAll("\n", " ");
}
