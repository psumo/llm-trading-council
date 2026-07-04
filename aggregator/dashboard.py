"""Self-contained dark trading-terminal dashboard. No build step, vanilla JS.

Layout (top -> bottom, by the manual trader's eye-path "do I act now?"):

  1. ACCOUNT STRIP  -- one compact row: balance + inline equity sparkline,
     return %, win rate, trades, profit factor, max DD as stat chips.
  2. ACTION ROW     -- 4 signal tiles (one per instrument). Each tile shows the
     judge direction as the dominant visual (big LONG/SHORT/FLAT), live price,
     conviction bar, tf_alignment one-liner, and an open-position / stale /
     market badge. The tiles ARE the tabs: clicking one selects it.
  3. DETAIL ZONE    -- for the selected symbol: judge panel (trade ticket +
     rationale/invalidation/disagreements), confluence status line, then the
     three source columns with their full rich detail (every original field
     preserved) and scorecard badges inline in each source header.
  4. FOOTER ZONE    -- collapsible: journal conditional-stats, lessons list, and
     the events table (events open by default, the rest collapsed).

All dynamic text is escaped (esc) before insertion and the page is served UTF-8
so Chinese reasoning text from the tradebot renders correctly. Color is used only
for semantics (long=green, short=red, flat/neutral=amber, offline=dim) plus one
blue accent. Numbers use tabular-nums everywhere.
"""
from __future__ import annotations

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>&#128202;</text></svg>"/>
<title>Confluence Aggregator</title>
<style>
  :root {
    --bg:#0a0e14; --panel:#0f141b; --panel2:#11161f; --raised:#161c26;
    --border:#222b36; --border2:#2c3744;
    --txt:#cdd6e0; --muted:#8a97a6; --dim:#5c6773;
    --long:#2ecc71; --short:#ff5252; --neutral:#e0a52b; --flat:#e0a52b;
    --offline:#5c6773; --amber:#e0a52b; --accent:#4aa3ff;
    --pos:#2ecc71; --neg:#ff5252; --fg:#cdd6e0;
    --s1:4px; --s2:8px; --s3:12px; --s4:16px; --s6:24px;
  }
  * { box-sizing:border-box; }
  html,body { background:var(--bg); }
  body { margin:0; color:var(--txt);
    font-family:"Inter","Segoe UI",system-ui,sans-serif; font-size:13px; line-height:1.45;
    font-variant-numeric:tabular-nums; -webkit-font-smoothing:antialiased; }
  .num { font-variant-numeric:tabular-nums; font-feature-settings:"tnum" 1; }
  main { max-width:1680px; margin:0 auto; padding:var(--s3) var(--s4) var(--s6);
    display:flex; flex-direction:column; gap:var(--s4); }

  .hd { font-size:10px; letter-spacing:1.4px; text-transform:uppercase;
    color:var(--muted); font-weight:600; }
  .dir-long,.dir-LONG{ color:var(--long); }
  .dir-short,.dir-SHORT{ color:var(--short); }
  .dir-neutral,.dir-flat,.dir-FLAT,.dir-NEUTRAL{ color:var(--flat); }
  .dir-offline{ color:var(--offline); }

  /* ============ 1. ACCOUNT STRIP ============ */
  .acct { display:flex; align-items:center; gap:var(--s4); flex-wrap:wrap;
    background:linear-gradient(180deg,var(--panel2),var(--panel));
    border:1px solid var(--border); border-radius:12px; padding:var(--s3) var(--s4); }
  .acct-bal { display:flex; align-items:center; gap:var(--s3); padding-right:var(--s4);
    border-right:1px solid var(--border); }
  .acct-bal .lab { font-size:9.5px; letter-spacing:1px; text-transform:uppercase;
    color:var(--muted); }
  .acct-bal .val { font-size:26px; font-weight:800; line-height:1; }
  .acct-bal .ret { font-size:12px; font-weight:700; margin-top:3px; }
  .acct-bal .ret.pos{ color:var(--pos); } .acct-bal .ret.neg{ color:var(--neg); }
  .spark { display:block; }
  .chips { display:flex; gap:var(--s2); flex-wrap:wrap; flex:1; }
  .chip-s { background:var(--raised); border:1px solid var(--border);
    border-radius:8px; padding:6px 12px; display:flex; flex-direction:column;
    gap:2px; min-width:74px; }
  .chip-s .cl { font-size:9px; letter-spacing:.7px; text-transform:uppercase;
    color:var(--muted); }
  .chip-s .cv { font-size:15px; font-weight:700; line-height:1.1; }
  .chip-s .cv.pos{ color:var(--pos); } .chip-s .cv.neg{ color:var(--neg); }
  .acct-meta { display:flex; flex-direction:column; gap:2px; align-items:flex-end;
    font-size:10.5px; color:var(--muted); white-space:nowrap; }
  .acct-meta .warn { color:var(--amber); }

  /* ============ 2. ACTION ROW (signal tiles = tabs) ============ */
  .row-lab { display:flex; align-items:baseline; gap:var(--s2); margin:-4px 0 -4px; }
  .tiles { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:var(--s3); }
  .tile { cursor:pointer; user-select:none; position:relative; overflow:hidden;
    background:var(--panel); border:1px solid var(--border); border-radius:12px;
    padding:var(--s3) var(--s3) var(--s2); display:flex; flex-direction:column;
    gap:var(--s2); transition:border-color .18s, transform .12s, box-shadow .18s; }
  .tile:hover { border-color:var(--border2); transform:translateY(-1px); }
  .tile.sel { border-color:var(--accent);
    box-shadow:0 0 0 1px var(--accent), 0 4px 18px -8px rgba(74,163,255,.5); }
  .tile.t-long::before,.tile.t-short::before,.tile.t-flat::before{
    content:""; position:absolute; left:0; top:0; bottom:0; width:3px; }
  .tile.t-long::before{ background:var(--long); }
  .tile.t-short::before{ background:var(--short); }
  .tile.t-flat::before{ background:var(--flat); }
  .tile-top { display:flex; align-items:flex-start; justify-content:space-between;
    gap:var(--s2); }
  .tile-sym { font-size:14px; font-weight:800; letter-spacing:.5px; }
  .tile-sym small { color:var(--dim); font-weight:600; font-size:10px;
    letter-spacing:0; }
  .tile-px { font-size:13px; font-weight:700; color:var(--txt); }
  .tile-px .pxstale { color:var(--amber); font-size:10px; }
  .tile-dir { font-size:30px; font-weight:800; line-height:.95; letter-spacing:.5px; }
  .tile-conv { display:flex; flex-direction:column; gap:3px; }
  .tile-conv .clab { display:flex; justify-content:space-between; font-size:9.5px;
    letter-spacing:.6px; text-transform:uppercase; color:var(--muted); }
  .convbar { height:5px; border-radius:3px; background:var(--raised);
    overflow:hidden; }
  .convbar > i { display:block; height:100%; border-radius:3px; }
  .t-long .convbar > i{ background:var(--long); }
  .t-short .convbar > i{ background:var(--short); }
  .t-flat .convbar > i{ background:var(--flat); }
  .tile-tf { font-size:10.5px; color:var(--muted); line-height:1.35;
    min-height:2.7em; }
  .tile-badges { display:flex; flex-wrap:wrap; gap:var(--s1); margin-top:auto;
    padding-top:2px; }
  .tb { font-size:9.5px; font-weight:700; letter-spacing:.4px; padding:2px 7px;
    border-radius:999px; line-height:1.5; }
  .tb-open-long{ background:rgba(46,204,113,.14); color:var(--long);
    border:1px solid rgba(46,204,113,.45); }
  .tb-open-short{ background:rgba(255,82,82,.14); color:var(--short);
    border:1px solid rgba(255,82,82,.45); }
  .tb-guarded{ background:rgba(243,156,18,.14); color:var(--amber);
    border:1px solid rgba(243,156,18,.5); }
  .tb-stale{ background:rgba(224,165,43,.12); color:var(--amber);
    border:1px solid rgba(224,165,43,.45); }
  .tb-closed{ background:var(--raised); color:var(--muted);
    border:1px solid var(--border2); }
  .tb-nodata{ background:var(--raised); color:var(--dim);
    border:1px solid var(--border); }

  /* ============ 3. DETAIL ZONE ============ */
  .detail { display:flex; flex-direction:column; gap:var(--s3); }
  .detail-bar { display:flex; align-items:center; gap:var(--s3); flex-wrap:wrap;
    font-size:12px; color:var(--muted); padding:0 2px; }
  .detail-bar .sym { color:var(--accent); font-weight:800; font-size:15px;
    letter-spacing:.5px; }
  .sep { color:var(--dim); }
  .badge { font-weight:700; padding:3px 11px; border-radius:999px; font-size:10.5px;
    letter-spacing:.4px; }
  .lv-none{ background:var(--raised); color:var(--muted); border:1px solid var(--border); }
  .lv-alert{ background:rgba(224,165,43,.14); color:var(--neutral);
    border:1px solid var(--neutral); }
  .lv-strong{ background:rgba(46,204,113,.16); color:var(--long);
    border:1px solid var(--long); }
  .conf-dir { font-weight:700; }
  .sizing { color:var(--dim); }

  /* judge panel */
  .judge { border:1px solid var(--border); border-radius:12px;
    background:linear-gradient(180deg,var(--panel2),var(--panel));
    display:grid; gap:var(--s4); padding:var(--s4);
    grid-template-columns:minmax(180px,240px) minmax(260px,1fr) minmax(300px,1.4fr); }
  .judge.j-long{ border-color:rgba(46,204,113,.55);
    box-shadow:inset 0 0 0 1px rgba(46,204,113,.12); }
  .judge.j-short{ border-color:rgba(255,82,82,.55);
    box-shadow:inset 0 0 0 1px rgba(255,82,82,.12); }
  .judge.j-flat{ border-color:var(--border); }
  .judge.j-empty{ grid-template-columns:1fr; }
  .jb { display:flex; flex-direction:column; gap:6px; min-width:0; }
  .jb + .jb { border-left:1px solid var(--border); padding-left:var(--s4); }
  .judge-dir { font-size:40px; font-weight:800; letter-spacing:1px; line-height:1; }
  .j-long .judge-dir{ color:var(--long); }
  .j-short .judge-dir{ color:var(--short); }
  .j-flat .judge-dir{ color:var(--flat); }
  .judge-conv { font-size:13px; color:var(--muted); font-weight:600; }
  .judge-conv b { color:var(--accent); font-size:18px; }
  .judge .convbar { height:5px; border-radius:3px; background:var(--border);
    overflow:hidden; margin:3px 0 7px; }
  .judge .convbar i { display:block; height:100%; background:var(--accent); }
  .judge-bias { font-size:12px; color:var(--muted); font-weight:600;
    display:flex; align-items:center; gap:7px; margin:2px 0; }
  .judge-bias b.pos { color:var(--long); } .judge-bias b.neg { color:var(--short); }
  .biasbar { flex:1; height:5px; border-radius:3px; background:var(--border);
    overflow:hidden; }
  .biasbar i { display:block; height:100%; }
  .biasbar i.long { background:var(--long); } .biasbar i.short { background:var(--short); }
  .biasbar i.flat { background:var(--muted); }
  .judge-sub { font-size:11px; color:var(--muted); }
  .judge-sub.muted { opacity:.7; font-size:10px; }
  .judge-tf { font-size:11px; color:var(--accent); line-height:1.4; }
  .judge-stale { display:inline-block; color:var(--amber); font-size:9.5px;
    font-weight:700; border:1px solid var(--amber); border-radius:5px;
    padding:1px 6px; letter-spacing:.5px; margin-left:6px; }
  .ticket { display:grid; grid-template-columns:auto 1fr auto 1fr; gap:5px 14px;
    align-items:baseline; font-size:13px; }
  .ticket .tk { color:var(--muted); font-size:11px; }
  .ticket .tv { color:var(--txt); font-weight:600; text-align:right; }
  .ticket .tv.accent { color:var(--accent); }
  .jtext { font-size:12px; line-height:1.55; }
  .jtext .lbl { color:var(--muted); font-size:9.5px; letter-spacing:.8px;
    text-transform:uppercase; display:block; margin-bottom:1px; }
  .jtext p { margin:0 0 9px; max-height:8.5em; overflow:auto; }
  .judge-err { color:var(--short); font-size:11px; word-break:break-word; }
  .judge-empty { color:var(--muted); font-size:13px; padding:var(--s2) 0; }

  /* source columns */
  .cards { display:grid; gap:var(--s3);
    grid-template-columns:repeat(3,minmax(0,1fr)); align-items:start; }
  .card { background:var(--panel); border:1px solid var(--border);
    border-radius:12px; padding:var(--s3) var(--s4); display:flex;
    flex-direction:column; gap:var(--s2); min-width:0; }
  .card.off { opacity:.72; border-style:dashed; }
  .chead { display:flex; align-items:center; justify-content:space-between;
    gap:var(--s2); padding-bottom:var(--s1); border-bottom:1px solid var(--border); }
  .csrc { font-size:13px; font-weight:700; display:flex; align-items:center;
    gap:6px; }
  .cstate { display:flex; align-items:center; gap:6px; font-size:10.5px;
    color:var(--muted); }
  .dot { width:7px; height:7px; border-radius:50%; display:inline-block; }
  .on{ background:var(--long); box-shadow:0 0 5px rgba(46,204,113,.6); }
  .offd{ background:var(--offline); }
  .stale-badge{ color:var(--amber); border:1px solid var(--amber);
    border-radius:5px; padding:0 5px; font-size:9.5px; font-weight:700; }
  .cdir { font-size:22px; font-weight:800; line-height:1; }
  .cmeta { color:var(--muted); font-size:11px; }
  .off-reason { color:var(--amber); font-size:12px;
    background:rgba(224,165,43,.07); border:1px solid rgba(224,165,43,.3);
    border-radius:8px; padding:var(--s2) var(--s3); line-height:1.5; }
  .blurb { font-size:11px; color:var(--muted); line-height:1.5;
    word-break:break-word; }

  .sect { border-top:1px solid var(--border); padding-top:var(--s2); }
  .sect > .hd { margin-bottom:5px; }
  .kv { display:grid; grid-template-columns:auto 1fr; gap:2px 12px; font-size:12px; }
  .kv2 { grid-template-columns:auto 1fr auto 1fr; }
  .kv .k { color:var(--muted); white-space:nowrap; }
  .kv .v { color:var(--txt); word-break:break-word; text-align:right; }
  .scbadge { font-size:9.5px; padding:1px 6px; border-radius:6px;
    background:var(--raised); border:1px solid var(--border); color:var(--muted);
    cursor:help; font-weight:700; }
  .scbadge.good { color:var(--pos); border-color:rgba(46,204,113,.5); }
  .scbadge.bad { color:var(--neg); border-color:rgba(255,82,82,.5); }
  .chiprow { display:flex; flex-wrap:wrap; gap:var(--s1); }
  .chip { background:var(--raised); border:1px solid var(--border); border-radius:6px;
    padding:1px 6px; font-size:10.5px; font-family:Consolas,monospace; }
  .chip.pos{ color:var(--long); border-color:rgba(46,204,113,.4); }
  .chip.neg{ color:var(--short); border-color:rgba(255,82,82,.4); }
  .reason { font-size:11.5px; color:var(--txt); line-height:1.5;
    max-height:14em; overflow:auto; white-space:pre-wrap; word-break:break-word;
    background:var(--bg); border:1px solid var(--border); border-radius:8px;
    padding:var(--s2) var(--s3); }
  table.vt { width:100%; border-collapse:collapse; font-size:11px; }
  table.vt td { padding:1px 6px 1px 0; }
  table.vt td.k { color:var(--muted); white-space:nowrap; }
  table.vt td.v { color:var(--txt); text-align:right; }
  .empty-src { color:var(--dim); font-size:11px; padding:var(--s2) 0; }

  /* ============ 4. FOOTER ZONE ============ */
  .foot { display:flex; flex-direction:column; gap:var(--s3); margin-top:var(--s2); }
  details.fold { background:var(--panel); border:1px solid var(--border);
    border-radius:12px; overflow:hidden; }
  details.fold > summary { cursor:pointer; padding:10px var(--s4); font-weight:600;
    font-size:12px; letter-spacing:.04em; list-style:none; color:var(--txt);
    display:flex; align-items:center; gap:var(--s2); }
  details.fold > summary::-webkit-details-marker { display:none; }
  details.fold > summary::before { content:"\\25B8"; color:var(--muted);
    font-size:10px; transition:transform .15s; }
  details.fold[open] > summary::before { transform:rotate(90deg); }
  summary .cnt { color:var(--dim); font-weight:500; }
  .fold-body { padding:0 var(--s4) var(--s4); }

  .jgrid { display:grid; grid-template-columns:repeat(5,minmax(0,1fr));
    gap:var(--s3); }
  .jtbl { width:100%; border-collapse:collapse; font-size:11px; }
  .jtbl caption { text-align:left; font-weight:600; color:var(--muted);
    padding:2px 0 5px; font-size:10px; letter-spacing:.5px; text-transform:uppercase; }
  .jtbl th,.jtbl td { padding:2px 6px; border-bottom:1px solid var(--border);
    text-align:right; }
  .jtbl th { color:var(--muted); font-weight:600; font-size:9.5px; }
  .jtbl th:first-child,.jtbl td:first-child { text-align:left; }
  .jtbl td.pos { color:var(--pos); } .jtbl td.neg { color:var(--neg); }

  .lessons ul { margin:0; padding-left:18px; }
  .lessons li { font-size:12px; line-height:1.55; color:var(--fg); margin-bottom:3px; }
  .lessons .none { font-size:12px; color:var(--muted); }

  table.log { width:100%; border-collapse:collapse;
    font-family:"Cascadia Code",Consolas,monospace; font-size:11.5px; }
  table.log th { text-align:left; color:var(--muted); font-weight:600;
    font-size:9.5px; letter-spacing:1px; text-transform:uppercase;
    padding:6px var(--s3); border-bottom:1px solid var(--border); }
  table.log td { padding:4px var(--s3); border-bottom:1px solid #161c24;
    vertical-align:top; }
  table.log .t { color:var(--muted); white-space:nowrap; }
  table.log .sy { color:var(--dim); white-space:nowrap; }
  table.log .ty { color:var(--accent); white-space:nowrap; }
  table.log .sm { color:var(--txt); word-break:break-word; }
  table.log tr:last-child td { border-bottom:none; }
  .log-empty { color:var(--muted); font-size:12px; padding:var(--s3); }

  /* fade-in on selected-symbol detail swap */
  @keyframes fadein { from{ opacity:0; transform:translateY(4px); } to{ opacity:1; transform:none; } }
  .swap { animation:fadein .22s ease; }

  @media (prefers-reduced-motion: reduce){
    *,.swap,.tile { animation:none !important; transition:none !important; }
  }

  /* ============ responsive ============ */
  @media (max-width:1200px){
    .tiles { grid-template-columns:repeat(2,minmax(0,1fr)); }
    .cards { grid-template-columns:1fr; }
    .judge { grid-template-columns:1fr; }
    .jb + .jb { border-left:none; padding-left:0; border-top:1px solid var(--border);
      padding-top:var(--s3); }
    .jgrid { grid-template-columns:repeat(2,1fr); }
  }
  @media (max-width:640px){
    main { padding:var(--s2) var(--s2) var(--s4); }
    .tiles { grid-template-columns:1fr; }
    .acct-bal { border-right:none; }
    .jgrid { grid-template-columns:1fr; }
    .ticket { grid-template-columns:auto 1fr; }
  }
