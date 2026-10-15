"""Generate the LLM API surface architecture page (single HTML file)."""
from html import escape as e
from pathlib import Path

OUT = Path(__file__).with_name("llm-api-architecture.html")


def t(x, y, s, cls="", anchor=None):
    a = f' text-anchor="{anchor}"' if anchor else ""
    c = f' class="{cls}"' if cls else ""
    return f'<text x="{x}" y="{y}"{c}{a}>{e(s)}</text>'


def rect(x, y, w, h, cls, rx=6):
    return f'<rect class="{cls}" x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}"/>'


def line(x1, y1, x2, y2, cls="edge", mk="ah"):
    m = f' marker-end="url(#{mk})"' if mk else ""
    return f'<line class="{cls}" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}"{m}/>'


def path(d, cls="edge", mk="ah"):
    m = f' marker-end="url(#{mk})"' if mk else ""
    return f'<path class="{cls}" d="{d}"{m}/>'


def defs(prefix):
    out = ["<defs>"]
    for name, cls in (("ah", "ah"), ("ahA", "ahA"), ("ahW", "ahW")):
        out.append(
            f'<marker id="{prefix}{name}" viewBox="0 0 10 10" refX="9" refY="5" '
            f'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
            f'<path d="M0,0 L10,5 L0,10 z" class="{cls}"/></marker>'
        )
    out.append("</defs>")
    return "".join(out)


# --------------------------------------------------------------------------
# Figure 1: the whole architecture
# --------------------------------------------------------------------------

def fig_main():
    p = "f1"
    A, AA = f"{p}ah", f"{p}ahA"
    o = [
        '<svg class="dg" viewBox="0 0 1200 740" role="img" aria-label="'
        "目標架構：每個 API 面一個 adapter，全部進同一份治理核心（面登記表、順序寫死的 PIPELINE、處置表），"
        "依工作負載形狀交給四個執行家族，最後都回到同一個 terminal 記帳與稽核；IAM 與 Audit 在 gateway 之外，只經 HTTP。"
        '">',
        defs(p),
    ]
    # column headers
    for x, s in ((67, "呼叫端"), (275, "L1 · adapter（每個面一個）"), (625, "L2 · 治理核心（只有一份）"),
                 (942, "L3 · 執行家族"), (1127, "上游")):
        o.append(t(x, 28, s, "hdr", "middle"))
    # owner boundary
    o.append(rect(150, 44, 885, 568, "bnd", 10))
    o.append(t(164, 604, "apps/gateway · 單一 owner（PRD-302 邊界內）", "mono xs mut"))
    # client
    o.append(rect(15, 80, 105, 510, "box", 8))
    o.append(t(67.5, 300, "Client", "b", "middle"))
    o.append(t(67.5, 318, "SDK · Agent", "xs mut", "middle"))
    for i, s in enumerate(("Codex", "Claude Code", "OpenCode")):
        o.append(t(67.5, 344 + i * 15, s, "mono xs mut", "middle"))
    # mid-gap labels
    o.append(t(137, 72, "HTTP", "mono xs mut", "middle"))
    o.append(t(407, 72, "SurfaceInput", "mono xs mut", "middle"))
    o.append(t(842, 72, "DispatchContext", "mono xs mut", "middle"))

    rows = [
        ("/v1/chat/completions", "chat · 既有", "now"),
        ("/v1/messages", "messages · 拆出自己的 adapter", "now"),
        ("/v1/responses", "responses · 既有", "now"),
        ("/v1/embeddings", "embeddings · 併入（M6）", "new"),
        ("/v1/audio/speech", "audio.speech · 併入（M7）", "new"),
        ("/v1/audio/transcriptions", "audio.transcriptions · 併入（M7）", "new"),
        ("/v1/images/*", "images · 未來（unary）", "fut"),
        ("/mcp", "mcp · 未來（MCP gateway）", "fut"),
        ("A2A（標準未定）", "a2a · 未來", "fut"),
    ]
    for i, (pth, tag, kind) in enumerate(rows):
        top = 80 + i * 50
        cy = top + 19
        cls = {"now": "box", "new": "box-new", "fut": "box-fut"}[kind]
        o.append(rect(165, top, 220, 38, cls, 6))
        o.append(t(177, top + 16, pth, "mono sm" if pth.startswith("/") else "sm"))
        o.append(t(177, top + 31, tag, "xs acc-t" if kind == "new" else "xs mut"))
        ecls = "edge edge-fut" if kind == "fut" else "edge"
        o.append(line(120, cy, 163, cy, ecls, A))
        o.append(line(385, cy, 428, cy, ecls, A))

    # core
    o.append(rect(430, 80, 390, 438, "core", 10))
    o.append(rect(445, 92, 360, 48, "box", 6))
    o.append(t(457, 111, "面登記表", "b"))
    o.append(t(512, 111, "surface registry", "mono xs mut"))
    o.append(t(793, 111, "查不到 → 拒絕＋稽核", "xs warn-t", "end"))
    o.append(t(457, 130, "name · path · family · adapter · usage_unit", "mono xs mut"))
    o.append(t(445, 160, "PIPELINE", "mono sm b acc-t"))
    o.append(t(510, 160, "順序寫死，只有一份（ADR-494 D1）", "xs mut"))
    o.append(t(805, 160, "粗框＝強制 stage", "xs mut", "end"))
    stages = [
        ("auth", True, "↔ IAM"), ("request_fields", True, ""), ("session", False, ""),
        ("policy_actions", True, ""), ("tool_results", False, ""), ("tool_rules", False, ""),
        ("input_rail", False, ""), ("semantic_cache", False, ""), ("request_policy", False, ""),
        ("store", False, ""), ("addressing", False, ""), ("budget", True, "↔ IAM"),
        ("routing", False, ""), ("policy_kernel", False, ""), ("agent_mode", False, ""),
        ("chain", False, ""), ("classifier_and_admission", True, ""), ("endpoint_lease", False, ""),
    ]
    for n, (name, mand, tag) in enumerate(stages):
        col, k = divmod(n, 9)
        x = 445 + col * 185
        y = 172 + k * 27
        o.append(rect(x, y, 175, 22, "chip-m" if mand else "chip", 4))
        o.append(t(x + 8, y + 15, f"{n + 1:02d}", "mono xs mut"))
        o.append(t(x + 30, y + 15, name, "mono xxs" + (" b acc-t" if mand else "")))
        if tag:
            o.append(t(x + 167, y + 15, tag, "mono xs mut", "end"))
    o.append(t(445, 434, "每個面對每個 stage 三選一，沒有預設值：", "xs mut"))
    o.append(t(445, 452, "RUN ｜ NotApplicable(ref) ｜ KnownGap(#issue)", "mono xs"))
    o.append(t(445, 470, "沒填 → 拒絕＋稽核（disposition_missing）", "xs warn-t"))
    o.append(t(445, 492, "實際跑了哪些 stage 記成軌跡，conformance 拿來比對（G4）", "xs mut"))

    # core -> L3
    for cy, fut in ((149, False), (324, False), (449, True), (499, True)):
        o.append(line(820, cy, 863, cy, "edge edge-fut" if fut else "edge", A))
    # L3 boxes
    o.append(rect(865, 80, 155, 138, "box", 8))
    o.append(t(877, 101, "generate-stream", "mono sm b"))
    for j, s in enumerate(("chat：狀態機", "Responses：透明轉送", "messages：chat 轉碼")):
        o.append(t(877, 121 + j * 16, s, "xs"))
    o.append(t(877, 177, "output rail · deadline", "xs mut"))
    o.append(t(877, 195, "串流不合併（§4 C）", "xs mut"))
    o.append(rect(865, 230, 155, 188, "box-new", 8))
    o.append(t(877, 251, "unary", "mono sm b acc-t"))
    o.append(t(877, 271, "一次請求、一次回應", "xs"))
    o.append(t(877, 291, "embeddings", "mono xs"))
    o.append(t(877, 306, "speech · transcription", "mono xxs"))
    o.append(t(877, 321, "images（未來）", "xs mut"))
    o.append(t(877, 345, "output rail（Q4）", "xs mut"))
    o.append(t(877, 363, "deadline · resilience", "mono xs mut"))
    o.append(t(877, 400, "新增：M6–M7", "xs acc-t"))
    o.append(rect(865, 430, 155, 38, "box-fut", 8))
    o.append(t(877, 446, "tool-invoke", "mono sm b"))
    o.append(t(877, 461, "session · tools/call", "mono xs mut"))
    o.append(rect(865, 480, 155, 38, "box-fut", 8))
    o.append(t(877, 496, "agent-task", "mono sm b"))
    o.append(t(877, 511, "A2A 任務生命週期", "xs mut"))
    # L3 -> upstream
    for cy, fut in ((149, False), (324, False), (449, True), (499, True)):
        o.append(line(1020, cy, 1063, cy, "edge edge-fut" if fut else "edge", A))
    o.append(rect(1065, 80, 125, 338, "box", 8))
    o.append(t(1127.5, 232, "模型 provider", "sm b", "middle"))
    for j, s in enumerate(("OpenAI · Azure", "Anthropic · vLLM", "地端端點")):
        o.append(t(1127.5, 252 + j * 15, s, "xs mut", "middle"))
    o.append(rect(1065, 430, 125, 38, "box-fut", 8))
    o.append(t(1127.5, 453, "上游 MCP server", "xs", "middle"))
    o.append(rect(1065, 480, 125, 38, "box-fut", 8))
    o.append(t(1127.5, 503, "遠端 agent", "xs", "middle"))

    # terminal + render + return paths
    o.append(rect(430, 540, 390, 46, "term", 8))
    o.append(t(445, 559, "terminal", "mono sm b acc-t"))
    o.append(t(510, 559, "唯一終端路徑（STARTED／COMPLETED／FAILED＋記帳）", "xs"))
    o.append(t(445, 576, "settle_completed · settle_failed · TerminalUsage(usage_unit)", "mono xs mut"))
    o.append(path("M942,518 V563 H822", "edge", A))
    o.append(t(830, 580, "上游終端", "xs mut"))
    o.append(t(830, 594, "→ TerminalUsage", "mono xs mut"))
    o.append(rect(165, 540, 220, 46, "box", 6))
    o.append(t(177, 559, "adapter.render", "mono sm b"))
    o.append(t(177, 576, "拒絕與終端 → 各自的 wire", "xs mut"))
    o.append(path("M430,510 H406 V556 H387", "edge", A))
    o.append(line(430, 572, 387, 572, "edge", A))
    o.append(line(165, 563, 122, 563, "edge", A))
    o.append(t(143, 555, "回應", "xs mut", "middle"))

    # outside owners
    o.append(rect(430, 650, 200, 70, "box", 8))
    o.append(t(442, 671, "Audit（外部）", "sm b"))
    o.append(t(442, 689, "EXECUTION_* · REQUEST_REJECTED", "mono xxs mut"))
    o.append(t(442, 706, "JSONL · fail-open（PRD-041）", "xs mut"))
    o.append(rect(660, 650, 230, 70, "box", 8))
    o.append(t(672, 671, "IAM（另一個 owner）", "sm b"))
    o.append(t(672, 689, "validate · 預算用量 · 授權", "xs mut"))
    o.append(t(672, 706, "只經 HTTP（PRD-302）", "xs mut"))
    o.append(rect(930, 650, 260, 70, "box-fut", 8))
    o.append(t(942, 671, "Operator MCP（#1226）", "sm b"))
    o.append(t(942, 689, "agent 用 MCP 操作控制面", "xs mut"))
    o.append(t(942, 706, "寫入走 HITL 核可；不走推論 pipeline", "xs mut"))
    o.append(line(530, 586, 530, 648, "edge", A))
    o.append(t(538, 628, "事件", "xs mut"))
    o.append(line(775, 586, 775, 648, "edge", A))
    o.append(t(783, 628, "記帳（HTTP）", "xs mut"))
    o.append(line(930, 685, 892, 685, "edge edge-fut", A))
    o.append(t(911, 678, "REST", "mono xs mut", "middle"))
    o.append("</svg>")
    return "".join(o)


