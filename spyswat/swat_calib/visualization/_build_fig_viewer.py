#!/usr/bin/env python
"""Build a self-contained interactive viewer for a SWAT fig.fig file."""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path


FILE_COMMANDS = {"subbasin", "route", "routres", "reccnst", "saveconc"}
KNOWN_COMMANDS = {
    "subbasin",
    "route",
    "routres",
    "transfer",
    "add",
    "reccnst",
    "saveconc",
    "finish",
}


def parse_int(value: str):
    try:
        if "." in value:
            return None
        return int(value)
    except ValueError:
        return None


def parse_float(value: str):
    try:
        return float(value)
    except ValueError:
        return None


def command_id(tokens: list[str]):
    if len(tokens) >= 3 and tokens[0] != "transfer":
        return parse_int(tokens[2])
    return None


def parse_fig(path: Path, red_reaches: set[int]):
    raw_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    commands = []
    id_to_index = {}
    issues = []

    i = 0
    while i < len(raw_lines):
        raw = raw_lines[i].rstrip("\r\n")
        stripped = raw.strip()
        if not stripped:
            i += 1
            continue

        tokens = stripped.split()
        kind = tokens[0].lower()
        if kind not in KNOWN_COMMANDS:
            i += 1
            continue

        file_line = ""
        if kind in FILE_COMMANDS and i + 1 < len(raw_lines):
            nxt = raw_lines[i + 1]
            if nxt[:1].isspace() and nxt.strip():
                file_line = nxt.strip()
                i += 1

        cmd = {
            "seq": len(commands),
            "line": i + 1 if not file_line else i,
            "kind": kind,
            "raw": raw,
            "tokens": tokens,
            "file": file_line,
            "id": command_id(tokens),
            "summary": "",
            "details": {},
            "red": False,
            "issue": "",
        }

        try:
            enrich_command(cmd, red_reaches)
        except Exception as exc:  # keep viewer generation robust for malformed FIGs
            cmd["issue"] = f"parser exception: {exc}"
            cmd["red"] = True

        if cmd["id"] is not None:
            id_to_index[cmd["id"]] = cmd["seq"]
        if cmd["issue"]:
            issues.append({"line": cmd["line"], "issue": cmd["issue"], "raw": cmd["raw"]})

        commands.append(cmd)
        i += 1

    edges = build_edges(commands, id_to_index)
    return {
        "source": str(path),
        "commands": commands,
        "edges": edges,
        "issues": issues,
        "redReaches": sorted(red_reaches),
    }


def enrich_command(cmd, red_reaches: set[int]):
    t = cmd["tokens"]
    kind = cmd["kind"]

    if kind == "subbasin" and len(t) >= 4:
        cmd["summary"] = f"subbasin {t[3]}"
        cmd["details"] = {"subbasin": parse_int(t[3])}
    elif kind == "route" and len(t) >= 5:
        sub = parse_int(t[3])
        src = parse_int(t[4])
        cmd["summary"] = f"route reach {sub} from hydrograph {src}"
        cmd["details"] = {"reach": sub, "input": src}
        cmd["red"] = sub in red_reaches or src in red_reaches
    elif kind == "routres" and len(t) >= 5:
        res = parse_int(t[3])
        src = parse_int(t[4])
        cmd["summary"] = f"route reservoir {res} from hydrograph {src}"
        cmd["details"] = {"reservoir": res, "input": src}
    elif kind == "add" and len(t) >= 5:
        a = parse_int(t[3])
        b = parse_int(t[4])
        cmd["summary"] = f"add hydrographs {a} + {b}"
        cmd["details"] = {"inputA": a, "inputB": b}
        cmd["red"] = a in red_reaches or b in red_reaches
    elif kind == "transfer":
        enrich_transfer(cmd, red_reaches)
    elif kind == "reccnst" and len(t) >= 4:
        cmd["summary"] = f"constant point source {t[3]}"
    elif kind == "saveconc":
        cmd["summary"] = "save concentration output"
    elif kind == "finish":
        cmd["summary"] = "finish"
    else:
        cmd["summary"] = " ".join(t[1:])


