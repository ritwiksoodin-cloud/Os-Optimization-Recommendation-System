"use strict";

const byId = id => document.getElementById(id);
const element = (tag, text, className) => {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
};
const percent = n => n == null ? "—" : `${n.toFixed(1)}%`;
const rate = (n, unit) => n == null ? "—" : `${n.toFixed(1)} ${unit}`;
let history = [];
let previousFindings = "";

function drawChart() {
  const canvas = byId("trend");
  const {width, height} = canvas.getBoundingClientRect();
  if (!width || !height) return;
  const ratio = window.devicePixelRatio || 1;
  canvas.width = width * ratio;
  canvas.height = height * ratio;
  const ctx = canvas.getContext("2d");
  ctx.scale(ratio, ratio);
  const plot = {left: 38, right: width - 8, top: 12, bottom: height - 12};
  const y = val => plot.bottom - val / 100 * (plot.bottom - plot.top);
  ctx.font = "11px monospace";
  for (const value of [0, 25, 50, 75, 100]) {
    ctx.fillStyle = "rgb(83, 97, 116)";
    ctx.fillText(value + "%", 0, y(value) + 3);
    ctx.strokeStyle = "rgb(220, 227, 235)";
    ctx.beginPath();
    ctx.moveTo(plot.left, y(value));
    ctx.lineTo(plot.right, y(value));
    ctx.stroke();
  }
  for (const [key, color] of [["cpu", "rgb(36, 92, 172)"], ["ram", "rgb(8, 119, 100)"]]) {
    ctx.strokeStyle = ctx.fillStyle = color;
    ctx.lineWidth = 2;
    ctx.beginPath();
    history.forEach((sample, i) => {
      const x = plot.right - (history.length - 1 - i) * (plot.right - plot.left) / 59;
      if (i === 0) ctx.moveTo(x, y(sample[key]));
      else ctx.lineTo(x, y(sample[key]));
    });
    ctx.stroke();
    if (history.length) {
      ctx.beginPath();
      ctx.arc(plot.right, y(history.at(-1)[key]), 3, 0, 2 * Math.PI);
      ctx.fill();
    }
  }
}
window.addEventListener("resize", drawChart);

async function refresh() {
  try {
    const response = await fetch("/api/monitor");
    if (!response.ok) throw new Error("Monitor unavailable");
    const report = await response.json();
    history = report.history;
    const latest = history.at(-1);
    const cards = [
      ["CPU utilization", percent(latest?.cpu)], ["Memory used", percent(latest?.ram)],
      ["Root disk used", percent(latest?.disk)], ["Processes", latest?.processes ?? "—"],
      ["Major faults/s", rate(latest?.major, "").trim()], ["Minor faults/s", rate(latest?.minor, "").trim()],
    ];
    byId("metrics").replaceChildren(...cards.map(([label, value]) => {
      const card = element("div", undefined, "card");
      card.append(element("span", label), element("strong", value));
      return card;
    }));
    drawChart();
    if (!latest) {
      byId("live").textContent = "Collecting data…";
      return;
    }
    byId("live").textContent = "Sample " + new Date(latest.time).toLocaleTimeString();
    const io = [["Available RAM", latest.available_mib + " MiB"],
      ["Disk read", rate(latest.read == null ? null : latest.read / 1048576, "MiB/s")],
      ["Disk write", rate(latest.write == null ? null : latest.write / 1048576, "MiB/s")],
      ["Swap activity", rate(latest.swap, "pages/s")]];
    byId("io").replaceChildren(...io.map(([label, value]) => {
      const term = element("div");
      term.append(element("dt", label), element("dd", value));
      return term;
    }));
    byId("window").textContent = report.ready ? `Last ${report.window_seconds}s · ${report.window_samples} samples` :
      `Collecting a baseline · ${report.window_samples}/15 samples`;
    const findings = JSON.stringify([report.ready, report.recommendations]);
    if (findings !== previousFindings) {
      previousFindings = findings;
      const messages = report.recommendations.map(item => {
        const box = element("article", undefined, "finding");
        box.append(element("h3", item.title), element("p", item.evidence), element("p", item.action));
        return box;
      });
      if (!messages.length) messages.push(element("p", report.ready ?
        "No optimization rule triggered during this window." :
        "Sustained-load rules run once the baseline is ready."));
      byId("recommendations").replaceChildren(...messages);
    }
    byId("processes").replaceChildren(...report.top.map(process => {
      const row = element("tr");
      for (const value of [process.pid, process.name, percent(process.cpu), process.rss.toFixed(1) + " MiB"]) {
        row.append(element("td", value));
      }
      return row;
    }));
  } catch {
    byId("live").textContent = "Disconnected";
  } finally {
    setTimeout(refresh, 2000);
  }
}

