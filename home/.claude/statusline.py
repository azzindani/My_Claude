#!/usr/bin/env python3
import sys, json, os, re, subprocess, time as _time, shutil
from datetime import datetime, timedelta

try:
    data = json.load(sys.stdin)
except Exception:
    data = {}


RS  = "\033[0m"
CY  = "\033[96m"
MG  = "\033[95m"
YE  = "\033[93m"
BL  = "\033[94m"
GR  = "\033[92m"
RD  = "\033[91m"
WH  = "\033[97m"
AM  = "\033[33m"
DIM = "\033[2m"
BLD = "\033[1m"

WEEK_BUDGET = 30.0

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
def vlen(s): return len(ANSI_RE.sub("", s))

def _get_term_width(fallback=120):
    try:
        c = int(os.environ.get('COLUMNS', 0))
        if c > 0: return c
    except (TypeError, ValueError):
        pass
    # SSH_TTY is the actual PTY device path — queryable even in subprocesses
    for tty_path in filter(None, [os.environ.get('SSH_TTY'), '/dev/tty']):
        try:
            fd = os.open(tty_path, os.O_RDONLY | os.O_NOCTTY)
            try:    return os.get_terminal_size(fd).columns
            finally: os.close(fd)
        except OSError:
            pass
    # stderr fallback (works when it's still connected to the tty)
    try:
        return os.get_terminal_size(2).columns
    except OSError:
        pass
    return fallback

_tw = _get_term_width()
PORTRAIT = _tw < 100
def pad(s, w):
    n = w - vlen(s)
    return s + (" " * n if n > 0 else "")

def to_int(v):
    try: return int(v or 0)
    except: return 0

def fmt_k(n):
    n = to_int(n)
    if n >= 1_000_000:
        m = n / 1_000_000
        return f"{m:.0f}M" if m == int(m) else f"{m:.2f}M"
    if n >= 1000:
        k = n / 1000
        return f"{k:.0f}k" if k == int(k) else f"{k:.1f}k"
    return str(n)

def draw_bar(ratio, cells=15):
    r = max(0.0, min(1.0, ratio))
    filled = round(r * cells)
    bc = GR if r < 0.5 else (AM if r < 0.75 else RD)
    return f"{DIM}[{RS}{bc}{'█'*filled}{'░'*(cells-filled)}{RS}{DIM}]{RS} {bc}{BLD}{int(r*100)}%{RS}"

def fmt_reset(epoch):
    if not epoch: return ""
    diff = datetime.fromtimestamp(epoch) - datetime.now()
    mins = int(diff.total_seconds() / 60)
    if mins < 0: return ""
    h, m = divmod(mins, 60)
    return f" {DIM}({'↺'}{h}h{m:02d}m){RS}" if h else f" {DIM}({'↺'}{m}m){RS}"

