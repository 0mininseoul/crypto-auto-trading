"""
트레이딩 상수 정의
PRD.md + TRADING_STRATEGY.md 기반
"""

# ============================================
# 거래 기본 설정
# ============================================
SYMBOL = "BTCUSDT"
CCXT_SYMBOL = "BTC/USDT:USDT"
PRODUCT_TYPE = "USDT-FUTURES"

# 타임프레임
TIMEFRAMES = {
    "main": "4h",       # 메인 분석
    "daily": "1d",      # 일봉 추세
    "hourly": "1h",     # 참조
    "fifteen": "15m",   # 세부 참조
    "one_min": "1m",    # 실시간 모니터링
}

# ============================================
# 기술적 지표 설정
# ============================================
EMA_PERIODS = [13, 21, 50, 200]
RSI_PERIOD = 14
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
VOLUME_MA_PERIOD = 14

# ============================================
# 리스크 관리
# ============================================
RISK_PER_TRADE = 0.05           # 1회 최대 리스크 5% (소액 운용)
DAILY_MAX_LOSS = 0.05           # 1일 최대 손실 5%
WEEKLY_MAX_LOSS = 0.10          # 주간 최대 손실 10%
TOTAL_CAPITAL_PROTECTION = 0.70 # 총 자본의 70% 보호

# ============================================
# 레버리지
# ============================================
DEFAULT_LEVERAGE = 10           # 기본 (소액 운용)
LOW_VOLATILITY_LEVERAGE = 15    # 저변동성
HIGH_VOLATILITY_LEVERAGE = 5    # 고변동성
MARGIN_MODE = "isolated"        # 격리 마진

# ============================================
# 손절 / 익절
# ============================================
STOP_LOSS_BUFFER_PERCENT = 0.5  # 손절 버퍼 %
MAX_STOP_LOSS_PERCENT = 3.0     # 최대 손절률

TAKE_PROFIT_LEVELS = {
    1: {"rr_ratio": 1.5, "close_percent": 50, "action": "move_sl_to_entry"},
    2: {"rr_ratio": 2.5, "close_percent": 30, "action": "activate_trailing"},
    3: {"rr_ratio": 4.0, "close_percent": 20, "action": "close_remaining"},
}

TRAILING_STOP_PERCENT = 1.5     # 트레일링 스탑 %

# ============================================
# 거래 제한
# ============================================
MAX_CONCURRENT_POSITIONS = 1
MAX_DAILY_TRADES = 3
MAX_WEEKLY_TRADES = 10
CONSECUTIVE_LOSS_COOLDOWN = {
    "losses": 3,
    "cooldown_hours": 24,
}

# ============================================
# 진입 회피 조건
# ============================================
EXTREME_VOLATILITY_MULTIPLIER = 3.0  # 24시간 변동성 > 평균 3배
LOW_VOLUME_THRESHOLD = 0.5           # 거래량 < 14MA의 50%
MIN_RR_RATIO = 1.5                   # 최소 손익비

# ============================================
# 긴급 중단
# ============================================
FLASH_CRASH_PERCENT = 5.0            # 15분 내 5% 이상 급등락
API_ERROR_STREAK_LIMIT = 3           # API 오류 3회 연속

# ============================================
# WebSocket 설정
# ============================================
BITGET_WS_PUBLIC_URL = "wss://ws.bitget.com/v2/ws/public"
BITGET_WS_PRIVATE_URL = "wss://ws.bitget.com/v2/ws/private"
WS_PING_INTERVAL = 25               # 초 단위
WS_RECONNECT_DELAY = 1              # 초기 재연결 대기
WS_RECONNECT_MAX_DELAY = 60         # 최대 재연결 대기
