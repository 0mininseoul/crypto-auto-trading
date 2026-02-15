"""
FastAPI 통합 서비스 (Web UI + Trading Bot + Discord Bot)
Single service architecture for Render Free Tier
"""
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse

from src.config.settings import get_settings
from src.utils.logger import setup_logger

logger = setup_logger("web")


# ──────────────────────────────────────
# Background Tasks
# ──────────────────────────────────────

async def run_trading_bot():
    """트레이딩 봇 백그라운드 태스크"""
    from src.core.trading_bot import TradingBot
    bot = TradingBot()
    await bot.run()


async def run_discord_bot():
    """Discord 봇 백그라운드 태스크"""
    from src.discord_bot.discord_bot import run_discord_bot as _run
    await _run()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan: 봇 시작/종료"""
    settings = get_settings()
    tasks = []

    if settings.trading_bot_enabled:
        logger.info("Trading Bot 백그라운드 태스크 시작...")
        tasks.append(asyncio.create_task(run_trading_bot()))

    if settings.discord_bot_token:
        logger.info("Discord Bot 백그라운드 태스크 시작...")
        tasks.append(asyncio.create_task(run_discord_bot()))
    else:
        logger.info("Discord Bot 비활성화 (DISCORD_BOT_TOKEN 미설정)")

    yield

    for t in tasks:
        if not t.done():
            t.cancel()
            try:
                await t
            except asyncio.CancelledError:
                pass
    logger.info("서비스 종료")


# ──────────────────────────────────────
# FastAPI App
# ──────────────────────────────────────

app = FastAPI(
    title="Bitcoin Autotrading Bot",
    description="BTC/USDT 선물 자동매매 봇",
    version="0.2.0",
    lifespan=lifespan,
)


# ──────────────────────────────────────
# Health Check
# ──────────────────────────────────────

@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": get_settings().trading_mode,
    }


# ──────────────────────────────────────
# API: 상태 / 잔고 / 포지션
# ──────────────────────────────────────

@app.get("/api/status")
async def get_bot_status():
    try:
        from src.database.repository import BotStatusRepository
        status = BotStatusRepository.get_status()
        return {"status": "ok", "data": status}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get("/api/balance")
async def get_balance():
    try:
        from src.exchange.bitget_client import BitgetClient
        client = BitgetClient()
        balance = await client.get_balance()
        await client.close()
        return {"status": "ok", "data": balance}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get("/api/positions")
async def get_positions():
    try:
        from src.exchange.bitget_client import BitgetClient
        client = BitgetClient()
        positions = await client.get_positions()
        await client.close()
        return {"status": "ok", "data": positions}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


# ──────────────────────────────────────
# API: 거래 내역 / 성과
# ──────────────────────────────────────

@app.get("/api/trades")
async def get_trades(limit: int = 20, offset: int = 0):
    try:
        from src.database.repository import TradeRepository
        trades = TradeRepository.get_trades(limit=limit, offset=offset)
        return {"status": "ok", "data": trades}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get("/api/performance")
async def get_performance(days: int = 30):
    try:
        from src.database.repository import PerformanceRepository
        data = PerformanceRepository.get_recent(days=days)
        return {"status": "ok", "data": data}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


# ──────────────────────────────────────
# API: 설정 조회 / 수정
# ──────────────────────────────────────

@app.get("/api/settings")
async def get_settings_api():
    try:
        from src.database.repository import SettingsRepository
        data = SettingsRepository.get_all()
        return {"status": "ok", "data": data}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.put("/api/settings")
async def update_settings_api(request: Request):
    try:
        from src.database.repository import SettingsRepository
        body = await request.json()
        for key, value in body.items():
            SettingsRepository.set(key, value)
        return {"status": "ok", "message": f"{len(body)}개 항목 업데이트"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


# ──────────────────────────────────────
# API: 봇 제어
# ──────────────────────────────────────

@app.post("/api/bot/stop")
async def bot_stop():
    try:
        from src.database.repository import BotStatusRepository
        from src.database.models import BotState
        BotStatusRepository.update_status(status=BotState.STOPPED)
        return {"status": "ok", "message": "봇 중단됨"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.post("/api/bot/pause")
async def bot_pause():
    try:
        from src.database.repository import BotStatusRepository
        from src.database.models import BotState
        BotStatusRepository.update_status(status=BotState.PAUSED)
        return {"status": "ok", "message": "봇 일시정지 — 포지션 유지, 신규 거래 차단"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.post("/api/bot/resume")
async def bot_resume():
    try:
        from src.database.repository import BotStatusRepository
        from src.database.models import BotState
        BotStatusRepository.update_status(status=BotState.RUNNING)
        return {"status": "ok", "message": "봇 거래 재개"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.post("/api/position/close")
async def close_position():
    try:
        from src.exchange.bitget_client import BitgetClient
        client = BitgetClient()
        positions = await client.get_positions()
        closed = 0
        for pos in positions:
            await client.close_position(pos.get("symbol", "BTCUSDT"))
            closed += 1
        await client.close()
        return {"status": "ok", "message": f"{closed}개 포지션 청산 완료"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


# ──────────────────────────────────────
# Web Dashboard
# ──────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    settings = get_settings()
    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>₿ BTC Trading Bot</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family:'Inter','Segoe UI',sans-serif; background:#0a0a1a; color:#e0e0e0; }}
.header {{ background:linear-gradient(135deg,#1a1a3e,#0d0d2b); padding:20px 24px; display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid #222; }}
.header h1 {{ color:#f7931a; font-size:20px; }}
.mode {{ padding:4px 12px; border-radius:12px; font-size:12px; font-weight:600;
  background:{"#1a3a1a" if settings.is_demo else "#3a1a1a"};
  color:{"#4ade80" if settings.is_demo else "#f87171"}; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); gap:16px; padding:20px; }}
.card {{ background:#12122a; border:1px solid #1e1e3a; border-radius:12px; padding:20px; }}
.card h3 {{ color:#888; font-size:12px; text-transform:uppercase; margin-bottom:8px; letter-spacing:1px; }}
.card .value {{ font-size:24px; font-weight:700; }}
.green {{ color:#4ade80; }} .red {{ color:#f87171; }} .yellow {{ color:#fbbf24; }}
.controls {{ padding:0 20px 20px; display:flex; gap:10px; flex-wrap:wrap; }}
.btn {{ padding:8px 20px; border-radius:8px; border:none; cursor:pointer; font-weight:600; font-size:13px; color:#fff; }}
.btn-stop {{ background:#dc2626; }} .btn-pause {{ background:#d97706; }}
.btn-resume {{ background:#16a34a; }} .btn-close {{ background:#7c3aed; }}
.btn:hover {{ opacity:.85; }}
.table-wrap {{ padding:0 20px 20px; }}
table {{ width:100%; border-collapse:collapse; background:#12122a; border-radius:12px; overflow:hidden; }}
th {{ background:#1a1a3a; color:#888; font-size:11px; text-transform:uppercase; padding:10px 12px; text-align:left; }}
td {{ padding:10px 12px; border-bottom:1px solid #1a1a2a; font-size:13px; }}
.chart-wrap {{ padding:0 20px 20px; }}
.chart-card {{ background:#12122a; border:1px solid #1e1e3a; border-radius:12px; padding:20px; }}
#pnlChart {{ max-height:200px; }}
.endpoints {{ padding:0 20px 20px; }}
.endpoints a {{ color:#60a5fa; text-decoration:none; font-size:13px; display:inline-block; margin-right:16px; }}
</style>
</head>
<body>
<div class="header">
  <h1>₿ BTC Trading Bot</h1>
  <span class="mode">{"🔧 DEMO" if settings.is_demo else "⚠️ LIVE"}</span>
</div>

<div class="grid" id="cards">
  <div class="card"><h3>봇 상태</h3><div class="value" id="botState">–</div></div>
  <div class="card"><h3>BTC 가격</h3><div class="value" id="btcPrice">–</div></div>
  <div class="card"><h3>잔고 (USDT)</h3><div class="value" id="balance">–</div></div>
  <div class="card"><h3>오늘 PnL</h3><div class="value" id="dailyPnl">–</div></div>
  <div class="card"><h3>오픈 포지션</h3><div class="value" id="openPos">–</div></div>
  <div class="card"><h3>하트비트</h3><div class="value" id="heartbeat" style="font-size:14px">–</div></div>
</div>

<div class="controls">
  <button class="btn btn-resume" onclick="botAction('resume')">▶ Resume</button>
  <button class="btn btn-pause" onclick="botAction('pause')">⏸ Pause</button>
  <button class="btn btn-stop" onclick="botAction('stop')">⏹ Stop</button>
  <button class="btn btn-close" onclick="botAction('close')">✕ Close Position</button>
</div>

<div class="chart-wrap">
  <div class="chart-card">
    <h3 style="color:#888;font-size:12px;text-transform:uppercase;margin-bottom:12px">일별 PnL</h3>
    <canvas id="pnlChart"></canvas>
  </div>
</div>

<div class="table-wrap">
  <table>
    <thead><tr><th>시간</th><th>방향</th><th>진입가</th><th>청산가</th><th>PnL</th><th>상태</th></tr></thead>
    <tbody id="tradesBody"><tr><td colspan="6" style="text-align:center;color:#666">로딩 중...</td></tr></tbody>
  </table>
</div>

<div class="endpoints" style="margin-top:8px">
  <a href="/health">/health</a>
  <a href="/api/status">/api/status</a>
  <a href="/api/balance">/api/balance</a>
  <a href="/api/trades">/api/trades</a>
  <a href="/api/positions">/api/positions</a>
  <a href="/api/performance">/api/performance</a>
  <a href="/api/settings">/api/settings</a>
</div>

<script>
const stateEmoji = {{running:'🟢',paused:'🟡',stopped:'🔴'}};

async function load() {{
  try {{
    const [statusR, balR, tradesR, perfR] = await Promise.all([
      fetch('/api/status').then(r=>r.json()),
      fetch('/api/balance').then(r=>r.json()),
      fetch('/api/trades?limit=10').then(r=>r.json()),
      fetch('/api/performance?days=14').then(r=>r.json()),
    ]);

    const s = statusR.data || {{}};
    const state = s.status || 'unknown';
    document.getElementById('botState').innerHTML = (stateEmoji[state]||'⚪')+' '+state.toUpperCase();
    document.getElementById('heartbeat').textContent = (s.last_heartbeat||'–').slice(0,19);

    const b = balR.data || {{}};
    document.getElementById('balance').textContent = (b.total||0).toFixed(2);

    const trades = tradesR.data || [];
    let todayPnl = 0;
    const tb = document.getElementById('tradesBody');
    if(trades.length){{
      tb.innerHTML = trades.map(t => {{
        const pnl = parseFloat(t.pnl||0);
        todayPnl += pnl;
        const cls = pnl>=0?'green':'red';
        return `<tr>
          <td>${{(t.entry_time||'').slice(0,16)}}</td>
          <td>${{(t.side||'').toUpperCase()}}</td>
          <td>${{parseFloat(t.entry_price||0).toLocaleString()}}</td>
          <td>${{t.exit_price?parseFloat(t.exit_price).toLocaleString():'–'}}</td>
          <td class="${{cls}}">${{pnl>=0?'+':''}}${{pnl.toFixed(2)}}</td>
          <td>${{t.status}}</td>
        </tr>`;
      }}).join('');
    }} else {{
      tb.innerHTML = '<tr><td colspan="6" style="text-align:center;color:#666">거래 없음</td></tr>';
    }}
    const pnlEl = document.getElementById('dailyPnl');
    pnlEl.textContent = (todayPnl>=0?'+':'') + todayPnl.toFixed(2);
    pnlEl.className = 'value '+(todayPnl>=0?'green':'red');

    // Chart
    const perf = (perfR.data || []).reverse();
    if(perf.length) {{
      new Chart(document.getElementById('pnlChart'), {{
        type:'bar',
        data:{{
          labels:perf.map(p=>p.date),
          datasets:[{{
            data:perf.map(p=>parseFloat(p.total_pnl||0)),
            backgroundColor:perf.map(p=>parseFloat(p.total_pnl||0)>=0?'rgba(74,222,128,.6)':'rgba(248,113,113,.6)'),
          }}]
        }},
        options:{{
          plugins:{{legend:{{display:false}}}},
          scales:{{
            y:{{grid:{{color:'#1a1a3a'}},ticks:{{color:'#888'}}}},
            x:{{grid:{{display:false}},ticks:{{color:'#888',maxRotation:45}}}},
          }}
        }}
      }});
    }}

    // Positions
    try {{
      const posR = await fetch('/api/positions').then(r=>r.json());
      document.getElementById('openPos').textContent = (posR.data||[]).length;
    }} catch(e) {{ document.getElementById('openPos').textContent = '–'; }}

    // BTC price
    try {{
      const pos = balR.data;
      document.getElementById('btcPrice').textContent = '–';
    }} catch(e){{}}

  }} catch(e) {{ console.error(e); }}
}}

async function botAction(action) {{
  const url = action==='close' ? '/api/position/close' : `/api/bot/${{action}}`;
  if(!confirm(action.toUpperCase()+' 실행?')) return;
  const r = await fetch(url, {{method:'POST'}});
  const j = await r.json();
  alert(j.message || j.status);
  load();
}}

load();
setInterval(load, 30000);
</script>
</body>
</html>"""
    return HTMLResponse(content=html)
