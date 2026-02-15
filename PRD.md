# PRD: Bitget BTC 선물 자동매매 트레이딩 에이전트

## 1. 프로젝트 개요

### 1.1 목적
EmperorBTC 트레이딩 매뉴얼의 기술적 분석 원칙을 기반으로 Bitget 거래소에서 BTC/USDT 무기한 선물을 자동으로 매매하는 트레이딩 에이전트를 개발한다.

### 1.2 핵심 목표
- 24시간 자동 시장 분석 및 매매 실행
- 철저한 리스크 관리로 자본 보존
- 웹 UI를 통한 실시간 설정 관리
- Discord Bot을 통한 모바일 긴급 제어
- 데모 트레이딩으로 전략 검증 후 실거래 전환

### 1.3 운용 규모
- 초기 자본금: 20,000원 (~$15) 파일럿
- 최대 자본금: 500,000원 미만 (~$380)
- 거래 자산: BTCUSDT 무기한 선물

---

## 2. 시스템 아키텍처

### 2.1 전체 구조

```
└─────────────────────────────────────────────────────────────────┐
│                         Render (호스팅)                          │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                  Single Web Service                       │  │
│  │                                                           │  │
│  │  ┌──────────────┐           ┌──────────────┐              │  │
│  │  │  Trading Bot │ (Task)    │    Web UI    │              │  │
│  │  │  (Asyncio)   │◄─────────►│   (FastAPI)  │              │  │
│  │  └──────────────┘           └──────────────┘              │  │
│  │         ▲                          ▲                      │  │
│  │         │ WebSocket                │ HTTP                 │  │
│  └─────────┼──────────────────────────┼──────────────────────┘  │
│            │                          │                         │
│  ┌─────────┴──────────────────────────┴──────────┐              │
│  │              Discord Bot (제어/알림)            │              │
│  │  /status /stop /pause /resume /close /pnl     │              │
│  └───────────────────────────────────────────────┘              │
└───────────────────────────┼─────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
        ▼                   ▼                   ▼
┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│   Supabase   │   │    Bitget    │   │   External   │
│ (PostgreSQL) │   │   Futures    │   │  Cron Job    │
│              │   │     API      │   │ (Keep-Alive) │
│ - 설정 저장   │   │ - 시세(WS)    │   │              │
│ - 거래 기록   │   │ - 주문(REST)  │   │ - 14분 주기   │
│ - 성과 데이터 │   │              │   │   Ping       │
└──────────────┘   └──────────────┘   └──────────────┘
```

### 2.2 기술 스택

| 영역 | 기술 | 버전 | 용도 |
|------|------|------|------|
| 언어 | Python | 3.11+ | 메인 개발 언어 (Asyncio 필수) |
| 거래소 연동 | aiohttp / websockets | 최신 | Bitget Public WebSocket (Free) |
| 주문 실행 | ccxt (Async) | 최신 | REST API (주문/잔고) |
| 기술적 분석 | pandas-ta | 최신 | 보조지표 계산 |
| 데이터 처리 | pandas, numpy | 최신 | 데이터 분석 |
| 웹 프레임워크 | FastAPI | 최신 | REST API + 웹 UI |
| 프론트엔드 | Jinja2 + Tailwind CSS | - | 서버사이드 렌더링 |
| Discord | discord.py | 최신 | Bot 구현 |
| 데이터베이스 | Supabase (PostgreSQL) | - | 클라우드 DB |
| 스케줄링 | APScheduler | 최신 | 주기적 작업 |
| 비동기 | asyncio, aiohttp | - | 비동기 처리 |
| 환경변수 | python-dotenv | 최신 | 설정 관리 |
| 호스팅 | Render | - | 클라우드 배포 |

---

## 3. 핵심 기능 명세

### 3.1 시장 분석 엔진

