"""
Discord 알림 전송 (Notifier)
트레이딩 이벤트 → Discord 채널 Embed 메시지
AI 분석 통합 - 진입/청산 시 자동 분석 전송
"""
import asyncio
from datetime import datetime, timezone
from typing import Optional, Dict, Any

import discord

from src.config.settings import get_settings
from src.config.constants import get_quote_currency
from src.utils.helpers import kst_now
from src.utils.logger import setup_logger

logger = setup_logger("notifier")

# 싱글톤
_notifier: Optional["Notifier"] = None


class Notifier:
    """Discord 채널로 트레이딩 알림 전송"""

    def __init__(self):
        self._settings = get_settings()
        self._channel: Optional[discord.TextChannel] = None
        self._ready = False

    def set_channel(self, channel: discord.TextChannel):
        """알림 채널 설정 (Bot이 ready 된 후 호출)"""
        self._channel = channel
        self._ready = True
        logger.info(f"📢 알림 채널 설정: #{channel.name}")

    @property
    def is_ready(self) -> bool:
        return self._ready and self._channel is not None

    # ─── 진입 알림 ───

    async def notify_entry(
        self,
        side: str,
        entry_price: float,
        quantity: float,
        leverage: int,
        stop_loss: float,
        take_profit: float,
        signal_info: Optional[Dict[str, Any]] = None,
    ):
        """포지션 진입 알림 + AI 분석"""
        color = 0x00FF88 if side.lower() == "long" else 0xFF4444
        direction = "📈 LONG" if side.lower() == "long" else "📉 SHORT"

        sl_pct = abs(stop_loss - entry_price) / entry_price * 100
        tp_pct = abs(take_profit - entry_price) / entry_price * 100

        embed = discord.Embed(
            title=f"{direction} 포지션 진입",
            color=color,
            timestamp=kst_now(),
        )
        embed.add_field(name="진입가", value=f"${entry_price:,.2f}", inline=True)
        embed.add_field(name="수량", value=f"{quantity:.6f} BTC", inline=True)
        embed.add_field(name="레버리지", value=f"{leverage}x", inline=True)
        embed.add_field(
            name="손절가",
            value=f"${stop_loss:,.2f} (-{sl_pct:.1f}%)",
            inline=True,
        )
        embed.add_field(
            name="익절가",
            value=f"${take_profit:,.2f} (+{tp_pct:.1f}%)",
            inline=True,
        )

        await self._send(embed)

        # AI 분석 전송 (비동기)
        asyncio.create_task(self._send_entry_analysis(signal_info))

    async def _send_entry_analysis(self, signal_info: Optional[Dict[str, Any]]):
        """진입 시 AI 분석 전송"""
        try:
            from src.ai.chart_analyzer import get_chart_analyzer

            analyzer = get_chart_analyzer()
            if not analyzer or not analyzer.is_available:
                return

            analysis = await analyzer.analyze_for_entry(signal_info or {})

            if analysis and len(analysis) > 50:  # 의미있는 분석인 경우만
                # 분석 결과가 길면 자르기
                if len(analysis) > 4000:
                    analysis = analysis[:3997] + "..."

                embed = discord.Embed(
                    title="🤖 AI 진입 분석",
                    description=analysis,
                    color=0x9B59B6,
                    timestamp=kst_now(),
                )
                embed.set_footer(text="이 분석은 참고용이며, 실제 결정은 전략에 따릅니다")
                await self._send(embed)

        except Exception as e:
            logger.error(f"진입 AI 분석 전송 실패: {e}")

    # ─── 청산 알림 ───

    async def notify_exit(
        self,
        side: str,
        entry_price: float,
        exit_price: float,
        pnl: float,
        pnl_percent: float,
        reason: str,
        quantity: float = 0,
    ):
        """포지션 청산 알림 + AI 복기"""
        is_win = pnl >= 0
        color = 0x00FF88 if is_win else 0xFF4444
        emoji = "💰" if is_win else "📉"

        embed = discord.Embed(
            title=f"{emoji} 포지션 청산 ({side.upper()})",
            color=color,
            timestamp=kst_now(),
        )
        embed.add_field(name="진입가", value=f"${entry_price:,.2f}", inline=True)
        embed.add_field(name="청산가", value=f"${exit_price:,.2f}", inline=True)
        embed.add_field(
            name="PnL",
            value=f"{'+'if pnl>=0 else ''}{pnl:.2f} {get_quote_currency()} ({pnl_percent:+.1f}%)",
            inline=True,
        )
        embed.add_field(name="사유", value=reason, inline=False)

        await self._send(embed)

        # AI 복기 분석 전송 (비동기)
        trade_data = {
            "side": side,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "pnl": pnl,
            "pnl_percent": pnl_percent,
            "exit_reason": reason,
            "quantity": quantity,
        }
        asyncio.create_task(self._send_exit_analysis(trade_data))

    async def _send_exit_analysis(self, trade_data: Dict[str, Any]):
        """청산 시 AI 복기 분석 전송 + 학습"""
        try:
            from src.ai.chart_analyzer import get_chart_analyzer

            analyzer = get_chart_analyzer()
            if not analyzer or not analyzer.is_available:
                return

            analysis = await analyzer.analyze_for_exit(trade_data)

            if analysis and len(analysis) > 50:
                # 분석 결과가 길면 자르기
                if len(analysis) > 4000:
                    analysis = analysis[:3997] + "..."

                pnl = trade_data.get("pnl", 0)
                color = 0x00FF88 if pnl >= 0 else 0xFF4444

                embed = discord.Embed(
                    title="🧠 AI 거래 복기",
                    description=analysis,
                    color=color,
                    timestamp=kst_now(),
                )
                embed.set_footer(text="이 복기는 AI 학습에 저장됩니다")
                await self._send(embed)

        except Exception as e:
            logger.error(f"청산 AI 분석 전송 실패: {e}")

    # ─── 손절 알림 ───

    async def notify_stop_loss(
        self,
        side: str,
        entry_price: float,
        exit_price: float,
        loss: float,
        loss_percent: float,
    ):
        """손절 발동 알림"""
        embed = discord.Embed(
            title="🚨 손절 발동",
            color=0xFF0000,
            timestamp=kst_now(),
        )
        embed.add_field(name="방향", value=side.upper(), inline=True)
        embed.add_field(name="진입가", value=f"${entry_price:,.2f}", inline=True)
        embed.add_field(name="손절가", value=f"${exit_price:,.2f}", inline=True)
        embed.add_field(
            name="손실",
            value=f"{loss:.2f} {get_quote_currency()} ({loss_percent:.1f}%)",
            inline=False,
        )

        await self._send(embed)

    # ─── 일일 한도 알림 ───

    async def notify_daily_limit(self, daily_loss: float, limit: float):
        """일일 손실 한도 도달 알림"""
        embed = discord.Embed(
            title="⚠️ 일일 손실 한도 도달",
            description="자동으로 신규 거래가 중단됩니다.",
            color=0xFFA500,
            timestamp=kst_now(),
        )
        embed.add_field(
            name="오늘 손실",
            value=f"{daily_loss:.2f} {get_quote_currency()}",
            inline=True,
        )
        embed.add_field(name="한도", value=f"{limit:.2f} {get_quote_currency()}", inline=True)

        await self._send(embed)

    # ─── 시스템 오류 알림 ───

    async def notify_error(self, error_msg: str, severity: str = "ERROR"):
        """시스템 오류 알림"""
        color = 0xFF0000 if severity == "CRITICAL" else 0xFFA500
        embed = discord.Embed(
            title=f"🔧 시스템 {severity}",
            description=f"```{error_msg[:1000]}```",
            color=color,
            timestamp=kst_now(),
        )

        await self._send(embed)

    # ─── 내부 ───

    async def _send(self, embed: discord.Embed):
        """Embed 전송"""
        if not self.is_ready:
            logger.warning("Discord 알림 채널 미설정 — 메시지 무시")
            return
        try:
            await self._channel.send(embed=embed)
        except Exception as e:
            logger.error(f"Discord 알림 전송 실패: {e}")


def get_notifier() -> Notifier:
    """Notifier 싱글톤"""
    global _notifier
    if _notifier is None:
        _notifier = Notifier()
    return _notifier
