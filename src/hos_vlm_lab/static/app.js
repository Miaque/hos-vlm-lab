"use strict";
const $ = (id) => document.getElementById(id);
const state = {
  config: null,
  images: [],
  selected: null,
  round: null,
  timer: null,
  historyOffset: 0,
  pending: null,
};
const labels = {
  queued: "等待中",
  running: "检测中",
  succeeded: "完成",
  failed: "调用失败",
  invalid_response: "解析失败",
  interrupted: "已中断",
  stopped: "未开始 · 已停止",
  completed: "轮次结束",
  stopping: "停止中",
};
function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}
function error(exc) {
  $("error").textContent = exc.message;
  $("error").hidden = false;
  const fields = {
    thinking: "thinking",
    thinking_budget: "budget",
    max_tokens: "max-tokens",
    temperature: "temperature",
    prompt_text: "prompt",
    image_ids: "files",
  };
  for (const detail of exc.details || []) {
    const input = detail.model_key
      ? [...document.querySelectorAll("[data-model]")].find(
          (i) => i.value === detail.model_key,
        )
      : $(fields[detail.field?.split(".").at(-1)]);
    if (input) {
      input.setAttribute("aria-invalid", "true");
      input.parentElement.append(
        element("small", detail.message, "field-error"),
      );
    }
  }
}
async function api(path, options = {}) {
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) {
    const e = data.error;
    const failure = new Error(
      (e?.message || "请求失败") +
        (e?.details?.length
          ? "：" +
            e.details
              .map((x) => (x.field || x.model_key || "") + " " + x.message)
              .join("；")
          : ""),
    );
    failure.details = e?.details;
    throw failure;
  }
  return data;
}
async function action(work) {
  $("error").hidden = true;
  for (const node of document.querySelectorAll(".field-error")) node.remove();
  for (const node of document.querySelectorAll('[aria-invalid="true"]'))
    node.removeAttribute("aria-invalid");
  try {
    await work();
  } catch (exc) {
    error(exc);
  }
}
function jsonPost(body) {
  return {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}
function selectImage(id) {
  state.selected = id;
  renderImages();
  renderResults();
}
function renderImages() {
  const host = $("thumbnails");
  host.replaceChildren();
  $("image-count").textContent = state.images.length + " / 20";
  for (const item of state.images) {
    const button = element(
      "button",
      undefined,
      item.id === state.selected ? "selected" : "",
    );
    button.title = item.name || item.original_name;
    const image = element("img");
    image.src = item.prepared_url;
    image.alt = button.title;
    button.append(image);
    button.onclick = () => selectImage(item.id);
    host.append(button);
  }
  const item = state.images.find((i) => i.id === state.selected);
  $("preview").hidden = !item;
  if (item) {
    $("preview").src = $("show-original").checked
      ? item.original_url
      : item.prepared_url;
    $("image-meta").textContent =
      `${item.name || item.original_name} · 实际发送 ${item.width} × ${item.height} · SHA256 ${item.prepared_sha256.slice(0, 16)}…`;
  } else {
    $("image-meta").textContent = "";
  }
}
function renderResults() {
  const host = $("results");
  host.replaceChildren();
  $("result-empty").hidden = !!state.round;
  if (!state.round) return;
  const round = state.round;
  $("progress").textContent = Object.entries(round.counts)
    .map(([k, v]) => `${labels[k] || k} ${v}`)
    .join(" · ");
  for (const attempt of round.attempts.filter(
    (a) => a.image_id === state.selected,
  )) {
    const model = round.model_snapshot.find((m) => m.key === attempt.model_key);
    const card = element("article", undefined, "result-card");
    card.append(
      element(
        "h3",
        `${model?.label || attempt.model_key} · 尝试 ${attempt.attempt_no}`,
      ),
      element("span", labels[attempt.status] || attempt.status, "status"),
    );
    if (attempt.status === "succeeded") {
      if (!attempt.parsed_events.length)
        card.append(element("p", "未检出（不代表确认不存在）", "muted"));
      for (const event of attempt.parsed_events) {
        const row = element("div", undefined, "event");
        row.append(
          element(
            "strong",
            round.event_snapshot[event.canonical_event_code] ||
              event.canonical_event_code,
          ),
          element("small", event.canonical_event_code, "muted"),
          element("p", `置信度 ${event.confidence}`),
          element("p", event.evidence),
        );
        card.append(row);
      }
    }
    if (attempt.error)
      card.append(element("p", attempt.error.message, "error"));
    card.append(
      element(
        "p",
        `耗时 ${attempt.elapsed_ms == null ? "未知" : attempt.elapsed_ms + " ms"} · 费用 ${attempt.cost == null ? "未知" : attempt.cost + " " + attempt.currency}`,
        "muted",
      ),
    );
    const details = element("details");
    details.append(element("summary", "查看原文、参数与用量"));
    const pre = element("pre");
    details.append(pre);
    details.addEventListener("toggle", () => {
      if (details.open && !pre.textContent)
        action(async () => {
          const data = await api("/api/attempts/" + attempt.id);
          pre.textContent = JSON.stringify(data, null, 2);
        });
    });
    card.append(details);
    addAttemptActions(card, attempt);
    host.append(card);
  }
}
async function loadRound(id) {
  clearTimeout(state.timer);
  const round = await api("/api/rounds/" + id);
  state.round = round;
  state.images = round.images;
  if (!state.images.some((i) => i.id === state.selected))
    state.selected = state.images[0]?.id;
  renderImages();
  renderResults();
  const active = ["running", "stopping"].includes(round.status);
  $("run").disabled = active;
  $("stop").disabled = !active;
  $("files").disabled = active;
  $("run-status").textContent = labels[round.status] || round.status;
  if (round.scheduler_error) {
    error(new Error(round.scheduler_error));
    clearTimeout(state.timer);
    return;
  }
  if (active) state.timer = setTimeout(() => action(() => loadRound(id)), 1000);
  else await history();
}
async function history() {
  const data = await api("/api/rounds?limit=20&offset=" + state.historyOffset);
  updateCompareOptions(data);
  const host = $("history");
  host.replaceChildren();
  if (!data.items.length) host.append(element("p", "尚无运行记录", "muted"));
  for (const item of data.items) {
    const row = element("div", undefined, "history-row");
    const open = element("button", new Date(item.created_at).toLocaleString());
    open.onclick = () => action(() => loadRound(item.id));
    row.append(
      open,
      element("span", labels[item.status] || item.status),
      element("small", item.id.slice(0, 8)),
    );
    const reuse = element("button", "复用输入", "subtle");
    reuse.onclick = () =>
      action(async () => {
        await loadRound(item.id);
        $("prompt").value = state.round.prompt_text;
        const c = state.round.controls;
        $("thinking").checked = c.thinking;
        $("budget").disabled = !c.thinking;
        $("budget").value = c.thinking_budget ?? 1024;
        $("max-tokens").value = c.max_tokens;
        $("temperature").value = c.temperature;
        for (const input of document.querySelectorAll("[data-model]"))
          input.checked = state.round.model_snapshot.some(
            (m) => m.key === input.value,
          );
      });
    row.append(reuse);
    host.append(row);
  }
}
$("thinking").onchange = () => {
  $("budget").disabled = !$("thinking").checked;
};
$("show-original").onchange = renderImages;
$("reset").onclick = () => {
  $("prompt").value = state.config.default_prompt;
};
$("files").onchange = () =>
  action(async () => {
    const files = [...$("files").files];
    if (!files.length) return;
    if (files.length > 20) throw new Error("每组最多20张图片");
    const form = new FormData();
    for (const file of files) form.append("files", file);
    const data = await api("/api/images", { method: "POST", body: form });
    state.images = data.images;
    state.selected = state.images[0].id;
    renderImages();
    renderResults();
  });
$("run").onclick = () =>
  action(async () => {
    if (!state.images.length) throw new Error("请先上传图片");
    const keys = [...document.querySelectorAll("[data-model]:checked")].map(
      (i) => i.value,
    );
    if (!keys.length) throw new Error("请至少选择一个可运行模型");
    const thinking = $("thinking").checked;
    const body = {
      request_id: crypto.randomUUID(),
      image_ids: state.images.map((i) => i.id),
      model_keys: keys,
      prompt_text: $("prompt").value,
      controls: {
        thinking,
        thinking_budget: thinking ? Number($("budget").value) : null,
        max_tokens: Number($("max-tokens").value),
        temperature: Number($("temperature").value),
      },
    };
    $("run").disabled = true;
    try {
      const fingerprint = JSON.stringify({ ...body, request_id: null });
      if (state.pending?.fingerprint === fingerprint)
        body.request_id = state.pending.request_id;
      else state.pending = { fingerprint, request_id: body.request_id };
      const data = await api("/api/rounds", jsonPost(body));
      state.pending = null;
      await loadRound(data.round_id);
    } catch (exc) {
      $("run").disabled = false;
      throw exc;
    }
  });
$("refresh-history").onclick = () => action(history);
action(async () => {
  state.config = await api("/api/config");
  $("simulation").hidden = !state.config.simulation;
  $("prompt").value = state.config.default_prompt;
  for (const model of state.config.models) {
    const label = element("label", undefined, "model");
    const input = element("input");
    input.type = "checkbox";
    input.value = model.key;
    input.dataset.model = "";
    input.disabled = !model.runnable;
    input.checked = model.runnable;
    label.append(input, document.createTextNode(" " + model.label));
    if (model.reason) label.append(element("small", model.reason));
    $("models").append(label);
  }
  await history();
  const data = await api("/api/rounds");
  const running = data.items.find(
    (i) => i.status === "running" || i.status === "stopping",
  );
  if (running) await loadRound(running.id);
});

function addAttemptActions(card, attempt) {
  const u = attempt.normalized_usage;
  card.append(
    element(
      "p",
      `Token 输入 ${u?.input ?? "未知"} / 输出 ${u?.output ?? "未知"} / 思考 ${u?.reasoning ?? "未知"}`,
      "muted",
    ),
  );
  if (["failed", "invalid_response", "interrupted"].includes(attempt.status)) {
    const retry = element("button", "重试此项", "subtle");
    retry.disabled = ["running", "stopping"].includes(state.round.status);
    let requestId = crypto.randomUUID();
    retry.onclick = () =>
      action(async () => {
        retry.disabled = true;
        try {
          const r = await api(
            "/api/attempts/" + attempt.id + "/retry",
            jsonPost({ request_id: requestId }),
          );
          await loadRound(r.round_id);
        } catch (exc) {
          retry.disabled = false;
          throw exc;
        }
      });
    card.append(retry);
  }
}
$("stop").onclick = () =>
  action(async () => {
    if (!state.round) return;
    await api("/api/rounds/" + state.round.id + "/stop", { method: "POST" });
    await loadRound(state.round.id);
  });
function updateCompareOptions(data) {
  for (const id of ["compare-a", "compare-b"]) {
    const select = $(id),
      previous = select.value,
      previousOption = select.selectedOptions[0];
    select.replaceChildren();
    for (const item of data.items) {
      const option = element(
        "option",
        new Date(item.created_at).toLocaleString() +
          " · " +
          item.id.slice(0, 8),
      );
      option.value = item.id;
      select.append(option);
    }
    if (previousOption && !data.items.some((i) => i.id === previous))
      select.append(previousOption);
    if (previousOption) select.value = previous;
    else if (id === "compare-b" && data.items.length > 1)
      select.selectedIndex = 1;
  }
  $("older").disabled = data.total <= state.historyOffset + 20;
  $("newer").disabled = state.historyOffset === 0;
}
$("older").onclick = () =>
  action(async () => {
    state.historyOffset += 20;
    await history();
  });
$("newer").onclick = () =>
  action(async () => {
    state.historyOffset = Math.max(0, state.historyOffset - 20);
    await history();
  });
$("compare").onclick = () =>
  action(async () => {
    const aid = $("compare-a").value,
      bid = $("compare-b").value;
    if (!aid || !bid || aid === bid) throw new Error("请选择两个不同轮次");
    const [a, b] = await Promise.all([
      api("/api/rounds/" + aid),
      api("/api/rounds/" + bid),
    ]);
    const host = $("comparison");
    host.replaceChildren();
    const snapshots = element("div", undefined, "compare-grid");
    for (const [label, round] of [
      ["A", a],
      ["B", b],
    ]) {
      const detail = element("details");
      detail.append(
        element("summary", label + " · 提示词与参数快照"),
        element(
          "pre",
          round.prompt_text + "\n" + JSON.stringify(round.controls, null, 2),
        ),
      );
      snapshots.append(detail);
    }
    host.append(snapshots);
    const remaining = [...b.images];
    const pairs = a.images.map((ai) => {
      let index = remaining.findIndex((bi) => bi.id === ai.id);
      if (index < 0)
        index = remaining.findIndex(
          (bi) => bi.original_sha256 === ai.original_sha256,
        );
      return [ai, index < 0 ? null : remaining.splice(index, 1)[0]];
    });
    pairs.push(...remaining.map((bi) => [null, bi]));
    const keys = [
      ...new Set([...a.model_snapshot, ...b.model_snapshot].map((m) => m.key)),
    ];
    for (const [ai, bi] of pairs) {
      const image = ai || bi;
      const section = element("section", undefined, "compare-image");
      section.append(element("h3", image.name || image.original_name));
      if (ai && bi && ai.prepared_sha256 !== bi.prepared_sha256)
        section.append(
          element("p", "预处理结果不同，本图输入不完全一致", "notice"),
        );
      for (const key of keys) {
        const row = element("div", undefined, "compare-grid");
        for (const [label, round, im] of [
          ["A", a, ai],
          ["B", b, bi],
        ]) {
          const card = element("article", undefined, "result-card");
          card.append(
            element(
              "h3",
              label +
                " · " +
                (round.model_snapshot.find((m) => m.key === key)?.label || key),
            ),
          );
          const attempts = round.attempts.filter(
            (t) => t.image_id === im?.id && t.model_key === key,
          );
          if (!attempts.length) card.append(element("p", "未运行", "muted"));
          for (const t of attempts) {
            card.append(
              element(
                "p",
                `尝试 ${t.attempt_no} · ${labels[t.status] || t.status}`,
              ),
            );
            if (t.status === "succeeded")
              card.append(
                element(
                  "pre",
                  t.parsed_events.length
                    ? JSON.stringify(t.parsed_events, null, 2)
                    : "未检出（不代表确认不存在）",
                ),
              );
            if (t.error) card.append(element("p", t.error.message, "error"));
          }
          row.append(card);
        }
        section.append(row);
      }
      host.append(section);
    }
  });