# --------------------------------------------------------------------------
# Figure 2: default-skip vs exhaustive dispositions
# --------------------------------------------------------------------------

def fig_skip():
    p = "f2"
    A, W = f"{p}ah", f"{p}ahW"
    o = [
        '<svg class="dg" viewBox="0 0 1200 430" role="img" aria-label="'
        "左：今天 run_pre_dispatch 遇到 stage 不認得的面就 continue，未登記的面會跳過全部 18 個 stage，變成沒有稽核的 500。"
        "右：提議先查面登記表、再逐 stage 查 adapter 的處置，查不到或沒填都拒絕並留稽核，RUN、不適用、缺口都記成軌跡給 conformance 比對。"
        '">',
        defs(p),
        rect(10, 10, 580, 410, "panel", 10),
        rect(610, 10, 580, 410, "panel", 10),
        t(30, 40, "今天", "b"),
        t(70, 40, "run_pre_dispatch", "mono sm mut"),
        t(630, 40, "提議：照處置表執行", "b"),
    ]
    # left
    o += [
        rect(40, 62, 230, 40, "box"), t(52, 80, "ctx.surface", "mono sm"),
        t(52, 95, "未知路徑被當成 chat（chat.py:92）", "xs mut"),
        line(155, 102, 155, 126, "edge", A),
        rect(40, 128, 230, 34, "box"), t(52, 150, "for stage in PIPELINE", "mono sm"),
        line(155, 162, 155, 184, "edge", A),
        '<polygon class="box" points="155,186 265,222 155,258 45,222"/>',
        t(155, 219, "surface ∈", "mono xs", "middle"),
        t(155, 233, "stage.surfaces？", "mono xs", "middle"),
        line(265, 222, 328, 222, "edge", A), t(296, 215, "是", "xs", "middle"),
        rect(330, 204, 230, 36, "box"), t(342, 226, "stage.run(ctx)", "mono sm"),
        path("M445,204 V145 H272", "edge", A), t(452, 180, "下一個 stage", "xs mut"),
        line(155, 258, 155, 288, "edge edge-warn", W), t(163, 277, "否", "xs warn-t"),
        rect(40, 290, 230, 40, "warn-box"), t(52, 308, "continue", "mono sm b warn-t"),
        t(52, 323, "靜默跳過，不留稽核", "xs warn-t"),
        path("M40,310 H24 V145 H38", "edge", A),
        line(270, 310, 328, 310, "edge edge-warn", W), t(299, 303, "面沒登記時", "xs warn-t", "middle"),
        rect(330, 280, 230, 86, "warn-box"),
        t(342, 301, "全部 18 個 stage 都跳過", "xs b warn-t"),
        t(342, 319, "route 讀 dispatch.auth", "mono xs"),
        t(342, 335, "→ 沒有稽核的 500", "xs"),
        t(342, 353, "INV-494-4 沒有實作", "xs warn-t"),
        t(30, 402, "dispatch_pipeline.py:465-467 · surface_adapters/chat.py:92", "mono xs mut"),
    ]
    # right
    o += [
        rect(640, 62, 250, 40, "box"), t(652, 80, "登記表查 ctx.surface", "sm"),
        t(652, 95, "精確路徑，查不到就 raise", "xs mut"),
        line(890, 82, 918, 82, "edge edge-warn", W), t(904, 75, "查不到", "xs warn-t", "middle"),
        rect(920, 62, 250, 40, "warn-box"), t(932, 80, "拒絕＋稽核", "xs b warn-t"),
        t(988, 80, "surface_unregistered", "mono xs warn-t"),
        t(932, 95, "G3 在 merge 前就擋下", "xs mut"),
        line(765, 102, 765, 126, "edge", A),
        rect(640, 128, 250, 34, "box"), t(652, 150, "for stage in PIPELINE", "mono sm"),
        line(765, 162, 765, 184, "edge", A),
        rect(640, 186, 250, 40, "box"), t(652, 204, "d = adapter.dispositions[stage]", "mono xs"),
        t(652, 219, "宣告放在 adapter（Q1）", "xs mut"),
        line(890, 206, 918, 206, "edge edge-warn", W), t(904, 199, "沒填", "xs warn-t", "middle"),
        rect(920, 186, 250, 40, "warn-box"), t(932, 204, "拒絕＋稽核", "xs b warn-t"),
        t(988, 204, "disposition_missing", "mono xs warn-t"),
        t(932, 219, "G2 在 merge 前就擋下", "xs mut"),
        line(765, 226, 765, 246, "edge", None),
        line(720, 246, 1080, 246, "edge", None),
    ]
    for cx in (720, 895, 1080):
        o.append(line(cx, 246, cx, 268, "edge", A))
    o += [
        rect(640, 270, 160, 44, "run-box"), t(652, 288, "RUN", "mono sm b run-t"), t(652, 304, "執行 stage", "xs"),
        rect(815, 270, 160, 44, "na-box"), t(827, 288, "NotApplicable(ref)", "mono xs b na-t"),
        t(827, 304, "跳過，附文件編號", "xs"),
        rect(990, 270, 180, 44, "gap-box"), t(1002, 288, "KnownGap(#issue)", "mono xs b gap-t"),
        t(1002, 304, "跳過，對應 strict xfail", "xs"),
    ]
    for cx in (720, 895, 1080):
        o.append(line(cx, 314, cx, 338, "edge", A))
    o += [
        rect(640, 340, 530, 40, "box"), t(652, 358, "記一筆 stage 軌跡", "sm b"),
        t(652, 373, "conformance 比對「宣告」與「實際跑了什麼」（G4）", "xs mut"),
        t(630, 402, "順序仍只寫在 PIPELINE；宣告的是適用性，不是順序（≠ ADR-494 §4 B）", "xs mut"),
        "</svg>",
    ]
    return "".join(o)


