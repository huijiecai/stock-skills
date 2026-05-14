-- jstock 量化数据中心 DDL
-- Database: jstock

CREATE TABLE IF NOT EXISTS stock_info (
    code      VARCHAR(10) PRIMARY KEY,
    name      VARCHAR(50) NOT NULL,
    exchange  VARCHAR(4)  NOT NULL,            -- sh / sz / bj
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS concept_info (
    code        VARCHAR(10) PRIMARY KEY,        -- BK0612
    name        VARCHAR(50) NOT NULL,
    stock_count INTEGER DEFAULT 0,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS trade_cal (
    trade_date DATE PRIMARY KEY,
    is_trade   BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS daily_k (
    code         VARCHAR(10) NOT NULL,
    trade_date   DATE        NOT NULL,
    type         VARCHAR(10) NOT NULL DEFAULT 'stock',   -- stock / index / concept
    open         DOUBLE PRECISION,
    high         DOUBLE PRECISION,
    low          DOUBLE PRECISION,
    close        DOUBLE PRECISION,
    pre_close    DOUBLE PRECISION,
    change_pct   DOUBLE PRECISION,
    volume       BIGINT,
    amount       DOUBLE PRECISION,
    turnover     DOUBLE PRECISION,
    PRIMARY KEY (code, trade_date, type)
);
CREATE INDEX IF NOT EXISTS idx_daily_k_date    ON daily_k (trade_date);
CREATE INDEX IF NOT EXISTS idx_daily_k_type    ON daily_k (type);

CREATE TABLE IF NOT EXISTS minute_k (
    code       VARCHAR(10) NOT NULL,
    dt         TIMESTAMP   NOT NULL,
    freq       VARCHAR(5)  NOT NULL,                    -- 1m / 5m / 15m / 30m / 60m
    type       VARCHAR(10) NOT NULL DEFAULT 'stock',
    open       DOUBLE PRECISION,
    high       DOUBLE PRECISION,
    low        DOUBLE PRECISION,
    close      DOUBLE PRECISION,
    volume     BIGINT,
    amount     DOUBLE PRECISION,
    avg_price  DOUBLE PRECISION,
    PRIMARY KEY (code, dt, freq, type)
);
CREATE INDEX IF NOT EXISTS idx_minute_k_dt    ON minute_k (dt);
CREATE INDEX IF NOT EXISTS idx_minute_k_freq  ON minute_k (freq);
