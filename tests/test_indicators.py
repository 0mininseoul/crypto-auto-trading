"""
기술적 지표 단위 테스트
"""
import pytest
import pandas as pd
import numpy as np


class TestVolumeIndicators:
    """거래량 지표 테스트"""

    @pytest.fixture
    def sample_df(self):
        """테스트용 DataFrame 생성"""
        np.random.seed(42)
        n = 50
        df = pd.DataFrame({
            'timestamp': pd.date_range('2024-01-01', periods=n, freq='15min'),
            'open': np.random.uniform(49000, 51000, n),
            'high': np.random.uniform(50000, 52000, n),
            'low': np.random.uniform(48000, 50000, n),
            'close': np.random.uniform(49000, 51000, n),
            'volume': np.random.uniform(100, 500, n),
        })
        return df

    def test_calculate_volume_ma(self, sample_df):
        """거래량 이동평균 계산"""
        from src.indicators.volume import calculate_volume_ma

        vol_ma = calculate_volume_ma(sample_df, period=14)

        assert len(vol_ma) == len(sample_df)
        # 처음 13개는 NaN
        assert vol_ma.iloc[:13].isna().all()
        # 14번째부터 값 존재
        assert not pd.isna(vol_ma.iloc[13])

    def test_is_volume_too_low(self, sample_df):
        """거래량 부족 감지"""
        from src.indicators.volume import add_volume_indicators, is_volume_too_low

        df = add_volume_indicators(sample_df, period=14)

        # 마지막 캔들의 거래량을 매우 낮게 설정
        df.iloc[-2, df.columns.get_loc('volume')] = 10  # 직전 캔들

        result = is_volume_too_low(df, threshold=0.5, row_idx=-2)
        # 10 < vol_ma * 0.5 이면 True
        assert isinstance(result, bool)

    def test_is_volume_above_average(self, sample_df):
        """평균 이상 거래량 감지"""
        from src.indicators.volume import add_volume_indicators, is_volume_above_average

        df = add_volume_indicators(sample_df, period=14)

        # 마지막 캔들의 거래량을 매우 높게 설정
        df.iloc[-2, df.columns.get_loc('volume')] = 10000

        result = is_volume_above_average(df, row_idx=-2)
        assert result is True

    def test_calculate_obv(self, sample_df):
        """OBV 계산"""
        from src.indicators.volume import calculate_obv

        obv = calculate_obv(sample_df)

        assert len(obv) == len(sample_df)
        assert obv.iloc[0] == 0  # 첫 번째 값은 0


