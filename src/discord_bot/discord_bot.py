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
            from src.database.repository import BotStatusRepository
            from src.exchange.bitget_client import BitgetClient

            status = BotStatusRepository.get_status()

            client = BitgetClient()
            balance = await client.get_balance()
            ticker = await client.get_ticker()
            positions = await client.get_positions()
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
                value=f"{balance.get('total', 0):.2f} USDT" if balance else "–",
                inline=True,
            )
            embed.add_field(name="하트비트", value=heartbeat_display, inline=True)

            # 포지션 상세 정보
            if positions:
                pos_lines = []
                for pos in positions:
                    side = pos.get("side", "?").upper()
                    size = pos.get("size", 0)
                    entry = pos.get("entry_price", 0)
                    pnl = pos.get("unrealized_pnl", 0)
                    leverage = pos.get("leverage", 1)
                    emoji = "🟢" if side == "LONG" else "🔴"
                    pos_lines.append(
                        f"{emoji} {side} {size:.4f} BTC @ ${entry:,.2f} ({leverage}x)\n"
                        f"   미실현 PnL: ${pnl:+,.2f}"
                    )
                embed.add_field(
                    name="📍 현재 포지션",
                    value="\n".join(pos_lines),
                    inline=False,
                )

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
                RISK_LOW_CONFIDENCE, RISK_MEDIUM_CONFIDENCE, RISK_HIGH_CONFIDENCE,
                CONFIDENCE_LOW_THRESHOLD, CONFIDENCE_HIGH_THRESHOLD,
                DAILY_MAX_LOSS, DEFAULT_LEVERAGE,
                MAX_DAILY_TRADES, MAX_STOP_LOSS_PERCENT, TRAILING_STOP_PERCENT,
            )
            from src.config.trading_mode import get_trading_mode

            embed = discord.Embed(title="⚙️ 트레이딩 설정", color=0x808080)

            # 신뢰도 기반 동적 리스크 표시
            risk_info = (
                f"📊 동적 리스크\n"
                f"• 낮음 (<{CONFIDENCE_LOW_THRESHOLD:.0%}): {RISK_LOW_CONFIDENCE*100:.0f}%\n"
                f"• 중간: {RISK_MEDIUM_CONFIDENCE*100:.0f}%\n"
                f"• 높음 (>{CONFIDENCE_HIGH_THRESHOLD:.0%}): {RISK_HIGH_CONFIDENCE*100:.0f}%"
            )
            embed.add_field(name="리스크 설정", value=risk_info, inline=False)

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
                side = pos.get("side", "long")
                size = pos.get("size", 0)
                await client.close_position(side=side, amount=size)
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

            closed_info = []
            for pos in positions:
                side = pos.get("side", "long")
                size = pos.get("size", 0)
                entry_price = pos.get("entry_price", 0)

                result = await client.close_position(side=side, amount=size)
                exit_price = result.get("price", 0)

                # PnL 계산
                if side == "long":
                    pnl = (exit_price - entry_price) * size
                else:
                    pnl = (entry_price - exit_price) * size

                closed_info.append(f"{side.upper()} {size:.4f} BTC | PnL: ${pnl:+,.2f}")

            await client.close()

            result_msg = "\n".join(closed_info)
            await interaction.followup.send(f"✅ {len(positions)}개 포지션 청산 완료\n```\n{result_msg}\n```")
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

    # ━━━ /analysis ━━━
    @tree.command(name="analysis", description="AI 차트 분석 (현재 시장 상황 + 전략 제안)")
    async def cmd_analysis(interaction: discord.Interaction):
        await interaction.response.defer()
        try:
            from src.ai.chart_analyzer import get_chart_analyzer
            from src.exchange.bitget_client import BitgetClient

            analyzer = get_chart_analyzer()
            if not analyzer or not analyzer.is_available:
                await interaction.followup.send(
                    "❌ AI 분석을 사용할 수 없습니다.\n"
                    "`.env` 파일에 `GEMINI_API_KEY`를 설정하세요."
                )
                return

            # 현재 포지션 조회
            client = BitgetClient()
            positions = await client.get_positions()
            await client.close()

            position = None
            if positions:
                pos = positions[0]
                ticker_price = analyzer._data.current_price
                entry_price = pos.get("entry_price", 0)
                side = pos.get("side", "long")

                # 미실현 PnL 계산
                size = pos.get("size", 0)
                if side == "long":
                    unrealized_pnl = (ticker_price - entry_price) * size
                else:
                    unrealized_pnl = (entry_price - ticker_price) * size
                pnl_pct = (unrealized_pnl / (entry_price * size) * 100) if entry_price > 0 and size > 0 else 0

                position = {
                    "side": side,
                    "entry_price": entry_price,
                    "current_price": ticker_price,
                    "quantity": size,
                    "unrealized_pnl": unrealized_pnl,
                    "pnl_percent": pnl_pct,
                    "stop_loss": pos.get("stop_loss", 0),
                    "take_profit": pos.get("take_profit", 0),
                }

            # AI 분석 실행
            logger.info(
                "/analysis 요청 수신 | user_id=%s | has_position=%s",
                interaction.user.id if interaction.user else "unknown",
                position is not None,
            )
            analysis_result = await analyzer.analyze(
                position=position,
                analysis_type="general",
                force_refresh=True,
            )

            # Discord Embed 생성
            color = 0x00BFFF  # 기본 파란색
            if position:
                color = 0x00FF88 if position["unrealized_pnl"] >= 0 else 0xFF4444

            # 결과가 길면 자르기
            if len(analysis_result) > 4000:
                analysis_result = analysis_result[:3997] + "..."

            embed = discord.Embed(
                title="📊 AI 차트 분석",
                description=analysis_result,
                color=color,
                timestamp=kst_now(),
            )
            embed.set_footer(text="Powered by Gemini 3 Flash Preview")

            await interaction.followup.send(embed=embed)
            logger.info(
                "/analysis 응답 전송 | chars=%d | user_id=%s",
                len(analysis_result),
                interaction.user.id if interaction.user else "unknown",
            )

        except Exception as e:
            logger.error(f"/analysis 오류: {e}", exc_info=True)
            await interaction.followup.send(f"❌ 분석 중 오류 발생: {str(e)[:200]}")

    # ━━━ /learning ━━━
    @tree.command(name="learning", description="AI 학습 현황 조회")
    async def cmd_learning(interaction: discord.Interaction):
        try:
            from src.ai.chart_analyzer import get_chart_analyzer

            analyzer = get_chart_analyzer()
            if not analyzer:
                await interaction.response.send_message(
                    "❌ AI 분석기가 초기화되지 않았습니다."
                )
                return

            stats = analyzer.get_learning_stats()

            embed = discord.Embed(
                title="🧠 AI 학습 현황",
                color=0x9B59B6,
                timestamp=kst_now(),
            )
            embed.add_field(
                name="복기한 거래",
                value=f"{stats['total_reviews']}건",
                inline=True,
            )
            embed.add_field(
                name="승리",
                value=f"{stats['wins']}건 ({stats['win_rate']:.0%})",
                inline=True,
            )
            embed.add_field(
                name="축적된 인사이트",
                value=f"{stats['insights_count']}개",
                inline=True,
            )
            embed.add_field(
                name="학습된 패턴",
                value=f"{stats['patterns_count']}개",
                inline=True,
            )
            if stats['last_updated']:
                embed.add_field(
                    name="마지막 업데이트",
                    value=stats['last_updated'][:19].replace("T", " "),
                    inline=True,
                )

            embed.set_footer(text="거래 복기를 통해 AI가 지속적으로 학습합니다")

            await interaction.response.send_message(embed=embed)

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
