package api

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestNewClient(t *testing.T) {
	c := NewClient("http://localhost:8000")
	if c.BaseURL != "http://localhost:8000" {
		t.Errorf("expected BaseURL 'http://localhost:8000', got %q", c.BaseURL)
	}
	if c.HTTPClient == nil {
		t.Error("expected non-nil HTTPClient")
	}
}

func TestCheckHealth_Success(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/v1/health" {
			t.Errorf("expected path /api/v1/health, got %s", r.URL.Path)
		}
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	c := NewClient(srv.URL)
	if err := c.CheckHealth(); err != nil {
		t.Fatalf("expected no error, got %v", err)
	}
}

func TestCheckHealth_Failure(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusServiceUnavailable)
	}))
	defer srv.Close()

	c := NewClient(srv.URL)
	if err := c.CheckHealth(); err == nil {
		t.Fatal("expected error for 503 response")
	}
}

func TestRecommend_Success(t *testing.T) {
	expected := RecommendResponse{
		Results: []RecommendResult{
			{ID: 1, Title: "Test Prompt", HybridScore: 0.95, Variables: []string{"NAME"}},
		},
	}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			t.Errorf("expected POST, got %s", r.Method)
		}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(expected)
	}))
	defer srv.Close()

	c := NewClient(srv.URL)
	resp, err := c.Recommend(context.Background(), RecommendRequest{
		Query:              "test query",
		TopK:               5,
		TradeoffPreference: "balanced",
	})
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}
	if len(resp.Results) != 1 {
		t.Fatalf("expected 1 result, got %d", len(resp.Results))
	}
	if resp.Results[0].Title != "Test Prompt" {
		t.Errorf("expected title 'Test Prompt', got %q", resp.Results[0].Title)
	}
}

func TestRecommend_ServerError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer srv.Close()

	c := NewClient(srv.URL)
	_, err := c.Recommend(context.Background(), RecommendRequest{Query: "test"})
	if err == nil {
		t.Fatal("expected error for 500 response")
	}
}

func TestIngest_Success(t *testing.T) {
	expected := IngestResponse{Ingested: 3, Titles: []string{"A", "B", "C"}}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(expected)
	}))
	defer srv.Close()

	c := NewClient(srv.URL)
	resp, err := c.Ingest(context.Background(), IngestRequest{
		Paths:     []string{"a.md", "b.md"},
		Directory: "/tmp/prompts",
	})
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}
	if resp.Ingested != 3 {
		t.Errorf("expected 3 ingested, got %d", resp.Ingested)
	}
}

func TestIngest_ServerError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer srv.Close()

	c := NewClient(srv.URL)
	_, err := c.Ingest(context.Background(), IngestRequest{Paths: []string{"a.md"}})
	if err == nil {
		t.Fatal("expected error for 500 response")
	}
}

func TestSubmitTelemetry_Success(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusCreated)
	}))
	defer srv.Close()

	c := NewClient(srv.URL)
	err := c.SubmitTelemetry(context.Background(), TelemetryRequest{
		TemplateID:       1,
		LatencyMs:        100.5,
		InputTokens:      50,
		OutputTokens:     200,
		ContextWindowPct: 25.0,
		Verbosity:        "moderate",
	})
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}
}

func TestSubmitTelemetry_ServerError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusBadRequest)
	}))
	defer srv.Close()

	c := NewClient(srv.URL)
	err := c.SubmitTelemetry(context.Background(), TelemetryRequest{
		TemplateID: 1, LatencyMs: 10, InputTokens: 5, OutputTokens: 20,
		ContextWindowPct: 10, Verbosity: "moderate",
	})
	if err == nil {
		t.Fatal("expected error for 400 response")
	}
}

func TestSubmitFeedback_Success(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusCreated)
	}))
	defer srv.Close()

	c := NewClient(srv.URL)
	err := c.SubmitFeedback(context.Background(), FeedbackRequest{
		ExecutionID:  1,
		QualityScore: 4,
		Notes:        "good result",
	})
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}
}

func TestSubmitFeedback_ServerError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusBadRequest)
	}))
	defer srv.Close()

	c := NewClient(srv.URL)
	err := c.SubmitFeedback(context.Background(), FeedbackRequest{
		ExecutionID:  1,
		QualityScore: 3,
	})
	if err == nil {
		t.Fatal("expected error for 400 response")
	}
}
