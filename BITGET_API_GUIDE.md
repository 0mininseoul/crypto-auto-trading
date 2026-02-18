# Bitget API Key 발급 가이드

## 사전 준비

- [x] Bitget 계정 가입 완료
- [ ] 2단계 인증(2FA) 설정 (필수)
- [ ] 본인 인증(KYC) 완료 (선물 거래에 필요할 수 있음)

---

## Step 1: API 관리 페이지 접속

1. Bitget 웹사이트 로그인: https://www.bitget.com
2. 우측 상단 **프로필 아이콘** 클릭
3. **API 관리** 또는 **API Management** 클릭
4. 또는 직접 접속: https://www.bitget.com/account/newapi

---

## Step 2: 새 API Key 생성

1. **API 생성** 또는 **Create API** 버튼 클릭

2. **API 이름 설정**
   - 예: `autotrading-bot`
   - 용도를 알 수 있는 이름 권장

3. **비밀번호 설정**
   - Passphrase 입력 (API 호출 시 필요, 반드시 기억!)
   - 예: `MySecretPass123!`

4. **권한 설정** (중요!)

   | 권한 | 설정 | 설명 |
   |------|------|------|
   | **읽기 (Read)** | O 활성화 | 잔고, 포지션 조회 |
   | **거래 (Trade)** | O 활성화 | 주문 생성/취소 |
   | **출금 (Withdraw)** | X 비활성화 | 보안상 절대 활성화하지 않음! |

5. **거래 유형 선택**
   - **선물 (Futures/USDT-M)** 선택
   - 현물은 필요시 추가

6. **IP 화이트리스트** (선택사항, 권장)
   - 로컬 테스트 시: 비워두기
   - 클라우드 배포 시: Render 서버 IP 추가
   - 보안 강화를 위해 나중에 설정 권장

---

## Step 3: 인증 및 생성 완료

1. **이메일 인증 코드** 입력
2. **Google OTP 코드** 입력 (2FA 설정된 경우)
3. **확인** 클릭

---

## Step 4: API Key 정보 저장

생성 완료 후 다음 3가지 정보가 표시됩니다:

```
API Key:      xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
Secret Key:   yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy
Passphrase:   (생성 시 입력한 비밀번호)
```

### 중요 주의사항

1. **Secret Key는 이 화면에서만 볼 수 있습니다!**
   - 창을 닫으면 다시 확인 불가
   - 반드시 안전한 곳에 저장

2. **절대 하지 말 것**
   - 코드에 직접 입력 (하드코딩)
   - 카카오톡, 이메일로 전송
   - 스크린샷 후 클라우드 저장
   - GitHub에 업로드

3. **안전한 저장 방법**
   - 로컬 `.env` 파일에 저장
   - 비밀번호 관리 앱 (1Password, Bitwarden 등)
   - 암호화된 메모장

---

## Step 5: 환경 변수 설정

프로젝트 루트에 `.env` 파일 생성:

```bash
# .env 파일 (절대 Git에 커밋하지 않음!)

BITGET_API_KEY=여기에_API_Key_입력
BITGET_SECRET_KEY=여기에_Secret_Key_입력
BITGET_PASSPHRASE=여기에_Passphrase_입력

# 데모/실거래 모드 설정
TRADING_MODE=demo  # demo 또는 live
```

`.gitignore`에 추가:
```
.env
.env.local
.env.*.local
```

---

## Step 6: API 연결 테스트

Python으로 API 연결 테스트:

```python
import ccxt

# 환경 변수에서 로드 (dotenv 사용)
from dotenv import load_dotenv
import os

load_dotenv()

exchange = ccxt.bitget({
    'apiKey': os.getenv('BITGET_API_KEY'),
    'secret': os.getenv('BITGET_SECRET_KEY'),
    'password': os.getenv('BITGET_PASSPHRASE'),
    'options': {
        'defaultType': 'swap',  # 선물 거래
    }
})

# 잔고 조회 테스트
try:
    balance = exchange.fetch_balance()
    print("API 연결 성공!")
    print(f"USDT 잔고: {balance['USDT']['free']}")
except Exception as e:
    print(f"API 연결 실패: {e}")
```

---

## 데모 트레이딩 (테스트넷) 설정

Bitget 데모 트레이딩 사용 시:

1. Bitget 앱/웹에서 **데모 트레이딩** 활성화
2. API 생성 시 **데모 트레이딩 API** 선택
3. 또는 ccxt에서 샌드박스 모드 사용:

```python
exchange = ccxt.bitget({
    'apiKey': os.getenv('BITGET_API_KEY'),
    'secret': os.getenv('BITGET_SECRET_KEY'),
    'password': os.getenv('BITGET_PASSPHRASE'),
    'options': {
        'defaultType': 'swap',
    }
})

# 샌드박스(데모) 모드 활성화
exchange.set_sandbox_mode(True)
```

---

## API 권한 체크리스트

| 항목 | 상태 | 비고 |
|------|------|------|
| 읽기 권한 | [ ] | 필수 |
| 거래 권한 | [ ] | 필수 |
| 출금 권한 | [ ] | 반드시 비활성화! |
| 선물 거래 | [ ] | 필수 |
| IP 화이트리스트 | [ ] | 배포 시 설정 권장 |

---

## 문제 해결

### "Invalid API Key" 오류
- API Key 복사 시 앞뒤 공백 확인
- 대소문자 정확히 입력

### "Signature Error" 오류
- Secret Key 확인
- Passphrase 확인 (대소문자 구분)

### "IP not in whitelist" 오류
- IP 화이트리스트 설정 확인
- 테스트 시에는 화이트리스트 비활성화

### "Permission Denied" 오류
- 거래 권한 활성화 확인
- 선물 거래 권한 확인

---

## 다음 단계

1. [ ] 2FA 설정 완료
2. [ ] API Key 생성
3. [ ] `.env` 파일 생성 및 저장
4. [ ] API 연결 테스트
5. [ ] 데모 트레이딩으로 봇 테스트
6. [ ] 전략 검증 후 실거래 전환

---

*작성일: 2024*
