"""
RiskManager 단위 테스트
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestCalculatePositionSize:
    """포지션 사이징 테스트"""

    @pytest.fixture
    def risk_manager(self):
        """RiskManager 인스턴스 생성"""
        with patch('src.core.risk_manager.BitgetClient'):
            from src.core.risk_manager import RiskManager
            mock_exchange = MagicMock()
            return RiskManager(mock_exchange)

    def test_normal_position_size(self, risk_manager):
        """정상적인 포지션 사이징"""
        result = risk_manager.calculate_position_size(
            balance=10000,      # $10,000
            entry_price=50000,  # BTC @ $50,000
            stop_loss_price=49000,  # SL @ $49,000 (2% 손절)
            leverage=10,
        )

        # 리스크: 10000 * 0.05 = 500
        # 손절폭: 50000 - 49000 = 1000
        # BTC 수량: 500 / 1000 = 0.5 BTC
        assert result["size_btc"] == pytest.approx(0.5, rel=0.01)
        assert result["size_usdt"] == pytest.approx(25000, rel=0.01)
        assert result["margin_required"] == pytest.approx(2500, rel=0.01)
        assert result["risk_amount"] == pytest.approx(500, rel=0.01)

    def test_minimum_order_size_validation(self, risk_manager):
        """최소 주문 금액 검증"""
        result = risk_manager.calculate_position_size(
            balance=10,         # 매우 작은 잔고
            entry_price=50000,
            stop_loss_price=49000,
            leverage=10,
        )

        # 포지션 크기가 최소 금액(5 USDT) 미만이면 0 반환
        # 리스크: 10 * 0.05 = 0.5 USDT
        # size_usdt = 0.0005 BTC * 50000 = 25 USDT
        # 25 USDT > 5 USDT이므로 통과
        # 더 작은 잔고로 테스트
        result = risk_manager.calculate_position_size(
            balance=1,          # $1 잔고
            entry_price=50000,
            stop_loss_price=49000,
            leverage=10,
        )
        # 리스크: 1 * 0.05 = 0.05 USDT
        # size_btc: 0.05 / 1000 = 0.00005 BTC
        # size_usdt: 0.00005 * 50000 = 2.5 USDT < 5 USDT
        assert result["size_btc"] == 0
        assert result["size_usdt"] == 0

    def test_zero_price_diff(self, risk_manager):
        """진입가와 손절가가 동일한 경우"""
        result = risk_manager.calculate_position_size(
            balance=10000,
            entry_price=50000,
            stop_loss_price=50000,  # 동일!
            leverage=10,
        )

        assert result["size_btc"] == 0
        assert result["size_usdt"] == 0

    def test_max_stop_loss_limit(self, risk_manager):
        """최대 손절률 제한 테스트"""
        result = risk_manager.calculate_position_size(
            balance=10000,
            entry_price=50000,
            stop_loss_price=45000,  # 10% 손절 (최대 2% 초과)
            leverage=10,
        )

        # 손절폭이 2%로 제한됨
        # 조정된 손절폭: 50000 * 0.02 = 1000
        # size_btc: 500 / 1000 = 0.5 BTC
        assert result["size_btc"] == pytest.approx(0.5, rel=0.01)


class TestSelectLeverage:
    """레버리지 선택 테스트"""

    @pytest.fixture
    def risk_manager(self):
        with patch('src.core.risk_manager.BitgetClient'):
            from src.core.risk_manager import RiskManager
            mock_exchange = MagicMock()
            return RiskManager(mock_exchange)

    def test_low_volatility_leverage(self, risk_manager):
        """저변동성 → 15x"""
        leverage = risk_manager.select_leverage(
            volatility=0.5,
            avg_volatility=1.0,
        )
        assert leverage == 15  # ratio 0.5 < 0.7

    def test_normal_volatility_leverage(self, risk_manager):
        """보통 변동성 → 10x"""
        leverage = risk_manager.select_leverage(
            volatility=1.0,
            avg_volatility=1.0,
        )
        assert leverage == 10  # ratio 1.0 (0.7 ~ 1.5)

    def test_high_volatility_leverage(self, risk_manager):
        """고변동성 → 5x"""
        leverage = risk_manager.select_leverage(
            volatility=2.0,
            avg_volatility=1.0,
        )
        assert leverage == 5  # ratio 2.0 > 1.5


class TestApiErrorTracking:
    """API 에러 추적 테스트"""

    @pytest.fixture
    def risk_manager(self):
        with patch('src.core.risk_manager.BitgetClient'):
            from src.core.risk_manager import RiskManager
            mock_exchange = MagicMock()
            return RiskManager(mock_exchange)

    def test_api_error_count(self, risk_manager):
        """API 에러 카운트 증가"""
        assert risk_manager._api_error_count == 0

        risk_manager.record_api_error()
        assert risk_manager._api_error_count == 1

        risk_manager.record_api_error()
        assert risk_manager._api_error_count == 2

    def test_api_error_reset(self, risk_manager):
        """API 에러 카운트 리셋"""
        risk_manager.record_api_error()
        risk_manager.record_api_error()
        assert risk_manager._api_error_count == 2

        risk_manager.reset_api_errors()
        assert risk_manager._api_error_count == 0


class TestConsecutiveLossTracking:
    """연속 손절 추적 테스트"""

    @pytest.fixture
    def risk_manager(self):
        with patch('src.core.risk_manager.BitgetClient'):
            from src.core.risk_manager import RiskManager
            mock_exchange = MagicMock()
            return RiskManager(mock_exchange)

    def test_loss_count_increase(self, risk_manager):
        """손실 시 연속 손절 카운트 증가"""
        risk_manager.record_trade_result(-100)  # 손실
        assert risk_manager._consecutive_losses == 1

        risk_manager.record_trade_result(-50)  # 손실
        assert risk_manager._consecutive_losses == 2

    def test_loss_count_reset_on_profit(self, risk_manager):
        """이익 시 연속 손절 카운트 리셋"""
        risk_manager.record_trade_result(-100)
        risk_manager.record_trade_result(-50)
        assert risk_manager._consecutive_losses == 2

        risk_manager.record_trade_result(200)  # 이익
        assert risk_manager._consecutive_losses == 0
