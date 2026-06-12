package config

import (
	"fmt"
	"os"
	"strconv"
	"time"
)

// Config 持有 astock 全部运行配置。
// 来源：环境变量（含 .env，由 godotenv 在 main 中加载）。
type Config struct {
	// ClickHouse 连接
	CHHost     string
	CHPort     int
	CHDatabase string
	CHUser     string
	CHPassword string

	// TDX 配置
	TDXDialTimeout   time.Duration
	TDXMaxConcurrent int

	// 日志
	LogLevel string
}

// Load 从环境变量加载配置，缺失项使用合理默认值。
func Load() *Config {
	return &Config{
		CHHost:     getEnv("CH_HOST", "localhost"),
		CHPort:     getEnvInt("CH_PORT", 9000),
		CHDatabase: getEnv("CH_DATABASE", "astock"),
		CHUser:     getEnv("CH_USER", "default"),
		CHPassword: getEnv("CH_PASSWORD", ""),

		TDXDialTimeout:   time.Duration(getEnvInt("TDX_DIAL_TIMEOUT", 5)) * time.Second,
		TDXMaxConcurrent: getEnvInt("TDX_MAX_CONCURRENT", 10),

		LogLevel: getEnv("LOG_LEVEL", "info"),
	}
}

// CHAddr 返回 host:port 形式的 ClickHouse 地址。
func (c *Config) CHAddr() string {
	return fmt.Sprintf("%s:%d", c.CHHost, c.CHPort)
}

func getEnv(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

func getEnvInt(key string, fallback int) int {
	if v := os.Getenv(key); v != "" {
		if i, err := strconv.Atoi(v); err == nil {
			return i
		}
	}
	return fallback
}
