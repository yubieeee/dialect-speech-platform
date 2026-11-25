const $ = (id) => document.getElementById(id);

const TRAIN_FIELDS = [
  "exp_name", "model", "train_engine", "cuda_visible_devices", "pretrained_model_dir",
  "train_data_list", "cv_data_list", "data_instruct", "note", "ref_model",
  "lr", "optim", "scheduler", "warmup_steps", "max_epoch", "grad_clip", "accum_grad",
  "log_interval", "save_per_step", "gan_lr", "gan_lr_d", "gan_accum_grad",
  "num_workers", "prefetch", "batch_type", "max_frames_in_batch",
  "filter_max_length", "filter_min_length", "token_max_length", "token_min_length",
  "shuffle_size", "sort_size", "truncate_length", "average_num",
  "top_p", "top_k", "win_size", "tau_r", "training_cfg_rate", "inference_cfg_rate",
  "chunk_size", "num_decoding_left_chunks", "nnodes", "nproc_per_node",
  "rdzv_endpoint", "dist_backend",
  "ds_micro_batch_size", "ds_gradient_accumulation_steps", "ds_gradient_clipping",
  "ds_zero_stage", "ds_lr", "ds_weight_decay", "ds_save_states",
];

const TRAIN_BOOLS = ["dpo", "pin_memory", "use_amp", "use_spk_embedding"];
const TRAIN_NUMS = new Set([
  "lr", "warmup_steps", "max_epoch", "grad_clip", "accum_grad", "log_interval", "save_per_step",
  "gan_lr", "gan_lr_d", "gan_accum_grad", "num_workers", "prefetch", "max_frames_in_batch",
  "filter_max_length", "filter_min_length", "token_max_length", "token_min_length",
  "shuffle_size", "sort_size", "truncate_length", "average_num",
  "top_p", "top_k", "win_size", "tau_r", "training_cfg_rate", "inference_cfg_rate",
  "chunk_size", "num_decoding_left_chunks", "nnodes", "nproc_per_node",
  "ds_micro_batch_size", "ds_gradient_accumulation_steps", "ds_gradient_clipping",
  "ds_zero_stage", "ds_lr", "ds_weight_decay",
]);

let statusCache = null;
/** 最近一次合成的预览路径（未保存到 evals） */
let lastPreview = null;

/** 与 dialect-assets/wenchang/sentences/eval_bank_v0.json 对齐；API 失败时兜底 */
const EVAL_BANK_FALLBACK = [
  { id: "E01", text: "老乡你好，今天想办什么业务？", scene: "迎客" },
  { id: "E02", text: "密码千万不要随便告诉别人，银行卡要亲自保管好。", scene: "安全" },
  { id: "E03", text: "业务办理结束啦，请收好你的证件、存折或者银行卡。", scene: "结束" },
  { id: "E04", text: "请确认转账金额是一万二千三百元整。", scene: "金额" },
  { id: "E05", text: "您的预约时间是明天下午三点半。", scene: "日期时间" },
];

function fillEvalSentenceSelect(sentences) {
  const evalSel = $("eval_sentence");
  if (!evalSel) return;
  const prevEval = evalSel.value;
  const items = sentences && sentences.length ? sentences : EVAL_BANK_FALLBACK;
  evalSel.innerHTML = "";
  const evalEmpty = document.createElement("option");
  evalEmpty.value = "";
  evalEmpty.textContent = "（手输 / 选择冻结评测句）";
  evalSel.appendChild(evalEmpty);
  for (const item of items) {
    const opt = document.createElement("option");
    opt.value = item.id;
    opt.textContent = `${item.id} · ${item.scene || ""} · ${item.text}`;
    opt.dataset.text = item.text;
    evalSel.appendChild(opt);
  }
  if (prevEval && [...evalSel.options].some((o) => o.value === prevEval)) {
    evalSel.value = prevEval;
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

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    ...opts,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok && data.ok !== true) {
    const err = data.error || res.statusText || "request failed";
    throw new Error(err);
  }
  return data;
}

function fillTrain(params) {
  for (const key of TRAIN_FIELDS) {
    const el = $("t_" + key);
    if (!el || params[key] === undefined) continue;
    el.value = params[key];
  }
  for (const key of TRAIN_BOOLS) {
    const el = $("t_" + key);
    if (el) el.checked = Boolean(params[key]);
  }
}

