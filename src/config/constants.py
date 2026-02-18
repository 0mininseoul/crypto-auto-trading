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

# 테스트넷 (Demo) 심볼
DEMO_SYMBOL = "SBTCSUSDT"
DEMO_CCXT_SYMBOL = "SBTC/SUSDT:SUSDT"
DEMO_PRODUCT_TYPE = "SUSDT-FUTURES"

# 타임프레임 (15분봉 데이트레이딩 체제)
TIMEFRAMES = {
    "main": "15m",      # 메인 분석 (신호 생성)
    "trend_1h": "1h",   # 추세 확인 (상위 TF 필터)
    "trend_4h": "4h",   # 추세 확인 (보조)
    "timing": "5m",     # 정밀 타이밍 확인
    "one_min": "1m",    # 실시간 모니터링
}

# ============================================
# 기술적 지표 설정
# ============================================
EMA_PERIODS = [9, 21, 50, 200]
RSI_PERIOD = 14
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
VOLUME_MA_PERIOD = 14

# ============================================
# 리스크 관리
# ============================================
# 신뢰도 기반 동적 리스크 (TRADING_KNOWLEDGE_BASE.md 기반)
# - 낮음: 3% (확인 요소 부족)
# - 중간: 5% (기본값, 필수 조건 충족)
# - 높음: 7% (추가 조건 다수 충족)
RISK_LOW_CONFIDENCE = 0.03      # 신뢰도 < 70%
RISK_MEDIUM_CONFIDENCE = 0.05   # 신뢰도 70-85%
RISK_HIGH_CONFIDENCE = 0.07     # 신뢰도 > 85%

# 신뢰도 임계값
CONFIDENCE_LOW_THRESHOLD = 0.70     # 70% 미만 = 낮음
CONFIDENCE_HIGH_THRESHOLD = 0.85    # 85% 초과 = 높음

RISK_PER_TRADE = 0.05           # 기본 리스크 (후방 호환)
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
STOP_LOSS_BUFFER_PERCENT = 0.3  # 손절 버퍼 %
MAX_STOP_LOSS_PERCENT = 2.0     # 최대 손절률 (데이트레이딩)
ATR_PERIOD = 14                 # ATR 계산 기간
ATR_SL_BUFFER_MULTIPLIER = 0.35 # SL 버퍼에 반영할 ATR 배수
ATR_TP_BUFFER_MULTIPLIER = 0.20 # TP(선행 체결) 버퍼에 반영할 ATR 배수

# 지지/저항 레벨 추출 (스윙 클러스터링)
LEVEL_LOOKBACK_15M = 120
LEVEL_LOOKBACK_1H = 80
LEVEL_SWING_WINDOW_15M = 3
LEVEL_SWING_WINDOW_1H = 2
LEVEL_CLUSTER_TOLERANCE_PERCENT = 0.20  # 0.20% 이내를 같은 존으로 취급

# 손절/익절 계산 방식
USE_HYBRID_SR_TP = True          # R:R + 지지/저항 혼합 TP
ENFORCE_SR_MIN_RR_FILTER = False # SR 기준 손익비가 낮으면 진입 회피 (옵션)
MIN_RR_RATIO = 1.5               # 최소 손익비

# 거래소 브래킷 주문 정책
# 부분익절(50/30/20)은 봇 로직으로 관리하므로, 진입 시 거래소 TP는 기본 비활성화.
# (중복 TP 주문으로 인한 충돌/과청산 방지)
PLACE_ENTRY_TAKE_PROFIT_ON_EXCHANGE = False

TAKE_PROFIT_LEVELS = {
    1: {"rr_ratio": 1.5, "close_percent": 50, "action": "move_sl_to_entry"},
    2: {"rr_ratio": 2.5, "close_percent": 30, "action": "activate_trailing"},
    3: {"rr_ratio": 4.0, "close_percent": 20, "action": "close_remaining"},
}

TRAILING_STOP_PERCENT = 1.0     # 트레일링 스탑 % (데이트레이딩)
SYNC_STOP_LOSS_TO_EXCHANGE = True  # TP/트레일링 이벤트 시 거래소 SL 동기화