# --------------------------------------------------------------------------
# Figure 3: where MCP / A2A go
# --------------------------------------------------------------------------

def fig_mcp():
    p = "f3"
    A, AA = f"{p}ah", f"{p}ahA"
    o = [
        '<svg class="dg" viewBox="0 0 1200 420" role="img" aria-label="'
        "MCP 有三種意思加上 A2A：(a) Responses 的 hosted MCP tool 留在 Responses 面、由 provider 代呼叫；"
        "(b) MCP gateway 是 gateway 內的新執行家族、共用治理核心；(c) Operator MCP 屬於 IAM 控制面、寫入走 HITL；"
        "A2A 等標準選定後比照 (b)。"
        '">',
        defs(p),
    ]
    lanes = [
        ("(a) hosted MCP tool", "Runtime · 既有 Responses 面", "今天整個剝除",
         [("Client", "", "box"), ("/v1/responses", "Tool 規則判定（ADR-490 v2）", "box"),
          ("模型 provider", "", "box"), ("MCP server", "由 provider 代呼叫", "box-fut")],
         ["tools[].type = mcp", "允許才轉送", "provider 執行"]),
        ("(b) MCP gateway", "Runtime · gateway 內新家族", "代理執行與否待定（#1226）",
         [("Agent", "", "box"), ("/mcp · tool-invoke", "共用同一份治理核心", "box-new"),
          ("上游 MCP server", "", "box-fut"), None],
         ["tools/call（JSON-RPC）", "治理通過才轉送", ""]),
        ("(c) Operator MCP", "Control · 屬 IAM（#1226）", "不走推論 pipeline",
         [("Agent", "", "box"), ("Operator MCP server", "read tools 直接回", "box-fut"),
          ("HITL 核可", "write tools 必經", "box-fut"), ("IAM／Fleet REST", "核可後 atomic commit＋重讀", "box")],
         ["MCP tools", "提議變更", "核可後執行"]),
        ("A2A", "Runtime · gateway 內新家族（#1107）", "等標準選定",
         [("Agent", "", "box"), ("agent-task", "委派鏈 identity 綁一次", "box-fut"),
          ("遠端 agent", "", "box-fut"), None],
         ["任務委派", "轉送任務", ""]),
    ]
    xs = [(270, 120), (450, 230), (740, 160), (960, 220)]
    for i, (title, plane, status, boxes, labels) in enumerate(lanes):
        top = 20 + i * 100
        if i:
            o.append(f'<line class="sep" x1="20" y1="{top - 6}" x2="1180" y2="{top - 6}"/>')
        o.append(t(20, top + 24, title, "sm b"))
        o.append(t(20, top + 44, plane, "xs mut"))
        o.append(t(20, top + 62, status, "xs warn-t" if i == 0 else "xs"))
        for j, bx in enumerate(boxes):
            if bx is None:
                continue
            name, sub, cls = bx
            x, w = xs[j]
            o.append(rect(x, top + 18, w, 44, cls, 6))
            mono = name.startswith("/") or name in ("agent-task",)
            if sub:
                o.append(t(x + 12, top + 36, name, ("mono " if mono else "") + "sm b"))
                o.append(t(x + 12, top + 52, sub, "xs acc-t" if cls == "box-new" else "xs mut"))
            else:
                o.append(t(x + w / 2, top + 45, name, ("mono " if mono else "") + "sm", "middle"))
        for j in range(3):
            if boxes[j + 1] is None:
                continue
            x1 = xs[j][0] + xs[j][1]
            x2 = xs[j + 1][0]
            fut = boxes[j + 1][2] == "box-fut"
            o.append(line(x1, top + 40, x2 - 2, top + 40, "edge edge-fut" if fut else "edge", A))
            if labels[j]:
                o.append(t((x1 + x2) / 2, top + 80, labels[j], "xs mut", "middle"))
    o.append("</svg>")
    return "".join(o)