function readTrain() {
  const params = {};
  for (const key of TRAIN_FIELDS) {
    const el = $("t_" + key);
    if (!el) continue;
    let v = el.value;
    if (TRAIN_NUMS.has(key) && v !== "") v = Number(v);
    params[key] = v;
  }
  for (const key of TRAIN_BOOLS) {
    params[key] = $("t_" + key).checked;
  }
  return params;
}

function renderRefs(items) {
  const box = $("refList");
  box.innerHTML = "";
  if (!items.length) {
    box.innerHTML = "<button type='button' disabled>暂无参考音，请上传或放到 dialect-assets/wenchang/refs</button>";
    return;
  }
  for (const item of items) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = `${item.name}  ·  ${(item.size / 1024).toFixed(1)} KB`;
    btn.title = item.path;
    btn.addEventListener("click", () => {
      $("prompt_wav").value = item.path;
    });
    box.appendChild(btn);
  }
}

function renderEvals(items) {
  const box = $("evalList");
  box.innerHTML = "";
  for (const item of items.slice().reverse()) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = item.name;
    btn.addEventListener("click", async () => {
      $("histPlayer").src = `/media?path=${encodeURIComponent(item.path)}`;
      $("histPlayer").play().catch(() => {});
      const metaPath = item.path.replace(/\.wav$/i, ".json");
      try {
        const metaRes = await fetch(`/media?path=${encodeURIComponent(metaPath)}`);
        if (metaRes.ok) {
          $("histLog").textContent = await metaRes.text();
        } else {
          $("histLog").textContent = item.path;
        }
      } catch {
        $("histLog").textContent = item.path;
      }
    });
    box.appendChild(btn);
  }
}

async function refreshStatus() {
  statusCache = await api("/api/status");
  const ready = statusCache.ready;
  $("readyBadge").textContent = ready ? "模型已加载" : "模型未加载";
  $("readyBadge").classList.toggle("on", ready);
  $("pathBadge").textContent = statusCache.model_dir || "";
  renderRefs(statusCache.refs || []);
  renderEvals(statusCache.evals || []);

  const preset = $("instruct_preset");
  preset.innerHTML = "";
  const empty = document.createElement("option");
  empty.value = "";
  empty.textContent = "（选择预设填入 instruct）";
  preset.appendChild(empty);
  for (const text of statusCache.instruct_presets || []) {
    const opt = document.createElement("option");
    opt.value = text;
    opt.textContent = text.replace("You are a helpful assistant. ", "").replace("<|endofprompt|>", "");
    preset.appendChild(opt);
  }

  fillEvalSentenceSelect(statusCache.eval_sentences);

  if ($("t_exp_name") && !$("t_exp_name").value) fillTrain(statusCache.train_defaults || {});
}

$("instruct_preset").addEventListener("change", (e) => {
  if (e.target.value) $("instruct_text").value = e.target.value;
});

$("eval_sentence")?.addEventListener("change", (e) => {
  const opt = e.target.selectedOptions[0];
  if (!opt || !opt.value) return;
  $("text").value = opt.dataset.text || opt.getAttribute("data-text") || "";
  $("note").value = opt.value;
});

// 首屏：即使 /api/status 尚未返回，下拉也有句可选
fillEvalSentenceSelect(EVAL_BANK_FALLBACK);

$("upload").addEventListener("change", async (e) => {
  const file = e.target.files?.[0];
  if (!file) return;
  const fd = new FormData();
  fd.append("file", file);
  $("inferMsg").textContent = "上传中…";
  const res = await fetch("/api/upload", { method: "POST", body: fd });
  const data = await res.json();
  if (!data.ok) {
    $("inferMsg").textContent = data.error || "上传失败";
    return;
  }
  $("prompt_wav").value = data.ref_copy || data.path;
  $("inferMsg").textContent = "上传完成";
  await refreshStatus();
});

$("btnLoad").addEventListener("click", async () => {
  $("btnLoad").disabled = true;
  $("inferMsg").textContent = "加载模型中（首次可能较慢）…";
  try {
    const data = await api("/api/load", {
      method: "POST",
      body: JSON.stringify({
        fp16: $("fp16").checked,
        load_trt: $("load_trt").checked,
        load_vllm: $("load_vllm").checked,
      }),
    });
    $("inferMsg").textContent = data.ok ? `已加载 · ${JSON.stringify(data.loaded_opts || {})}` : data.error;
    await refreshStatus();
  } catch (err) {
    $("inferMsg").textContent = String(err.message || err);
  } finally {
    $("btnLoad").disabled = false;
  }
});