#### 3.1.1 데이터 수집
```python
# 수집 데이터 (WebSocket 실시간 스트리밍)
- 실시간 체결 데이터 (Trade Steam)
- 실시간 호가 데이터 (Orderbook Stream)
- 캔들 데이터 (1분봉 업데이트)

```

#### 3.1.2 기술적 지표 계산
```python
# 필수 지표
indicators = {
    'EMA': [13, 21, 50, 200],      # 지수이동평균
    'RSI': 14,                      # 상대강도지수
    'MACD': (12, 26, 9),           # MACD
    'OBV': True,                    # On-Balance Volume
    'Volume_MA': 14,                # 거래량 이동평균
}
```

#### 3.1.3 분석 주기
| 작업 | 주기 | 설명 |
|------|------|------|
| 실시간 시세 수신 | WebSocket | ms 단위 반응 |
| 지표 계산 | 캔들 마감/틱 변화 시 | 실시간 업데이트 |
| 신호 생성 | 조건 충족 즉시 | 놓치는 신호 방지 |
| 포지션 모니터링 | 실시간 (Tick-by-Tick) | 손절/익절 즉각 반응 |

### 3.2 매매 실행 엔진

#### 3.2.1 롱 포지션 진입 조건

**필수 조건 (모두 충족):**
```python
LONG_ENTRY_CONDITIONS = {
    'trend': {
        'daily_above_ema50': True,          # 1일봉 가격 > EMA 50
        'ema_alignment': '13 > 21 > 50',    # 4시간봉 EMA 정배열
    },
    'structure': {
        'higher_low': True,                  # 이전 저점보다 높은 저점
    },
    'volume': {
        'above_average': True,               # 거래량 > 14MA
    }
}
```

**추가 확인 (2개 이상):**
```python
LONG_CONFIRMATION = [
    'rsi_bullish_divergence',    # RSI 상승 다이버전스
    'rsi_bounce_from_30',        # RSI 30 이하에서 반등
    'macd_bullish_cross',        # MACD 골든크로스
    'obv_uptrend',               # OBV 상승 추세
    'reversal_candle',           # 반전 캔들 (해머, 장악형)
    'support_retest_success',    # 지지 리테스트 성공
]
# 최소 2개 이상 충족 시 진입
```

#### 3.2.2 숏 포지션 진입 조건

**필수 조건 (모두 충족):**
```python
SHORT_ENTRY_CONDITIONS = {
    'trend': {
        'daily_below_ema50': True,          # 1일봉 가격 < EMA 50
        'ema_alignment': '13 < 21 < 50',    # 4시간봉 EMA 역배열
    },
    'structure': {
        'lower_high': True,                  # 이전 고점보다 낮은 고점
    },
    'volume': {
        'above_average': True,               # 거래량 > 14MA
    }
}
```

**추가 확인 (2개 이상):**
```python
SHORT_CONFIRMATION = [
    'rsi_bearish_divergence',    # RSI 하락 다이버전스
    'rsi_drop_from_70',          # RSI 70 이상에서 하락
    'macd_bearish_cross',        # MACD 데드크로스
    'obv_downtrend',             # OBV 하락 추세
    'reversal_candle',           # 반전 캔들 (슈팅스타)
    'resistance_retest_fail',    # 저항 리테스트 실패
]
```

#### 3.2.3 청산 조건

**익절 (Take Profit):**
```python
TAKE_PROFIT_RULES = {
    'level_1': {'rr_ratio': 1.5, 'close_percent': 50, 'action': 'move_sl_to_entry'},
    'level_2': {'rr_ratio': 2.5, 'close_percent': 30, 'action': 'activate_trailing'},
    'level_3': {'rr_ratio': 4.0, 'close_percent': 20, 'action': 'close_remaining'},
}
```

**손절 (Stop Loss):**
```python
STOP_LOSS_RULES = {
    'type': 'swing_based',           # 스윙 로우/하이 기반
    'buffer_percent': 0.5,           # 버퍼
    'max_loss_percent': 3.0,         # 최대 손실률
}
```