# --------------------------------------------------------------------------
# Page
# --------------------------------------------------------------------------

CSS = r"""
:root{
  /* Layout: one spec-sheet column (max 1240px); figures keep their drawn width and scroll inside their own frame on narrow screens. */
  --bg:#F3F5F8; --surface:#FFFFFF; --ink:#16202C; --muted:#5B6878; --line:#D3DAE3; --line-strong:#A9B4C2;
  --accent:#2546C4; --accent-soft:#E8EDFD; --accent-ink:#1A338F;
  --run:#1D7348; --run-bg:#E2F3E9; --na:#5F6B7B; --na-bg:#ECEFF3; --gap:#985400; --gap-bg:#FBEBD3;
  --q:#7438A8; --q-bg:#F0E6FA; --off:#B0222E; --off-bg:#FBE4E6; --inl:#256584; --inl-bg:#DDEEF6;
  --font-body:"Noto Sans TC","PingFang TC","Microsoft JhengHei",system-ui,sans-serif;
  --font-mono:"IBM Plex Mono",ui-monospace,SFMono-Regular,Menlo,monospace;
}
@media (prefers-color-scheme: dark){ :root:not([data-theme="light"]){
  --bg:#0E1217; --surface:#151B23; --ink:#E2E8F0; --muted:#95A2B3; --line:#28313C; --line-strong:#465262;
  --accent:#88A2FF; --accent-soft:#19234A; --accent-ink:#BCC9FF;
  --run:#5CCB93; --run-bg:#11301F; --na:#A1ACBA; --na-bg:#1C232C; --gap:#F2AD52; --gap-bg:#3A2A12;
  --q:#CBA4F3; --q-bg:#2C1E40; --off:#FF8A92; --off-bg:#3B171B; --inl:#7CC8EC; --inl-bg:#102B38; color-scheme:dark } }
:root[data-theme="dark"]{
  --bg:#0E1217; --surface:#151B23; --ink:#E2E8F0; --muted:#95A2B3; --line:#28313C; --line-strong:#465262;
  --accent:#88A2FF; --accent-soft:#19234A; --accent-ink:#BCC9FF;
  --run:#5CCB93; --run-bg:#11301F; --na:#A1ACBA; --na-bg:#1C232C; --gap:#F2AD52; --gap-bg:#3A2A12;
  --q:#CBA4F3; --q-bg:#2C1E40; --off:#FF8A92; --off-bg:#3B171B; --inl:#7CC8EC; --inl-bg:#102B38; color-scheme:dark }

body{background:var(--bg);color:var(--ink);font-family:var(--font-body);font-size:15px;line-height:1.7}
.wrap{max-width:1240px;margin:0 auto;padding-inline:20px;padding-block:40px 64px;display:flex;flex-direction:column;gap:56px}
code,.mono{font-family:var(--font-mono)}
code{font-size:.88em;background:var(--na-bg);padding:.05em .35em;border-radius:4px}
h1,h2,h3{text-wrap:balance;margin:0;line-height:1.3}
h1{font-size:clamp(28px,4.2vw,42px);font-weight:900;letter-spacing:-.01em}
h2{font-size:22px;font-weight:700}
h3{font-size:16px;font-weight:700}
p{margin:0;max-width:68ch}
.eyebrow{font-family:var(--font-mono);font-size:12px;letter-spacing:.06em;color:var(--accent);text-transform:uppercase}
.sec{display:flex;flex-direction:column;gap:16px}
.sec>header{display:flex;flex-direction:column;gap:6px}
.lede{font-size:17px;color:var(--ink);max-width:62ch}
.meta{display:flex;flex-wrap:wrap;gap:8px 18px;font-size:13px;color:var(--muted)}
.meta b{color:var(--ink);font-weight:500}
.top{display:flex;flex-direction:column;gap:18px}
.points{margin:0;padding-left:1.2em;display:flex;flex-direction:column;gap:6px;max-width:72ch}
.crit{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px}
.crit>div{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:14px 16px;display:flex;flex-direction:column;gap:6px;min-width:0}
.crit .k{font-family:var(--font-mono);font-size:12px;color:var(--accent);font-weight:500}
.crit .q{font-weight:700}
.crit .a{font-size:13.5px;color:var(--muted)}
nav.toc{display:flex;flex-wrap:wrap;gap:6px 14px;font-size:13px}
nav.toc a{color:var(--accent);text-decoration:none;border-bottom:1px solid transparent}
nav.toc a:hover,nav.toc a:focus-visible{border-bottom-color:var(--accent)}
a:focus-visible,button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}

figure{margin:0;display:flex;flex-direction:column;gap:10px}
.frame{background:var(--surface);border:1px solid var(--line);border-radius:12px;overflow-x:auto;padding:12px}
.frame svg{display:block;width:100%;min-width:1000px;height:auto}
figcaption{font-size:13.5px;color:var(--muted);max-width:80ch}

.dg{color:var(--muted);font-family:var(--font-body)}
.dg text{fill:var(--ink);font-size:12px}
.dg .hdr{fill:var(--muted);font-size:11.5px;font-weight:500;letter-spacing:.03em}
.dg .mono{font-family:var(--font-mono)}
.dg .sm{font-size:12px}
.dg .xs{font-size:10.5px}
.dg .xxs{font-size:10px}
.dg .b{font-weight:700}
.dg .mut{fill:var(--muted)}
.dg .acc-t{fill:var(--accent-ink)}
.dg .warn-t{fill:var(--off)}
.dg .run-t{fill:var(--run)} .dg .na-t{fill:var(--na)} .dg .gap-t{fill:var(--gap)}
.dg .box{fill:var(--surface);stroke:var(--line-strong);stroke-width:1}
.dg .box-new{fill:var(--surface);stroke:var(--accent);stroke-width:1.4}
.dg .box-fut{fill:none;stroke:var(--line-strong);stroke-width:1;stroke-dasharray:4 3}
.dg .core{fill:var(--accent-soft);stroke:var(--accent);stroke-width:1.5}
.dg .term{fill:var(--surface);stroke:var(--accent);stroke-width:1.5}
.dg .chip{fill:var(--surface);stroke:var(--line)}
.dg .chip-m{fill:var(--surface);stroke:var(--accent);stroke-width:1.6}
.dg .bnd{fill:none;stroke:var(--line-strong);stroke-width:1;stroke-dasharray:7 5}
.dg .panel{fill:none;stroke:var(--line)}
.dg .sep{stroke:var(--line)}
.dg .warn-box{fill:var(--off-bg);stroke:var(--off);stroke-width:1}
.dg .run-box{fill:var(--run-bg);stroke:var(--run)}
.dg .na-box{fill:var(--na-bg);stroke:var(--na)}
.dg .gap-box{fill:var(--gap-bg);stroke:var(--gap)}
.dg .edge{fill:none;stroke:currentColor;stroke-width:1.2}
.dg .edge-fut{stroke-dasharray:4 3}
.dg .edge-warn{stroke:var(--off)}
.dg .ah{fill:var(--muted)} .dg .ahA{fill:var(--accent)} .dg .ahW{fill:var(--off)}

.howto{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:10px 24px;margin:0;padding:0;list-style:none;font-size:14px}
.howto li{display:flex;gap:10px;min-width:0}
.howto b{font-family:var(--font-mono);color:var(--accent);font-weight:500;flex:none}

.toolbar{display:flex;flex-wrap:wrap;align-items:center;gap:10px 16px}
.seg{display:inline-flex;border:1px solid var(--line-strong);border-radius:8px;overflow:hidden}
.seg button{font:inherit;font-size:13.5px;padding:6px 14px;background:var(--surface);color:var(--ink);border:0;cursor:pointer}
.seg button+button{border-left:1px solid var(--line-strong)}
.seg button[aria-pressed="true"]{background:var(--accent);color:var(--surface)}
.count{font-size:13.5px;color:var(--muted)}
.count b{color:var(--off);font-variant-numeric:tabular-nums}
.legend{display:flex;flex-wrap:wrap;gap:6px 12px;font-size:12.5px;color:var(--muted)}
.legend span{display:inline-flex;align-items:center;gap:6px}
.tbl{overflow-x:auto;background:var(--surface);border:1px solid var(--line);border-radius:12px}
table{border-collapse:collapse;width:100%;font-size:13px}
th,td{padding:7px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
thead th{font-weight:500;color:var(--muted);font-size:12px;white-space:nowrap;background:var(--surface);position:sticky;top:0}
tbody tr:last-child td,tbody tr:last-child th{border-bottom:0}
.mx th[scope=row]{font-family:var(--font-mono);font-weight:400;white-space:nowrap}
.mx th[scope=row] .n{color:var(--muted);margin-right:8px;font-variant-numeric:tabular-nums}
.mx th[scope=row].m{font-weight:600;color:var(--accent-ink)}
.mx .tag-m{font-family:var(--font-body);font-size:11px;color:var(--accent);border:1px solid var(--accent);border-radius:4px;padding:0 4px;margin-left:6px}
.mx td.c{white-space:nowrap;text-align:center}
.mx td.note{color:var(--muted);font-size:12.5px;min-width:220px}
.mx tr.grp td{background:var(--na-bg);color:var(--muted);font-size:12px;padding:4px 10px}
.mx .divider{border-left:2px solid var(--line-strong)}
.cell{display:inline-block;min-width:64px;padding:1px 8px;border-radius:5px;font-size:12px;font-family:var(--font-mono);border:1px solid transparent}
.cell.R{background:var(--run-bg);color:var(--run);border-color:color-mix(in srgb,var(--run) 35%,transparent)}
.cell.N{background:var(--na-bg);color:var(--na)}
.cell.G{background:var(--gap-bg);color:var(--gap);border-color:color-mix(in srgb,var(--gap) 40%,transparent)}
.cell.Q{background:var(--q-bg);color:var(--q);border-color:color-mix(in srgb,var(--q) 40%,transparent)}
.cell.O{background:var(--off-bg);color:var(--off);border-color:color-mix(in srgb,var(--off) 45%,transparent);font-weight:600}
.cell.I{background:var(--inl-bg);color:var(--inl)}
.cell.D{background:transparent;color:var(--muted)}

.cols{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px}
.card{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:14px 16px;display:flex;flex-direction:column;gap:8px;min-width:0}
.card ul{margin:0;padding-left:1.1em;display:flex;flex-direction:column;gap:4px;font-size:14px}
.card h3 .s{font-weight:400;color:var(--muted);font-size:13px;margin-left:6px}

.track{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:12px}
.phase{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:14px 16px;display:flex;flex-direction:column;gap:10px;min-width:0}
.phase h3{display:flex;align-items:baseline;gap:8px;flex-wrap:wrap}
.phase h3 .s{font-weight:400;color:var(--muted);font-size:13px}
.phase ol{margin:0;padding:0;list-style:none;display:flex;flex-direction:column;gap:8px}
.phase li{display:grid;grid-template-columns:48px 1fr;gap:8px;font-size:13.5px}
.phase li .id{font-family:var(--font-mono);color:var(--accent);font-weight:500}
.chg{font-size:11px;color:var(--gap);border:1px solid var(--gap);border-radius:4px;padding:0 5px;margin-left:6px;white-space:nowrap}
.gatebar{font-size:13.5px;border:1px dashed var(--gap);color:var(--ink);background:var(--gap-bg);border-radius:8px;padding:8px 12px}

.s123{display:inline-flex;gap:4px}
.s123 i{font-style:normal;font-family:var(--font-mono);font-size:11px;padding:0 5px;border-radius:4px;border:1px solid var(--accent);color:var(--accent)}
.top3 td:first-child{font-weight:700;color:var(--accent-ink)}
.first{font-size:11px;color:var(--surface);background:var(--accent);border-radius:4px;padding:1px 6px;margin-left:6px;white-space:nowrap}
.oos{display:flex;flex-wrap:wrap;gap:8px;margin:0;padding:0;list-style:none}
.oos li{font-size:13px;border:1px solid var(--line-strong);border-radius:999px;padding:3px 12px;background:var(--surface)}
footer{font-size:12.5px;color:var(--muted);border-top:1px solid var(--line);padding-top:16px;display:flex;flex-direction:column;gap:4px}
@media (max-width:520px){ .wrap{padding-inline:16px;gap:44px} .lede{font-size:16px} }
@media (prefers-reduced-motion:reduce){ *{transition:none!important} }
"""