$("btnSynth").addEventListener("click", async () => {
  $("btnSynth").disabled = true;
  $("btnSaveEval").disabled = true;
  lastPreview = null;
  $("inferMsg").textContent = "合成中…";
  $("inferLog").textContent = "…";
  try {
    const payload = {
      mode: $("mode").value,
      text: $("text").value,
      prompt_text: $("prompt_text").value,
      instruct_text: $("instruct_text").value,
      prompt_wav: $("prompt_wav").value,
      speed: Number($("speed").value),
      stream: $("stream").checked,
      text_frontend: $("text_frontend").checked,
      seed: Number($("seed").value),
      auto_prefix_prompt: $("auto_prefix_prompt").checked,
      auto_prefix_instruct: $("auto_prefix_instruct").checked,
      zero_shot_spk_id: $("zero_shot_spk_id").value,
      group: $("group").value,
      note: $("note").value,
      fp16: $("fp16").checked,
      load_trt: $("load_trt").checked,
      load_vllm: $("load_vllm").checked,
      persist: false,
    };
    const data = await api("/api/synthesize", { method: "POST", body: JSON.stringify(payload) });
    if (!data.ok) {
      $("inferMsg").textContent = data.error || "失败";
      $("inferLog").textContent = JSON.stringify(data, null, 2);
      return;
    }
    lastPreview = {
      wav_path: data.wav_path,
      mode: $("mode").value,
      group: $("group").value,
      note: $("note").value,
    };
    $("btnSaveEval").disabled = false;
    $("inferMsg").textContent =
      `完成 · ${data.duration_sec}s 音频 · 耗时 ${data.elapsed_sec}s（预览未写入 evals，可点「保存到 evals」）`;
    // cache-bust preview overwrite
    $("player").src = `${data.audio_url}${data.audio_url.includes("?") ? "&" : "?"}t=${Date.now()}`;
    $("player").play().catch(() => {});
    $("inferLog").textContent = JSON.stringify(data.meta, null, 2);
  } catch (err) {
    $("inferMsg").textContent = String(err.message || err);
    $("inferLog").textContent = String(err);
  } finally {
    $("btnSynth").disabled = false;
  }
});

$("btnSaveEval").addEventListener("click", async () => {
  if (!lastPreview?.wav_path) {
    $("inferMsg").textContent = "没有可保存的预览，请先合成";
    return;
  }
  $("btnSaveEval").disabled = true;
  $("inferMsg").textContent = "保存到 evals…";
  try {
    const data = await api("/api/save_eval", {
      method: "POST",
      body: JSON.stringify({
        wav_path: lastPreview.wav_path,
        mode: lastPreview.mode || $("mode").value,
        group: $("group").value || lastPreview.group,
        note: $("note").value || lastPreview.note,
      }),
    });
    if (!data.ok) {
      $("inferMsg").textContent = data.error || "保存失败";
      $("btnSaveEval").disabled = false;
      return;
    }
    $("inferMsg").textContent = `已保存 · ${data.wav_path}`;
    $("inferLog").textContent = JSON.stringify(data.meta || data, null, 2);
    lastPreview = null;
    await refreshStatus();
  } catch (err) {
    $("inferMsg").textContent = String(err.message || err);
    $("btnSaveEval").disabled = false;
  }
});

$("btnTrainReset").addEventListener("click", async () => {
  const data = await api("/api/train/defaults");
  fillTrain(data.params);
  $("trainMsg").textContent = "已恢复默认";
});

$("btnTrainExport").addEventListener("click", async () => {
  $("btnTrainExport").disabled = true;
  $("trainMsg").textContent = "导出中…";
  try {
    const data = await api("/api/train/export", {
      method: "POST",
      body: JSON.stringify({ params: readTrain() }),
    });
    $("trainMsg").textContent = `已导出到 ${data.out_dir}`;
    $("trainLog").textContent = JSON.stringify(
      { out_dir: data.out_dir, files: data.files, run_sh_preview: data.run_sh_preview },
      null,
      2,
    );
  } catch (err) {
    $("trainMsg").textContent = String(err.message || err);
  } finally {
    $("btnTrainExport").disabled = false;
  }
});

$("btnRefresh").addEventListener("click", refreshStatus);

refreshStatus().catch((err) => {
  $("inferMsg").textContent = "状态加载失败: " + err;
});