def enrich_transfer(cmd, red_reaches: set[int]):
    t = cmd["tokens"]
    cmd["red"] = True
    if len(t) != 9:
        cmd["issue"] = (
            f"transfer should have 9 whitespace tokens, found {len(t)}. "
            "Check for joined fields such as DEST_NUM and TRANS_AMT."
        )
        cmd["summary"] = "malformed transfer"
        return

    code = parse_int(t[1])
    dep_type = parse_int(t[2])
    dep_num = parse_int(t[3])
    dest_type = parse_int(t[4])
    dest_num = parse_int(t[5])
    trans_amt = parse_float(t[6])
    trans_code = parse_int(t[7])
    trans_se = parse_int(t[8])

    bad = []
    for name, value in [
        ("command code", code),
        ("DEP_TYPE", dep_type),
        ("DEP_NUM", dep_num),
        ("DEST_TYPE", dest_type),
        ("DEST_NUM", dest_num),
        ("TRANS_CODE", trans_code),
        ("TRANS_SE", trans_se),
    ]:
        if value is None:
            bad.append(name)
    if trans_amt is None:
        bad.append("TRANS_AMT")
    if bad:
        cmd["issue"] = "Cannot parse fields: " + ", ".join(bad)

    cmd["details"] = {
        "commandCode": code,
        "DEP_TYPE": dep_type,
        "DEP_NUM": dep_num,
        "DEST_TYPE": dest_type,
        "DEST_NUM": dest_num,
        "TRANS_AMT": trans_amt,
        "TRANS_CODE": trans_code,
        "TRANS_SE": trans_se,
    }
    src_label = ("reach" if dep_type == 1 else "reservoir" if dep_type == 2 else "source")
    dst_label = ("reach" if dest_type == 1 else "reservoir" if dest_type == 2 else "dest")
    cmd["summary"] = (
        f"transfer {src_label} {dep_num} -> {dst_label} {dest_num}, "
        f"amount {t[6]}, code {trans_code}"
    )
    if dep_num in red_reaches or dest_num in red_reaches:
        cmd["red"] = True


def build_edges(commands, id_to_index):
    edges = []
    for cmd in commands:
        details = cmd["details"]
        target = cmd["seq"]
        if cmd["kind"] in {"route", "routres"}:
            src = details.get("input")
            if src in id_to_index:
                edges.append({"from": id_to_index[src], "to": target, "type": "flow"})
        elif cmd["kind"] == "add":
            for src in (details.get("inputA"), details.get("inputB")):
                if src in id_to_index:
                    edges.append({"from": id_to_index[src], "to": target, "type": "flow"})
    return edges