MATRIX_JS = r"""
(function(){
  var S=["chat","messages","responses","embeddings","audio.speech","audio.transcriptions"];
  var ROWS=[
    ["auth",1,"R R R I I I","R R R R R R","三個 route 自己呼叫 authenticate_request","強制"],
    ["request_fields",1,"R R R O O O","R R R R R R","去向表只有三面（request_fields.py:177）","強制；要建去向表與 SDK 快照"],
    ["session",0,"R R R O O O","R R R N N N","","沒有多輪對話（ADR-447）"],
    ["policy_actions",1,"R R R O O O","R R R R R R","這三面的 action 是 inert","強制"],
    ["tool_results",0,"R R R O O O","R R R N N N","","沒有工具（ADR-490）"],
    ["tool_rules",0,"R R R O O O","R R R N N N","","沒有工具（ADR-490）"],
    ["input_rail",0,"R R R O O O","R R R Q:Q3 Q:Q3 R:prompt","input 沒掃；沒有文件說是刻意","Q3 建議先 shadow"],
    ["semantic_cache",0,"R R G:#4247 O O O","R R G:#4247 N N N","Responses 延後（#4247）","ADR-054 只針對生成"],
    ["request_policy",0,"R R R O O O","R R R R R R","",""],
    ["store",0,"N N R O O O","N N R N N N","只屬 Responses（PRD-157）","只屬 Responses（PRD-157）"],
    ["addressing",0,"R R R I O I","R R R R R R","embeddings 不查 binding；speech 不查模型；transcription 未知模型退回預設","transcription 未知模型改 404（行為變更）"],
    ["budget",1,"R R R I I I","R R R R R R","經 run_admission","強制"],
    ["routing",0,"R R R O O O","R R R Q:Q5 Q:Q5 Q:Q5","繞過（audio_passthrough）","Q5 建議 v1 不適用"],
    ["policy_kernel",0,"R R R:shadow O O O","R R R:shadow R R R","Responses 預設 shadow（#1060）；speech provider 寫死 openai",""],
    ["agent_mode",0,"N N R O O O","N N R N N N","只屬 Responses（ADR-437 D5）","只屬 Responses（ADR-437 D5）"],
    ["chain",0,"N N R O O O","N N R N N N","只屬 Responses（PRD-157）","只屬 Responses（PRD-157）"],
    ["classifier_and_admission",1,"R R R I I I","R R R R R R","經 admit_audio","強制"],
    ["endpoint_lease",0,"R R R O O O","R R R R R R","Resource Manager lease 只在 pipeline 內","只對地端端點有作用"],
    null,
    ["output rail",0,"R R R O O O","R R R N N Q:Q4","transcript 原樣回傳","Q4 建議跑"],
    ["terminal",1,"R R R I I I","R R R R R R","自己 emit 與記帳，沒走 terminal.py","強制"]
  ];
  var LABEL={R:"RUN",N:"不適用",G:"缺口",O:"沒有",I:"自己做",D:"—"};
  var tbody=document.getElementById("mx-body");
  var countEl=document.getElementById("mx-count");
  function cellHtml(code,extra){
    var txt=code==="Q"?extra:(LABEL[code]+(extra?(code==="G"?" "+extra:"·"+extra):""));
    return '<span class="cell '+code+'">'+txt+'</span>';
  }
  function render(view){
    var html="",red=0,n=0;
    ROWS.forEach(function(r){
      if(r===null){ html+='<tr class="grp"><td colspan="8">串流／執行段（L3）與 terminal</td></tr>'; return; }
      if(r[0]!=="output rail"&&r[0]!=="terminal"){ n++; }
      var now=r[2].split(" "), tgt=r[3].split(" "), use=view==="now"?now:tgt;
      var head='<th scope="row"'+(r[1]?' class="m"':'')+'>'+(r[0]==="output rail"||r[0]==="terminal"?'<span class="n">L3</span>':'<span class="n">'+String(n).padStart(2,"0")+'</span>')+r[0]+(r[1]?'<span class="tag-m">強制</span>':'')+'</th>';
      var cells="";
      use.forEach(function(v,i){
        var parts=v.split(":"), code=parts[0], extra=parts[1]||"";
        if(view==="now"&&code==="O"&&tgt[i].charAt(0)==="N"){ code="D"; }
        if(view==="now"&&code==="O"){ red++; }
        cells+='<td class="c'+(i===3?' divider':'')+'">'+cellHtml(code,extra)+'</td>';
      });
      html+='<tr>'+head+cells+'<td class="note">'+(view==="now"?r[4]:r[5])+'</td></tr>';
    });
    tbody.innerHTML=html;
    countEl.innerHTML=view==="now"
      ? '紅格＝目標要跑、今天沒有：<b>'+red+'</b> 格，全在 embeddings／audio'
      : '目標：每格都有明確處置；Q 是要你決定的格子';
    document.querySelectorAll(".seg button").forEach(function(b){ b.setAttribute("aria-pressed", String(b.dataset.view===view)); });
    try{ localStorage.setItem("mx-view",view); }catch(_){}
  }
  document.querySelectorAll(".seg button").forEach(function(b){ b.addEventListener("click",function(){ render(b.dataset.view); }); });
  var start="now"; try{ var s=localStorage.getItem("mx-view"); if(s==="now"||s==="tgt"){ start=s; } }catch(_){}
  render(start);
})();
"""


