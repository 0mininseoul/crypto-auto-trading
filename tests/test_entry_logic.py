"""
진입 로직 테스트 (Hybrid Strategy Verification)
"""
import pytest
import pandas as pd
import numpy as np
from src.indicators.signals import check_long_entry, SignalType

@pytest.fixture
def hybrid_setup_df():
    """
    하이브리드 전략 테스트용 데이터프레임
    - 시나리오: 
      - iloc[-2] (마감 캔들): 모든 진입 조건 충족 (Setup & Trigger)
      - iloc[-1] (현재 캔들): 조건 불충족
    """
    n = 100
    dates = pd.date_range('2024-01-01', periods=n, freq='15min')
    
    # 기본 데이터 생성
    data = {
        'timestamp': dates,
        'open': np.full(n, 50000.0),
        'high': np.full(n, 51000.0),
        'low': np.full(n, 49000.0),
        'close': np.full(n, 50000.0),
        'volume': np.full(n, 1000.0),
    }
    df = pd.DataFrame(data)
    
    # 지표 컬럼 추가 (계산 로직 없이 강제 할당)
    df['ema_9'] = 50000.0
    df['ema_21'] = 49000.0
    df['ema_50'] = 48000.0
    df['ema_200'] = 40000.0
    df['rsi'] = 50.0
    df['macd'] = 100.0
    df['macd_signal'] = 90.0
    df['macd_hist'] = 10.0
    df['volume_ma'] = 500.0
    df['obv'] = 1000.0
    
    # === 15분봉 설정 ===
    # iloc[-2] (마감): 조건 충족
    # 1. RSI > 40
    df.loc[98, 'rsi'] = 60.0 
    # 2. MACD 상승 (moderate)
    df.loc[97, 'macd_hist'] = 5.0
    df.loc[98, 'macd_hist'] = 10.0 
    # 3. 거래량 > 70%
    df.loc[98, 'volume'] = 1000.0
    df.loc[98, 'volume_ma'] = 500.0
    
    # iloc[-1] (현재): 조건 불충족 (이걸 참조하면 신호 안 나와야 함)
    df.loc[99, 'rsi'] = 30.0       # RSI 탈락
    df.loc[99, 'macd_hist'] = -5.0 # MACD 탈락
    
    return df

@pytest.fixture
def trend_1h_df():
    """1시간봉 (추세 충족)"""
    n = 100
    df = pd.DataFrame({
        'timestamp': pd.date_range('2024-01-01', periods=n, freq='1h'),
        'close': np.full(n, 52000.0), # 15분봉보다 높거나 비슷
        'ema_9': np.full(n, 51000.0),
        'ema_50': np.full(n, 49000.0), # 가격(50000) > 50(49000) 충족하도록 수정
    })
    return df

@pytest.fixture
def timing_5m_df():
    """5분봉 (타이밍 충족)"""
    n = 100
    df = pd.DataFrame({
        'timestamp': pd.date_range('2024-01-01', periods=n, freq='5min'),
        'close': np.full(n, 50000.0),
        'ema_9': np.full(n, 50100.0),
        'ema_21': np.full(n, 50000.0), # 정배열
    })
    
    # iloc[-2] (마감): 정배열 충족
    df.loc[98, 'ema_9'] = 50100.0
    df.loc[98, 'ema_21'] = 50000.0
    
    # iloc[-1] (현재): 역배열 (참조하면 안됨)
    df.loc[99, 'ema_9'] = 49900.0
    df.loc[99, 'ema_21'] = 50000.0
    
    return df

def test_check_long_entry_uses_closed_candle(hybrid_setup_df, trend_1h_df, timing_5m_df):
    """
    check_long_entry가 iloc[-2](마감 캔들/직전 캔들)를 사용하는지 검증
    """
    # 15분봉 iloc[-2]는 조건 충족, iloc[-1]은 불충족
    # 5분봉 iloc[-2]는 조건 충족, iloc[-1]은 불충족
    
    signal = check_long_entry(hybrid_setup_df, trend_1h_df, timing_5m_df)
    
    print(f"\nSignal Reasons: {signal.reasons}")
    
    # iloc[-2]를 참조했다면 LONG 신호가 나와야 함
    assert signal.signal_type == SignalType.LONG
    assert signal.mandatory_met >= 3
    assert signal.additional_met >= 1