**반전 신호 청산:**
```python
REVERSAL_EXIT_SIGNALS = [
    'opposite_ema_crossover',        # 반대 EMA 크로스
    'opposite_rsi_divergence',       # 반대 RSI 다이버전스
    'strong_reversal_candle',        # 강한 반전 캔들 + 거래량
    'opposite_macd_crossover',       # 반대 MACD 크로스
]
```

#### 3.2.4 진입 회피 조건
```python
NO_ENTRY_CONDITIONS = [
    'extreme_volatility',            # 24시간 변동성 > 평균 3배
    'unclear_trend',                 # EMA 50-200 사이 가격
    'low_volume',                    # 거래량 < 14MA의 50%
    'no_clear_sr',                   # 명확한 지지/저항 없음
    'poor_rr_ratio',                 # R:R < 1.5:1
    'max_positions_reached',         # 최대 포지션 수 도달
]
```

### 3.3 리스크 관리 엔진

#### 3.3.1 자본 관리
```python
CAPITAL_MANAGEMENT = {
    'risk_per_trade': 0.05,          # 1회 최대 리스크 5%
    'daily_max_loss': 0.05,          # 1일 최대 손실 5%
    'weekly_max_loss': 0.10,         # 주간 최대 손실 10%
    'total_capital_protection': 0.70, # 총 자본의 70% 보호
}
```

#### 3.3.2 레버리지 설정
```python
LEVERAGE_SETTINGS = {
    'default': 10,                   # 기본 레버리지 (소액 운용)
    'low_volatility': 15,            # 저변동성 시
    'high_volatility': 5,            # 고변동성 시
    'margin_mode': 'isolated',       # 격리 마진
}
```

#### 3.3.3 포지션 사이징
```python
def calculate_position_size(balance, entry_price, stop_loss_price, risk_percent):
    """
    포지션 크기 = (잔고 × 리스크%) ÷ |진입가 - 손절가|
    """
    risk_amount = balance * risk_percent
    price_diff = abs(entry_price - stop_loss_price)
    position_size = risk_amount / price_diff
    return position_size
```

#### 3.3.4 거래 제한
```python
TRADING_LIMITS = {
    'max_concurrent_positions': 1,   # 최대 동시 포지션
    'max_daily_trades': 3,           # 1일 최대 거래
    'max_weekly_trades': 10,         # 주간 최대 거래
    'cooldown_after_loss_streak': {
        'consecutive_losses': 3,
        'cooldown_hours': 24,
    },
}
```

#### 3.3.5 긴급 중단 조건
```python
EMERGENCY_STOP_CONDITIONS = [
    'daily_loss_limit_reached',      # 1일 최대 손실 도달
    'weekly_loss_limit_reached',     # 주간 최대 손실 도달
    'consecutive_loss_limit',        # 3회 연속 손절
    'flash_crash_detected',          # 15분 내 5% 이상 급등락
    'api_error_streak',              # API 오류 3회 연속
    'manual_stop_command',           # 수동 긴급 중단
]
```

### 3.4 웹 UI (설정 관리 대시보드)

#### 3.4.1 페이지 구성

| 페이지 | 경로 | 기능 |
|--------|------|------|
| 대시보드 | `/` | 현재 상태, 포지션, 잔고, 최근 거래 |
| 설정 | `/settings` | 전략 파라미터 수정 |
| 거래 내역 | `/trades` | 전체 거래 기록 및 필터링 |
| 성과 분석 | `/performance` | PnL 차트, 승률, 통계 |
| 로그 | `/logs` | 시스템 로그 조회 |