def parse_ts(raw):
    """Return epoch seconds from either numeric ms or ISO-8601 string."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return raw / 1000
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).timestamp()
    except Exception:
        return None

def parse_usage_lines(lines_bytes, ts_after_s=None):
    """Sum token usage from JSONL lines. Deduplicates by requestId (each API call stored twice).
    If ts_after_s set, skip lines before that epoch."""
    by_req = {}   # requestId → (inp, cw, cr, out)
    no_req = []   # records without requestId — deduplicate consecutively
    last_no_req = None
    for line in lines_bytes.decode("utf-8", errors="replace").splitlines():
        try:
            d = json.loads(line)
            if ts_after_s is not None:
                ts = parse_ts(d.get("timestamp"))
                if ts is None or ts < ts_after_s:
                    continue
            msg = d.get("message", {})
            if not (isinstance(msg, dict) and msg.get("role") == "assistant"):
                continue
            u = msg.get("usage") or {}
            rec = (u.get("input_tokens", 0), u.get("cache_creation_input_tokens", 0),
                   u.get("cache_read_input_tokens", 0), u.get("output_tokens", 0))
            rid = d.get("requestId")
            if rid:
                by_req[rid] = rec   # last write wins (final usage beats streaming partial)
            else:
                if rec != last_no_req:
                    no_req.append(rec)
                    last_no_req = rec
        except Exception:
            pass
    all_recs = list(by_req.values()) + no_req
    if not all_recs:
        return 0, 0, 0, 0
    inp = sum(r[0] for r in all_recs)
    cw  = sum(r[1] for r in all_recs)
    cr  = sum(r[2] for r in all_recs)
    out = sum(r[3] for r in all_recs)
    return inp, out, cr, cw

# ── Model + effort ─────────────────────────────────────────────────────────
raw_model = data.get("model", {}).get("display_name", "?")
model = raw_model.replace("Claude ", "").replace("claude-", "")

# ── Pricing table — (inp, cache_write_5m, cache_read, out) $/MTok ──────────
_PRICE = {
    "opus-4-7":   (15.00, 18.75, 1.50, 75.00),
    "opus-4-6":   (15.00, 18.75, 1.50, 75.00),
    "sonnet-4-6": ( 3.00,  3.75, 0.30, 15.00),
    "sonnet-4-5": ( 3.00,  3.75, 0.30, 15.00),
    "haiku-4-5":  ( 1.00,  1.25, 0.10,  5.00),
}

def token_cost(inp_new, cw, cr, out, model_str):
    m = model_str.lower()
    prices = next((p for k, p in _PRICE.items() if k in m), (3.00, 3.75, 0.30, 15.00))
    pi, pcw, pcr, po = prices
    return (inp_new * pi + cw * pcw + cr * pcr + out * po) / 1_000_000

effort = data.get("effortLevel") or data.get("effort") or data.get("thinking") or ""
if isinstance(effort, dict):
    effort = effort.get("level") or effort.get("type") or next(iter(effort.values()), "")
emap = {"low":"low","medium":"med","high":"high","highest":"max","none":"none","auto":"auto"}
eff_str = emap.get(str(effort).lower(), str(effort)) if effort else ""

# ── Dir + branch ───────────────────────────────────────────────────────────
cwd     = data.get("workspace", {}).get("current_dir") or data.get("cwd", "") or os.getcwd()
dir_str = cwd.replace("\\", "/")
branch  = ""
try:
    r = subprocess.run(["git","-C",cwd,"rev-parse","--abbrev-ref","HEAD"],
                       capture_output=True, text=True, timeout=2)
    if r.returncode == 0: branch = r.stdout.strip()
except Exception: pass

# ── Context window ─────────────────────────────────────────────────────────
ctx      = data.get("context_window", {})
used_pct = ctx.get("used_percentage")
max_ctx  = to_int(ctx.get("context_window_size") or ctx.get("max_tokens") or ctx.get("total_capacity") or 200_000)
ctx_used = int(used_pct / 100 * max_ctx) if used_pct is not None else 0
cost_all = float(data.get("cost", {}).get("total_cost_usd") or 0)
sess_id  = data.get("session_id", "")
transcript_path = data.get("transcript_path", "")

# ── Rate limits ────────────────────────────────────────────────────────────
rl          = data.get("rate_limits") or {}
rl_5h       = rl.get("five_hour") or {}
rl_7d       = rl.get("seven_day") or {}
rl_5h_pct   = rl_5h.get("used_percentage")
rl_5h_reset = rl_5h.get("resets_at")
rl_7d_pct   = rl_7d.get("used_percentage")
rl_7d_reset = rl_7d.get("resets_at")
now_ts      = int(_time.time())
# Current 5h window started 5 hours before the next reset
win_start   = (rl_5h_reset - 5 * 3600) if rl_5h_reset else (now_ts - 5 * 3600)

# ── Token accounting ───────────────────────────────────────────────────────
USAGE_FILE = os.path.join(os.path.expanduser("~"), ".claude", "usage_log.json")
sess_cost = 0.0
win_cost = win_inp_new = win_cache_r = win_out = 0
week_cost = week_inp = week_out = 0.0

try:
    try:
        with open(USAGE_FILE) as f: log = json.load(f)
    except Exception:
        log = {}
    today  = datetime.now().strftime("%Y-%m-%d")
    cutoff = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    log    = {k:v for k,v in log.items() if v.get("date","") >= cutoff}

    if sess_id:
        prev      = log.get(sess_id, {})
        cost_init = prev.get("cost_init", cost_all)
        sess_cost = max(0.0, cost_all - cost_init)

        # ── Full-session incremental read (for 7d totals) ──────────────────
        d_inp = d_out = d_cr = d_cw = 0
        new_offset = prev.get("transcript_offset", 0)
        raw_content = b""
        if transcript_path and os.path.exists(transcript_path):
            try:
                with open(transcript_path, "rb") as tf:
                    tf.seek(new_offset)
                    chunk = tf.read()
                last_nl = chunk.rfind(b"\n")
                if last_nl >= 0:
                    new_offset += last_nl + 1
                    d_inp, d_out, d_cr, d_cw = parse_usage_lines(chunk[:last_nl])
                    raw_content = chunk  # reuse below if needed
            except Exception:
                pass

        acc_inp     = prev.get("acc_inp",    0) + d_inp + d_cw
        acc_cache_r = prev.get("acc_cache_r",0) + d_cr
        acc_out     = prev.get("acc_out",    0) + d_out

        # ── Window-scoped stats (for 5h totals) ───────────────────────────
        # Re-scan full transcript with timestamp filter when:
        #   • rl_5h_reset changed  (window just rolled over)
        #   • first time we track this session (no win_acc_* stored)
        win_reset_changed = (
            rl_5h_reset is not None
            and rl_5h_reset != prev.get("win_reset_at")
        )
        # Trigger re-scan when win_acc_inp_new absent (field upgrade) or window rolled
        first_win_track = "win_acc_inp_new" not in prev

        if win_reset_changed or first_win_track:
            w_inp = w_out = w_cr = w_cw = 0
            if transcript_path and os.path.exists(transcript_path):
                try:
                    with open(transcript_path, "rb") as tf:
                        full = tf.read()
                    last_nl = full.rfind(b"\n")
                    if last_nl >= 0:
                        w_inp, w_out, w_cr, w_cw = parse_usage_lines(
                            full[:last_nl], ts_after_s=win_start
                        )
                except Exception:
                    pass
            win_acc_inp_new = w_inp
            win_acc_cw      = w_cw
            win_acc_cache_r = w_cr
            win_acc_out     = w_out
        else:
            # Same window — new bytes are all within it
            win_acc_inp_new = prev.get("win_acc_inp_new", 0) + d_inp
            win_acc_cw      = prev.get("win_acc_cw",      0) + d_cw
            win_acc_cache_r = prev.get("win_acc_cache_r", 0) + d_cr
            win_acc_out     = prev.get("win_acc_out",     0) + d_out

        win_acc_inp  = win_acc_inp_new + win_acc_cw
        win_cost_est = token_cost(win_acc_inp_new, win_acc_cw, win_acc_cache_r, win_acc_out, raw_model)

        log[sess_id] = {
            "date":              today,
            "started_at":        prev.get("started_at", now_ts),
            "cost_init":         cost_init,
            "cost":              sess_cost,
            "transcript_offset": new_offset,
            # full session (7d)
            "acc_inp":           acc_inp,
            "acc_cache_r":       acc_cache_r,
            "acc_out":           acc_out,
            "inp":               acc_inp + acc_cache_r,
            "out":               acc_out,
            # current 5h window
            "win_reset_at":      rl_5h_reset,
            "win_acc_inp_new":   win_acc_inp_new,
            "win_acc_cw":        win_acc_cw,
            "win_acc_inp":       win_acc_inp,
            "win_acc_cache_r":   win_acc_cache_r,
            "win_acc_out":       win_acc_out,
            "win_cost":          win_cost_est,
        }
        with open(USAGE_FILE, "w") as f: json.dump(log, f)

    # ── Aggregate across all tracked sessions ──────────────────────────────
    for v in log.values():
        c = v.get("cost", 0)
        # 5h: only sessions whose window-tracking matches the current window
        if rl_5h_reset and v.get("win_reset_at") == rl_5h_reset:
            win_cost    += v.get("win_cost", 0)
            win_inp_new += v.get("win_acc_inp",    0)
            win_cache_r += v.get("win_acc_cache_r",0)
            win_out     += v.get("win_acc_out",    0)
        # 7d: all sessions in log
        week_cost += c
        week_inp  += v.get("inp", 0)
        week_out  += v.get("out", 0)

except Exception:
    pass

# ── Build lines ────────────────────────────────────────────────────────────
LBL_W = 5
def label(s): return f"{DIM}{s:>{LBL_W}}{RS}"

lines    = []
pct_val  = used_pct if used_pct is not None else 0

if PORTRAIT:
    # ── Portrait / narrow layout (< 100 cols) ──────────────────────────────
    BAR_C  = 10
    INDENT = " " * (LBL_W + 2)  # aligns bar under the data values

    # Line 1: model + effort + branch
    hdr = f"{BLD}{CY}{model}{RS}"
    if eff_str: hdr += f" {DIM}→{RS} {MG}{eff_str}{RS}"
    if branch:  hdr += f"  {DIM}⎇{RS} {BL}{branch}{RS}"
    lines.append(hdr)

    # Line 2: directory, truncated from left to fit terminal width
    max_dir = _tw - 2
    trunc   = ("…" + dir_str[-(max_dir - 1):]) if len(dir_str) > max_dir else dir_str
    lines.append(f"{YE}{trunc}{RS}")

    # ctx: data line, then bar on its own line
    tok = f"{WH}{fmt_k(ctx_used)}{DIM}/{fmt_k(max_ctx)}{RS}"
    lines.append(f"{label('ctx')}  {tok}")
    lines.append(f"{INDENT}{draw_bar(pct_val/100, BAR_C)}")

    # 5h: data line, then bar on its own line (only when rate-limit % is known)
    tok = f"{GR}▲{fmt_k(win_inp_new)}{RS}  {RD}▼{fmt_k(win_out)}{RS}"
    if win_cache_r:
        tok += f"  {DIM}↺{fmt_k(win_cache_r)}{RS}"
    cost = f"{AM}◆${win_cost:.4f}{RS}"
    lines.append(f"{label('5h')}  {tok}  {cost}")
    if rl_5h_pct is not None:
        lines.append(f"{INDENT}{draw_bar(rl_5h_pct/100, BAR_C)}{fmt_reset(rl_5h_reset)}")

    # 7d: data line, then bar on its own line
    tok  = f"{GR}▲{fmt_k(week_inp)}{RS}  {RD}▼{fmt_k(week_out)}{RS}"
    cost = f"{AM}◆${week_cost:.4f}{RS}"
    lines.append(f"{label('7d')}  {tok}  {cost}")
    if rl_7d_pct is not None:
        lines.append(f"{INDENT}{draw_bar(rl_7d_pct/100, BAR_C)}{fmt_reset(rl_7d_reset)}")
    else:
        ratio = min(1.0, week_cost / WEEK_BUDGET) if WEEK_BUDGET else 0
        lines.append(f"{INDENT}{draw_bar(ratio, BAR_C)}")

else:
    # ── Landscape layout (≥ 100 cols) — original wide format ───────────────
    TOK_W  = 32
    COST_W = 12
    BAR_C  = 15

    # Line 1 — header
    hdr = f"{BLD}{CY}{model}{RS}"
    if eff_str: hdr += f" {DIM}→{RS} {MG}{eff_str}{RS}"
    hdr += f"  {DIM}│{RS}  {YE}{dir_str}{RS}"
    if branch: hdr += f"  {DIM}⎇{RS} {BL}{branch}{RS}"
    lines.append(hdr)

    # Line 2 — ctx
    tok = f"{WH}{fmt_k(ctx_used)}{DIM}/{fmt_k(max_ctx)}{RS}"
    lines.append(f"{label('ctx')}  {pad(tok, TOK_W)}{pad('', COST_W)}{draw_bar(pct_val/100, BAR_C)}")

    # Line 3 — 5h window  (▲ new+cache_w  ↺ cache reads  ▼ output)
    tok  = f"{GR}▲{fmt_k(win_inp_new)}{RS}  {RD}▼{fmt_k(win_out)}{RS}"
    if win_cache_r:
        tok += f"  {DIM}↺{fmt_k(win_cache_r)}{RS}"
    cost = f"{AM}◆${win_cost:.4f}{RS}"
    if rl_5h_pct is not None:
        lines.append(f"{label('5h')}  {pad(tok, TOK_W)}{pad(cost, COST_W)}{draw_bar(rl_5h_pct/100, BAR_C)}{fmt_reset(rl_5h_reset)}")
    else:
        lines.append(f"{label('5h')}  {pad(tok, TOK_W)}{pad(cost, COST_W)}")

    # Line 4 — 7d  (▲ total effective input = new+cache  ▼ output)
    tok  = f"{GR}▲{fmt_k(week_inp)}{RS}  {RD}▼{fmt_k(week_out)}{RS}"
    cost = f"{AM}◆${week_cost:.4f}{RS}"
    if rl_7d_pct is not None:
        lines.append(f"{label('7d')}  {pad(tok, TOK_W)}{pad(cost, COST_W)}{draw_bar(rl_7d_pct/100, BAR_C)}{fmt_reset(rl_7d_reset)}")
    else:
        ratio = min(1.0, week_cost / WEEK_BUDGET) if WEEK_BUDGET else 0
        lines.append(f"{label('7d')}  {pad(tok, TOK_W)}{pad(cost, COST_W)}{draw_bar(ratio, BAR_C)}")

out_str = "\n".join(lines) + "\n"
sys.stdout.buffer.write(out_str.encode("utf-8", errors="replace"))
sys.stdout.buffer.flush()