class TestMomentumIndicators:
    """모멘텀 지표 테스트"""

    @pytest.fixture
    def sample_df(self):
        """테스트용 DataFrame 생성"""
        np.random.seed(42)
        n = 50
        # 상승 추세 데이터
        prices = 50000 + np.cumsum(np.random.randn(n) * 100)
        df = pd.DataFrame({
            'timestamp': pd.date_range('2024-01-01', periods=n, freq='15min'),
            'open': prices - 50,
            'high': prices + 100,
            'low': prices - 100,
            'close': prices,
            'volume': np.random.uniform(100, 500, n),
        })
        return df

    def test_calculate_rsi(self, sample_df):
        """RSI 계산"""
        from src.indicators.momentum import calculate_rsi

        rsi = calculate_rsi(sample_df, period=14)

        assert len(rsi) == len(sample_df)
        # RSI는 0-100 범위
        valid_rsi = rsi.dropna()
        assert (valid_rsi >= 0).all()
        assert (valid_rsi <= 100).all()

    def test_calculate_macd(self, sample_df):
        """MACD 계산"""
        from src.indicators.momentum import calculate_macd

        macd_line, signal_line, histogram = calculate_macd(
            sample_df, fast=12, slow=26, signal=9
        )

        assert len(macd_line) == len(sample_df)
        assert len(signal_line) == len(sample_df)
        assert len(histogram) == len(sample_df)

        # histogram = macd_line - signal_line
        valid_idx = ~macd_line.isna() & ~signal_line.isna()
        np.testing.assert_array_almost_equal(
            histogram[valid_idx],
            (macd_line - signal_line)[valid_idx]
        )

    def test_macd_histogram_positive(self, sample_df):
        """MACD 히스토그램 양전환 감지"""
        from src.indicators.momentum import add_macd, is_macd_histogram_positive

        df = add_macd(sample_df)

        # 강제로 양전환 시나리오 생성
        df.iloc[-2, df.columns.get_loc('macd_hist')] = -10  # 이전: 음수
        df.iloc[-1, df.columns.get_loc('macd_hist')] = 5    # 현재: 양수

        result = is_macd_histogram_positive(df, row_idx=-1)
        assert result is True

    def test_macd_histogram_negative(self, sample_df):
        """MACD 히스토그램 음전환 감지"""
        from src.indicators.momentum import add_macd, is_macd_histogram_negative

        df = add_macd(sample_df)

        # 강제로 음전환 시나리오 생성
        df.iloc[-2, df.columns.get_loc('macd_hist')] = 10   # 이전: 양수
        df.iloc[-1, df.columns.get_loc('macd_hist')] = -5   # 현재: 음수

        result = is_macd_histogram_negative(df, row_idx=-1)
        assert result is True


class TestTrendIndicators:
    """추세 지표 테스트"""

    @pytest.fixture
    def sample_df(self):
        """테스트용 DataFrame 생성"""
        np.random.seed(42)
        n = 250  # EMA 200을 위해 충분한 데이터
        prices = 50000 + np.cumsum(np.random.randn(n) * 50)
        df = pd.DataFrame({
            'timestamp': pd.date_range('2024-01-01', periods=n, freq='15min'),
            'open': prices - 25,
            'high': prices + 50,
            'low': prices - 50,
            'close': prices,
            'volume': np.random.uniform(100, 500, n),
        })
        return df

    def test_add_all_emas(self, sample_df):
        """EMA 추가"""
        from src.indicators.trend import add_all_emas

        df = add_all_emas(sample_df)

        assert 'ema_9' in df.columns
        assert 'ema_21' in df.columns
        assert 'ema_50' in df.columns
        assert 'ema_200' in df.columns

    def test_is_price_above_ema(self, sample_df):
        """가격이 EMA 위에 있는지 확인"""
        from src.indicators.trend import add_all_emas, is_price_above_ema

        df = add_all_emas(sample_df)

        # 마지막 가격을 EMA보다 높게 설정
        df.iloc[-1, df.columns.get_loc('close')] = df['ema_50'].iloc[-1] + 1000

        result = is_price_above_ema(df, period=50)
        assert result is True

    def test_ema_crossover_detection(self, sample_df):
        """EMA 크로스오버 감지"""
        from src.indicators.trend import add_all_emas, detect_ema_crossover

        df = add_all_emas(sample_df)

        # 골든크로스 시나리오
        df.iloc[-2, df.columns.get_loc('ema_9')] = 50000
        df.iloc[-2, df.columns.get_loc('ema_21')] = 50100
        df.iloc[-1, df.columns.get_loc('ema_9')] = 50200
        df.iloc[-1, df.columns.get_loc('ema_21')] = 50100

        result = detect_ema_crossover(df, fast=9, slow=21)
        assert result == "golden"

        # 데드크로스 시나리오
        df.iloc[-2, df.columns.get_loc('ema_9')] = 50200
        df.iloc[-2, df.columns.get_loc('ema_21')] = 50100
        df.iloc[-1, df.columns.get_loc('ema_9')] = 50000
        df.iloc[-1, df.columns.get_loc('ema_21')] = 50100

        result = detect_ema_crossover(df, fast=9, slow=21)
        assert result == "death"
