package query

import (
    "context"
    "log"
    "time"
)

const maxRetries = 3

func AsyncWrite(ctx context.Context, name string, fn func(context.Context) error) {
    go func() {
        for i := 0; i < maxRetries; i++ {
            if err := fn(ctx); err != nil {
                log.Printf("[cache] %s attempt %d failed: %v", name, i+1, err)
                time.Sleep(time.Second * time.Duration(i+1))
                continue
            }
            return
        }
        log.Printf("[cache] %s failed after %d retries", name, maxRetries)
    }()
}
