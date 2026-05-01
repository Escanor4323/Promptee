package api

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"
)

// Client wraps an http.Client for communicating with the Promptee backend.
type Client struct {
	BaseURL    string
	HTTPClient *http.Client
}

// NewClient creates a new API client with the given base URL and default timeout.
func NewClient(baseURL string) *Client {
	return &Client{
		BaseURL:    baseURL,
		HTTPClient: &http.Client{Timeout: 30 * time.Second},
	}
}

// CheckHealth queries the backend /api/v1/health endpoint.
func (c *Client) CheckHealth() error {
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, c.BaseURL+"/api/v1/health", nil)
	if err != nil {
		return fmt.Errorf("health check request: %w", err)
	}
	resp, err := c.HTTPClient.Do(req)
	if err != nil {
		return fmt.Errorf("health check failed: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("health check returned status %d", resp.StatusCode)
	}
	return nil
}

// RecommendRequest is the body for POST /api/v1/recommend.
type RecommendRequest struct {
	Query              string `json:"query"`
	TopK               int    `json:"top_k"`
	TradeoffPreference string `json:"tradeoff_preference"`
}

// AddOn represents a prompt addon.
type AddOn struct {
	Name        string `json:"name"`
	Mode        string `json:"mode"`
	Suffix      string `json:"suffix"`
	Description string `json:"description"`
}

// RecommendResult is a single recommendation from the backend.
type RecommendResult struct {
	ID               int     `json:"id"`
	Title            string  `json:"title"`
	Objective        string  `json:"objective"`
	FullText         string  `json:"full_text"`
	Variables        []string `json:"variables"`
	HybridScore      float64 `json:"hybrid_score"`
	ApplicableAddons []AddOn `json:"applicable_addons"`
}

// RecommendResponse is the response from POST /api/v1/recommend.
type RecommendResponse struct {
	Results []RecommendResult `json:"results"`
}

// Recommend calls POST /api/v1/recommend and returns parsed results.
func (c *Client) Recommend(ctx context.Context, req RecommendRequest) (*RecommendResponse, error) {
	body, err := json.Marshal(req)
	if err != nil {
		return nil, fmt.Errorf("marshal recommend request: %w", err)
	}
	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, c.BaseURL+"/api/v1/recommend", bytes.NewReader(body))
	if err != nil {
		return nil, fmt.Errorf("create recommend request: %w", err)
	}
	httpReq.Header.Set("Content-Type", "application/json")
	resp, err := c.HTTPClient.Do(httpReq)
	if err != nil {
		return nil, fmt.Errorf("recommend request failed: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("recommend returned status %d", resp.StatusCode)
	}
	var result RecommendResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("decode recommend response: %w", err)
	}
	return &result, nil
}

// TelemetryRequest is the body for POST /api/v1/telemetry.
type TelemetryRequest struct {
	TemplateID       int     `json:"template_id"`
	LatencyMs        float64 `json:"latency_ms"`
	InputTokens      int     `json:"input_tokens"`
	OutputTokens     int     `json:"output_tokens"`
	ContextWindowPct float64 `json:"context_window_pct"`
	Verbosity        string  `json:"verbosity"`
	AddonMode        string  `json:"addon_mode,omitempty"`
}

// SubmitTelemetry sends execution telemetry to the backend.
func (c *Client) SubmitTelemetry(ctx context.Context, req TelemetryRequest) error {
	body, err := json.Marshal(req)
	if err != nil {
		return fmt.Errorf("marshal telemetry request: %w", err)
	}
	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, c.BaseURL+"/api/v1/telemetry", bytes.NewReader(body))
	if err != nil {
		return fmt.Errorf("create telemetry request: %w", err)
	}
	httpReq.Header.Set("Content-Type", "application/json")
	resp, err := c.HTTPClient.Do(httpReq)
	if err != nil {
		return fmt.Errorf("telemetry request failed: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusCreated {
		var bodyBytes []byte
		bodyBytes, _ = io.ReadAll(resp.Body)
		return fmt.Errorf("telemetry returned status %d: %s", resp.StatusCode, string(bodyBytes))
	}
	return nil
}

// FeedbackRequest is the body for POST /api/v1/feedback.
type FeedbackRequest struct {
	ExecutionID  int    `json:"execution_id"`
	QualityScore int    `json:"quality_score"`
	Notes        string `json:"notes,omitempty"`
}

// IngestRequest is the body for POST /api/v1/ingest.
type IngestRequest struct {
	Paths     []string `json:"paths,omitempty"`
	Directory string   `json:"directory,omitempty"`
}

// IngestResponse is the response from POST /api/v1/ingest.
type IngestResponse struct {
	Ingested int      `json:"ingested"`
	Titles   []string `json:"titles"`
}

// Ingest calls POST /api/v1/ingest and returns parsed results.
func (c *Client) Ingest(ctx context.Context, req IngestRequest) (*IngestResponse, error) {
	body, err := json.Marshal(req)
	if err != nil {
		return nil, fmt.Errorf("marshal ingest request: %w", err)
	}
	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, c.BaseURL+"/api/v1/ingest", bytes.NewReader(body))
	if err != nil {
		return nil, fmt.Errorf("create ingest request: %w", err)
	}
	httpReq.Header.Set("Content-Type", "application/json")
	resp, err := c.HTTPClient.Do(httpReq)
	if err != nil {
		return nil, fmt.Errorf("ingest request failed: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		var bodyBytes []byte
		bodyBytes, _ = io.ReadAll(resp.Body)
		return nil, fmt.Errorf("ingest returned status %d: %s", resp.StatusCode, string(bodyBytes))
	}
	var result IngestResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("decode ingest response: %w", err)
	}
	return &result, nil
}

// SubmitFeedback sends quality feedback to the backend.
func (c *Client) SubmitFeedback(ctx context.Context, req FeedbackRequest) error {
	body, err := json.Marshal(req)
	if err != nil {
		return fmt.Errorf("marshal feedback request: %w", err)
	}
	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, c.BaseURL+"/api/v1/feedback", bytes.NewReader(body))
	if err != nil {
		return fmt.Errorf("create feedback request: %w", err)
	}
	httpReq.Header.Set("Content-Type", "application/json")
	resp, err := c.HTTPClient.Do(httpReq)
	if err != nil {
		return fmt.Errorf("feedback request failed: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusCreated {
		return fmt.Errorf("feedback returned status %d", resp.StatusCode)
	}
	return nil
}