#### 3.4.2 대시보드 표시 항목
```python
DASHBOARD_WIDGETS = {
    'status': {
        'bot_status': 'running/paused/stopped',
        'trading_mode': 'demo/live',
        'uptime': 'HH:MM:SS',
    },
    'account': {
        'balance': 'USDT',
        'available_margin': 'USDT',
        'unrealized_pnl': 'USDT',
    },
    'position': {
        'symbol': 'BTCUSDT',
        'side': 'long/short/none',
        'size': 'BTC',
        'entry_price': 'USDT',
        'current_price': 'USDT',
        'pnl_percent': '%',
        'stop_loss': 'USDT',
        'take_profit': 'USDT',
    },
    'daily_stats': {
        'trades_today': 'count',
        'win_rate': '%',
        'daily_pnl': 'USDT',
    },
}
```

#### 3.4.3 설정 페이지 항목
```python
CONFIGURABLE_SETTINGS = {
    'trading': {
        'enabled': bool,
        'mode': ['demo', 'live'],
        'symbol': 'BTCUSDT',
    },
    'risk': {
        'risk_per_trade': float,        # 0.01 ~ 0.10
        'max_daily_loss': float,        # 0.01 ~ 0.20
        'leverage': int,                # 1 ~ 20
    },
    'strategy': {
        'timeframe': ['15m', '1h', '4h'],
        'ema_periods': list,
        'rsi_period': int,
    },
    'notifications': {
        'discord_enabled': bool,
        'notify_on_entry': bool,
        'notify_on_exit': bool,
        'notify_on_error': bool,
    },
}
```

### 3.5 Discord Bot (모바일 제어)

#### 3.5.1 명령어 목록

| 명령어 | 설명 | 응답 |
|--------|------|------|
| `/status` | 현재 상태 조회 | 봇 상태, 포지션, 잔고, PnL |
| `/stop` | 긴급 중단 | 모든 포지션 청산 + 거래 중단 |
| `/pause` | 일시 정지 | 신규 거래 중단 (포지션 유지) |
| `/resume` | 거래 재개 | 일시 정지 해제 |
| `/close` | 포지션 청산 | 현재 포지션 즉시 청산 |
| `/settings` | 설정 조회 | 현재 주요 설정값 |
| `/pnl [period]` | 수익 현황 | 일간/주간/월간 PnL |
| `/balance` | 잔고 조회 | 현재 USDT 잔고 |

#### 3.5.2 자동 알림

| 이벤트 | 알림 내용 |
|--------|----------|
| 포지션 진입 | 방향, 가격, 수량, 손절가, 익절가 |
| 포지션 청산 | 결과, PnL, 보유 시간 |
| 손절 발동 | 손실 금액, 손실률 |
| 일일 한도 도달 | 경고 + 자동 중단 알림 |
| 시스템 오류 | 오류 내용 + 조치 필요 |

#### 3.5.3 권한 관리
```python
DISCORD_PERMISSIONS = {
    'admin_only_commands': ['/stop', '/close', '/pause', '/resume'],
    'public_commands': ['/status', '/pnl', '/balance', '/settings'],
}
```

### 3.6 데이터베이스 스키마

#### 3.6.1 테이블 구조

