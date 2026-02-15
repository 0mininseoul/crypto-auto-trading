"""
Supabase 데이터베이스 초기화 스크립트
테이블 생성 및 초기 데이터 삽입
"""
import os
import sys

# 프로젝트 루트를 path에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from supabase import create_client
from dotenv import load_dotenv

load_dotenv()


def setup_database():
    """Supabase에 테이블 생성 (RPC 또는 직접 SQL)"""
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")

    if not url or not key or "여기에" in url:
        print("❌ SUPABASE_URL과 SUPABASE_KEY를 .env에 설정해주세요.")
        return False

    client = create_client(url, key)

    # 테이블 존재 여부 확인 (bot_status 테이블로 체크)
    try:
        result = client.table("bot_status").select("id").limit(1).execute()
        print("✅ 테이블이 이미 존재합니다.")

        # 초기 봇 상태가 없으면 추가
        if len(result.data) == 0:
            client.table("bot_status").insert({
                "status": "stopped",
                "trading_mode": "demo",
            }).execute()
            print("✅ 초기 봇 상태 데이터 삽입 완료")

        return True
    except Exception as e:
        error_msg = str(e)
        if "relation" in error_msg and "does not exist" in error_msg:
            print("⚠️  테이블이 아직 생성되지 않았습니다.")
            print()
            print("Supabase Dashboard에서 아래 SQL을 실행해주세요:")
            print("  1. https://supabase.com/dashboard 접속")
            print("  2. 프로젝트 선택 → SQL Editor")
            print("  3. 아래 SQL을 복사하여 실행")
            print()
            print_create_sql()
            return False
        else:
            print(f"❌ 오류: {e}")
            return False


def print_create_sql():
    """테이블 생성 SQL 출력"""
    sql = """
-- =============================================
-- Bitcoin Autotrading Bot - Database Schema
-- =============================================

-- 설정 테이블
CREATE TABLE IF NOT EXISTS settings (
    id SERIAL PRIMARY KEY,
    key VARCHAR(100) UNIQUE NOT NULL,
    value JSONB NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 거래 기록 테이블
CREATE TABLE IF NOT EXISTS trades (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL,
    entry_price DECIMAL(20, 8) NOT NULL,
    exit_price DECIMAL(20, 8),
    quantity DECIMAL(20, 8) NOT NULL,
    leverage INT NOT NULL,
    stop_loss DECIMAL(20, 8),
    take_profit DECIMAL(20, 8),
    pnl DECIMAL(20, 8),
    pnl_percent DECIMAL(10, 4),
    status VARCHAR(20) NOT NULL DEFAULT 'open',
    entry_reason JSONB,
    exit_reason VARCHAR(100),
    entry_time TIMESTAMP WITH TIME ZONE NOT NULL,
    exit_time TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 일별 성과 테이블
CREATE TABLE IF NOT EXISTS daily_performance (
    id SERIAL PRIMARY KEY,
    date DATE UNIQUE NOT NULL,
    starting_balance DECIMAL(20, 8),
    ending_balance DECIMAL(20, 8),
    total_trades INT DEFAULT 0,
    winning_trades INT DEFAULT 0,
    losing_trades INT DEFAULT 0,
    total_pnl DECIMAL(20, 8),
    max_drawdown DECIMAL(10, 4),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 시스템 로그 테이블
CREATE TABLE IF NOT EXISTS system_logs (
    id SERIAL PRIMARY KEY,
    level VARCHAR(20) NOT NULL,
    message TEXT NOT NULL,
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 봇 상태 테이블
CREATE TABLE IF NOT EXISTS bot_status (
    id SERIAL PRIMARY KEY,
    status VARCHAR(20) NOT NULL DEFAULT 'stopped',
    trading_mode VARCHAR(10) NOT NULL DEFAULT 'demo',
    last_heartbeat TIMESTAMP WITH TIME ZONE,
    current_position JSONB,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 인덱스
CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status);
CREATE INDEX IF NOT EXISTS idx_trades_entry_time ON trades(entry_time);
CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);
CREATE INDEX IF NOT EXISTS idx_daily_performance_date ON daily_performance(date);
CREATE INDEX IF NOT EXISTS idx_system_logs_level ON system_logs(level);
CREATE INDEX IF NOT EXISTS idx_system_logs_created_at ON system_logs(created_at);

-- 초기 봇 상태
INSERT INTO bot_status (status, trading_mode) VALUES ('stopped', 'demo');
"""
    print(sql)


if __name__ == "__main__":
    setup_database()
