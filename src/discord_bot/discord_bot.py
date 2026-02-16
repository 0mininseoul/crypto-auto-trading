"""
Discord Bot (Slash 명령어 + 알림)
PRD 3.5 기반
"""
import asyncio
from datetime import datetime, timezone
from typing import Optional

import discord
from discord import app_commands

from src.config.settings import get_settings
from src.discord_bot.notifier import get_notifier
from src.utils.helpers import kst_now
from src.utils.logger import setup_logger

logger = setup_logger("discord_bot")


class TradingDiscordBot(discord.Client):
    """트레이딩 봇 Discord 클라이언트"""

    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)

        self.tree = app_commands.CommandTree(self)
        self._settings = get_settings()
        self._guild_id = int(self._settings.discord_guild_id) if self._settings.discord_guild_id else None

    async def setup_hook(self):
        """봇 시작 시 Slash 명령어 등록"""
        _register_commands(self.tree, self._settings)

        if self._guild_id:
            guild = discord.Object(id=self._guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            logger.info(f"✅ Slash 명령어 등록 완료 (guild={self._guild_id})")
        else:
            await self.tree.sync()
            logger.info("✅ Slash 명령어 등록 완료 (global)")

    async def on_ready(self):
        """봇 준비 완료"""
        logger.info(f"🤖 Discord Bot 로그인: {self.user}")

        # 알림 채널 설정
        channel_id = self._settings.discord_channel_id
        if channel_id:
            channel = self.get_channel(int(channel_id))
            if channel:
                get_notifier().set_channel(channel)
                await channel.send("🟢 **Bitcoin Trading Bot** 접속 완료!")
            else:
                logger.warning(f"채널 {channel_id}을 찾을 수 없음")


def _is_admin(interaction: discord.Interaction) -> bool:
    """관리자 권한 확인"""
    settings = get_settings()
    return str(interaction.user.id) == settings.discord_admin_id


def _register_commands(tree: app_commands.CommandTree, settings):
    """Slash 명령어 등록"""

    # ━━━ /status ━━━
    @tree.command(name="status", description="봇 상태 조회")
    async def cmd_status(interaction: discord.Interaction):
        await interaction.response.defer()
        try:
            from src.database.repository import BotStatusRepository, TradeRepository
            from src.exchange.bitget_client import BitgetClient

            status = BotStatusRepository.get_status()
            open_trades = TradeRepository.get_open_trades()

            client = BitgetClient()
            balance = await client.get_balance()
            ticker = await client.get_ticker()
            await client.close()

            state = status.get("status", "unknown") if status else "unknown"
            mode = status.get("trading_mode", "demo") if status else "demo"
            heartbeat = status.get("last_heartbeat", "–") if status else "–"
            btc_price = ticker.get("last", 0) if ticker else 0

            state_emoji = {"running": "🟢", "paused": "🟡", "stopped": "🔴"}.get(state, "⚪")

            # heartbeat KST 변환
            heartbeat_display = "–"
            if heartbeat and heartbeat != "–":
                try:
                    heartbeat_display = heartbeat[:19].replace("T", " ") + " KST"
                except Exception:
                    heartbeat_display = str(heartbeat)[:19]

            embed = discord.Embed(
                title="📊 봇 상태",
                color=0x00BFFF,
                timestamp=kst_now(),
            )
            embed.add_field(name="상태", value=f"{state_emoji} {state.upper()}", inline=True)
            embed.add_field(name="모드", value=mode.upper(), inline=True)
            embed.add_field(name="BTC 가격", value=f"${btc_price:,.2f}", inline=True)
            embed.add_field(
                name="잔고",
                value=f"{balance.get('total', 0):.2f} {balance.get('currency', 'USDT')}" if balance else "–",
                inline=True,
            )
            embed.add_field(name="오픈 포지션", value=str(len(open_trades)), inline=True)
            embed.add_field(name="하트비트 (KST)", value=heartbeat_display, inline=True)

            await interaction.followup.send(embed=embed)
        except Exception as e:
            await interaction.followup.send(f"❌ 오류: {e}")

    # ━━━ /balance ━━━
    @tree.command(name="balance", description="잔고 조회")
    async def cmd_balance(interaction: discord.Interaction):
        await interaction.response.defer()
        try:
            from src.exchange.bitget_client import BitgetClient

            client = BitgetClient()
            balance = await client.get_balance()
            await client.close()

            currency = balance.get('currency', 'USDT')
            embed = discord.Embed(title="💰 잔고", color=0xFFD700)
            embed.add_field(name="총 잔고", value=f"{balance.get('total', 0):.4f} {currency}", inline=True)
            embed.add_field(name="사용 가능", value=f"{balance.get('free', 0):.4f} {currency}", inline=True)
            embed.add_field(name="사용 중", value=f"{balance.get('used', 0):.4f} {currency}", inline=True)

            await interaction.followup.send(embed=embed)
        except Exception as e:
            await interaction.followup.send(f"❌ 오류: {e}")

    # ━━━ /pnl ━━━
    @tree.command(name="pnl", description="수익 현황 조회")
    @app_commands.describe(period="조회 기간 (daily/weekly)")
    async def cmd_pnl(interaction: discord.Interaction, period: str = "daily"):
        await interaction.response.defer()
        try:
            from src.database.repository import TradeRepository

            today_pnl = TradeRepository.get_today_pnl()
            today_count = TradeRepository.get_today_trade_count()

            from src.config.constants import get_quote_currency
            currency = get_quote_currency()

            embed = discord.Embed(title="📈 수익 현황", color=0x00FF88)
            embed.add_field(name="오늘 PnL", value=f"{today_pnl:+.2f} {currency}", inline=True)
            embed.add_field(name="오늘 거래 수", value=str(today_count), inline=True)

            # 최근 거래
            recent = TradeRepository.get_trades(limit=5)
            if recent:
                lines = []
                for t in recent:
                    pnl_val = float(t.get("pnl", 0) or 0)
                    emoji = "✅" if pnl_val >= 0 else "❌"
                    lines.append(f"{emoji} {t.get('side','?').upper()} {pnl_val:+.2f} {currency}")
                embed.add_field(name="최근 거래", value="\n".join(lines), inline=False)

            await interaction.followup.send(embed=embed)
        except Exception as e:
            await interaction.followup.send(f"❌ 오류: {e}")

    # ━━━ /settings ━━━
    @tree.command(name="settings", description="현재 설정값 조회")
    async def cmd_settings(interaction: discord.Interaction):
        try:
            from src.config.constants import (
                RISK_PER_TRADE, DAILY_MAX_LOSS, DEFAULT_LEVERAGE,
                MAX_DAILY_TRADES, MAX_STOP_LOSS_PERCENT, TRAILING_STOP_PERCENT,
            )
            from src.config.trading_mode import get_trading_mode

            embed = discord.Embed(title="⚙️ 트레이딩 설정", color=0x808080)
            embed.add_field(name="1회 리스크", value=f"{RISK_PER_TRADE*100:.0f}%", inline=True)
            embed.add_field(name="일일 최대 손실", value=f"{DAILY_MAX_LOSS*100:.0f}%", inline=True)
            embed.add_field(name="기본 레버리지", value=f"{DEFAULT_LEVERAGE}x", inline=True)
            embed.add_field(name="일일 최대 거래", value=f"{MAX_DAILY_TRADES}회", inline=True)
            embed.add_field(name="최대 손절률", value=f"{MAX_STOP_LOSS_PERCENT}%", inline=True)
            embed.add_field(name="트레일링 스탑", value=f"{TRAILING_STOP_PERCENT}%", inline=True)
            embed.add_field(name="거래 모드", value=get_trading_mode().upper(), inline=True)

            await interaction.response.send_message(embed=embed)
        except Exception as e:
            await interaction.response.send_message(f"❌ 오류: {e}")

    # ━━━ /stop (Admin) ━━━
    @tree.command(name="stop", description="[Admin] 긴급 중단 — 포지션 청산 + 거래 중단")
    async def cmd_stop(interaction: discord.Interaction):
        if not _is_admin(interaction):
            await interaction.response.send_message("❌ 관리자 권한이 필요합니다.", ephemeral=True)
            return
        await interaction.response.defer()
        try:
            from src.database.repository import BotStatusRepository
            from src.database.models import BotState
            from src.exchange.bitget_client import BitgetClient

            # 모든 포지션 청산
            client = BitgetClient()
            positions = await client.get_positions()
            closed = 0
            for pos in positions:
                await client.close_position(pos.get("symbol", client.symbol))
                closed += 1
            await client.close()

            # 봇 상태 → STOPPED
            BotStatusRepository.update_status(status=BotState.STOPPED)

            embed = discord.Embed(
                title="🛑 긴급 중단 완료",
                description=f"청산 포지션: {closed}개\n봇 상태: STOPPED",
                color=0xFF0000,
            )
            await interaction.followup.send(embed=embed)
        except Exception as e:
            await interaction.followup.send(f"❌ 오류: {e}")

    # ━━━ /close (Admin) ━━━
    @tree.command(name="close", description="[Admin] 현재 포지션 즉시 청산")
    async def cmd_close(interaction: discord.Interaction):
        if not _is_admin(interaction):
            await interaction.response.send_message("❌ 관리자 권한이 필요합니다.", ephemeral=True)
            return
        await interaction.response.defer()
        try:
            from src.exchange.bitget_client import BitgetClient

            client = BitgetClient()
            positions = await client.get_positions()
            if not positions:
                await interaction.followup.send("ℹ️ 열린 포지션이 없습니다.")
                await client.close()
                return

            for pos in positions:
                await client.close_position(pos.get("symbol", client.symbol))
            await client.close()

            await interaction.followup.send(f"✅ {len(positions)}개 포지션 청산 완료")
        except Exception as e:
            await interaction.followup.send(f"❌ 오류: {e}")

    # ━━━ /pause (Admin) ━━━
    @tree.command(name="pause", description="[Admin] 신규 거래 중단 (포지션 유지)")
    async def cmd_pause(interaction: discord.Interaction):
        if not _is_admin(interaction):
            await interaction.response.send_message("❌ 관리자 권한이 필요합니다.", ephemeral=True)
            return
        try:
            from src.database.repository import BotStatusRepository
            from src.database.models import BotState

            BotStatusRepository.update_status(status=BotState.PAUSED)
            await interaction.response.send_message("⏸️ 봇 일시정지 — 신규 거래 중단, 기존 포지션 유지")
        except Exception as e:
            await interaction.response.send_message(f"❌ 오류: {e}")

    # ━━━ /resume (Admin) ━━━
    @tree.command(name="resume", description="[Admin] 거래 재개")
    async def cmd_resume(interaction: discord.Interaction):
        if not _is_admin(interaction):
            await interaction.response.send_message("❌ 관리자 권한이 필요합니다.", ephemeral=True)
            return
        try:
            from src.database.repository import BotStatusRepository
            from src.database.models import BotState

            BotStatusRepository.update_status(status=BotState.RUNNING)
            await interaction.response.send_message("▶️ 봇 거래 재개")
        except Exception as e:
            await interaction.response.send_message(f"❌ 오류: {e}")

    # ━━━ /mode (Admin) ━━━
    @tree.command(name="mode", description="[Admin] 거래 모드 조회/전환 (demo/live)")
    @app_commands.describe(new_mode="전환할 모드 (demo 또는 live). 생략 시 현재 모드 조회")
    async def cmd_mode(interaction: discord.Interaction, new_mode: str = None):
        if not _is_admin(interaction):
            await interaction.response.send_message("❌ 관리자 권한이 필요합니다.", ephemeral=True)
            return

        await interaction.response.defer()
        try:
            from src.config.trading_mode import (
                get_trading_mode, set_trading_mode, is_demo_mode
            )
            from src.config.constants import CCXT_SYMBOL, DEMO_CCXT_SYMBOL

            if new_mode is None:
                # 현재 모드 조회
                mode = get_trading_mode().upper()
                is_demo = is_demo_mode()
                symbol = DEMO_CCXT_SYMBOL if is_demo else CCXT_SYMBOL

                if is_demo:
                    mode_desc = "🧪 데모 트레이딩 (가상 자금)"
                else:
                    mode_desc = "🔴 라이브 (실거래)"

                embed = discord.Embed(
                    title="🔀 거래 모드",
                    color=0x00FF88 if is_demo else 0xFF4444,
                )
                embed.add_field(name="현재 모드", value=mode, inline=True)
                embed.add_field(name="유형", value=mode_desc, inline=True)
                embed.add_field(name="심볼", value=symbol, inline=True)
                embed.set_footer(text="모드 전환: /mode demo 또는 /mode live")
                await interaction.followup.send(embed=embed)
            else:
                # 모드 전환
                new_mode = new_mode.lower()
                if new_mode not in ["demo", "live"]:
                    await interaction.followup.send("❌ 유효하지 않은 모드입니다. `demo` 또는 `live`를 입력하세요.")
                    return

                # DB 업데이트 + 캐시 갱신
                success = set_trading_mode(new_mode)
                if not success:
                    await interaction.followup.send("❌ 모드 전환 실패")
                    return

                # BitgetClient 재연결
                from src.exchange.bitget_client import get_bitget_client
                client = get_bitget_client()
                await client.reconnect()

                if new_mode == "demo":
                    msg = "🧪 **데모 트레이딩 모드**로 전환되었습니다.\n심볼: `SBTC/SUSDT:SUSDT`\n가상 자금으로 거래됩니다."
                else:
                    msg = "🔴 **라이브 모드**로 전환되었습니다.\n⚠️ 실제 자금으로 거래됩니다!"

                await interaction.followup.send(msg)
                logger.info(f"거래 모드 변경: {new_mode.upper()}")

        except Exception as e:
            await interaction.followup.send(f"❌ 오류: {e}")


async def run_discord_bot():
    """Discord 봇 실행 (별도 태스크)"""
    settings = get_settings()
    token = settings.discord_bot_token
    if not token:
        logger.warning("DISCORD_BOT_TOKEN 미설정 — Discord 봇 비활성화")
        return

    try:
        logger.info("🔌 Discord 봇 초기화 중...")
        bot = TradingDiscordBot()
        logger.info("🔌 Discord 봇 연결 시도...")
        await bot.start(token)
    except discord.LoginFailure:
        logger.error("❌ Discord 로그인 실패 — 토큰을 확인하세요")
    except Exception as e:
        logger.error(f"❌ Discord 봇 오류: {e}", exc_info=True)