def html_page(data):
    payload = json.dumps(data, ensure_ascii=True).replace("</script>", r"<\/script>")
    title = "SWAT FIG Interactive Viewer"
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
:root {{
  --bg: #f6f7f9;
  --panel: #ffffff;
  --line: #d8dde6;
  --text: #17202a;
  --muted: #667085;
  --blue: #2563eb;
  --green: #0f766e;
  --amber: #b45309;
  --red: #dc2626;
  --red-soft: #fee2e2;
  --ink-soft: #eef2f7;
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  font-family: Arial, Helvetica, sans-serif;
  background: var(--bg);
  color: var(--text);
}}
header {{
  padding: 14px 18px;
  border-bottom: 1px solid var(--line);
  background: var(--panel);
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
}}
h1 {{
  font-size: 18px;
  margin: 0;
  line-height: 1.2;
}}
.source {{
  color: var(--muted);
  font-size: 12px;
  flex: 1 1 360px;
}}
.toolbar {{
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 18px;
  background: #fbfcfe;
  border-bottom: 1px solid var(--line);
  flex-wrap: wrap;
}}
button, input, select {{
  height: 34px;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: #fff;
  color: var(--text);
  padding: 0 10px;
  font-size: 13px;
}}
button {{
  cursor: pointer;
  font-weight: 600;
}}
button.primary {{
  background: var(--blue);
  color: white;
  border-color: var(--blue);
}}
main {{
  display: grid;
  grid-template-columns: minmax(320px, 42%) minmax(360px, 58%);
  gap: 0;
  height: calc(100vh - 106px);
}}
.list {{
  overflow: auto;
  padding: 12px;
  border-right: 1px solid var(--line);
}}
.card {{
  border: 1px solid var(--line);
  background: var(--panel);
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 8px;
  cursor: pointer;
}}
.card.active {{
  border-color: var(--blue);
  box-shadow: 0 0 0 2px rgba(37, 99, 235, .14);
}}
.card.red {{
  border-color: #fca5a5;
  background: #fff7f7;
}}
.card.issue {{
  border-color: var(--red);
  background: var(--red-soft);
}}
.meta {{
  color: var(--muted);
  font-size: 12px;
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 4px;
}}
.summary {{
  font-weight: 700;
  font-size: 14px;
}}
code {{
  font-family: Consolas, Monaco, monospace;
  font-size: 12px;
}}
.detail {{
  overflow: auto;
  padding: 14px;
}}
.panel {{
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 12px;
  margin-bottom: 12px;
}}
.panel h2 {{
  font-size: 15px;
  margin: 0 0 10px 0;
}}
.raw {{
  white-space: pre-wrap;
  background: #111827;
  color: #f9fafb;
  border-radius: 6px;
  padding: 10px;
  overflow-x: auto;
}}
.kv {{
  display: grid;
  grid-template-columns: 150px 1fr;
  gap: 6px 12px;
  font-size: 13px;
}}
.kv div:nth-child(odd) {{
  color: var(--muted);
}}
.warning {{
  color: #991b1b;
  background: var(--red-soft);
  border: 1px solid #fca5a5;
  padding: 8px;
  border-radius: 6px;
}}
.graph-wrap {{
  height: 520px;
  overflow: auto;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: #fff;
}}
svg text {{
  font-family: Arial, Helvetica, sans-serif;
  font-size: 11px;
}}
.legend {{
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  color: var(--muted);
  font-size: 12px;
}}
.dot {{
  width: 10px;
  height: 10px;
  display: inline-block;
  border-radius: 50%;
  margin-right: 4px;
}}
@media (max-width: 900px) {{
  main {{ grid-template-columns: 1fr; height: auto; }}
  .list {{ max-height: 45vh; border-right: 0; border-bottom: 1px solid var(--line); }}
  .detail {{ min-height: 55vh; }}
}}
</style>
</head>
<body>
<header>
  <h1>SWAT FIG Interactive Viewer</h1>
  <div class="source" id="source"></div>
</header>
<section class="toolbar">
  <button id="prev">Previous</button>
  <button id="next" class="primary">Next</button>
  <button id="firstRed">First redpoint</button>
  <label><input id="redOnly" type="checkbox" style="height:auto"> redpoints only</label>
  <input id="search" type="search" placeholder="Search command, line, reach, raw text" size="38">
  <select id="kindFilter">
    <option value="">all commands</option>
    <option value="transfer">transfer</option>
    <option value="route">route</option>
    <option value="routres">routres</option>
    <option value="add">add</option>
    <option value="reccnst">reccnst</option>
    <option value="subbasin">subbasin</option>
  </select>
</section>
<main>
  <section class="list" id="list"></section>
  <section class="detail">
    <div class="panel">
      <h2>Current command</h2>
      <div id="detail"></div>
    </div>
    <div class="panel">
      <h2>Timeline graph</h2>
      <div class="legend">
        <span><span class="dot" style="background:#2563eb"></span>active</span>
        <span><span class="dot" style="background:#dc2626"></span>transfer/issue/redpoint</span>
        <span><span class="dot" style="background:#0f766e"></span>route/routres</span>
        <span><span class="dot" style="background:#b45309"></span>add/reccnst</span>
      </div>
      <div class="graph-wrap"><svg id="graph"></svg></div>
    </div>
    <div class="panel">
      <h2>Issues</h2>
      <div id="issues"></div>
    </div>
  </section>