const jobs = byId("jobs");
function updateJobs() {
  Array.from(jobs.children).forEach((row, i) => {
    row.firstChild.textContent = "P" + (i + 1);
    row.children[1].setAttribute("aria-label", `P${i + 1} arrival`);
    row.children[2].setAttribute("aria-label", `P${i + 1} burst`);
    row.lastChild.setAttribute("aria-label", `Remove P${i + 1}`);
    row.lastChild.disabled = jobs.children.length === 1;
  });
  byId("add").disabled = jobs.children.length >= 12;
}

function numberInput(value, min, max) {
  const input = element("input");
  Object.assign(input, {type: "number", value, min, max, required: true});
  return input;
}

function addJob(arrival = 0, burst = 1) {
  const row = element("div", undefined, "job");
  const remove = element("button", "×", "secondary");
  remove.type = "button";
  remove.addEventListener("click", () => { row.remove(); updateJobs(); });
  row.append(element("span"), numberInput(arrival, 0, 1000), numberInput(burst, 1, 100), remove);
  jobs.append(row);
  updateJobs();
}
byId("add").addEventListener("click", () => addJob());
[[0, 7], [2, 4], [3, 1], [5, 4]].forEach(job => addJob(...job));

function table(labels, rows) {
  const wrap = element("div", undefined, "table-wrap");
  const tbl = element("table");
  const head = tbl.createTHead().insertRow();
  labels.forEach(label => head.append(element("th", label)));
  const body = tbl.createTBody();
  rows.forEach(values => {
    const row = body.insertRow();
    values.forEach(value => row.append(element("td", value)));
  });
  wrap.append(tbl);
  return wrap;
}

byId("workload").addEventListener("submit", async event => {
  event.preventDefault();
  const button = event.submitter;
  if (button) button.disabled = true;
  byId("error").textContent = "";
  try {
    const workload = Array.from(jobs.children, row => ({
      arrival: row.children[1].valueAsNumber, burst: row.children[2].valueAsNumber,
    }));
    const response = await fetch("/api/schedule", {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({workload, quantum: byId("quantum").valueAsNumber})});
    const results = await response.json();
    if (!response.ok) throw new Error(results.error);
    const advice = ["waiting", "response"].map(metric => {
      const min = Math.min(...results.map(r => r.averages[metric]));
      const policies = results.filter(r => r.averages[metric] === min).map(r => r.policy).join(" and ");
      return `Lowest average ${metric} time: ${policies} (${min.toFixed(2)} units).`;
    });
    const content = [element("h3", "Simulation results"), element("p", advice.join(" ")),
      table(["Algorithm", "Avg. wait", "Avg. turnaround", "Avg. response"], results.map(r =>
        [r.policy, ...["waiting", "turnaround", "response"].map(metric => r.averages[metric].toFixed(2))]))];
    for (const result of results) {
      const details = element("details");
      const timeline = element("div", undefined, "timeline");
      for (const item of result.timeline) timeline.append(element("span", `${item.job} ${item.start}–${item.end}`));
      details.append(element("summary", result.policy + " execution timeline"), timeline,
        table(["Process", "Completion", "Wait", "Turnaround", "Response"], result.rows.map(row =>
          [row.job, row.completion, row.waiting, row.turnaround, row.response])));
      content.push(details);
    }
    byId("results").replaceChildren(...content);
  } catch (error) {
    byId("error").textContent = error.message || "Could not run the simulation.";
  } finally {
    if (button) button.disabled = false;
  }
});

refresh();
