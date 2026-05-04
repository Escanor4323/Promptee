package api

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
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
			{ID: 1, TemplateID: 10, Title: "Test Prompt", HybridScore: 0.95, Variables: []string{"NAME"}},
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
		Query: "test query", TopK: 5, TradeoffPreference: "balanced",
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
	if resp.Results[0].TemplateID != 10 {
		t.Errorf("expected TemplateID 10, got %d", resp.Results[0].TemplateID)
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

// TestIngest_Returns202AndJobID verifies that a 202 response is parsed as a JobEnqueueResponse.
func TestIngest_Returns202AndJobID(t *testing.T) {
	expected := JobEnqueueResponse{
		JobID:     "abc-123",
		Status:    "pending",
		StatusURL: "/api/v1/jobs/abc-123",
	}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			t.Errorf("expected POST, got %s", r.Method)
		}
		if r.URL.Path != "/api/v1/ingest" {
			t.Errorf("expected path /api/v1/ingest, got %s", r.URL.Path)
		}
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusAccepted)
		json.NewEncoder(w).Encode(expected)
	}))
	defer srv.Close()

	c := NewClient(srv.URL)
	resp, err := c.Ingest(context.Background(), IngestRequest{
		Paths: []string{"prompts/a.md"}, Directory: "",
	})
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}
	if resp.JobID != "abc-123" {
		t.Errorf("expected JobID 'abc-123', got %q", resp.JobID)
	}
	if resp.Status != "pending" {
		t.Errorf("expected Status 'pending', got %q", resp.Status)
	}
	if resp.StatusURL != "/api/v1/jobs/abc-123" {
		t.Errorf("expected StatusURL '/api/v1/jobs/abc-123', got %q", resp.StatusURL)
	}
}

// TestIngest_ServerError ensures non-202 responses surface as errors.
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