</main>
<script type="application/json" id="__figdata__">{payload}</script>
<script>
const data = JSON.parse(document.getElementById("__figdata__").textContent);
let active = 0;

const state = {{
  search: "",
  redOnly: false,
  kind: ""
}};

const listEl = document.getElementById("list");
const detailEl = document.getElementById("detail");
const graphEl = document.getElementById("graph");
const issuesEl = document.getElementById("issues");
document.getElementById("source").textContent = data.source + " | commands: " + data.commands.length;

function esc(s) {{
  return String(s ?? "").replace(/[&<>"']/g, c => ({{"&":"&amp;","<":"&lt;",">":"&gt;","\\"":"&quot;","'":"&#39;"}}[c]));
}}

function visibleCommands() {{
  const q = state.search.trim().toLowerCase();
  return data.commands.filter(c => {{
    if (state.redOnly && !c.red && !c.issue) return false;
    if (state.kind && c.kind !== state.kind) return false;
    if (!q) return true;
    const hay = [
      c.kind, c.line, c.id, c.summary, c.raw, c.file,
      JSON.stringify(c.details || {{}})
    ].join(" ").toLowerCase();
    return hay.includes(q);
  }});
}}

function cardClass(c) {{
  return ["card", c.seq === active ? "active" : "", c.red ? "red" : "", c.issue ? "issue" : ""].join(" ");
}}

function renderList() {{
  const rows = visibleCommands();
  listEl.innerHTML = rows.map(c => `
    <div class="${{cardClass(c)}}" data-seq="${{c.seq}}">
      <div class="meta">
        <span>#${{c.seq + 1}}</span>
        <span>line ${{c.line}}</span>
        <span>${{esc(c.kind)}}</span>
        ${{c.id !== null ? `<span>hyd ${{c.id}}</span>` : ""}}
      </div>
      <div class="summary">${{esc(c.summary || c.raw)}}</div>
      ${{c.issue ? `<div class="warning" style="margin-top:6px">${{esc(c.issue)}}</div>` : ""}}
    </div>
  `).join("");
  listEl.querySelectorAll(".card").forEach(el => {{
    el.addEventListener("click", () => setActive(Number(el.dataset.seq), true));
  }});
}}

function renderDetail() {{
  const c = data.commands[active];
  const kv = Object.entries(c.details || {{}}).map(([k, v]) => `<div>${{esc(k)}}</div><div><code>${{esc(v)}}</code></div>`).join("");
  detailEl.innerHTML = `
    ${{c.issue ? `<div class="warning">${{esc(c.issue)}}</div><br>` : ""}}
    <div class="kv">
      <div>sequence</div><div><code>${{c.seq + 1}}</code></div>
      <div>line</div><div><code>${{c.line}}</code></div>
      <div>kind</div><div><code>${{esc(c.kind)}}</code></div>
      <div>hydrograph id</div><div><code>${{esc(c.id ?? "")}}</code></div>
      ${{kv}}
      <div>file line</div><div><code>${{esc(c.file || "")}}</code></div>
    </div>
    <h2 style="margin-top:14px">Raw line</h2>
    <div class="raw">${{esc(c.raw)}}${{c.file ? "\\n" + esc(c.file) : ""}}</div>
  `;
}}

function nodeColor(c) {{
  if (c.seq === active) return "#2563eb";
  if (c.issue || c.red || c.kind === "transfer") return "#dc2626";
  if (c.kind === "route" || c.kind === "routres") return "#0f766e";
  if (c.kind === "add" || c.kind === "reccnst") return "#b45309";
  return "#64748b";
}}

function col(c) {{
  const order = {{
    subbasin: 80,
    route: 230,
    routres: 230,
    add: 380,
    transfer: 530,
    reccnst: 380,
    saveconc: 680,
    finish: 680
  }};
  return order[c.kind] || 80;
}}

