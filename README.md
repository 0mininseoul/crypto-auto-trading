# Bitcoin Auto Trading Bot

BTC/USDT 선물 자동매매 봇 - Bitget API + Discord 제어 + 웹 대시보드

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/template)

## Features

- **자동 매매**: EMA, RSI, MACD, OBV 기반 기술적 분석 (15분봉 데이 트레이딩)
- **AI 차트 분석**: **Gemini 3.0 Flash** 모델을 이용한 실시간 시장 분석 및 인사이트 제공
- **리스크 관리**: ATR 기반 손절/익절, 트레일링 스탑, 일일 손실 한도
- **Discord Bot**: 모바일에서 긴급 제어 및 AI 분석 요청 (`/analysis`, `/learning`)
- **웹 대시보드**: 실시간 상태 모니터링, 거래 내역, PnL 차트
- **데모 모드**: 실거래 전 테스트넷 검증 (SUSDT)

## Live Demo

- **Web Dashboard**: https://crypto-auto-trading.up.railway.app
- **Health Check**: https://crypto-auto-trading.up.railway.app/health

## Tech Stack

| Category | Technology |
|----------|------------|
| Language | Python 3.11+ |
| Exchange | Bitget (ccxt) |
| Analysis | pandas, ta (Technical Analysis) |
| Web | FastAPI, Uvicorn |
| Database | Supabase (PostgreSQL) |
| Notification | Discord.py |
| Hosting | Railway |

## Project Structure

```
src/
├── config/          # 설정 관리
│   ├── settings.py  # 환경변수 로드
│   └── constants.py # 상수 정의
├── core/            # 핵심 트레이딩 로직
│   ├── trading_bot.py     # 메인 봇 오케스트레이션
│   ├── market_analyzer.py # 시장 분석
│   ├── order_executor.py  # 주문 실행
│   ├── position_manager.py# 포지션 관리
│   └── risk_manager.py    # 리스크 관리
├── exchange/        # 거래소 연동
│   ├── bitget_client.py   # Bitget REST API
│   ├── data_fetcher.py    # OHLCV 데이터 수집
│   └── websocket_client.py# WebSocket 실시간 데이터
├── indicators/      # 기술적 지표
│   ├── trend.py     # EMA, MACD
│   ├── momentum.py  # RSI
│   ├── volume.py    # OBV, Volume MA
│   └── signals.py   # 매매 신호 생성
├── database/        # 데이터베이스
│   ├── supabase_client.py
│   ├── models.py
│   └── repository.py
├── discord_bot/     # Discord 봇
│   ├── discord_bot.py
│   └── notifier.py
├── web/             # 웹 대시보드
│   └── app.py       # FastAPI 앱 (통합 서비스)
└── utils/           # 유틸리티
    ├── logger.py
    └── helpers.py
```

## Quick Start

### 1. Clone Repository

```bash
git clone https://github.com/0mininseoul/crypto-auto-trading.git
cd crypto-auto-trading
```

### 2. Install Dependencies

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configure Environment

```bash
cp .env.example .env
# .env 파일을 열어 API 키 설정
```

### 4. Run Locally

```bash
uvicorn src.web.app:app --reload --port 8000
```

Open http://localhost:8000

## Environment Variables

| Variable | Description |
|----------|-------------|
| `BITGET_API_KEY` | Bitget API Key |
| `BITGET_SECRET_KEY` | Bitget Secret Key |
| `BITGET_PASSPHRASE` | Bitget API Passphrase |
| `TRADING_MODE` | `demo` or `live` |
| `DISCORD_BOT_TOKEN` | Discord Bot Token |
| `DISCORD_GUILD_ID` | Discord Server ID |
| `DISCORD_CHANNEL_ID` | Notification Channel ID |
| `DISCORD_ADMIN_ID` | Admin User ID |
| `SUPABASE_URL` | Supabase Project URL |
| `SUPABASE_KEY` | Supabase Anon Key |

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/api/status` | GET | Bot status |
| `/api/balance` | GET | Account balance |
| `/api/positions` | GET | Open positions |
| `/api/trades` | GET | Trade history |
| `/api/performance` | GET | Daily PnL |
| `/api/bot/stop` | POST | Stop bot |
| `/api/bot/pause` | POST | Pause trading |
| `/api/bot/resume` | POST | Resume trading |
| `/api/position/close` | POST | Close all positions |

## Discord Commands

| Command | Description |
|---------|-------------|
| `/status` | 현재 봇 상태, 잔고, 포지션 조회 |
| `/analysis` | **AI 시장 분석** (Gemini 3.0 Flash) 및 전략 제안 |
| `/learning` | AI 자가 학습 현황 및 통계 조회 |
| `/mode` | 거래 모드 전환 (Demo ↔️ Live) |
| `/stop` | 긴급 중단 (포지션 청산 + 거래 중단) |
| `/pause` | 일시 정지 (포지션 유지, 신규 거래 차단) |
| `/resume` | 거래 재개 |
| `/close` | 현재 포지션 청산 |
| `/pnl` | 일간/주간/월간 수익 현황 |

## Trading Strategy

### Entry Signals (Long)
### Entry Signals (Long)
- EMA 9 > EMA 21 (단기 상승 추세)
- RSI 40 이상 + MACD 히스토그램 상승
- 직전 캔들 거래량 > 14MA의 70%
- 추가 확인: OBV 상승, 캔들 패턴 등 (AI 분석 참고)

### Risk Management
- 1회 최대 리스크: 자본의 2~5%
- ATR 기반 동적 손절/익절
- 일일 최대 손실: 5%
- 최대 동시 포지션: 1개

## Deployment

### Railway (Recommended)

1. Fork this repository
2. Create new project on [Railway](https://railway.app)
3. Connect GitHub repo
4. Set environment variables
5. Deploy!

## License

MIT License

## Disclaimer

**투자 주의**: 이 봇은 교육 및 연구 목적으로 개발되었습니다. 암호화폐 선물 거래는 높은 위험을 수반하며, 원금 손실이 발생할 수 있습니다. 실거래 전 반드시 데모 모드에서 충분히 테스트하세요.