</style>
</head>
<body>
<main>
  <div id="acct"></div>
  <div class="row-lab"><span class="hd">Signals &mdash; click a symbol for detail</span></div>
  <div id="tiles" class="tiles"></div>
  <div id="detail" class="detail"></div>
  <div id="foot" class="foot"></div>
</main>
<script>
const dirClass = d => "dir-" + (d||"offline");
function esc(s){ return String(s==null?"":s)
  .replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;")
  .replace(/"/g,"&quot;"); }
function fmtAge(a){ if(a==null) return "n/a";
  if(a<60) return Math.round(a)+"s ago";
  if(a<5400) return Math.round(a/60)+"m ago";
  if(a<172800) return Math.round(a/3600)+"h ago";
  return Math.round(a/86400)+"d ago"; }
function fmtHold(sec){ if(sec==null||sec===0) return "&mdash;";
  if(sec<3600) return Math.round(sec/60)+"m";
  return (sec/3600).toFixed(1)+"h"; }
function num(x,d){ if(x==null||x==="") return "&mdash;";
  const n=Number(x); if(!isFinite(n)) return esc(x);
  return n.toLocaleString(undefined,{minimumFractionDigits:(d==null?2:d),
    maximumFractionDigits:(d==null?2:d)}); }
function signed(x,d){ if(x==null||x==="") return "&mdash;";
  const n=Number(x); if(!isFinite(n)) return esc(x);
  const s=Math.abs(n).toLocaleString(undefined,{minimumFractionDigits:(d==null?2:d),
    maximumFractionDigits:(d==null?2:d)});
  return n>0?("+"+s):(n<0?("-"+s):s); }
function rCls(r){ const n=Number(r); return n>0?"pos":n<0?"neg":""; }

/* ============ 1. ACCOUNT STRIP ============ */
function sparkline(points){
  const pts = (points||[]).filter(p=>p!=null && isFinite(p));
  if(pts.length<2) return "";
  const W=120, H=30, min=Math.min(...pts), max=Math.max(...pts);
  const span = (max-min)||1;
  const last = pts[pts.length-1], first = pts[0];
  const stroke = last>=first ? "var(--pos)" : "var(--neg)";
  const d = pts.map((p,i)=>{
    const x=(i/(pts.length-1))*W;
    const y=H-2-((p-min)/span)*(H-4);
    return (i?"L":"M")+x.toFixed(1)+" "+y.toFixed(1);
  }).join(" ");
  return `<svg class="spark" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" `+
    `aria-hidden="true"><path d="${d}" fill="none" stroke="${stroke}" `+
    `stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
}
function equityPoints(tr){
  // Reconstruct equity curve from closed trades' realized R if available;
  // fall back to [start_balance, balance].
  const s = tr.stats || {};
  const start = s.start_balance!=null ? s.start_balance : 1000;
  const closed = (tr.recent_closed||[]).slice().filter(t=>t.pnl_usd!=null);
  if(!closed.length) return [start, tr.balance];
  // recent_closed is newest-first in payload order; sort by closed_at ascending.
  const ordered = closed.slice().sort((a,b)=>
    new Date(a.closed_at||0) - new Date(b.closed_at||0));
  const pts=[start]; let bal=start;
  ordered.forEach(t=>{ bal += Number(t.pnl_usd)||0; pts.push(bal); });
  return pts;
}
function chipS(label, value, cls){
  return `<div class="chip-s"><span class="cl">${esc(label)}</span>`+
    `<span class="cv ${cls||''}">${value}</span></div>`;
}
function acctStrip(s){
  const tr = s.tracker;
  if(!tr) return `<div class="acct"><div class="acct-bal">`+
    `<div><span class="lab">paper account</span>`+
    `<div class="val">&mdash;</div></div></div></div>`;
  const st = tr.stats || {};
  const retCls = (st.total_return_pct||0)>=0 ? "pos" : "neg";
  const openCount = (tr.open_positions||[]).length;
  // price-feed warnings (aggregate any non-ok per-symbol status)
  const insts = s.instruments || {};
  const warns = Object.keys(insts).filter(k=>{
    const t=insts[k].tracker; return t && t.price_status && t.price_status!=="ok"; })
    .map(k=>`${k}:${insts[k].tracker.price_status}`);
  const warnLine = warns.length
    ? `<div class="warn">&#9888; price: ${esc(warns.join(" · "))}</div>` : "";
  return `<div class="acct">
    <div class="acct-bal">
      <div>
        <span class="lab">paper account</span>
        <div class="val num">$${num(tr.balance,2)}</div>
        <div class="ret ${retCls} num">${signed(st.total_return_pct,1)}% return</div>
      </div>
      ${sparkline(equityPoints(tr))}
    </div>
    <div class="chips">
      ${chipS("win rate", num(st.win_rate,1)+"%")}
      ${chipS("trades", num(st.total_trades,0))}
      ${chipS("avg R", signed(st.avg_r,2), rCls(st.avg_r))}
      ${chipS("cum R", signed(st.cumulative_r,2), rCls(st.cumulative_r))}
      ${chipS("profit f.", num(st.profit_factor,2))}
      ${chipS("max DD", num(st.max_drawdown_pct,1)+"%", "neg")}
      ${chipS("open", num(openCount,0))}
    </div>
    <div class="acct-meta">
      <div id="stamp">connecting&hellip;</div>
      <div id="backend"></div>
      ${warnLine}
    </div>
  </div>`;
}

/* ============ 2. SIGNAL TILES (= tabs) ============ */
function tileFor(sym, inst){
  const j = inst.judge || {};
  const tr = inst.tracker || {};
  const nodata = !j.status || j.status==="starting" || j.status==="no_data";
  const dir = nodata ? "FLAT" : (j.direction||"FLAT").toUpperCase();
  const cls = dir==="LONG"?"t-long":dir==="SHORT"?"t-short":"t-flat";
  const conv = Number(j.conviction)||0;
  const px = tr.last_price;
  const pxStale = tr.price_status && tr.price_status!=="ok";
  const pxStr = px!=null
    ? `${num(px)} ${pxStale?`<span class="pxstale" title="${esc(tr.price_status)}">&#9888;</span>`:""}`
    : `<span class="pxstale">no price</span>`;
  const op = tr.open_position;
  const sel = sym===ACTIVE ? " sel" : "";
  // badges
  let badges = "";
  if(op){
    const od=(op.direction||"").toUpperCase();
    const ur=op.unrealized_r;
    const bcls = od==="SHORT" ? "tb-open-short" : "tb-open-long";
    badges += `<span class="tb ${bcls}">${esc(od)} ${signed(ur,2)}R</span>`;
  }
  if(!op){
    const rc=(tr.recent_closed||[])[0];
    if(rc) badges += `<span class="tb tb-closed">last ${signed(rc.r_multiple,2)}R</span>`;
  }
  const lb = tr.last_block;
  if(lb && lb.at){
    const ageMin = (Date.now() - Date.parse(lb.at)) / 60000;
    if(ageMin >= 0 && ageMin < 30){
      const reasons = (lb.reasons||[]).join("; ");
      badges += `<span class="tb tb-guarded" title="${esc(reasons)}">GUARDED</span>`;
    }
  }
  if(j.stale) badges += `<span class="tb tb-stale">STALE</span>`;
  if(nodata) badges += `<span class="tb tb-nodata">${esc(j.status==="no_data"?"no data":"warming up")}</span>`;
  if(pxStale && !nodata) badges += `<span class="tb tb-stale">feed</span>`;
  const tf = nodata ? "" : (j.tf_alignment||"");
  const base = sym.replace(/USDT$/,"");
  return `<div class="tile ${cls}${sel}" data-sym="${esc(sym)}" role="button" `+
    `tabindex="0" aria-pressed="${sym===ACTIVE}">
    <div class="tile-top">
      <div class="tile-sym">${esc(base)}<small> ${esc(sym.slice(base.length))}</small></div>
      <div class="tile-px num">${pxStr}</div>
    </div>
    <div class="tile-dir ${dirClass(dir)}">${esc(dir)}</div>
    <div class="tile-conv">
      <div class="clab"><span>conviction</span><span class="num">${num(conv,0)}</span></div>
      <div class="convbar"><i style="width:${Math.max(0,Math.min(100,conv))}%"></i></div>
    </div>
    <div class="tile-tf">${esc(tf)}</div>
    <div class="tile-badges">${badges||'<span class="tb tb-nodata">flat</span>'}</div>
  </div>`;
}
function renderTiles(s){
  const syms = s.symbols || [];
  if(!ACTIVE || !syms.includes(ACTIVE)) ACTIVE = syms[0] || null;
  const insts = s.instruments || {};
  const el = document.getElementById('tiles');
  el.innerHTML = syms.map(sym=>tileFor(sym, insts[sym]||{})).join("");
  el.querySelectorAll('.tile').forEach(t=>{
    const pick = ()=>{
      ACTIVE = t.getAttribute('data-sym');
      if(LAST_STATE){ renderTiles(LAST_STATE); renderDetail(LAST_STATE, true); }
      tickJournal();
    };
    t.addEventListener('click', pick);
    t.addEventListener('keydown', e=>{
      if(e.key==="Enter"||e.key===" "){ e.preventDefault(); pick(); } });
  });
}

/* ============ 3. DETAIL ZONE ============ */
function scBadge(source, scorecards){
  const sc = scorecards && scorecards.voices ? scorecards.voices[source] : null;
  if(!sc || sc.resolved==null || sc.resolved===0) return "";
  const hr = sc.hit_rate;
  const cls = hr==null?"":(hr>=55?"good":hr<45?"bad":"");
  const br = sc.by_regime||{};
  const regimeBits = Object.keys(br).map(k=>{
    const r=br[k]; return r.hit_rate==null?null:`${esc(k)} ${num(r.hit_rate,0)}%`;
  }).filter(Boolean).join(" · ");
  const tip = `hit rate over last ${sc.resolved} resolved`+
    (regimeBits?` | by regime: ${regimeBits}`:"")+
    (sc.streak?` | streak ${sc.streak} ${esc(sc.streak_kind||'')}`:"");
  return `<span class="scbadge ${cls}" title="${esc(tip)}">`+
    `${num(hr,0)}% (${sc.resolved})</span>`;
}

function judgePanel(j){
  if(!j || j.status==="starting")
    return `<div class="judge j-flat j-empty"><div class="hd">Judge verdict</div>`+
      `<div class="judge-empty">warming up &mdash; awaiting first assessment&hellip;</div></div>`;
  if(j.status==="no_data")
    return `<div class="judge j-flat j-empty"><div class="hd">Judge verdict</div>`+
      `<div class="judge-empty">no data &mdash; all sources offline for this symbol</div></div>`;
  const dir=(j.direction||"FLAT").toUpperCase();
  const cls = dir==="LONG"?"j-long":dir==="SHORT"?"j-short":"j-flat";
  const staleTag = j.stale ? `<span class="judge-stale">STALE</span>` : "";
  const errBlk = j.error ? `<div class="judge-err">&#9888; ${esc(j.error)}</div>` : "";
  const tk = (lbl,v,d,acc)=>`<span class="tk">${lbl}</span>`+
    `<span class="tv num${acc?' accent':''}">${num(v,d)}</span>`;
  // Decoupled conviction signals: entry_conviction gates a trade (prominent);
  // directional_bias is a signed -100..+100 read; flat_confidence is muted.
  const ec = (j.entry_conviction!=null) ? j.entry_conviction : j.conviction;
  const db = Number(j.directional_bias)||0;
  const dbPct = Math.min(100, Math.abs(db));
  const dbSide = db>0 ? "long" : db<0 ? "short" : "flat";
  const dbCls = db>0 ? "pos" : db<0 ? "neg" : "";
  const wp = (j.win_probability!=null) ? `${num(j.win_probability*100,0)}%` : "&mdash;";
  const regimeStr = [j.regime, j.playbook].filter(Boolean)
    .map(x=>esc(String(x))).join(" / ");
  return `<div class="judge ${cls}">
    <div class="jb">
      <div class="hd">Judge verdict</div>
      <div class="judge-dir">${esc(dir)}${staleTag}</div>
      <div class="judge-conv">entry conviction <b class="num">${num(ec,0)}</b></div>
      <div class="convbar"><i style="width:${Math.max(0,Math.min(100,Number(ec)||0))}%"></i></div>
      <div class="judge-bias">directional bias
        <b class="num ${dbCls}">${signed(db,0)}</b>
        <span class="biasbar"><i class="${dbSide}" style="width:${dbPct}%"></i></span></div>
      <div class="judge-sub muted">flat confidence ${num(j.flat_confidence,0)} &middot; win prob ${wp}</div>
      ${regimeStr?`<div class="judge-sub">regime: ${regimeStr}</div>`:""}
      <div class="judge-sub">${esc(j.timeframe||"&mdash;")} timeframe</div>
      <div class="judge-sub">${esc(j.model||"")} &middot; ${fmtAge(j.age_seconds)} &middot; ${num(j.call_count,0)} calls</div>
      ${j.tf_alignment?`<div class="judge-tf">TF: ${esc(j.tf_alignment)}</div>`:""}
      ${errBlk}
    </div>
    <div class="jb">
      <div class="hd">Trade ticket</div>
      <div class="ticket">
        ${tk("entry",j.entry,2,true)} ${tk("R:R",j.risk_reward,2)}
        ${tk("stop",j.stop_loss)} ${tk("size %",j.position_size_pct,1)}
        ${tk("TP1",j.take_profit_1)} ${tk("TP2",j.take_profit_2)}
      </div>
    </div>
    <div class="jb">
      <div class="hd">Rationale</div>
      <div class="jtext">
        <span class="lbl">rationale</span><p>${esc(j.rationale||"&mdash;")}</p>
        <span class="lbl">invalidation</span><p>${esc(j.invalidation||"&mdash;")}</p>
        <span class="lbl">disagreements</span><p>${esc(j.disagreements||"&mdash;")}</p>
      </div>
    </div>
  </div>`;
}

/* ---- per-source building blocks (all original fields preserved) ---- */
function kvBlock(title, obj, two){
  const keys = Object.keys(obj||{}).filter(k=>obj[k]!=null && obj[k]!=="");
  if(!keys.length) return "";
  const rows = keys.map(k=>
    `<div class="k">${esc(k)}</div><div class="v num">${esc(
      typeof obj[k]==="object"?JSON.stringify(obj[k]):obj[k])}</div>`).join("");
  return `<div class="sect"><div class="hd">${esc(title)}</div>`+
    `<div class="kv${two?' kv2':''}">${rows}</div></div>`;
}
function chips(title, arr, signed_){
  if(!arr || !arr.length) return "";
  const c = arr.map(x=>{
    if(typeof x==="object") return `<span class="chip">${esc(JSON.stringify(x))}</span>`;
    let cl=""; const n=Number(x);
    if(signed_ && isFinite(n)) cl = n>0?" pos":n<0?" neg":"";
    const lbl = (signed_ && isFinite(n)) ? signed(n,2) : esc(x);
    return `<span class="chip${cl}">${lbl}</span>`;
  }).join("");
  return `<div class="sect"><div class="hd">${esc(title)}</div><div class="chiprow">${c}</div></div>`;
}
function reasonBlock(title, txt){
  if(!txt) return "";
  return `<div class="sect"><div class="hd">${esc(title)}</div>`+
    `<div class="reason">${esc(txt)}</div></div>`;
}
function tradeLevels(e){
  const m = {};
  if(e.entry!=null) m.entry=num(e.entry);
  if(e.stop_loss!=null) m["stop loss"]=num(e.stop_loss);
  if(e.take_profit!=null) m["take profit"]=num(e.take_profit);
  if(e.risk_reward!=null) m["R:R"]=num(e.risk_reward);
  if(e.position_size!=null) m["size"]=num(e.position_size);
  return m;
}
function traderDetail(e){
  let h = "";
  h += kvBlock("trade levels", tradeLevels(e), true);
  if(e.trend) h += kvBlock("trend", e.trend, true);
  if(e.key_levels) h += kvBlock("key levels", e.key_levels);
  if(e.confluence_factors) h += kvBlock("confluence factors", e.confluence_factors, true);
  if(e.indicators) h += kvBlock("indicators", e.indicators, true);
  h += reasonBlock("reasoning", e.reasoning || e.trade_reasoning);
  return h || `<div class="empty-src">no detail fields</div>`;
}
function tradebotDetail(e){
  let h = "";
  h += kvBlock("decision", {action:e.action, weighted_score:e.weighted_score,
    regime:e.regime, risk_level:e.risk_level, price:e.market_price,
    position:e.market_position});
  if(e.order_params) h += kvBlock("order params", e.order_params);
  const vd = e.vote_details;
  if(vd){
    const votes = {};
    const bull = vd.bull_reasons, bear = vd.bear_reasons, oi = vd.oi_fuel;
    Object.keys(vd).forEach(k=>{
      if(k==="bull_reasons"||k==="bear_reasons"||k==="oi_fuel") return;
      votes[k]=vd[k];
    });
    const rows = Object.keys(votes).map(k=>
      `<tr><td class="k">${esc(k)}</td><td class="v num">${esc(
        typeof votes[k]==="object"?JSON.stringify(votes[k]):votes[k])}</td></tr>`).join("");
    h += `<div class="sect"><div class="hd">vote details</div>`+
      `<table class="vt">${rows}</table></div>`;
    if(oi) h += kvBlock("oi fuel", oi);
    if(bull) h += chips("bull reasons", [].concat(bull));
    if(bear) h += chips("bear reasons", [].concat(bear));
  }
  if(e.virtual_account){
    const va=e.virtual_account;
    h += kvBlock("virtual account", {balance:num(va.balance),
      available:num(va.available_balance), uPnL:signed(va.total_unrealized_pnl),
      rPnL:signed(va.cumulative_realized_pnl),
      positions:Object.keys(va.positions||{}).length});
  }
  h += reasonBlock("reasoning", e.reasoning);
  return h || `<div class="empty-src">no detail fields</div>`;
}
function orderflowDetail(e){
  let h = "";
  h += kvBlock("window", {close:num(e.close), high:num(e.window_high),
    low:num(e.window_low), candles:e.candles, interval:e.interval,
    "tick size":e.tick_size}, true);
  h += kvBlock("flow", {"total delta":signed(e.total_delta),
    "total volume":num(e.total_volume)}, true);
  h += kvBlock("stacked imbalance", {"buy stacks":e.buy_stack,
    "sell stacks":e.sell_stack, "buy levels":e.buy_stack_count,
    "sell levels":e.sell_stack_count, ratio:e.imbalance_ratio,
    threshold:e.stacked_threshold}, true);
  if(e.per_candle_delta) h += chips("per-candle delta (old&rarr;new)",
    e.per_candle_delta, true);
  if(e.buy_stack_levels && e.buy_stack_levels.length)
    h += chips("buy imbalance levels", e.buy_stack_levels);
  if(e.sell_stack_levels && e.sell_stack_levels.length)
    h += chips("sell imbalance levels", e.sell_stack_levels);
  return h || `<div class="empty-src">no detail fields</div>`;
}
function detailFor(v){
  const e = v.extra || {};
  if(v.source==="llm_trader") return traderDetail(e);
  if(v.source==="llm_tradebot") return tradebotDetail(e);
  if(v.source==="orderflow") return orderflowDetail(e);
  return kvBlock("extra", e) || `<div class="empty-src">no detail fields</div>`;
}
function card(v, scorecards){
  const off = v.direction==="offline";
  const stale = !off && v.age_seconds!=null && v.age_seconds>900;
  const staleBadge = stale ? `<span class="stale-badge">STALE</span>` : "";
  const badge = scBadge(v.source, scorecards);
  if(off){
    return `<div class="card off">
      <div class="chead"><span class="csrc">${esc(v.source)} ${badge}</span>
        <span class="cstate"><span class="dot offd"></span>offline</span></div>
      <div class="off-reason">${esc(v.detail||"source offline")}</div>
    </div>`;
  }
  return `<div class="card">
    <div class="chead">
      <span class="csrc">${esc(v.source)} ${badge}</span>
      <span class="cstate">${staleBadge}<span class="dot on"></span>online</span>
    </div>
    <div>
      <div class="cdir ${dirClass(v.direction)}">${esc((v.direction||'').toUpperCase())}</div>
      <div class="cmeta">confidence ${num((v.confidence||0)*100,0)}% &middot; ${fmtAge(v.age_seconds)}</div>
    </div>
    <div class="blurb">${esc(v.detail||'')||'&mdash;'}</div>
    ${detailFor(v)}
  </div>`;
}

function renderDetail(s, swap){
  const inst = (s.instruments||{})[ACTIVE] || {};
  const j = inst.judge || {};
  const c = inst.confluence || {direction:"neutral",level:"none",agree_count:0,online_count:0,score:0,sizing_note:""};
  const lvlTxt = c.level==="strong" ? "STRONG ALERT"
    : c.level==="alert" ? "ALERT" : "NO ALERT";
  const tr = inst.tracker || {};
  const pxStale = tr.price_status && tr.price_status!=="ok";
  const bar = `<div class="detail-bar">
    <span class="sym">${esc(ACTIVE||"&mdash;")}</span>
    <span class="num">${tr.last_price!=null?("$"+num(tr.last_price)):"&mdash;"}</span>
    ${pxStale?`<span class="sep">|</span><span style="color:var(--amber)">&#9888; ${esc(tr.price_status)}</span>`:""}
    <span class="sep">|</span>
    <span class="badge lv-${esc(c.level)}">${esc(lvlTxt)}</span>
    <span class="conf-dir ${dirClass(c.direction)}">${esc((c.direction||'').toUpperCase())}</span>
    <span class="sep">|</span>
    <span>${c.agree_count}/${c.online_count} sources agree &middot; score ${Number(c.score||0).toFixed(2)}</span>
    ${c.sizing_note?`<span class="sizing">&middot; ${esc(c.sizing_note)}</span>`:""}
  </div>`;
  const votes = inst.votes || [];
  const cardsHtml = votes.length
    ? votes.map(v=>card(v, inst.scorecards)).join("")
    : `<div class="card"><div class="empty-src">no sources reporting for ${esc(ACTIVE||'')}</div></div>`;
  const wrap = swap ? "swap" : "";
  document.getElementById('detail').innerHTML =
    `<div class="${wrap}">${bar}${judgePanel(j)}`+
    `<div class="cards" style="margin-top:var(--s3)">${cardsHtml}</div></div>`;
  // page title reflects selected symbol + judge direction
  const base = (ACTIVE||"").replace(/USDT$/,"");
  const jd = (!j.status||j.status==="no_data"||j.status==="starting")
    ? "" : (j.direction||"FLAT").toUpperCase();
  document.title = base ? `${base} ${jd} | Confluence` : "Confluence Aggregator";
}

/* ============ 4. FOOTER ZONE ============ */
function aggTable(caption, groups){
  const keys = Object.keys(groups||{});
  if(!keys.length) return "";
  const rows = keys.map(k=>{
    const g = groups[k];
    const wr = g.win_rate==null ? "&mdash;" : num(g.win_rate,1)+"%";
    const ar = g.avg_r==null ? "&mdash;" : signed(g.avg_r,2);
    const arCls = g.avg_r==null?"":(g.avg_r>0?"pos":g.avg_r<0?"neg":"");
    return `<tr><td>${esc(k)}</td><td>${g.trades}</td>`+
      `<td>${wr}</td><td class="${arCls}">${ar}R</td></tr>`;
  }).join("");
  return `<table class="jtbl"><caption>${esc(caption)}</caption>`+
    `<thead><tr><th>bucket</th><th>n</th><th>win%</th><th>avg R</th></tr></thead>`+
    `<tbody>${rows}</tbody></table>`;
}
function journalSection(jr){
  if(!jr || !jr.count){
    return `<details class="fold"><summary>Journal &mdash; conditional performance `+
      `<span class="cnt">(no closed trades yet)</span></summary>`+
      `<div class="fold-body"><div class="lessons none">`+
      `Conditional stats appear once trades close.</div></div></details>`;
  }
  const a = jr.aggregates || {};
  const filt = jr.symbol ? ` [${esc(jr.symbol)}]` : "";
  return `<details class="fold"><summary>Journal &mdash; conditional performance`+
    `<span class="cnt">${filt} (${jr.count} closed)</span></summary>
    <div class="fold-body"><div class="jgrid">
      ${aggTable("by symbol", a.by_symbol)}
      ${aggTable("by regime", a.by_regime)}
      ${aggTable("by session", a.by_session)}
      ${aggTable("by agree count", a.by_agree_count)}
      ${aggTable("by direction", a.by_direction)}
    </div></div></details>`;
}
function lessonsSection(lessons){
  const active = (lessons||[]).filter(l=>l.status==="active");
  const body = active.length
    ? `<ul>${active.map(l=>`<li>${esc(l.text)}</li>`).join("")}</ul>`
    : `<div class="lessons none">No learned rules yet &mdash; the reflection pass adds these over time.</div>`;
  return `<details class="fold"><summary>Lessons &mdash; learned rules `+
    `<span class="cnt">(${active.length})</span></summary>`+
    `<div class="fold-body lessons">${body}</div></details>`;
}
function eventsSection(events){
  const ev = (events||[]).slice().reverse();
  const body = ev.length
    ? `<table class="log"><thead><tr>`+
      `<th style="width:84px;">Time</th><th style="width:62px;">Sym</th>`+
      `<th style="width:78px;">Type</th><th>Summary</th></tr></thead><tbody>`+
      ev.map(e=>`<tr>`+
        `<td class="t">${esc(new Date(e.ts).toLocaleTimeString())}</td>`+
        `<td class="sy">${esc((e.symbol||'').replace(/USDT$/,'')||'&mdash;')}</td>`+
        `<td class="ty">${esc(e.type)}</td>`+
        `<td class="sm">${esc(e.summary||'')}</td></tr>`).join("")+
      `</tbody></table>`
    : `<div class="log-empty">No events yet.</div>`;
  return `<details class="fold" open><summary>Recent events `+
    `<span class="cnt">(last ${ev.length})</span></summary>`+
    `<div class="fold-body" style="padding:0 0 var(--s2);">${body}</div></details>`;
}
let JOURNAL_HTML = "";
function renderFooter(s){
  document.getElementById('foot').innerHTML =
    JOURNAL_HTML +
    lessonsSection(s.lessons) +
    eventsSection(s.events);
}

/* ============ poll loop ============ */
let ACTIVE = null;          // active symbol
let LAST_STATE = null;      // most recent /api/state payload

async function tick(){
  try{
    const r = await fetch('/api/state'); const s = await r.json();
    const firstOrSwitch = !LAST_STATE;
    LAST_STATE = s;
    document.getElementById('acct').innerHTML = acctStrip(s);
    document.getElementById('stamp').textContent =
      "updated " + new Date(s.updated_at).toLocaleTimeString();
    document.getElementById('backend').textContent = "toast: " + s.toast_backend;
    renderTiles(s);
    renderDetail(s, firstOrSwitch);
    renderFooter(s);
  }catch(err){
    const st = document.getElementById('stamp');
    if(st) st.textContent = "fetch error: " + err;
  }
}
async function tickJournal(){
  try{
    const q = ACTIVE ? ('?symbol='+encodeURIComponent(ACTIVE)) : '';
    const r = await fetch('/api/journal'+q); const jr = await r.json();
    JOURNAL_HTML = journalSection(jr);
    if(LAST_STATE) renderFooter(LAST_STATE);
  }catch(err){ /* journal is non-critical; keep prior render */ }
}
tick(); setInterval(tick, 5000);
tickJournal(); setInterval(tickJournal, 15000);
</script>
</body>
</html>
"""