function renderGraph() {{
  const h = Math.max(560, data.commands.length * 42 + 40);
  const w = 780;
  graphEl.setAttribute("width", w);
  graphEl.setAttribute("height", h);

  const y = c => 28 + c.seq * 42;
  let out = "";
  for (const e of data.edges) {{
    const a = data.commands[e.from];
    const b = data.commands[e.to];
    out += `<line x1="${{col(a)+72}}" y1="${{y(a)}}" x2="${{col(b)-18}}" y2="${{y(b)}}" stroke="#cbd5e1" stroke-width="1" />`;
  }}
  for (const c of data.commands) {{
    const x = col(c);
    const yy = y(c);
    const fill = nodeColor(c);
    out += `<g data-seq="${{c.seq}}" style="cursor:pointer">
      <circle cx="${{x}}" cy="${{yy}}" r="${{c.seq === active ? 8 : 6}}" fill="${{fill}}" />
      <text x="${{x + 12}}" y="${{yy + 4}}" fill="#111827">${{c.seq + 1}} line ${{c.line}} ${{esc(c.kind)}} ${{esc(c.summary).slice(0, 54)}}</text>
    </g>`;
  }}
  graphEl.innerHTML = out;
  graphEl.querySelectorAll("g[data-seq]").forEach(el => {{
    el.addEventListener("click", () => setActive(Number(el.dataset.seq), true));
  }});
}}

function renderIssues() {{
  if (!data.issues.length) {{
    issuesEl.innerHTML = "<div>No parser issues found.</div>";
    return;
  }}
  issuesEl.innerHTML = data.issues.map(i => `
    <div class="warning" style="margin-bottom:8px">
      <strong>Line ${{i.line}}</strong>: ${{esc(i.issue)}}<br>
      <code>${{esc(i.raw)}}</code>
    </div>
  `).join("");
}}

function setActive(seq, scroll) {{
  active = Math.max(0, Math.min(data.commands.length - 1, seq));
  render();
  if (scroll) {{
    const card = listEl.querySelector(`[data-seq="${{active}}"]`);
    if (card) card.scrollIntoView({{block: "center"}});
  }}
}}

function render() {{
  renderList();
  renderDetail();
  renderGraph();
  renderIssues();
}}

document.getElementById("prev").addEventListener("click", () => setActive(active - 1, true));
document.getElementById("next").addEventListener("click", () => setActive(active + 1, true));
document.getElementById("firstRed").addEventListener("click", () => {{
  const idx = data.commands.findIndex(c => c.red || c.issue);
  if (idx >= 0) setActive(idx, true);
}});
document.getElementById("redOnly").addEventListener("change", e => {{
  state.redOnly = e.target.checked;
  renderList();
}});
document.getElementById("search").addEventListener("input", e => {{
  state.search = e.target.value;
  renderList();
}});
document.getElementById("kindFilter").addEventListener("change", e => {{
  state.kind = e.target.value;
  renderList();
}});
document.addEventListener("keydown", e => {{
  if (e.key === "ArrowRight") setActive(active + 1, true);
  if (e.key === "ArrowLeft") setActive(active - 1, true);
}});

const firstIssue = data.commands.findIndex(c => c.issue);
if (firstIssue >= 0) active = firstIssue;
render();
</script>
</body>
</html>
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fig",
        default="../../SWAT_RES/sBa_rivBasin/Scenarios/Default/TxtInOut/fig.fig",
        help="Path to fig.fig",
    )
    parser.add_argument("--out", default="fig_interactive_viewer.html", help="Output HTML file")
    parser.add_argument(
        "--red-reach",
        action="append",
        type=int,
        default=[32, 33],
        help="Reach/hydrograph numbers to mark as redpoints. Can be repeated.",
    )
    args = parser.parse_args()

    fig_path = Path(args.fig).resolve()
    out_path = Path(args.out)
    data = parse_fig(fig_path, set(args.red_reach))
    out_path.write_text(html_page(data), encoding="utf-8", newline="\n")
    print(f"Wrote {out_path.resolve()}")
    print(f"Commands: {len(data['commands'])}, issues: {len(data['issues'])}")
    for issue in data["issues"]:
        print(f"issue line {issue['line']}: {issue['issue']}")


if __name__ == "__main__":
    main()
