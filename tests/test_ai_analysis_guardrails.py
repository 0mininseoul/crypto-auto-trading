"""
AI 분석 응답 가드레일 테스트
"""
from src.ai.analysis_guardrails import post_process_analysis


def _sample_market_data():
    return {
        "df_1h": {"trend": "중립/혼조"},
        "df_15m": {"rsi": 55.2, "macd_direction": "상승", "candle_pattern": "보통"},
        "df_5m": {"ema_aligned": True},
        "volume": {"ratio": 0.82, "obv_trend": "상승"},
    }


def test_general_analysis_fallback_when_sections_missing():
    raw = "단기 추세: 15분, MACD 상승."

    result, fallback_used = post_process_analysis(
        analysis_type="general",
        raw_text=raw,
        market_data=_sample_market_data(),
        position=None,
        finish_reason="STOP",
    )

    assert fallback_used is True
    assert "[시장 상황]" in result
    assert "[포지션 조언]" in result


def test_general_analysis_passes_when_format_is_complete():
    raw = (
        "[시장 상황]\n1시간 추세는 중립/혼조이며 15분 RSI 55.2, MACD 상승, 거래량 비율 82%입니다.\n\n"
        "[진입 조건 점검]\n롱 필수 2/3(추가 2/4), 숏 필수 1/3(추가 1/4)로 아직 확정 신호는 아닙니다.\n\n"
        "[미진입 사유]\n필수 조건이 완전 충족되지 않아 현재는 관망이 타당합니다.\n\n"
        "[전략 제안]\n1시간 추세와 15분 MACD가 같은 방향으로 재정렬되면 진입을 검토하세요.\n\n"
        "[포지션 조언]\n포지션 없음 상태이므로 조건 3/3 충족 전까지 신규 진입을 보류하세요."
    )

    result, fallback_used = post_process_analysis(
        analysis_type="general",
        raw_text=raw,
        market_data=_sample_market_data(),
        position=None,
        finish_reason="STOP",
    )

    assert fallback_used is False
    assert result == raw


def test_entry_analysis_fallback_on_short_max_tokens():
    raw = "1. 현재 시장 상황 요약\n- 추세: 1"

    result, fallback_used = post_process_analysis(
        analysis_type="entry",
        raw_text=raw,
        market_data=_sample_market_data(),
        position=None,
        finish_reason="FinishReason.MAX_TOKENS",
        signal_info={
            "signal_type": "SHORT",
            "mandatory_met": 3,
            "additional_met": 3,
            "reasons": ["1시간 하락 추세", "MACD 하락 지속"],
        },
    )

    assert fallback_used is True
    assert "[시장 상황]" in result
    assert "[진입 근거]" in result
