"""
AI 분석 응답 가드레일
모델 응답 품질 검증 및 fallback 생성 로직
"""
import re
from typing import Any, Dict, List, Optional, Tuple


GENERAL_REQUIRED_SECTIONS = [
    "[시장 상황]",
    "[진입 조건 점검]",
    "[미진입 사유]",
    "[전략 제안]",
    "[포지션 조언]",
]
MIN_ANALYSIS_LENGTH = 120


def extract_finish_reason(response: Any) -> str:
    """Gemini 응답 종료 사유 추출"""
    try:
        candidates = getattr(response, "candidates", None) or []
        if candidates:
            finish_reason = getattr(candidates[0], "finish_reason", None)
            if finish_reason is not None:
                return str(finish_reason)
    except Exception:
        pass
    return "unknown"


def sanitize_analysis_text(text: str) -> str:
    """응답 텍스트 기본 정리"""
    if not text:
        return ""

    cleaned = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    cleaned = re.sub(r"^```[a-zA-Z]*\n", "", cleaned)
    cleaned = re.sub(r"\n```$", "", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def looks_truncated(text: str) -> bool:
    """문장 미완성 가능성 탐지"""
    if not text:
        return True

    tail = text.rstrip()
    if not tail:
        return True
    if tail[-1] in {",", ":", "(", "/", "-", "•"}:
        return True
    if tail.count("(") > tail.count(")"):
        return True
    return False


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def build_general_fallback(
    market_data: Dict[str, Any],
    position: Optional[Dict[str, Any]],
) -> str:
    """형식 불량 응답 대체용 로컬 분석 템플릿"""
    df_1h = market_data.get("df_1h", {})
    df_15m = market_data.get("df_15m", {})
    df_5m = market_data.get("df_5m", {})
    volume = market_data.get("volume", {})

    trend_1h = df_1h.get("trend", "데이터 부족")
    rsi_15m = safe_float(df_15m.get("rsi"), 50.0)
    macd_direction = df_15m.get("macd_direction", "N/A")
    vol_ratio = safe_float(volume.get("ratio"), 0.0)

    is_1h_up = "상승" in trend_1h
    is_1h_down = "하락" in trend_1h
    is_5m_up = bool(df_5m.get("ema_aligned", False))
    is_5m_down = not is_5m_up if "ema_aligned" in df_5m else False

    long_mandatory = sum(
        [
            is_1h_up,
            rsi_15m >= 40 and macd_direction == "상승",
            vol_ratio >= 0.7,
        ]
    )
    short_mandatory = sum(
        [
            is_1h_down,
            rsi_15m <= 60 and macd_direction == "하락",
            vol_ratio >= 0.7,
        ]
    )

    candle_pattern = str(df_15m.get("candle_pattern", ""))
    long_additional = sum(
        [
            volume.get("obv_trend") == "상승",
            "양봉" in candle_pattern or "해머" in candle_pattern,
            is_5m_up,
        ]
    )
    short_additional = sum(
        [
            volume.get("obv_trend") == "하락",
            "음봉" in candle_pattern or "슈팅스타" in candle_pattern,
            is_5m_down,
        ]
    )

    if position:
        side = str(position.get("side", "")).upper()
        pnl_pct = safe_float(position.get("pnl_percent"), 0.0)
        if pnl_pct <= -1.0:
            position_advice = f"현재 {side} 포지션 손익 {pnl_pct:+.2f}%로 손실 확장 구간입니다. 손절/비중 축소를 우선 검토하세요."
        elif pnl_pct >= 1.0:
            position_advice = f"현재 {side} 포지션 손익 {pnl_pct:+.2f}%로 우위입니다. 일부 익절 후 추세 유지 여부를 확인하세요."
        else:
            position_advice = f"현재 {side} 포지션 손익 {pnl_pct:+.2f}%로 중립 구간입니다. 추세 확정 전에는 보수적으로 대응하세요."
    else:
        position_advice = "포지션 없음 상태입니다. 필수 조건 3/3이 되기 전까지 신규 진입은 보류하세요."

    if long_mandatory == 3 or short_mandatory == 3:
        wait_reason = "필수 조건은 충족 가능 구간이지만 추가 확인(거래량/패턴/OBV) 확정이 더 필요합니다."
    else:
        wait_reason = "롱/숏 모두 필수 조건 3개가 완전히 충족되지 않아 관망이 우선입니다."

    return (
        "[시장 상황]\n"
        f"1시간 추세는 {trend_1h}, 15분 RSI는 {rsi_15m:.1f}, MACD는 {macd_direction}, 거래량 비율은 {vol_ratio:.0%}입니다.\n\n"
        "[진입 조건 점검]\n"
        f"롱 필수 {long_mandatory}/3 (추가 {long_additional}/4), 숏 필수 {short_mandatory}/3 (추가 {short_additional}/4) 상태입니다.\n\n"
        "[미진입 사유]\n"
        f"{wait_reason}\n\n"
        "[전략 제안]\n"
        "현재는 추세 추종보다 조건 확정 대기 전략이 유리합니다. 1시간 추세 방향과 15분 MACD 방향이 동시 정렬될 때 진입을 검토하세요.\n\n"
        "[포지션 조언]\n"
        f"{position_advice}"
    )


def build_entry_fallback(
    market_data: Dict[str, Any],
    signal_info: Optional[Dict[str, Any]] = None,
) -> str:
    """진입 분석 응답 불량 시 대체 메시지"""
    df_1h = market_data.get("df_1h", {})
    df_15m = market_data.get("df_15m", {})
    volume = market_data.get("volume", {})
    signal_info = signal_info or {}

    trend_1h = df_1h.get("trend", "데이터 부족")
    rsi_15m = safe_float(df_15m.get("rsi"), 50.0)
    macd = df_15m.get("macd_direction", "N/A")
    vol_ratio = safe_float(volume.get("ratio"), 0.0)
    mandatory = signal_info.get("mandatory_met", "-")
    additional = signal_info.get("additional_met", "-")
    signal_type = str(signal_info.get("signal_type", "UNKNOWN")).upper()

    reasons = signal_info.get("reasons", [])
    reason_text = ", ".join(str(r) for r in reasons[:2]) if reasons else "핵심 근거 로그를 확인하세요."
    risk_note = "고변동성 구간이므로 분할 진입과 손절 준수가 필수입니다." if vol_ratio >= 1.2 else "거래량이 평균 대비 높지 않으므로 추격 진입은 주의하세요."

    return (
        "[시장 상황]\n"
        f"1시간 추세는 {trend_1h}, 15분 RSI {rsi_15m:.1f}, MACD {macd}, 거래량 비율 {vol_ratio:.0%}입니다.\n\n"
        "[진입 근거]\n"
        f"신호는 {signal_type}, 필수 {mandatory}/3, 추가 {additional}/4로 집계되었습니다. 근거: {reason_text}\n\n"
        "[리스크]\n"
        f"{risk_note}\n\n"
        "[전략]\n"
        "손절/익절 가격을 사전에 고정하고, 가격이 역행하면 계획대로 즉시 대응하세요."
    )


def build_exit_fallback(
    market_data: Dict[str, Any],
    trade_data: Optional[Dict[str, Any]] = None,
) -> str:
    """청산/복기 응답 불량 시 대체 메시지"""
    df_1h = market_data.get("df_1h", {})
    df_15m = market_data.get("df_15m", {})
    trend_1h = df_1h.get("trend", "데이터 부족")
    rsi_15m = safe_float(df_15m.get("rsi"), 50.0)
    macd = df_15m.get("macd_direction", "N/A")
    trade_data = trade_data or {}

    pnl = safe_float(trade_data.get("pnl"), 0.0)
    pnl_pct = safe_float(trade_data.get("pnl_percent"), 0.0)
    outcome = "수익" if pnl >= 0 else "손실"

    return (
        "[복기 요약]\n"
        f"현재 지표는 1시간 {trend_1h}, 15분 RSI {rsi_15m:.1f}, MACD {macd}입니다.\n\n"
        "[거래 결과]\n"
        f"이번 거래는 {outcome} ({pnl:+.2f} USDT / {pnl_pct:+.2f}%)로 기록되었습니다.\n\n"
        "[개선 포인트]\n"
        "진입 근거와 청산 근거를 각각 1개씩 로그로 고정해 다음 거래에서 동일 조건 재현 여부를 확인하세요."
    )


def post_process_analysis(
    analysis_type: str,
    raw_text: str,
    market_data: Dict[str, Any],
    position: Optional[Dict[str, Any]],
    finish_reason: str,
    signal_info: Optional[Dict[str, Any]] = None,
    trade_data: Optional[Dict[str, Any]] = None,
    logger: Any = None,
) -> Tuple[str, bool]:
    """모델 응답 정리 + 품질 검증 + fallback"""
    cleaned = sanitize_analysis_text(raw_text)

    if analysis_type != "general":
        non_general_bad = (
            not cleaned
            or len(cleaned) < 120
            or looks_truncated(cleaned)
            or str(finish_reason).endswith("MAX_TOKENS")
        )
        if non_general_bad:
            if logger is not None:
                logger.warning(
                    "AI %s fallback 적용 | finish_reason=%s | raw_chars=%d",
                    analysis_type,
                    finish_reason,
                    len(raw_text),
                )
            if analysis_type == "entry":
                return build_entry_fallback(market_data, signal_info), True
            if analysis_type == "exit":
                return build_exit_fallback(market_data, trade_data), True
            return "AI 응답이 불완전하여 요약을 제공할 수 없습니다. 잠시 후 다시 시도하세요.", True

        normalized = cleaned or "AI 응답이 비어 있습니다. 잠시 후 다시 시도하세요."
        return normalized, normalized != raw_text

    issues: List[str] = []
    if not cleaned:
        issues.append("empty")
    if len(cleaned) < MIN_ANALYSIS_LENGTH:
        issues.append("too_short")
    if not re.search(r"[가-힣]", cleaned):
        issues.append("no_korean")

    missing_sections = [section for section in GENERAL_REQUIRED_SECTIONS if section not in cleaned]
    if missing_sections:
        issues.append("missing_sections")
    if looks_truncated(cleaned):
        issues.append("looks_truncated")

    if issues:
        if logger is not None:
            logger.warning(
                "AI 분석 fallback 적용 | finish_reason=%s | issues=%s | missing=%s | raw_chars=%d",
                finish_reason,
                ",".join(issues),
                ",".join(missing_sections) if missing_sections else "-",
                len(raw_text),
            )
        return build_general_fallback(market_data, position), True

    return cleaned, cleaned != raw_text
