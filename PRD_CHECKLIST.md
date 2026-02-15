# PRD 작성 사전 체크리스트

## 완료된 항목

- [x] 트레이딩 지식 베이스 구축 (TRADING_KNOWLEDGE_BASE.md)
- [x] 트레이딩 핵심 전략 설계 (TRADING_STRATEGY.md - Section 1)
- [x] 리스크 및 자금 관리 계획 (TRADING_STRATEGY.md - Section 2~4)
- [x] Bitget API 발급 가이드 (BITGET_API_GUIDE.md)

---

## PRD 검토 및 개선 (2024.05)
- [x] 해외 사례 및 오픈소스 봇(Freqtrade, Hummingbot) 분석
- [x] 아키텍처/호스팅 타당성 검토 (Render Free Tier 제한 등)
- [x] 리스크 관리 전략 고도화 (ATR, Chandelier Exit)
- [x] **PRD 업데이트 완료** (WebSocket 도입, Single Service 아키텍처)
- [x] Render Free Tier 유지를 위한 Uptime Monitoring 설정 준비

---

## 개발 체크리스트 (Updated)

### Phase 1.5: Real-time Infrastructure (New)
- [x] Bitget WebSocket Client 구현 (`aiohttp` 사용)
- [x] Connection Manager (Auto-reconnect) 구현
- [x] Unified Service (FastAPI + Asyncio Task) 구조 설계


---

## 확정된 사항

### 1. 설정 관리 인터페이스 ✅

**선택: 웹 UI + Discord Bot 조합**

```
[구성]
1. 설정 저장: Supabase (PostgreSQL)
2. 설정 수정: 웹 UI (FastAPI + React/HTML)
3. 긴급 제어: Discord Bot (중지/재시작/상태 확인)
4. 호스팅: Render (봇 + 웹) + Supabase (DB)
```

### 2. 모바일 긴급 제어 시스템 ✅

**선택: Discord Bot**

| 명령어 | 기능 | 설명 |
|--------|------|------|
| `/status` | 상태 확인 | 현재 포지션, 잔고, PnL 조회 |
| `/stop` | 긴급 중단 | 모든 포지션 청산 + 신규 거래 중단 |
| `/pause` | 일시 정지 | 신규 거래만 중단 (기존 포지션 유지) |
| `/resume` | 재개 | 일시 정지 해제 |
| `/close` | 포지션 청산 | 현재 포지션 즉시 청산 |
| `/settings` | 설정 조회 | 현재 전략 설정 요약 |
| `/pnl` | 수익 현황 | 일간/주간/월간 PnL |

### 3. 호스팅 환경 ✅

**선택: Render + Supabase 조합**

| 서비스 | 용도 | 비용 |
|--------|------|------|
| **Render** | 자동매매 봇 (Background Worker) | 무료 티어 |
| **Render** | 웹 UI (Web Service) | 무료 티어 |
| **Supabase** | PostgreSQL 데이터베이스 | 무료 티어 (500MB) |

**예상 비용: 무료 (무료 티어 범위 내)**

### 4. 자본금 설정 ✅

| 항목 | 설정값 |
|------|--------|
| **초기 자본금 (파일럿)** | 20,000원 (~$15) |
| **최대 자본금** | 500,000원 미만 (~$380) |
| **테스트 방식** | 데모 트레이딩(테스트넷) 먼저 진행 |

**리스크 파라미터 조정 (소액 운용):**

| 항목 | 기존 설정 | 소액 조정 |
|------|----------|----------|
| 1회 최대 리스크 | 2% | 5% (400원) |
| 최소 주문 금액 | - | Bitget 최소 주문 확인 필요 |
| 레버리지 | 5x | 10x (소액이므로 조정) |

> **참고**: Bitget BTC 선물 최소 주문: 약 5 USDT. 2만원(~15 USDT)으로 운용 가능하나 포지션 사이징에 제약이 있을 수 있음.

### 5. 기술 스택 ✅

| 영역 | 기술 | 비고 |
|------|------|------|
| **언어** | Python 3.11+ | - |
| **거래소 연동** | ccxt | Bitget 지원 |
| **기술적 분석** | pandas-ta | ta-lib 대신 (설치 용이) |
| **웹 프레임워크** | FastAPI | 비동기 지원 |
| **프론트엔드** | HTML + Tailwind CSS | 간단한 UI |
| **알림/제어** | discord.py | Discord Bot |
| **데이터베이스** | Supabase (PostgreSQL) | 클라우드 DB |
| **스케줄링** | APScheduler | Python 스케줄러 |
| **호스팅** | Render | 무료 티어 |

---

## 추가 확인 필요 사항

### API 키 발급

- [x] Bitget 2FA 설정 완료
- [x] API Key 발급 (가이드: BITGET_API_GUIDE.md 참조)
- [x] 데모 트레이딩 API 발급 (테스트용)

### Discord Bot 설정

- [x] Discord 서버 생성/선택
- [x] Discord Developer Portal에서 Bot 생성
- [x] Bot Token 발급
- [x] 서버에 Bot 초대

### 거래 자산

- [x] **BTC만 거래** (초기 단계)
- [ ] 추후 ETH, 알트코인 추가 검토

### 운영 시간

- [x] **24시간 무중단 운영** (Render Background Worker)

---

## 비트겟 API 참고 자료

### 공식 문서

- **Bitget API V2 문서**: https://www.bitget.com/api-doc/
- **Futures API**: https://www.bitget.com/api-doc/contract/intro
- **ccxt Bitget 문서**: https://docs.ccxt.com/en/latest/exchanges/bitget.html

### 주요 API 엔드포인트 (V2)

| 기능 | 엔드포인트 | 용도 |
|------|-----------|------|
| 계정 정보 | `/api/v2/mix/account/account` | 잔고 조회 |
| 포지션 조회 | `/api/v2/mix/position/single-position` | 현재 포지션 |
| 주문 생성 | `/api/v2/mix/order/place-order` | 신규 주문 |
| 주문 취소 | `/api/v2/mix/order/cancel-order` | 주문 취소 |
| 시세 조회 | `/api/v2/mix/market/ticker` | 현재가 조회 |
| 캔들 조회 | `/api/v2/mix/market/candles` | OHLCV 데이터 |

---

## 다음 단계

1. **사전 준비** (사용자) ✅ 완료
   - [x] Bitget API Key 발급
   - [x] Discord Bot 생성
   - [x] Supabase 계정 생성
   - [x] Render 계정 생성

2. **PRD 최종 작성** (Claude Code) ✅ 완료
   - [x] 확정된 내용으로 PRD 작성
   - [x] 프로젝트 구조 설계
   - [x] 개발 시작

3. **배포 완료**
   - [x] Render 배포 (https://crypto-auto-trading.onrender.com)
   - [x] 환경변수 설정
   - [ ] 데모 트레이딩 테스트 (2주간)

---

*최종 업데이트: 2024*