```sql
-- 설정 테이블
CREATE TABLE settings (
    id SERIAL PRIMARY KEY,
    key VARCHAR(100) UNIQUE NOT NULL,
    value JSONB NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 거래 기록 테이블
CREATE TABLE trades (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL,           -- 'long' or 'short'
    entry_price DECIMAL(20, 8) NOT NULL,
    exit_price DECIMAL(20, 8),
    quantity DECIMAL(20, 8) NOT NULL,
    leverage INT NOT NULL,
    stop_loss DECIMAL(20, 8),
    take_profit DECIMAL(20, 8),
    pnl DECIMAL(20, 8),
    pnl_percent DECIMAL(10, 4),
    status VARCHAR(20) NOT NULL,         -- 'open', 'closed', 'cancelled'
    entry_reason JSONB,
    exit_reason VARCHAR(100),
    entry_time TIMESTAMP NOT NULL,
    exit_time TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 일별 성과 테이블
CREATE TABLE daily_performance (
    id SERIAL PRIMARY KEY,
    date DATE UNIQUE NOT NULL,
    starting_balance DECIMAL(20, 8),
    ending_balance DECIMAL(20, 8),
    total_trades INT DEFAULT 0,
    winning_trades INT DEFAULT 0,
    losing_trades INT DEFAULT 0,
    total_pnl DECIMAL(20, 8),
    max_drawdown DECIMAL(10, 4),
    created_at TIMESTAMP DEFAULT NOW()
);

-- 시스템 로그 테이블
CREATE TABLE system_logs (
    id SERIAL PRIMARY KEY,
    level VARCHAR(20) NOT NULL,          -- 'DEBUG', 'INFO', 'WARNING', 'ERROR'
    message TEXT NOT NULL,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 봇 상태 테이블
CREATE TABLE bot_status (
    id SERIAL PRIMARY KEY,
    status VARCHAR(20) NOT NULL,         -- 'running', 'paused', 'stopped'
    trading_mode VARCHAR(10) NOT NULL,   -- 'demo', 'live'
    last_heartbeat TIMESTAMP,
    current_position JSONB,
    updated_at TIMESTAMP DEFAULT NOW()
);
```

---

## 4. 프로젝트 구조

```
bitcoin-autotrading/
├── README.md
├── requirements.txt
├── .env.example
├── .gitignore
├── render.yaml                    # Render 배포 설정
│
├── src/
│   ├── __init__.py
│   │
│   ├── core/                      # 핵심 엔진
│   │   ├── __init__.py
│   │   ├── trading_bot.py         # 메인 봇 클래스
│   │   ├── market_analyzer.py     # 시장 분석 엔진
│   │   ├── order_executor.py      # 주문 실행 엔진
│   │   ├── position_manager.py    # 포지션 관리
│   │   └── risk_manager.py        # 리스크 관리 엔진
│   │
│   ├── indicators/                # 기술적 지표
│   │   ├── __init__.py
│   │   ├── trend.py               # EMA, MA 등
│   │   ├── momentum.py            # RSI, MACD 등
│   │   ├── volume.py              # OBV, Volume MA 등
│   │   └── signals.py             # 매매 신호 생성
│   │
│   ├── exchange/                  # 거래소 연동
│   │   ├── __init__.py
│   │   ├── bitget_client.py       # Bitget API 클라이언트
│   │   └── data_fetcher.py        # 데이터 수집
│   │
│   ├── database/                  # 데이터베이스
│   │   ├── __init__.py
│   │   ├── supabase_client.py     # Supabase 연동
│   │   ├── models.py              # 데이터 모델
│   │   └── repository.py          # CRUD 작업
│   │
│   ├── discord_bot/               # Discord Bot
│   │   ├── __init__.py
│   │   ├── bot.py                 # Bot 메인
│   │   ├── commands.py            # Slash 명령어
│   │   └── notifications.py       # 알림 전송
│   │
│   ├── web/                       # 웹 UI
│   │   ├── __init__.py
│   │   ├── app.py                 # FastAPI 앱
│   │   ├── routes/
│   │   │   ├── __init__.py
│   │   │   ├── dashboard.py
│   │   │   ├── settings.py
│   │   │   ├── trades.py
│   │   │   └── api.py             # REST API
│   │   ├── templates/             # Jinja2 템플릿
│   │   │   ├── base.html
│   │   │   ├── dashboard.html
│   │   │   ├── settings.html
│   │   │   └── trades.html
│   │   └── static/                # CSS, JS
│   │       └── css/
│   │           └── style.css
│   │
│   ├── config/                    # 설정
│   │   ├── __init__.py
│   │   ├── settings.py            # 환경변수 로드
│   │   └── constants.py           # 상수 정의
│   │
│   └── utils/                     # 유틸리티
│       ├── __init__.py
│       ├── logger.py              # 로깅
│       └── helpers.py             # 헬퍼 함수
│
├── tests/                         # 테스트
│   ├── __init__.py
│   ├── test_indicators.py
│   ├── test_signals.py
│   └── test_risk_manager.py
│
├── scripts/                       # 스크립트
│   ├── backtest.py                # 백테스트
│   └── setup_db.py                # DB 초기화
│
└── docs/                          # 문서
    ├── TRADING_KNOWLEDGE_BASE.md
    ├── TRADING_STRATEGY.md
    └── API.md
```

