const $ = (id) => document.getElementById(id);

async function api(url, opts = {}) {
  const res = await fetch(url, {
    headers: opts.body instanceof FormData ? undefined : { "Content-Type": "application/json" },
    ...opts,
  });
  const data = await res.json().catch(() => ({ ok: false, error: `HTTP ${res.status}` }));
  if (!res.ok && data.ok !== true) {
    throw new Error(data.error || `HTTP ${res.status}`);
  }
  return data;
}

function dialect() {
  return $("dialect").value || "wenchang";
}

function setLog(el, obj) {
  el.textContent = typeof obj === "string" ? obj : JSON.stringify(obj, null, 2);
}

async function pollJob(jobId, logEl) {
  $("jobBadge").textContent = `任务 ${jobId.slice(-8)}…`;
  $("jobBadge").classList.add("on");
  for (;;) {
    const data = await api(`/api/jobs/${jobId}`);
    const job = data.job;
    setLog(logEl, job);
    setLog($("jobLog"), job);
    if (job.status === "ok" || job.status === "error") {
      $("jobBadge").textContent = job.status === "ok" ? "任务完成" : "任务失败";
      $("jobBadge").classList.toggle("on", job.status === "ok");
      await refreshDialect();
      return job;
    }
    await new Promise((r) => setTimeout(r, 900));
  }
}

async function refreshStatus() {
  const st = await api("/api/status");
  $("verBadge").textContent = `corpus-kit ${st.version}`;
  $("pathBadge").textContent = st.dialect_assets;
  const sel = $("dialect");
  const cur = sel.value || "wenchang";
  sel.innerHTML = "";
  const dialects = st.dialects?.length ? st.dialects : ["wenchang"];
  for (const d of dialects) {
    const opt = document.createElement("option");
    opt.value = d;
    opt.textContent = d;
    sel.appendChild(opt);
  }
  if ([...sel.options].some((o) => o.value === cur)) sel.value = cur;
  else if ([...sel.options].some((o) => o.value === "wenchang")) sel.value = "wenchang";
  $("jobBadge").textContent = st.jobs_running ? `运行中 ${st.jobs_running}` : "任务空闲";
  await refreshDialect();
}

function renderMedia(media) {
  const box = $("mediaList");
  box.innerHTML = "";
  const groups = [
    ["inbox", media.inbox || []],
    ["video", media.video || []],
    ["wav16k", media.wav16k || []],
  ];
  for (const [kind, items] of groups) {
    if (!items.length) continue;
    const head = document.createElement("button");
    head.type = "button";
    head.textContent = `── ${kind}/ (${items.length}) ──`;
    head.disabled = true;
    head.style.opacity = "0.7";
    box.appendChild(head);
    for (const it of items) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = `${it.rel}  (${Math.round(it.size / 1024)} KB)`;
      btn.title = it.path;
      btn.addEventListener("click", () => {
        const dir = it.path.replace(/\/[^/]+$/, "") || it.path;
        if (kind === "inbox" || kind === "video") $("mineInput").value = dir;
        if ([".mp4", ".mkv", ".mov", ".webm", ".avi", ".m4v"].includes(it.suffix)) {
          $("ocrInput").value = it.path;
        }
        $("ingestInput").value = it.path;
      });
      box.appendChild(btn);
    }
  }
  if (!box.children.length) {
    const empty = document.createElement("button");
    empty.type = "button";
    empty.disabled = true;
    empty.textContent = "暂无媒资，可上传到 inbox/ 或 video/";
    box.appendChild(empty);
  }
}

async function refreshDialect() {
  const d = dialect();
  const data = await api(`/api/dialect/${encodeURIComponent(d)}`);
  const m = data.manifest || {};
  $("stats").innerHTML = `
    <span>dialect: <strong>${d}</strong></span>
    <span>manifest: <strong>${m.count || 0}</strong></span>
    <span>有文本: <strong>${m.with_text || 0}</strong></span>
    <span>root: ${data.root || ""}</span>
  `;
  renderMedia(data.media || {});
  if (!( $("ocrInput").value || "").trim() && data.root) {
    $("ocrInput").placeholder = `${data.root}/video/`;
  }
}

document.querySelectorAll(".tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".panel").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    $(btn.dataset.tab).classList.add("active");
  });
});

$("dialect").addEventListener("change", refreshDialect);
$("btnRefresh").addEventListener("click", refreshStatus);

$("btnInit").addEventListener("click", async () => {
  const name = $("newDialect").value.trim();
  if (!name) return alert("填写方言名");
  const data = await api("/api/init", { method: "POST", body: JSON.stringify({ dialect: name }) });
  setLog($("jobLog"), data);
  await refreshStatus();
  $("dialect").value = name;
  await refreshDialect();
});

$("btnUpload").addEventListener("click", async () => {
  const files = $("uploadFile").files;
  if (!files?.length) return alert("选择文件");
  const fd = new FormData();
  fd.append("dialect", dialect());
  fd.append("dest", $("uploadDest").value);
  for (const f of files) fd.append("file", f);
  $("btnUpload").disabled = true;
  try {
    const data = await api("/api/upload", { method: "POST", body: fd });
    setLog($("jobLog"), data);
    await refreshDialect();
  } catch (err) {
    setLog($("jobLog"), String(err.message || err));
  } finally {
    $("btnUpload").disabled = false;
  }
});

