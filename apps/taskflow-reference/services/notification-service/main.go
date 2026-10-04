package main

import (
	"context"
	"encoding/json"
	"log"
	"net/http"
	"os"
	"strconv"
	"time"

	"github.com/go-redis/redis/v8"
)

var (
	ctx = context.Background()
	rdb *redis.Client
)

// Notification is stored as a JSON blob inside a per-user Redis list.
// Redis is the sole datastore for this service, matching the required
// Notification Service -> Redis edge.
type Notification struct {
	ID        string    `json:"id"`
	UserID    int       `json:"user_id"`
	Type      string    `json:"type"`
	Message   string    `json:"message"`
	CreatedAt time.Time `json:"created_at"`
}

type createNotificationRequest struct {
	UserID  int    `json:"user_id"`
	Type    string `json:"type"`
	Message string `json:"message"`
}

func notificationKey(userID int) string {
	return "notifications:user:" + strconv.Itoa(userID)
}

func waitForRedis(client *redis.Client, maxRetries int, delay time.Duration) error {
	var lastErr error
	for i := 0; i < maxRetries; i++ {
		lastErr = client.Ping(ctx).Err()
		if lastErr == nil {
			return nil
		}
		time.Sleep(delay)
	}
	return lastErr
}

func healthHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{
		"service": "notification-service",
		"status":  "ok",
	})
}

func createNotificationHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}

	var req createNotificationRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "invalid request body", http.StatusBadRequest)
		return
	}
	if req.UserID == 0 || req.Message == "" {
		http.Error(w, "user_id and message are required", http.StatusBadRequest)
		return
	}
	if req.Type == "" {
		req.Type = "general"
	}

	notification := Notification{
		ID:        strconv.FormatInt(time.Now().UnixNano(), 10),
		UserID:    req.UserID,
		Type:      req.Type,
		Message:   req.Message,
		CreatedAt: time.Now().UTC(),
	}

	payload, err := json.Marshal(notification)
	if err != nil {
		http.Error(w, "failed to encode notification", http.StatusInternalServerError)
		return
	}

	key := notificationKey(req.UserID)
	// LPUSH newest-first, cap list length so it doesn't grow unbounded.
	pipe := rdb.TxPipeline()
	pipe.LPush(ctx, key, payload)
	pipe.LTrim(ctx, key, 0, 199)
	if _, err := pipe.Exec(ctx); err != nil {
		log.Printf("redis write failed: %v", err)
		http.Error(w, "failed to store notification in redis", http.StatusBadGateway)
		return
	}

	log.Printf("stored notification id=%s for user_id=%d in redis key=%s", notification.ID, req.UserID, key)

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusCreated)
	json.NewEncoder(w).Encode(notification)
}

func listNotificationsHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}

	userIDStr := r.URL.Query().Get("user_id")
	userID, err := strconv.Atoi(userIDStr)
	if err != nil || userID == 0 {
		http.Error(w, "user_id query parameter is required", http.StatusBadRequest)
		return
	}

	key := notificationKey(userID)
	raw, err := rdb.LRange(ctx, key, 0, 49).Result()
	if err != nil {
		log.Printf("redis read failed: %v", err)
		http.Error(w, "failed to read notifications from redis", http.StatusBadGateway)
		return
	}

	notifications := make([]Notification, 0, len(raw))
	for _, item := range raw {
		var n Notification
		if err := json.Unmarshal([]byte(item), &n); err == nil {
			notifications = append(notifications, n)
		}
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(notifications)
}

func main() {
	redisAddr := os.Getenv("REDIS_ADDR")
	if redisAddr == "" {
		redisAddr = "redis:6379"
	}

	rdb = redis.NewClient(&redis.Options{
		Addr: redisAddr,
	})

	log.Printf("notification-service starting up, waiting for redis at %s...", redisAddr)
	if err := waitForRedis(rdb, 30, time.Second); err != nil {
		log.Fatalf("could not connect to redis after retries: %v", err)
	}
	log.Println("notification-service connected to redis")

	mux := http.NewServeMux()
	mux.HandleFunc("/health", healthHandler)
	mux.HandleFunc("/notifications", func(w http.ResponseWriter, r *http.Request) {
		switch r.Method {
		case http.MethodPost:
			createNotificationHandler(w, r)
		case http.MethodGet:
			listNotificationsHandler(w, r)
		default:
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		}
	})

	port := os.Getenv("PORT")
	if port == "" {
		port = "8003"
	}

	log.Printf("notification-service listening on :%s", port)
	if err := http.ListenAndServe(":"+port, mux); err != nil {
		log.Fatalf("server failed: %v", err)
	}
}