def table(head, rows, cls=""):
    h = "".join(f"<th>{c}</th>" for c in head)
    b = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<div class="tbl"><table class="{cls}"><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table></div>'


def page():
    gates = [
        ["G1", "面登記表是唯一來源", "路由、conformance fixture、請求欄位 gate、terminal 鎖都從同一張表導出，不再有手寫的面清單", "S1 S3"],
        ["G2", "處置窮舉 gate", "每個「已登記面 × stage」恰好一個處置；強制 stage 不得不適用；不適用附文件編號、缺口附 #issue", "S2 S3"],
        ["G3", "路由覆蓋 gate", "從真 app 列舉路由：會執行的 route 必須經過 <code>run_pre_dispatch</code>，否則要歸類為非執行並附理由", "S3"],
        ["G4", "conformance＋執行期軌跡", "每支測試跑所有已登記的面；<b>實際跑到的 stage</b> 必須等於宣告的處置", "S3"],
        ["G5", "單一 terminal", "只有 <code>terminal.py</code> emit 三種終端事件；每個家族都以 <code>settle_*</code> 結束", "S2"],
        ["G6", "執行期 fail-closed", "未登記的面、缺處置 → 拒絕＋稽核（最後一道防線）", "S3"],
        ["G7", "usage 解析窮舉", "每個 <code>usage_unit</code> 都有解析函式；不認得的終端形狀要紅，不能算成 0", "S2"],
    ]
    gates_rows = [[f'<span class="mono">{g[0]}</span>', f"<b>{g[1]}</b>", g[2],
                   '<span class="s123">' + "".join(f"<i>{s}</i>" for s in g[3].split()) + "</span>"] for g in gates]

    ext = [
        ["LiteLLM", "共用 <code>base_process_llm_request</code>；guardrail 依 call_type 配 adapter",
         "沒 adapter 的 call_type 直接 <code>return data</code>（<code>unified_guardrail.py:222-226</code>）", "MCP＋A2A 都有，同 pipeline"],
        ["Bifrost", "一個 union 型別＋一條 plugin pipeline（含串流）",
         "治理 plugin 的 token 計數 switch 漏 image／rerank／OCR／video（<code>governance/main.go:1661-1683</code>）", "MCP 同 pipeline、另一組 hook"],
        ["Portkey OSS", "一條 <code>tryPost</code>；每個面只是一個 <code>fn</code> 字串",
         "<code>shouldSkipHook</code> 只認 4 種，Responses／圖片／音訊的 guardrail 靜默跳過（<code>hooks/index.ts:449-464</code>）", "沒有"],
        ["One-API", "auth、選 channel 在 middleware",
         "計費在 text／image／audio 各寫一份；proxy 不計費（<code>proxy.go:17-41</code>）", "沒有"],
        ["vLLM", "共用 <code>BaseServing</code>；Messages 是 chat 的 adapter",
         "auth 只看路徑前綴，<code>/tokenize</code>、<code>/score</code>、<code>/rerank</code> 沒保護（<code>authenticate.py:11</code>）", "MCP 只接給 Responses"],
    ]

    qs = [
        ["Q1", "處置宣告放哪", "放在各 adapter，核心只標強制 stage（新增面才能只動 adapter）", True],
        ["Q3", "embeddings／speech 跑不跑 input rail", "跑，先 shadow：embeddings 的 PII 會進客戶的向量庫", True],
        ["Q7", "三種 MCP 哪個先", "先 (a)（ADR-490 v2 已有設計）；(b) 等「也代理執行」定案（#1104 已關閉，題目在 #1226）", True],
        ["Q2", "<code>PIPELINE</code> 一份還是每家族一份", "一份；分家族會讓新功能要接好幾次", False],
        ["Q4", "transcription 輸出過 output rail", "跑，比照 chat 非串流", False],
        ["Q5", "embeddings／audio 要不要 routing", "v1 不適用", False],
        ["Q6", "<code>count_tokens</code>", "歸類為非執行（不呼叫 provider、不記帳）", False],
        ["Q8", "A2A", "等標準；先保留 agent-task 家族的位置", False],
        ["Q9", "文件形式", "ADR-494 Amendment A＋ADR-492 改 Accepted 並出 Amendment", False],
        ["Q10", "agent mode 少了串流段治理", "先實測 lease 釋放；output rail 無依據就標缺口", False],
        ["Q11", "未登記面的狀態碼", "500＋稽核 <code>surface_unregistered</code>；CI 讓它不會在線上發生", False],
    ]
    q_rows = ""
    for q, ask, rec, first in qs:
        flag = '<span class="first">先決定</span>' if first else ""
        q_rows += (f'<tr class="{"top3" if first else ""}"><td class="mono">{q}</td>'
                   f"<td>{ask}{flag}</td><td>{rec}</td></tr>")

    return f"""<title>LLM API 面重整架構</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=Noto+Sans+TC:wght@400;500;700;900&display=swap">
<style>{CSS}</style>
<div class="wrap">

<section class="top">
  <span class="eyebrow">Xparse Gateway · 架構草案（不是 ADR）</span>
  <h1>LLM API 面重整架構</h1>
  <p class="lede">chat、messages、responses、embeddings、audio，以及之後的 images、MCP、A2A，格式都不同，但都要過同一套認證、政策、預算、稽核與記帳。這份設計建立在已核定的 ADR-494（共用 pipeline）與 ADR-492（跨面 conformance）之上。</p>
  <ul class="points">
    <li><b>不拆 service。</b>一個 gateway owner、一份治理核心、每個面一個 adapter。PRD-302 下另開一個 app 就不能共用治理程式碼。</li>
    <li><b>要修的是「預設跳過」。</b>五家參考平台和我們的 <code>run_pre_dispatch</code> 都一樣：不認得的面就跳過，請求照樣放行。</li>
    <li><b>改成一張不能留白的「面 × stage」處置表。</b>CI 從真路由導出面的清單，再檢查每格都填了、實際跑的和宣告的一致。</li>
  </ul>
  <div class="meta"><span>基準 <b class="mono">origin/main 3d78bf885</b></span><span>日期 <b>2026-10-05</b></span><span>草案全文 <b class="mono">docs/草案/LLM-api-重構.md</b></span></div>
  <div class="crit">
    <div><span class="k">S1</span><span class="q">新增一個 API 面，只寫 adapter</span><span class="a">adapter Protocol＋面登記表＋adapter 自帶處置宣告；治理核心不動</span></div>
    <div><span class="k">S2</span><span class="q">新增一個治理功能，只接一次</span><span class="a"><code>PIPELINE</code> 只有一份；新 stage 一加，每個面都得宣告處置</span></div>
    <div><span class="k">S3</span><span class="q">任一面漏接，CI 會紅</span><span class="a">路由 gate、處置窮舉 gate、執行期軌跡比對、未知面 fail-closed</span></div>
  </div>
  <nav class="toc" aria-label="章節">
    <a href="#arch">全貌</a><a href="#skip">預設跳過</a><a href="#matrix">處置表</a><a href="#mcp">MCP／A2A</a><a href="#gates">防回歸</a><a href="#slices">遷移切片</a><a href="#peers">外部對照</a><a href="#decide">要決定的事</a>
  </nav>
</section>

<section class="sec" id="arch">
  <header><span class="eyebrow">草案 §3</span><h2>一張圖看全貌</h2></header>
  <figure>
    <div class="frame">{fig_main()}</div>
    <figcaption>請求從左進、往右走。L1 只碰 wire；所有治理判斷都在中間那一份核心；執行依工作負載形狀分四個家族，但都回到同一個 terminal 記帳與稽核。藍框是這次新增的部分，虛線是還沒有的面。</figcaption>
  </figure>
  <ul class="howto">
    <li><b>L1</b><span>adapter 把 wire 讀成中立的 <code>SurfaceInput</code>、過濾候選模型、把中立的拒絕與終端渲染回自己的格式。不做任何治理判斷。</span></li>
    <li><b>L2</b><span>面登記表、順序寫死的 <code>PIPELINE</code>、處置表、terminal。依面寫 <code>if</code> 不准出現在這裡；差異只能是具名的 adapter 參數。</span></li>
    <li><b>L3</b><span>依工作負載形狀分家族。串流引擎不合併（ADR-494 §4 C），只共用 deadline、resilience、usage 解析。</span></li>
    <li><b>邊界</b><span>IAM 與 Audit 是別的 owner，只經 HTTP。Operator MCP 屬於 IAM 控制面，不走推論 pipeline。</span></li>
  </ul>
</section>

<section class="sec" id="skip">
  <header><span class="eyebrow">草案 §2.3 · §3.3</span><h2>要修的機制：從「預設跳過」到「窮舉處置」</h2></header>
  <figure>
    <div class="frame">{fig_skip()}</div>
    <figcaption>左邊是今天的程式碼：stage 不認得這個面就 <code>continue</code>，ADR 寫了 INV-494-4（fail-closed），但沒有實作。右邊拿掉預設值：查不到面、某格沒填都拒絕並留稽核，而且 CI 在 merge 前就擋下；三種處置都記成軌跡，讓 conformance 比對「宣告」和「實際」。</figcaption>
  </figure>
</section>

<section class="sec" id="matrix">
  <header><span class="eyebrow">草案 §2.2 · §4.2</span><h2>面 × stage 處置表</h2>
  <p>每一列是 <code>PIPELINE</code> 的一個 stage（編號是真實的執行順序），每一欄是一個面。切換看今天和目標的差別。</p></header>
  <div class="toolbar">
    <div class="seg" role="group" aria-label="切換檢視">
      <button type="button" id="mx-now" data-view="now" aria-pressed="true">今天</button>
      <button type="button" id="mx-tgt" data-view="tgt" aria-pressed="false">目標</button>
    </div>
    <span class="count" id="mx-count"></span>
  </div>
  <div class="legend">
    <span><span class="cell R">RUN</span>跑</span>
    <span><span class="cell N">不適用</span>附文件編號</span>
    <span><span class="cell G">缺口</span>附 issue</span>
    <span><span class="cell Q">Q3</span>等你決定</span>
    <span><span class="cell O">沒有</span>目標要跑、今天沒有</span>
    <span><span class="cell I">自己做</span>在 pipeline 外各自實作</span>
    <span><span class="cell D">—</span>不在 pipeline，也不需要</span>
  </div>
  <div class="tbl"><table class="mx">
    <thead><tr><th>stage</th><th>chat</th><th>messages</th><th>responses</th><th class="divider">embeddings</th><th>audio.speech</th><th>audio.transcriptions</th><th>說明</th></tr></thead>
    <tbody id="mx-body"></tbody>
  </table></div>
</section>

<section class="sec" id="mcp">
  <header><span class="eyebrow">草案 §5</span><h2>MCP／A2A 放哪</h2>
  <p>「MCP」在 roadmap 上有三種不同的意思，放的位置也不同。</p></header>
  <figure>
    <div class="frame">{fig_mcp()}</div>
    <figcaption>(b) 放在 gateway 內，是因為 PRD-302 不准跨 owner 共用 package：另開一個 MCP app 就得把治理再寫一份。要不要拆 process 是部署層的決定，同一個 image、不同的路由 allowlist 就能做到。</figcaption>
  </figure>
  <div class="cols">
    <div class="card"><h3>共用<span class="s">(b) MCP gateway 與 A2A</span></h3>
      <ul><li>認證（IAM validate）、請求欄位去向、policy actions</li><li>預算閘、admission／並發</li><li>稽核生命週期、terminal 與記帳（單位：工具呼叫次數、任務數）</li><li>面登記表、處置表、conformance</li></ul></div>
    <div class="card"><h3>不共用<span class="s">各自的執行家族</span></h3>
      <ul><li>定址、routing、semantic cache（沒有模型）</li><li>串流引擎</li><li>session 狀態（MCP session id、A2A task id）</li><li>只屬工具的 stage：上游 server allowlist、呼叫頻率（推論面宣告不適用）</li></ul></div>
    <div class="card"><h3>待定<span class="s">Q7</span></h3>
      <ul><li>input／output rail 套在工具參數與結果上（LiteLLM 有做）</li><li>Policy Kernel 的資料邊界套在上游 MCP server 的位置</li></ul></div>
  </div>
</section>

<section class="sec" id="gates">
  <header><span class="eyebrow">草案 §7</span><h2>防回歸：漏接怎麼變紅</h2>
  <p>G1、G2、G5 是純 stdlib 的靜態檢查；G4 沿用現有的 gateway owner suite。每個 gate 都要先看它對植入的回歸變紅過才算數。G4 是關鍵：沒有執行期軌跡，處置表只是另一份宣告。</p></header>
  {table(["#", "機制", "鎖什麼", "對應"], gates_rows)}
</section>

<section class="sec" id="slices">
  <header><span class="eyebrow">草案 §6</span><h2>遷移切片</h2>
  <p>每片都可以獨立 merge，對 client 的行為不變；標「行為變更」的片各自一個 PR、各自宣告。先讓漏接會紅，再把新的面搬進來。</p></header>
  <div class="gatebar"><b>開工條件：</b>等 <code>/v1/responses</code> 第二輪（W1–W16）部署到 rel 並重跑 <code>responses_gap_probe.py</code> 之後再開 M1。M1–M5 會動到同一批檔案。</div>
  <div class="track">
    <div class="phase"><h3>讓漏接會紅<span class="s">M0–M5</span></h3><ol>
      <li><span class="id">M0</span><span>ADR-494 Amendment A、ADR-492 Amendment、SPEC-308／306 修訂</span></li>
      <li><span class="id">M1</span><span>面登記表；adapter 用精確路徑查面；未登記的面 fail-closed＋稽核</span></li>
      <li><span class="id">M2</span><span>處置表取代 <code>Stage.surfaces</code>（三面照今天的行為填）；adapter 改 Protocol；messages 拆出來</span></li>
      <li><span class="id">M3</span><span>conformance 從登記表導出；「事件 × 面」範圍；執行期軌跡；保留第二輪的 fake provider 形狀</span></li>
      <li><span class="id">M4</span><span>路由 gate；embeddings／audio 暫列 <code>legacy_unpiped</code>，名單只能縮小</span></li>
      <li><span class="id">M5</span><span>terminal 唯一化：STARTED 收成一處、非串流 FAILED 走 <code>settle_failed</code>（附中性證明）</span></li>
    </ol></div>
    <div class="phase"><h3>搬進來<span class="s">M6a–M7</span></h3><ol>
      <li><span class="id">M6a</span><span>修 embeddings 失敗時 FAILED＋COMPLETED 都發（讀碼確認）<span class="chg">行為變更</span></span></li>
      <li><span class="id">M6</span><span>embeddings adapter＋unary 家族；沒接的 stage 先宣告缺口，所以行為不變</span></li>
      <li><span class="id">M7</span><span>speech、transcriptions 同 M6</span></li>
    </ol></div>
    <div class="phase"><h3>補缺口<span class="s">M8–M9</span></h3><ol>
      <li><span class="id">M8…</span><span>一個缺口一個 PR：policy_actions → request_fields → addressing → policy_kernel → endpoint_lease → input rail → transcription output rail<span class="chg">各自宣告</span></span></li>
      <li><span class="id">M9</span><span><code>count_tokens</code> 登記成面或歸類為非執行（Q6）</span></li>
      <li><span class="id">之後</span><span>MCP gateway（先寫 PRD／ADR）；A2A（先選標準）</span></li>
    </ol></div>
  </div>
</section>

<section class="sec" id="peers">
  <header><span class="eyebrow">草案 §2.4 · 附錄 A</span><h2>外部對照</h2>
  <p>五家都有某種共用 pipeline，漏洞全出在「功能內依面分流，遇到沒處理的面就預設跳過」。手刻流程的面漏得最多，正是我們 embeddings／audio 的現況。</p></header>
  {table(["平台", "共用的部分", "漏在哪", "MCP／A2A"], ext)}
</section>

<section class="sec" id="decide">
  <header><span class="eyebrow">草案 §8</span><h2>要決定的事</h2></header>
  <div class="tbl"><table><thead><tr><th>#</th><th>問題</th><th>建議</th></tr></thead><tbody>{q_rows}</tbody></table></div>
  <h3>不做的事</h3>
  <ul class="oos">
    <li>合併串流引擎（ADR-494 §4 C）</li><li>宣告式排序／hook 登記表（§4 B）</li><li>每個面拆成獨立 service</li>
    <li>全部轉成 chat 的萬用格式</li><li>commit point 延後</li><li>Realtime／WebSocket 面</li><li>音訊計價</li><li>改變任何政策語意</li>
  </ul>
</section>

<footer>
  <span>程式行號以 <span class="mono">origin/main 3d78bf885</span> 為準；外部平台原始碼為 LiteLLM sep-29、Bifrost、Portkey 1.15.2、One-API、vLLM 的 2026-10-05 快照。</span>
  <span>與 <code>/v1/responses</code> 兩輪修補的關係見草案 §11：沒有推翻任何既有決定。</span>
</footer>
</div>
<script>{MATRIX_JS}</script>
"""


OUT.write_text(page(), encoding="utf-8")
print(OUT, OUT.stat().st_size)
