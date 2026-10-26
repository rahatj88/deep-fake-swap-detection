/* Sandbox dashboard client — escape all untrusted text; no eval. */
(function () {
  "use strict";

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  async function api(path, options) {
    const res = await fetch(path, options);
    let body = null;
    try {
      body = await res.json();
    } catch (_) {
      body = null;
    }
    if (!res.ok) {
      const msg =
        body && body.error && body.error.message
          ? body.error.message
          : "Request failed (" + res.status + ")";
      const err = new Error(msg);
      err.status = res.status;
      err.body = body;
      throw err;
    }
    return body;
  }

  function fmtBytes(n) {
    if (n == null || Number.isNaN(n)) return "—";
    const u = ["B", "KB", "MB", "GB", "TB"];
    let v = Number(n);
    let i = 0;
    while (v >= 1024 && i < u.length - 1) {
      v /= 1024;
      i += 1;
    }
    return v.toFixed(i === 0 ? 0 : 1) + " " + u[i];
  }

  function setBanner(items) {
    const ul = document.getElementById("banner-list");
    ul.innerHTML = "";
    const list = items && items.length ? items : ["UNVERIFIED status unknown"];
    // Hard cap rendered items
    const max = Math.min(list.length, 20);
    for (let i = 0; i < max; i += 1) {
      const li = document.createElement("li");
      li.textContent = list[i];
      ul.appendChild(li);
    }
  }

  async function refreshHealth() {
    const kv = document.getElementById("health-kv");
    try {
      const h = await api("/api/health");
      setBanner(h.unverified || []);
      const gpu = h.gpu || {};
      const disk = h.disk || {};
      const cpu = h.cpu || {};
      const rows = [
        ["API version", h.version],
        ["Inference mode", h.inference_mode],
        ["Uptime (s)", h.uptime_sec],
        ["GPU", gpu.available ? gpu.name : "N/A (nvidia-smi unavailable)"],
        [
          "GPU memory",
          gpu.available
            ? String(gpu.memory_free_mb) + " / " + String(gpu.memory_total_mb) + " MB free/total"
            : "N/A",
        ],
        ["Disk free", fmtBytes(disk.free_bytes) + " / " + fmtBytes(disk.total_bytes)],
        [
          "CPU load",
          cpu.load1 == null
            ? "N/A"
            : String(cpu.load1) + " / " + String(cpu.load5) + " / " + String(cpu.load15),
        ],
        ["Host", h.host],
        ["Bind", h.bind],
      ];
      kv.innerHTML = rows
        .map(function (r) {
          return "<dt>" + escapeHtml(r[0]) + "</dt><dd>" + escapeHtml(r[1]) + "</dd>";
        })
        .join("");
    } catch (e) {
      kv.innerHTML = "<dt>Error</dt><dd>" + escapeHtml(e.message) + "</dd>";
    }
  }

  async function refreshModels() {
    const body = document.getElementById("models-body");
    try {
      const data = await api("/api/models");
      const models = data.models || [];
      if (!models.length) {
        body.innerHTML = '<tr><td colspan="4" class="empty">No models listed</td></tr>';
      } else {
        body.innerHTML = models
          .slice(0, 20)
          .map(function (m) {
            const stClass = m.status === "ready" ? "status-ready" : "status-missing";
            return (
              "<tr>" +
              "<td>" +
              escapeHtml(m.name) +
              "</td>" +
              '<td class="mono">' +
              escapeHtml(m.path) +
              "</td>" +
              "<td>" +
              escapeHtml(m.size_bytes != null ? fmtBytes(m.size_bytes) : "—") +
              "</td>" +
              '<td class="' +
              stClass +
              '">' +
              escapeHtml(m.status) +
              "</td>" +
              "</tr>"
            );
          })
          .join("");
      }
      const hy = data.hybrid_defaults || {};
      const lim = data.limits || {};
      document.getElementById("hybrid-hint").textContent =
        "Hybrid defaults (UNVERIFIED): coco≥" +
        hy.coco_threshold +
        " → FAKE (coco branch); face≥" +
        hy.face_threshold +
        " → FAKE / face<" +
        hy.face_real_floor +
        " → REAL (face branch). " +
        (hy.note || "");
      document.getElementById("upload-hint").textContent =
        "Accepted: mp4, mov, avi, mkv · max " +
        (lim.max_upload_mb != null ? lim.max_upload_mb : 50) +
        " MB · timeout " +
        (lim.inference_timeout_sec != null ? lim.inference_timeout_sec : 60) +
        "s · max frames " +
        (lim.max_frames != null ? lim.max_frames : 300);
    } catch (e) {
      body.innerHTML =
        '<tr><td colspan="4" class="empty">' + escapeHtml(e.message) + "</td></tr>";
    }
  }

  async function refreshHistory() {
    const body = document.getElementById("history-body");
    try {
      const data = await api("/api/history");
      const items = data.history || [];
      if (!items.length) {
        body.innerHTML = '<tr><td colspan="5" class="empty">No analyses yet</td></tr>';
        return;
      }
      body.innerHTML = items
        .slice(0, 50)
        .map(function (h) {
          return (
            "<tr>" +
            "<td>" +
            escapeHtml(h.filename) +
            "</td>" +
            "<td>" +
            escapeHtml(h.decision) +
            "</td>" +
            "<td>" +
            escapeHtml(h.confidence) +
            "</td>" +
            "<td>" +
            escapeHtml(h.elapsed_sec) +
            "s</td>" +
            "<td>" +
            escapeHtml(h.inference_mode) +
            "</td>" +
            "</tr>"
          );
        })
        .join("");
    } catch (e) {
      body.innerHTML =
        '<tr><td colspan="5" class="empty">' + escapeHtml(e.message) + "</td></tr>";
    }
  }

  async function refreshFindings() {
    const body = document.getElementById("findings-body");
    try {
      const data = await api("/api/findings");
      const items = data.findings || [];
      if (!items.length) {
        body.innerHTML = '<tr><td colspan="4" class="empty">No findings parsed</td></tr>';
        return;
      }
      body.innerHTML = items
        .slice(0, 100)
        .map(function (f) {
          return (
            "<tr>" +
            "<td>" +
            escapeHtml(f.severity) +
            "</td>" +
            '<td class="mono">' +
            escapeHtml(f.where) +
            "</td>" +
            "<td>" +
            escapeHtml(f.what) +
            "</td>" +
            "<td>" +
            escapeHtml(f.fix) +
            "</td>" +
            "</tr>"
          );
        })
        .join("");
    } catch (e) {
      body.innerHTML =
        '<tr><td colspan="4" class="empty">' + escapeHtml(e.message) + "</td></tr>";
    }
  }

  let selectedFile = null;

  function setSelected(file) {
    selectedFile = file;
    const nameEl = document.getElementById("chosen-name");
    const btn = document.getElementById("analyze-btn");
    if (!file) {
      nameEl.textContent = "No file selected";
      btn.disabled = true;
      return;
    }
    nameEl.textContent = file.name + " (" + fmtBytes(file.size) + ")";
    btn.disabled = false;
  }

  function showError(msg) {
    const el = document.getElementById("analyze-err");
    el.textContent = msg || "";
    el.classList.toggle("on", !!msg);
  }

  function showResult(data) {
    const box = document.getElementById("analyze-result");
    const dec = document.getElementById("decision");
    const kv = document.getElementById("result-kv");
    box.classList.add("on");
    dec.textContent = data.decision;
    dec.className = "decision " + String(data.decision || "");
    const rows = [
      ["Confidence", data.confidence],
      ["COCO v5 score", data.coco_score],
      ["Face v6 score", data.face_score],
      ["Face detected", data.face_detected],
      ["Hybrid branch", data.hybrid_branch],
      [
        "Thresholds",
        JSON.stringify(data.thresholds || {}),
      ],
      ["Elapsed (s)", data.elapsed_sec],
      ["Inference mode", data.inference_mode],
      ["Notes", (data.notes || []).join(" · ")],
    ];
    kv.innerHTML = rows
      .map(function (r) {
        return "<dt>" + escapeHtml(r[0]) + "</dt><dd>" + escapeHtml(r[1]) + "</dd>";
      })
      .join("");
  }

  async function runAnalyze() {
    if (!selectedFile) return;
    showError("");
    const prog = document.getElementById("progress");
    const bar = prog.querySelector("span");
    prog.classList.add("on");
    bar.style.width = "15%";
    document.getElementById("analyze-btn").disabled = true;
    try {
      const fd = new FormData();
      fd.append("file", selectedFile, selectedFile.name);
      bar.style.width = "55%";
      const data = await api("/api/analyze", { method: "POST", body: fd });
      bar.style.width = "100%";
      showResult(data);
      await refreshHistory();
      await refreshHealth();
    } catch (e) {
      showError(e.message || "Analyze failed");
    } finally {
      document.getElementById("analyze-btn").disabled = !selectedFile;
      setTimeout(function () {
        prog.classList.remove("on");
        bar.style.width = "0%";
      }, 400);
    }
  }

  function wireUpload() {
    const input = document.getElementById("file-input");
    const drop = document.getElementById("dropzone");
    document.getElementById("pick-btn").addEventListener("click", function () {
      input.click();
    });
    input.addEventListener("change", function () {
      setSelected(input.files && input.files[0] ? input.files[0] : null);
    });
    document.getElementById("analyze-btn").addEventListener("click", runAnalyze);
    ["dragenter", "dragover"].forEach(function (ev) {
      drop.addEventListener(ev, function (e) {
        e.preventDefault();
        e.stopPropagation();
        drop.classList.add("dragover");
      });
    });
    ["dragleave", "drop"].forEach(function (ev) {
      drop.addEventListener(ev, function (e) {
        e.preventDefault();
        e.stopPropagation();
        drop.classList.remove("dragover");
      });
    });
    drop.addEventListener("drop", function (e) {
      const f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
      if (f) setSelected(f);
    });
  }

  document.getElementById("health-refresh").addEventListener("click", refreshHealth);
  wireUpload();
  refreshHealth();
  refreshModels();
  refreshHistory();
  refreshFindings();
  setInterval(refreshHealth, 10000);
})();
