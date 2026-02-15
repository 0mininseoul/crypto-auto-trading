# Discord Bot 생성 가이드

## 개요

자동매매 에이전트 제어용 Discord Bot을 생성합니다.

**Bot 기능:**
- `/status` - 현재 포지션, 잔고, PnL 조회
- `/stop` - 긴급 중단 (모든 포지션 청산 + 거래 중단)
- `/pause` - 일시 정지 (신규 거래만 중단)
- `/resume` - 거래 재개
- `/close` - 현재 포지션 청산
- `/settings` - 현재 설정 조회
- `/pnl` - 수익 현황

---

## Step 1: Discord Developer Portal 접속

1. https://discord.com/developers/applications 접속
2. Discord 계정으로 로그인

---

## Step 2: 새 Application 생성

1. 우측 상단 **"New Application"** 클릭

2. **이름 입력**
   - 예: `BTC Trading Bot`
   - 또는 원하는 이름

3. **"Create"** 클릭

---

## Step 3: Bot 설정

### 3.1 Bot 탭으로 이동

좌측 메뉴에서 **"Bot"** 클릭

### 3.2 Bot 생성

**"Add Bot"** 버튼 클릭 → **"Yes, do it!"** 확인

### 3.3 Bot Token 발급

1. **"Reset Token"** 클릭
2. 2FA 인증 (설정된 경우)
3. **Token 복사** (반드시 안전한 곳에 저장!)

```
⚠️ 중요: Token은 이 화면에서만 볼 수 있습니다!
창을 닫으면 다시 Reset 해야 합니다.
```

### 3.4 Privileged Gateway Intents 설정

아래 항목들을 **활성화 (ON)**:

| 항목 | 설정 | 용도 |
|------|------|------|
| **PRESENCE INTENT** | OFF | 불필요 |
| **SERVER MEMBERS INTENT** | OFF | 불필요 |
| **MESSAGE CONTENT INTENT** | ON | 메시지 내용 읽기 |

> Slash Command만 사용할 경우 MESSAGE CONTENT INTENT는 OFF로 해도 됩니다.

### 3.5 Bot 설정 옵션

| 항목 | 설정 | 설명 |
|------|------|------|
| **PUBLIC BOT** | OFF | 다른 사람이 봇을 초대하지 못하게 |
| **REQUIRES OAUTH2 CODE GRANT** | OFF | 기본값 유지 |

**"Save Changes"** 클릭

---

## Step 4: OAuth2 권한 설정

### 4.1 OAuth2 탭으로 이동

좌측 메뉴 **"OAuth2"** → **"URL Generator"**

### 4.2 Scopes 선택

다음 항목 체크:

- [x] `bot`
- [x] `applications.commands`

### 4.3 Bot Permissions 선택

**최소 권한 원칙**에 따라 필요한 것만 선택:

#### General Permissions
| 권한 | 선택 | 용도 |
|------|------|------|
| Read Messages/View Channels | ✅ | 채널 접근 |

#### Text Permissions
| 권한 | 선택 | 용도 |
|------|------|------|
| Send Messages | ✅ | 메시지 전송 |
| Send Messages in Threads | ⬜ | 불필요 |
| Create Public Threads | ⬜ | 불필요 |
| Create Private Threads | ⬜ | 불필요 |
| Embed Links | ✅ | 임베드 메시지 |
| Attach Files | ⬜ | 불필요 |
| Read Message History | ✅ | 메시지 기록 읽기 |
| Mention Everyone | ⬜ | 불필요 (보안상 비활성화) |
| Use External Emojis | ⬜ | 불필요 |
| Add Reactions | ✅ | 반응 추가 |
| Use Slash Commands | ✅ | 슬래시 명령어 |

#### 권장 Permission Integer

위 설정 시 자동 생성되는 값: `2147559488`

또는 간단하게: `274878024704`

### 4.4 초대 URL 복사

하단에 생성된 **Generated URL** 복사

예시:
```
https://discord.com/api/oauth2/authorize?client_id=YOUR_CLIENT_ID&permissions=274878024704&scope=bot%20applications.commands
```

---

## Step 5: 서버에 Bot 초대

### 5.1 전용 서버 생성 (권장)

보안을 위해 트레이딩 봇 전용 서버를 만드는 것을 권장합니다.

1. Discord 앱 열기
2. 좌측 하단 **"+"** 버튼 클릭
3. **"Create My Own"** 선택
4. **"For me and my friends"** 선택
5. 서버 이름 입력 (예: `Trading Bot`)
6. **"Create"** 클릭