---

## 5. 개발 단계

### Phase 1: 기반 구축 (Core Infrastructure)

**목표**: 기본 인프라 및 거래소 연동

```
[ ] 프로젝트 구조 생성
[ ] 환경변수 설정 (config/settings.py)
[ ] Bitget API 연동 (exchange/bitget_client.py)
    [ ] 인증 처리
    [ ] 잔고 조회
    [ ] OHLCV 데이터 조회
    [ ] 주문 생성/취소
    [ ] 포지션 조회
[ ] Supabase 연동 (database/supabase_client.py)
    [ ] 테이블 생성
    [ ] CRUD 함수
[ ] 로깅 시스템 (utils/logger.py)
[ ] 데모 트레이딩 모드 구현
```

### Phase 2: 분석 엔진 (Analysis Engine)

**목표**: 기술적 분석 및 신호 생성

```
[ ] 기술적 지표 구현 (indicators/)
    [ ] EMA (13, 21, 50, 200)
    [ ] RSI (14)
    [ ] MACD (12, 26, 9)
    [ ] OBV
    [ ] 거래량 MA
[ ] 시장 분석 엔진 (core/market_analyzer.py)
    [ ] 추세 분석
    [ ] 다이버전스 감지
    [ ] 지지/저항 식별
[ ] 신호 생성 (indicators/signals.py)
    [ ] 롱 진입 신호
    [ ] 숏 진입 신호
    [ ] 청산 신호
```

### Phase 3: 매매 엔진 (Trading Engine)

**목표**: 자동 매매 실행

```
[ ] 주문 실행 (core/order_executor.py)
    [ ] 진입 주문
    [ ] 손절/익절 주문
    [ ] 포지션 청산
[ ] 포지션 관리 (core/position_manager.py)
    [ ] 포지션 모니터링
    [ ] 트레일링 스탑
    [ ] 부분 청산
[ ] 리스크 관리 (core/risk_manager.py)
    [ ] 포지션 사이징
    [ ] 일일 손실 한도
    [ ] 긴급 중단
[ ] 메인 트레이딩 봇 (core/trading_bot.py)
    [ ] 스케줄링
    [ ] 상태 관리
```

### Phase 4: 제어 인터페이스 (Control Interface)

**목표**: 웹 UI 및 Discord Bot

```
[ ] Discord Bot (discord_bot/)
    [ ] Bot 초기화
    [ ] Slash 명령어 구현
    [ ] 알림 전송
[ ] 웹 UI (web/)
    [ ] FastAPI 앱 설정
    [ ] 대시보드 페이지
    [ ] 설정 페이지
    [ ] 거래 내역 페이지
    [ ] REST API
```

### Phase 5: 배포 및 테스트 (Deployment & Testing)

**목표**: Render 배포 및 전략 검증

```
[ ] Render 배포 설정
    [ ] render.yaml 작성
    [ ] 환경변수 설정
    [ ] Background Worker 설정
    [ ] Web Service 설정
[ ] 데모 트레이딩 테스트
    [ ] 최소 2주간 테스트
    [ ] 성과 분석
    [ ] 버그 수정
[ ] 실거래 전환 준비
    [ ] 설정 최종 검토
    [ ] 실거래 API 키 설정
```

---

## 6. API 명세

### 6.1 REST API 엔드포인트

#### 상태 조회
```
GET /api/status
Response: {
    "bot_status": "running",
    "trading_mode": "demo",
    "uptime": "12:34:56",
    "current_position": {...},
    "balance": 15.00
}
```

