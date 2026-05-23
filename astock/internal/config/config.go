package config

import (
    "os"
    "strconv"
)

type Config struct {
    DBHost         string
    DBPort         int
    DBName         string
    DBUser         string
    DBPassword     string
    RetentionDays  int
    LogLevel       string
}

func Load() *Config {
    return &Config{
        DBHost:        getEnv("ASTOCK_DB_HOST", "localhost"),
        DBPort:        getEnvInt("ASTOCK_DB_PORT", 5432),
        DBName:        getEnv("ASTOCK_DB_NAME", "astock"),
        DBUser:        getEnv("ASTOCK_DB_USER", "postgres"),
        DBPassword:    getEnv("ASTOCK_DB_PASS", "postgres"),
        RetentionDays: getEnvInt("ASTOCK_RETENTION_DAYS", 30),
        LogLevel:      getEnv("ASTOCK_LOG_LEVEL", "info"),
    }
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