# 시간 배리어 (포지션 장기 방치 방지)
TIME_BARRIER_ENABLED = True
TIME_BARRIER_SOFT_MINUTES = 720      # 12시간 경과 시 성과 미흡하면 청산
TIME_BARRIER_HARD_MINUTES = 1440     # 24시간 경과 시 강제 청산
TIME_BARRIER_MIN_RR_PROGRESS = 0.30  # soft 배리어에서 요구하는 최소 R 진행도

# ============================================
# 거래 제한
# ============================================
MAX_CONCURRENT_POSITIONS = 1
MAX_DAILY_TRADES = 8            # 데이트레이딩 빈도 반영
MAX_WEEKLY_TRADES = 30           # 데이트레이딩 빈도 반영
CONSECUTIVE_LOSS_COOLDOWN = {
    "losses": 3,
    "cooldown_hours": 12,        # 데이트레이딩 특성 반영
}

# 추가 진입(불타기/물타기) 설정
# - 포지션 수 제한(1개)은 유지하면서 같은 방향 추가 진입만 허용
SCALE_IN_ENABLED = True
SCALE_IN_MIN_CONFIDENCE = 0.90        # 90% 이상일 때만 추가 진입 (보수형)
SCALE_IN_MAX_ADDS = 1                 # 추가 진입 최대 1회
SCALE_IN_MAX_SIZE_RATIO_PER_ADD = 0.3 # 1회 추가 진입은 현재 포지션의 최대 30%

# ============================================
# 진입 회피 조건
# ============================================
EXTREME_VOLATILITY_MULTIPLIER = 3.0  # 24시간 변동성 > 평균 3배
LOW_VOLUME_THRESHOLD = 0.3           # 거래량 < 14MA의 30% (진입 회피)
ENTRY_VOLUME_THRESHOLD = 0.7         # 거래량 > 14MA의 70% (진입 필수)

# ============================================
# MACD 히스토그램 해석 모드
# ============================================
# "strict": 히스토그램 > 0 (양수) 필수 (보수적)
# "moderate": 히스토그램 증가 추세면 OK (기본값)
MACD_HISTOGRAM_MODE = "moderate"

# ============================================
# 긴급 중단
# ============================================
FLASH_CRASH_PERCENT = 5.0            # 15분 내 5% 이상 급등락
API_ERROR_STREAK_LIMIT = 3           # API 오류 3회 연속

# ============================================
# 최소 주문 금액
# ============================================
MIN_ORDER_SIZE_USDT = 5.0            # Bitget 최소 주문 금액 (USDT)

# ============================================
# WebSocket 설정
# ============================================
BITGET_WS_PUBLIC_URL = "wss://ws.bitget.com/v2/ws/public"
BITGET_WS_PRIVATE_URL = "wss://ws.bitget.com/v2/ws/private"

# 테스트넷 (Demo) WebSocket
DEMO_WS_PUBLIC_URL = "wss://ws.bitget.com/v2/ws/public/demo"
DEMO_WS_PRIVATE_URL = "wss://ws.bitget.com/v2/ws/private/demo"
WS_PING_INTERVAL = 25               # 초 단위
WS_RECONNECT_DELAY = 1              # 초기 재연결 대기
WS_RECONNECT_MAX_DELAY = 60         # 최대 재연결 대기


# ============================================
# 모드별 동적 헬퍼 함수
# ============================================

def get_quote_currency() -> str:
    """현재 모드에 맞는 통화 단위 반환 (USDT / SUSDT)"""
    from src.config.trading_mode import is_demo_mode
    return "SUSDT" if is_demo_mode() else "USDT"


def get_active_symbol() -> str:
    """현재 모드에 맞는 심볼 반환 (SBTCSUSDT / BTCUSDT)"""
    from src.config.trading_mode import is_demo_mode
    return DEMO_SYMBOL if is_demo_mode() else SYMBOL


def get_active_ccxt_symbol() -> str:
    """현재 모드에 맞는 ccxt 심볼 반환"""
    from src.config.trading_mode import is_demo_mode
    return DEMO_CCXT_SYMBOL if is_demo_mode() else CCXT_SYMBOL


def get_active_product_type() -> str:
    """현재 모드에 맞는 product type 반환"""
    from src.config.trading_mode import is_demo_mode
    return DEMO_PRODUCT_TYPE if is_demo_mode() else PRODUCT_TYPE