#### 설정 조회/수정
```
GET /api/settings
Response: { "risk_per_trade": 0.05, ... }

PUT /api/settings
Body: { "risk_per_trade": 0.03 }
Response: { "success": true }
```

#### 거래 제어
```
POST /api/bot/start
POST /api/bot/stop
POST /api/bot/pause
POST /api/bot/resume
POST /api/position/close
```

#### 거래 내역
```
GET /api/trades?limit=50&offset=0
GET /api/trades/{id}
GET /api/performance?period=daily
```

---

## 7. 배포 설정

### 7.1 render.yaml

```yaml
services:
  # 통합 서비스 (Web + Bot) - Free Tier 최적화
  - type: web
    name: trading-service
    env: python
    buildCommand: pip install -r requirements.txt
    startCommand: uvicorn src.web.app:app --host 0.0.0.0 --port $PORT
    envVars:
      - key: PYTHON_VERSION
        value: 3.11.0
      - key: TRADING_BOT_ENABLED
        value: "true"

```

### 7.2 환경변수 (Render Dashboard에서 설정)

```
BITGET_API_KEY=***
BITGET_SECRET_KEY=***
BITGET_PASSPHRASE=***
TRADING_MODE=demo
DISCORD_BOT_TOKEN=***
DISCORD_GUILD_ID=***
DISCORD_CHANNEL_ID=***
DISCORD_ADMIN_ID=***
SUPABASE_URL=***
SUPABASE_KEY=***
LOG_LEVEL=INFO
```

---

## 8. 모니터링 및 알림

### 8.1 로깅 레벨

| 레벨 | 내용 |
|------|------|
| DEBUG | API 호출, 지표 계산 상세 |
| INFO | 거래 실행, 신호 생성, 상태 변경 |
| WARNING | 일일 한도 50% 도달, 연속 손실 |
| ERROR | API 오류, 주문 실패, 시스템 오류 |
| CRITICAL | 긴급 중단, 연결 끊김 |

### 8.2 Discord 알림 포맷

```
📈 포지션 진입
━━━━━━━━━━━━━━━
방향: LONG
진입가: $98,500.00
수량: 0.001 BTC
레버리지: 10x
손절가: $97,515.00 (-1.0%)
익절가: $99,977.50 (+1.5%)
━━━━━━━━━━━━━━━
```

---

## 9. 보안 요구사항

### 9.1 API 키 관리
- 환경변수로만 관리 (하드코딩 금지)
- 출금 권한 비활성화
- IP 화이트리스트 설정 (배포 후)

### 9.2 웹 UI 보안
- HTTPS 필수 (Render 자동 제공)
- 인증 미구현 시 Render Private Service 사용 검토

### 9.3 Discord Bot 보안
- 관리자 명령어는 Admin ID 확인
- PUBLIC BOT 비활성화
- 전용 서버 사용

---

## 10. 성공 기준

### 10.1 데모 트레이딩 (2주)
- [ ] 봇 24시간 안정 운영
- [ ] 일일 손실 한도 초과 없음
- [ ] Discord 알림 정상 작동
- [ ] 웹 UI 정상 작동

### 10.2 성과 지표 목표
| 지표 | 목표 | 최소 |
|------|------|------|
| 승률 | 45%+ | 40% |
| 평균 R:R | 2:1+ | 1.5:1 |
| 최대 낙폭 | 15% 이하 | 20% |
| 수익 팩터 | 1.5+ | 1.2 |

---

## 11. 참고 문서

- `TRADING_KNOWLEDGE_BASE.md`: EmperorBTC 트레이딩 지식 베이스
- `TRADING_STRATEGY.md`: 상세 전략 파라미터
- `BITGET_API_GUIDE.md`: Bitget API 발급 가이드
- `DISCORD_BOT_GUIDE.md`: Discord Bot 설정 가이드

---

*문서 버전: 1.0.0*
*작성일: 2024*
