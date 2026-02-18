"""
AI 분석용 프롬프트 템플릿
자체 학습 시스템 포함 - 복기 결과를 축적하여 고도화
"""
import json
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List

from src.utils.logger import setup_logger

logger = setup_logger("ai_prompts")


# ─── 학습 기록 관리 ───

LEARNING_FILE = Path(__file__).parent.parent.parent / "data" / "ai_learning.json"
MAX_REFERENCE_CHARS = 5000
MAX_LEARNING_CONTEXT_CHARS = 1200


def _compact_text(text: str, max_chars: int) -> str:
    """LLM 컨텍스트 길이 제어용 텍스트 압축"""
    if not text:
        return ""

    compact = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(compact) <= max_chars:
        return compact

    head_len = int(max_chars * 0.8)
    head = compact[:head_len].rstrip()
    if "\n" in head:
        head = head.rsplit("\n", 1)[0].rstrip()
    return f"{head}\n\n...(중략)..."


def _ensure_data_dir():
    """data 디렉토리 생성"""
    data_dir = LEARNING_FILE.parent
    data_dir.mkdir(parents=True, exist_ok=True)


def load_learning_history() -> Dict[str, Any]:
    """학습 기록 로드"""
    _ensure_data_dir()
    if LEARNING_FILE.exists():
        try:
            return json.loads(LEARNING_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error(f"학습 기록 로드 실패: {e}")
    return {
        "insights": [],  # 축적된 인사이트
        "trade_reviews": [],  # 거래 복기 기록
        "patterns": {  # 학습된 패턴
            "successful_entries": [],
            "failed_entries": [],
            "false_signals": [],
        },
        "stats": {  # 통계
            "total_analyses": 0,
            "accurate_predictions": 0,
            "last_updated": None,
        },
    }


def save_learning_history(history: Dict[str, Any]):
    """학습 기록 저장"""
    _ensure_data_dir()
    history["stats"]["last_updated"] = datetime.now().isoformat()
    try:
        LEARNING_FILE.write_text(
            json.dumps(history, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as e:
        logger.error(f"학습 기록 저장 실패: {e}")


def add_trade_review(
    trade_data: Dict[str, Any],
    analysis_before: str,
    result: str,  # "win", "loss", "breakeven"
    lessons_learned: List[str],
):
    """거래 복기 기록 추가"""
    history = load_learning_history()

    review = {
        "timestamp": datetime.now().isoformat(),
        "trade": trade_data,
        "analysis_before": analysis_before[:500],  # 분석 요약
        "result": result,
        "lessons": lessons_learned,
    }

    history["trade_reviews"].append(review)

    # 최근 50개만 유지
    history["trade_reviews"] = history["trade_reviews"][-50:]

    # 통계 업데이트
    history["stats"]["total_analyses"] += 1
    if result == "win":
        history["stats"]["accurate_predictions"] += 1

    save_learning_history(history)
    logger.info(f"거래 복기 저장: {result}")


def add_insight(insight: str, category: str = "general"):
    """인사이트 추가"""
    history = load_learning_history()

    history["insights"].append({
        "timestamp": datetime.now().isoformat(),
        "category": category,
        "content": insight,
    })

    # 최근 30개만 유지
    history["insights"] = history["insights"][-30:]

    save_learning_history(history)


def add_pattern(pattern_type: str, pattern_data: Dict[str, Any]):
    """학습된 패턴 추가

    pattern_type: "successful_entries", "failed_entries", "false_signals"
    """
    history = load_learning_history()

    if pattern_type in history["patterns"]:
        history["patterns"][pattern_type].append({
            "timestamp": datetime.now().isoformat(),
            **pattern_data,
        })
        # 각 카테고리 최근 20개만 유지
        history["patterns"][pattern_type] = history["patterns"][pattern_type][-20:]

    save_learning_history(history)


def get_learning_context() -> str:
    """학습된 내용을 프롬프트 컨텍스트로 변환"""
    history = load_learning_history()

    if not history["insights"] and not history["trade_reviews"]:
        return ""

    parts = ["## 학습된 인사이트 (이전 거래 복기 기반)\n"]

    # 최근 인사이트
    if history["insights"]:
        parts.append("### 핵심 교훈")
        for insight in history["insights"][-10:]:
            parts.append(f"- {insight['content']}")
        parts.append("")

    # 최근 거래 패턴
    if history["trade_reviews"]:
        wins = [r for r in history["trade_reviews"] if r["result"] == "win"]
        losses = [r for r in history["trade_reviews"] if r["result"] == "loss"]

        parts.append(f"### 최근 성과: 승 {len(wins)}회 / 패 {len(losses)}회")

        # 최근 실패에서 배운 교훈
        if losses:
            parts.append("\n### 최근 실패 교훈 (반복 방지)")
            for loss in losses[-3:]:
                for lesson in loss.get("lessons", [])[:2]:
                    parts.append(f"- {lesson}")
        parts.append("")

    # 성공 패턴
    success_patterns = history["patterns"].get("successful_entries", [])
    if success_patterns:
        parts.append("### 성공 패턴")
        for p in success_patterns[-5:]:
            if "description" in p:
                parts.append(f"- {p['description']}")
        parts.append("")

    return _compact_text("\n".join(parts), MAX_LEARNING_CONTEXT_CHARS)


# ─── 지식 베이스 로드 ───

def load_knowledge_base() -> str:
    """TRADING_KNOWLEDGE_BASE.md 로드"""
    base_path = Path(__file__).parent.parent.parent
    kb_path = base_path / "TRADING_KNOWLEDGE_BASE.md"

    if kb_path.exists():
        return kb_path.read_text(encoding="utf-8")
    return ""


def load_trading_strategy() -> str:
    """TRADING_STRATEGY.md 로드"""
    base_path = Path(__file__).parent.parent.parent
    strategy_path = base_path / "TRADING_STRATEGY.md"

    if strategy_path.exists():
        return strategy_path.read_text(encoding="utf-8")
    return ""


def get_system_prompt() -> str:
    """시스템 프롬프트 생성 (학습된 인사이트 포함)"""
    knowledge_base = _compact_text(load_knowledge_base(), MAX_REFERENCE_CHARS)
    trading_strategy = _compact_text(load_trading_strategy(), MAX_REFERENCE_CHARS)
    learning_context = get_learning_context()

    return f"""당신은 비트코인 선물 데이 트레이딩 전문가입니다.

## 역할
- 실시간 차트 데이터를 분석하여 현재 시장 상황을 명확히 설명
- 트레이딩 전략 문서에 기반한 진입/청산 조건 충족 여부 판단
- 구체적이고 실행 가능한 전략 제안 (불타기, 물타기 포함)
- 리스크 요인과 주의사항 명시
- 이전 거래 복기에서 배운 교훈을 현재 분석에 적용

## 응답 규칙
1. 한국어로 응답
2. 간결하고 핵심 위주로 작성 (Discord Embed에 맞게)
3. 구체적인 가격 레벨과 조건 명시
4. 불확실한 예측보다 조건부 시나리오 제시
5. 절대로 과장된 수익 예측이나 확신적 표현 사용 금지
6. 이전에 학습한 실패 패턴을 반복하지 않도록 주의

{learning_context}

## 참고 문서

### 트레이딩 지식 베이스
{knowledge_base}

### 트레이딩 전략 설계서
{trading_strategy}
"""


def format_market_data_prompt(
    current_price: float,
    df_15m_summary: Dict[str, Any],
    df_1h_summary: Dict[str, Any],
    df_5m_summary: Dict[str, Any],
    volume_info: Dict[str, Any],
    signal_info: Optional[Dict[str, Any]] = None,
) -> str:
    """시장 데이터 프롬프트 생성"""
    return f"""## 현재 시장 데이터

### 가격 정보
- 현재가: ${current_price:,.2f}

### 1시간봉 (추세 확인용)
- EMA 9: ${df_1h_summary.get('ema_9', 0):,.2f}
- EMA 21: ${df_1h_summary.get('ema_21', 0):,.2f}
- EMA 50: ${df_1h_summary.get('ema_50', 0):,.2f}
- EMA 200: ${df_1h_summary.get('ema_200', 0):,.2f}
- RSI(14): {df_1h_summary.get('rsi', 0):.1f}
- 추세: {df_1h_summary.get('trend', 'N/A')}

### 15분봉 (메인 타임프레임)
- EMA 9: ${df_15m_summary.get('ema_9', 0):,.2f}
- EMA 21: ${df_15m_summary.get('ema_21', 0):,.2f}
- EMA 50: ${df_15m_summary.get('ema_50', 0):,.2f}
- RSI(14): {df_15m_summary.get('rsi', 0):.1f}
- MACD 히스토그램: {df_15m_summary.get('macd_hist', 0):.4f}
- MACD 방향: {df_15m_summary.get('macd_direction', 'N/A')}
- 캔들 패턴: {df_15m_summary.get('candle_pattern', 'N/A')}

### 5분봉 (타이밍 확인용)
- EMA 9: ${df_5m_summary.get('ema_9', 0):,.2f}
- EMA 21: ${df_5m_summary.get('ema_21', 0):,.2f}
- EMA 정배열: {df_5m_summary.get('ema_aligned', False)}

### 거래량
- 현재 거래량: {volume_info.get('current', 0):,.0f}
- 14MA 거래량: {volume_info.get('ma_14', 0):,.0f}
- 비율: {volume_info.get('ratio', 0):.0%}
- OBV 추세: {volume_info.get('obv_trend', 'N/A')}
"""


def format_signal_info(signal_info: Dict[str, Any]) -> str:
    """시그널 정보 포맷팅"""
    if not signal_info:
        return ""

    signal_type = signal_info.get('signal_type', 'NO_SIGNAL')
    reasons = signal_info.get('reasons', [])
    mandatory_met = signal_info.get('mandatory_met', 0)
    additional_met = signal_info.get('additional_met', 0)

    reasons_text = "\n".join([f"  - {r}" for r in reasons]) if reasons else "  - 없음"

    return f"""
### 현재 시그널 상태
- 시그널: {signal_type}
- 필수 조건 충족: {mandatory_met}/3
- 추가 조건 충족: {additional_met}/4
- 판단 근거:
{reasons_text}
"""


def format_position_info(position: Optional[Dict[str, Any]]) -> str:
    """포지션 정보 포맷팅"""
    if not position:
        return """
## 현재 포지션
- 없음 (관망 중)
"""

    side = position.get('side', 'N/A').upper()
    entry_price = position.get('entry_price', 0)
    current_price = position.get('current_price', 0)
    quantity = position.get('quantity', 0)
    unrealized_pnl = position.get('unrealized_pnl', 0)
    pnl_pct = position.get('pnl_percent', 0)
    stop_loss = position.get('stop_loss', 0)
    take_profit = position.get('take_profit', 0)

    return f"""
## 현재 포지션
- 방향: {side}
- 진입가: ${entry_price:,.2f}
- 현재가: ${current_price:,.2f}
- 수량: {quantity:.6f} BTC
- 미실현 PnL: {'+' if unrealized_pnl >= 0 else ''}{unrealized_pnl:.2f} USDT ({pnl_pct:+.2f}%)
- 손절가: ${stop_loss:,.2f}
- 익절가: ${take_profit:,.2f}
"""


def get_analysis_request_prompt(analysis_type: str = "general") -> str:
    """분석 요청 프롬프트"""
    if analysis_type == "entry":
        return """
## 분석 요청 (진입 분석)
1. 현재 시장 상황 요약 (추세, 모멘텀, 거래량)
2. 진입 이유 설명 (어떤 조건들이 충족되었는지)
3. 주요 지지/저항 레벨
4. 리스크 요인과 주의사항
5. 추천 전략 (홀딩, 불타기 조건 등)

응답 형식 (아래 4개 섹션 제목을 그대로 사용):
[시장 상황]
...
[진입 근거]
...
[리스크]
...
[전략]
...

제약:
- 총 280~450자
- 문장이 중간에 끊기지 않게 완결형으로 작성
- 각 섹션 1~2문장
"""

    elif analysis_type == "exit":
        return """
## 분석 요청 (청산 분석)
1. 청산 이유 분석
2. 진입 시점과 청산 시점의 시장 변화
3. 잘한 점과 개선점 (복기 포인트)
4. 향후 재진입 조건

응답 형식:
- 객관적인 복기 위주
- 감정적 표현 배제
"""

    else:  # general
        return """
## 분석 요청
1. 현재 시장 상황을 TRADING_STRATEGY.md 기준으로 분석
2. 롱/숏 진입 조건 충족 여부 상세 설명
   - 필수 조건 3개 각각의 충족/미충족 상태
   - 추가 조건 4개 중 충족된 항목
3. 미진입 중이라면 그 이유 명확히
4. 향후 전략 제안
   - 어떤 조건이 충족되면 진입 가능한지
   - 주시해야 할 가격 레벨
5. 포지션 보유 중이라면 불타기/물타기/홀딩/청산 중 추천

응답 형식 (아래 5개 섹션 제목을 그대로 사용):
[시장 상황]
...
[진입 조건 점검]
...
[미진입 사유]
...
[전략 제안]
...
[포지션 조언]
...

제약:
- 총 350~550자
- 문장이 중간에 끊기지 않게 완결형으로 작성
- 각 섹션은 1~2문장, 핵심 수치 포함
"""


def build_full_prompt(
    current_price: float,
    df_15m_summary: Dict[str, Any],
    df_1h_summary: Dict[str, Any],
    df_5m_summary: Dict[str, Any],
    volume_info: Dict[str, Any],
    position: Optional[Dict[str, Any]] = None,
    signal_info: Optional[Dict[str, Any]] = None,
    analysis_type: str = "general",
) -> str:
    """전체 유저 프롬프트 조합"""
    parts = [
        format_market_data_prompt(
            current_price, df_15m_summary, df_1h_summary, df_5m_summary, volume_info
        ),
    ]

    if signal_info:
        parts.append(format_signal_info(signal_info))

    parts.append(format_position_info(position))
    parts.append(get_analysis_request_prompt(analysis_type))

    return "\n".join(parts)


def build_review_prompt(
    trade_data: Dict[str, Any],
    entry_analysis: str,
    market_at_entry: Dict[str, Any],
    market_at_exit: Dict[str, Any],
) -> str:
    """거래 복기 프롬프트 생성"""
    side = trade_data.get("side", "N/A").upper()
    entry_price = trade_data.get("entry_price", 0)
    exit_price = trade_data.get("exit_price", 0)
    pnl = trade_data.get("pnl", 0)
    pnl_pct = trade_data.get("pnl_percent", 0)
    exit_reason = trade_data.get("exit_reason", "N/A")

    return f"""## 거래 복기 요청

### 거래 정보
- 방향: {side}
- 진입가: ${entry_price:,.2f}
- 청산가: ${exit_price:,.2f}
- PnL: {'+' if pnl >= 0 else ''}{pnl:.2f} USDT ({pnl_pct:+.2f}%)
- 청산 사유: {exit_reason}

### 진입 시 분석
{entry_analysis[:500] if entry_analysis else "기록 없음"}

### 진입 시 시장 상황
- RSI: {market_at_entry.get('rsi', 'N/A')}
- 추세: {market_at_entry.get('trend', 'N/A')}
- MACD: {market_at_entry.get('macd_direction', 'N/A')}

### 청산 시 시장 상황
- RSI: {market_at_exit.get('rsi', 'N/A')}
- 추세: {market_at_exit.get('trend', 'N/A')}
- MACD: {market_at_exit.get('macd_direction', 'N/A')}

## 복기 요청
다음 항목에 대해 분석해주세요:

1. **진입 판단 평가**: 진입 시점의 조건 충족도와 타이밍 적절성
2. **청산 판단 평가**: 청산 시점과 방법의 적절성
3. **핵심 교훈**: 이 거래에서 배울 점 (성공이든 실패든)
4. **개선 포인트**: 다음에 비슷한 상황에서 어떻게 해야 하는지
5. **패턴 인식**: 이 거래에서 발견된 반복 가능한 패턴

응답 형식:
- 각 항목 2-3문장으로 간결하게
- 구체적인 가격과 지표 수치 언급
- JSON 형식으로 lessons 배열 포함:

```json
{{
  "lessons": ["교훈1", "교훈2", "교훈3"],
  "pattern_type": "successful_entries" 또는 "failed_entries" 또는 "false_signals",
  "pattern_description": "발견된 패턴 설명"
}}
```
"""
