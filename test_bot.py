import os

import discord
from discord.ext import commands
from dotenv import load_dotenv


def build_bot() -> commands.Bot:
    """로컬 Discord 연결 테스트용 봇 인스턴스 생성."""
    intents = discord.Intents.default()
    intents.message_content = True
    bot = commands.Bot(command_prefix='!', intents=intents)

    @bot.event
    async def on_ready():
        print(f'{bot.user} 연결 성공!')
        print(f'서버 수: {len(bot.guilds)}')

        try:
            guild_id = os.getenv('DISCORD_GUILD_ID')
            if guild_id:
                guild = discord.Object(id=int(guild_id))
                bot.tree.copy_global_to(guild=guild)
                await bot.tree.sync(guild=guild)
                print(f'TARGET GUILD({guild_id})에 Slash Commands 동기화 완료 (즉시 적용)')
            else:
                await bot.tree.sync()
                print('Global Slash Commands 동기화 완료 (약 1시간 소요될 수 있음)')
        except Exception as e:
            print(f"동기화 중 오류 발생: {e}")

    @bot.tree.command(name="ping", description="봇 응답 테스트")
    async def ping(interaction: discord.Interaction):
        await interaction.response.send_message("Pong! 🏓")

    @bot.tree.command(name="status", description="봇 상태 확인")
    async def status(interaction: discord.Interaction):
        embed = discord.Embed(
            title="📊 Trading Bot Status",
            color=discord.Color.green()
        )
        embed.add_field(name="상태", value="✅ 정상 작동 중", inline=False)
        embed.add_field(name="모드", value="테스트", inline=True)
        await interaction.response.send_message(embed=embed)

    return bot


def main() -> None:
    load_dotenv()
    token = os.getenv('DISCORD_BOT_TOKEN')
    if not token or token.startswith("여기에"):
        print("❌ 오류: .env 파일에 DISCORD_BOT_TOKEN이 설정되지 않았습니다.")
        return
    build_bot().run(token)


if __name__ == "__main__":
    main()