### 5.2 Bot 초대

1. Step 4에서 복사한 URL을 브라우저에 붙여넣기
2. **서버 선택** 드롭다운에서 방금 만든 서버 선택
3. **"Continue"** 클릭
4. 권한 확인 후 **"Authorize"** 클릭
5. Captcha 완료

### 5.3 Bot 초대 확인

서버의 멤버 목록에서 Bot이 **오프라인** 상태로 표시되면 성공!
(코드 실행 전까지는 오프라인 상태입니다)

---

## Step 6: 채널 설정 (선택사항)

### 6.1 전용 채널 생성

1. 서버에서 **"+"** 버튼으로 새 채널 생성
2. 채널 이름: `trading-alerts` 또는 `bot-control`
3. 텍스트 채널 선택
4. **"Create Channel"** 클릭

### 6.2 채널 권한 설정

봇 전용 채널로 만들려면:

1. 채널 설정 (톱니바퀴 아이콘) 클릭
2. **"Permissions"** 탭
3. **"@everyone"** 역할의 권한을 제한
4. Bot 역할에만 메시지 전송 권한 부여

---

## Step 7: 필요한 ID 수집

### 7.1 개발자 모드 활성화

1. Discord 설정 (톱니바퀴)
2. **"App Settings"** → **"Advanced"**
3. **"Developer Mode"** 활성화

### 7.2 ID 복사 방법

우클릭 → **"Copy ID"**

### 7.3 필요한 ID 목록

| 항목 | 복사 방법 | 용도 |
|------|----------|------|
| **Server ID (Guild ID)** | 서버 이름 우클릭 → Copy ID | 봇이 작동할 서버 지정 |
| **Channel ID** | 채널 이름 우클릭 → Copy ID | 알림 전송 채널 |
| **Your User ID** | 자신의 프로필 우클릭 → Copy ID | 관리자 권한 확인 |

---

## Step 8: 환경 변수 설정

`.env` 파일에 추가:

```bash
# Discord Bot 설정
DISCORD_BOT_TOKEN=여기에_Bot_Token_입력
DISCORD_GUILD_ID=여기에_Server_ID_입력
DISCORD_CHANNEL_ID=여기에_Channel_ID_입력
DISCORD_ADMIN_ID=여기에_Your_User_ID_입력
```

---

## Step 9: Bot 연결 테스트

간단한 테스트 코드:

```python
import discord
from discord.ext import commands
from dotenv import load_dotenv
import os

load_dotenv()

# Bot 설정
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'{bot.user} 연결 성공!')
    print(f'서버 수: {len(bot.guilds)}')

    # Slash Command 동기화
    await bot.tree.sync()
    print('Slash Commands 동기화 완료')

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

# Bot 실행
bot.run(os.getenv('DISCORD_BOT_TOKEN'))
```

실행:
```bash
pip install discord.py python-dotenv
python test_bot.py
```

Discord에서 `/ping` 또는 `/status` 명령어 테스트

---

## 보안 체크리스트

- [ ] Bot Token을 코드에 직접 입력하지 않음
- [ ] `.env` 파일이 `.gitignore`에 포함됨
- [ ] PUBLIC BOT 설정이 OFF
- [ ] 전용 서버 사용 (다른 사람 접근 제한)
- [ ] 관리자 ID로 명령어 권한 제한 (구현 시)

---

## 문제 해결

### "Invalid Token" 오류
- Token 복사 시 앞뒤 공백 확인
- Token을 Reset하고 다시 복사

### "Missing Access" 오류
- Bot이 서버에 초대되어 있는지 확인
- 채널 권한 확인

### "Slash Commands가 안 보임"
- `bot.tree.sync()` 호출 확인
- 최대 1시간까지 동기화 시간 소요 가능
- 특정 서버에만 동기화: `await bot.tree.sync(guild=discord.Object(id=GUILD_ID))`

### Bot이 오프라인
- 코드가 실행 중인지 확인
- Token이 올바른지 확인
- 인터넷 연결 확인

---

## 수집해야 할 정보 요약

| 항목 | 값 | 수집 완료 |
|------|-----|----------|
| Bot Token | `MTIxxxxx...` | [ ] |
| Server ID | `123456789...` | [ ] |
| Channel ID | `987654321...` | [ ] |
| Admin User ID | `111222333...` | [ ] |

위 정보를 `.env` 파일에 저장하세요!

---

*작성일: 2024*