// TestGetJobStatus runs table-driven cases covering all job lifecycle states.
func TestGetJobStatus(t *testing.T) {
	totalSteps := 10
	eta := 4.5
	errMsg := "vector store unavailable"
	ingestResult := IngestResponse{Ingested: 7, Titles: []string{"A", "B", "C", "D", "E", "F", "G"}}

	tests := []struct {
		name           string
		serverStatus   int
		serverPayload  interface{}
		expectErr      bool
		errContains    string
		checkResponse  func(t *testing.T, r *JobStatusResponse)
	}{
		{
			name:         "pending",
			serverStatus: http.StatusOK,
			serverPayload: JobStatusResponse{
				JobID:       "job-1",
				Kind:        "ingest",
				Status:      "pending",
				ProgressPct: 0,
				CurrentStep: "queued",
			},
			checkResponse: func(t *testing.T, r *JobStatusResponse) {
				if r.Status != "pending" {
					t.Errorf("expected status 'pending', got %q", r.Status)
				}
				if r.ProgressPct != 0 {
					t.Errorf("expected ProgressPct 0, got %f", r.ProgressPct)
				}
				if r.TotalSteps != nil {
					t.Error("expected TotalSteps nil for pending job")
				}
				if r.ETASeconds != nil {
					t.Error("expected ETASeconds nil for pending job")
				}
				if r.Error != nil {
					t.Error("expected Error nil for pending job")
				}
				if r.Result != nil {
					t.Error("expected Result nil for pending job")
				}
			},
		},
		{
			name:         "processing with progress",
			serverStatus: http.StatusOK,
			serverPayload: JobStatusResponse{
				JobID:          "job-2",
				Kind:           "ingest",
				Status:         "processing",
				ProgressPct:    60.0,
				CurrentStep:    "embedding",
				CompletedSteps: 6,
				TotalSteps:     &totalSteps,
				ETASeconds:     &eta,
			},
			checkResponse: func(t *testing.T, r *JobStatusResponse) {
				if r.Status != "processing" {
					t.Errorf("expected status 'processing', got %q", r.Status)
				}
				if r.ProgressPct != 60.0 {
					t.Errorf("expected ProgressPct 60.0, got %f", r.ProgressPct)
				}
				if r.TotalSteps == nil || *r.TotalSteps != 10 {
					t.Errorf("expected TotalSteps 10, got %v", r.TotalSteps)
				}
				if r.ETASeconds == nil || *r.ETASeconds != 4.5 {
					t.Errorf("expected ETASeconds 4.5, got %v", r.ETASeconds)
				}
				if r.CompletedSteps != 6 {
					t.Errorf("expected CompletedSteps 6, got %d", r.CompletedSteps)
				}
			},
		},
		{
			name:         "completed with result",
			serverStatus: http.StatusOK,
			serverPayload: JobStatusResponse{
				JobID:          "job-3",
				Kind:           "ingest",
				Status:         "completed",
				ProgressPct:    100.0,
				CurrentStep:    "done",
				CompletedSteps: 10,
				TotalSteps:     &totalSteps,
				Result:         &ingestResult,
			},
			checkResponse: func(t *testing.T, r *JobStatusResponse) {
				if r.Status != "completed" {
					t.Errorf("expected status 'completed', got %q", r.Status)
				}
				if r.ProgressPct != 100.0 {
					t.Errorf("expected ProgressPct 100.0, got %f", r.ProgressPct)
				}
				if r.Result == nil {
					t.Fatal("expected non-nil Result for completed job")
				}
				if r.Result.Ingested != 7 {
					t.Errorf("expected Result.Ingested 7, got %d", r.Result.Ingested)
				}
				if len(r.Result.Titles) != 7 {
					t.Errorf("expected 7 titles, got %d", len(r.Result.Titles))
				}
				if r.Error != nil {
					t.Error("expected Error nil for completed job")
				}
			},
		},
		{
			name:         "failed with error message",
			serverStatus: http.StatusOK,
			serverPayload: JobStatusResponse{
				JobID:       "job-4",
				Kind:        "ingest",
				Status:      "failed",
				ProgressPct: 30.0,
				CurrentStep: "embedding",
				Error:       &errMsg,
			},
			checkResponse: func(t *testing.T, r *JobStatusResponse) {
				if r.Status != "failed" {
					t.Errorf("expected status 'failed', got %q", r.Status)
				}
				if r.Error == nil {
					t.Fatal("expected non-nil Error for failed job")
				}
				if *r.Error != "vector store unavailable" {
					t.Errorf("expected error message 'vector store unavailable', got %q", *r.Error)
				}
				if r.Result != nil {
					t.Error("expected Result nil for failed job")
				}
			},
		},
		{
			name:         "not found returns descriptive error",
			serverStatus: http.StatusNotFound,
			serverPayload: map[string]string{"detail": "job not found"},
			expectErr:    true,
			errContains:  "job not found: missing-job",
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			jobID := "job-1"
			if tc.errContains != "" {
				jobID = "missing-job"
			}

			srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				if r.Method != http.MethodGet {
					t.Errorf("expected GET, got %s", r.Method)
				}
				w.Header().Set("Content-Type", "application/json")
				w.WriteHeader(tc.serverStatus)
				json.NewEncoder(w).Encode(tc.serverPayload)
			}))
			defer srv.Close()

			c := NewClient(srv.URL)
			resp, err := c.GetJobStatus(context.Background(), jobID)
			if tc.expectErr {
				if err == nil {
					t.Fatal("expected error, got nil")
				}
				if !strings.Contains(err.Error(), tc.errContains) {
					t.Errorf("expected error to contain %q, got %q", tc.errContains, err.Error())
				}
				return
			}
			if err != nil {
				t.Fatalf("unexpected error: %v", err)
			}
			if tc.checkResponse != nil {
				tc.checkResponse(t, resp)
			}
		})
	}
}

func TestSubmitTelemetry_Success(t *testing.T) {
	expected := TelemetryResponse{
		ID: 1, TemplateID: 1, LatencyMs: 100.5,
		InputTokens: 50, OutputTokens: 200, ContextWindowPct: 25.0,
		Verbosity: "moderate", TradeoffSpeed: 0.73, TradeoffCost: 0.82, TradeoffQuality: 0.5,
	}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusCreated)
		json.NewEncoder(w).Encode(expected)
	}))
	defer srv.Close()

	c := NewClient(srv.URL)
	resp, err := c.SubmitTelemetry(context.Background(), TelemetryRequest{
		TemplateID: 1, LatencyMs: 100.5,
		InputTokens: 50, OutputTokens: 200, ContextWindowPct: 25.0, Verbosity: "moderate",
	})
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}
	if resp.ID != 1 {
		t.Errorf("expected ID 1, got %d", resp.ID)
	}
	if resp.TradeoffSpeed != 0.73 {
		t.Errorf("expected TradeoffSpeed 0.73, got %f", resp.TradeoffSpeed)
	}
}

func TestSubmitTelemetry_ServerError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusBadRequest)
	}))
	defer srv.Close()

	c := NewClient(srv.URL)
	_, err := c.SubmitTelemetry(context.Background(), TelemetryRequest{
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
		ExecutionID: 1, QualityScore: 4, Notes: "good result",
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
		ExecutionID: 1, QualityScore: 3,
	})
	if err == nil {
		t.Fatal("expected error for 400 response")
	}
}