$("btnMine").addEventListener("click", async () => {
  $("btnMine").disabled = true;
  setLog($("mineLog"), "提交 mine…");
  try {
    const payload = {
      dialect: dialect(),
      input: $("mineInput").value.trim() || null,
      speaker: $("mineSpeaker").value.trim(),
      locale: $("mineLocale").value.trim(),
      license_note: $("mineLicense").value.trim() || "local_media_drop",
      split: $("mineSplit").value,
      min_sec: Number($("mineMinSec").value),
      max_sec: Number($("mineMaxSec").value),
      require_text: $("mineRequireText").checked,
      ocr_hardsubs: $("mineOcr").checked,
      no_subs: $("mineNoSubs").checked,
      ocr_band: $("mineOcrBand").value.trim(),
      ocr_region: $("mineOcrRegion").value.trim() || null,
      ocr_interval: Number($("mineOcrInterval").value),
      ocr_min_score: Number($("mineOcrMinScore").value),
    };
    const data = await api("/api/mine", { method: "POST", body: JSON.stringify(payload) });
    await pollJob(data.job_id, $("mineLog"));
  } catch (err) {
    setLog($("mineLog"), String(err.message || err));
  } finally {
    $("btnMine").disabled = false;
  }
});

$("btnOcr").addEventListener("click", async () => {
  $("btnOcr").disabled = true;
  setLog($("ocrLog"), "提交 OCR…");
  try {
    const payload = {
      input: $("ocrInput").value.trim(),
      ocr_band: $("ocrBand").value.trim(),
      ocr_region: $("ocrRegion").value.trim() || null,
      ocr_interval: Number($("ocrInterval").value),
      ocr_min_score: Number($("ocrMinScore").value),
    };
    const data = await api("/api/ocr", { method: "POST", body: JSON.stringify(payload) });
    await pollJob(data.job_id, $("ocrLog"));
  } catch (err) {
    setLog($("ocrLog"), String(err.message || err));
  } finally {
    $("btnOcr").disabled = false;
  }
});

$("btnCrawl").addEventListener("click", async () => {
  $("btnCrawl").disabled = true;
  setLog($("crawlLog"), "提交 crawl…");
  try {
    const payload = {
      dialect: dialect(),
      url: $("crawlUrl").value.trim(),
      urls: $("crawlUrls").value,
      license_note: $("crawlLicense").value.trim(),
      i_have_rights: $("crawlRights").checked,
      speaker: $("crawlSpeaker").value.trim(),
      locale: $("crawlLocale").value.trim(),
      allow_empty_text: $("crawlAllowEmpty").checked,
      no_auto_subs: $("crawlNoAutoSubs").checked,
      cookies_from_browser: $("crawlCookies").value.trim(),
      max_downloads: Number($("crawlMax").value),
    };
    const data = await api("/api/crawl", { method: "POST", body: JSON.stringify(payload) });
    await pollJob(data.job_id, $("crawlLog"));
  } catch (err) {
    setLog($("crawlLog"), String(err.message || err));
  } finally {
    $("btnCrawl").disabled = false;
  }
});

$("btnIngest").addEventListener("click", async () => {
  $("btnIngest").disabled = true;
  setLog($("ingestLog"), "提交 ingest…");
  try {
    const payload = {
      dialect: dialect(),
      input: $("ingestInput").value.trim(),
      speaker: $("ingestSpeaker").value.trim(),
      locale: $("ingestLocale").value.trim(),
      text_from_filename: $("ingestFromName").checked,
      skip_copy: $("ingestSkipCopy").checked,
    };
    const data = await api("/api/ingest", { method: "POST", body: JSON.stringify(payload) });
    await pollJob(data.job_id, $("ingestLog"));
  } catch (err) {
    setLog($("ingestLog"), String(err.message || err));
  } finally {
    $("btnIngest").disabled = false;
  }
});

async function simpleJob(btn, endpoint, logEl, extra = {}) {
  btn.disabled = true;
  setLog(logEl, `提交 ${endpoint}…`);
  try {
    const data = await api(endpoint, {
      method: "POST",
      body: JSON.stringify({ dialect: dialect(), ...extra }),
    });
    await pollJob(data.job_id, logEl);
  } catch (err) {
    setLog(logEl, String(err.message || err));
  } finally {
    btn.disabled = false;
  }
}

$("btnQc").addEventListener("click", () => simpleJob($("btnQc"), "/api/qc", $("opsLog")));
$("btnTranscode").addEventListener("click", () => simpleJob($("btnTranscode"), "/api/transcode", $("opsLog")));
$("btnSlim").addEventListener("click", () => simpleJob($("btnSlim"), "/api/slim", $("opsLog")));

$("btnManifest").addEventListener("click", async () => {
  try {
    const data = await api(`/api/manifest?dialect=${encodeURIComponent(dialect())}&limit=60`);
    setLog($("manifestLog"), { total: data.total, path: data.path, preview: data.items });
    setLog($("opsLog"), `已加载 ${data.total} 条（预览 ${data.items.length}）`);
  } catch (err) {
    setLog($("opsLog"), String(err.message || err));
  }
});

refreshStatus().catch((err) => setLog($("jobLog"), String(err.message || err)));
