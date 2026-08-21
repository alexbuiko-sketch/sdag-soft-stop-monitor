# LiveStop Monitoring Layer — Testing Guide

This guide provides instructions for connecting to the **LiveStop v0.9-cf** proxy
gateway to test real-time soft-stop inference optimization: entropy drift detection,
structural boundary tracking (lists / tables / JSON), water-pattern filtering,
and GPU compute reclamation via upstream connection abort.

---

## 1. Connection Parameters

- **Gateway Endpoint:** `https://sdag-gate.alex-buiko.workers.dev/v1/chat/completions`
- **Health Endpoint:** `https://sdag-gate.alex-buiko.workers.dev/health`
- **HTTP Method:** `POST`
- **Demo Period:** Active until **August 31, 2026**
  *(Token authorization is temporarily disabled; any placeholder string can be used.)*

---

## 2. Required Headers

| Header | Value | Notes |
|---|---|---|
| `Content-Type` | `application/json` | Required |
| `Authorization` | `Bearer demo` | Any placeholder token accepted during demo |
| `X-Target-URL` | `https://<YOUR_GPU_HOST>/v1/chat/completions` | Your active vLLM / SGLang / TGI / OpenAI-compatible endpoint |

> **Note:** The worker forces `stream: true`, `logprobs: true`, and
> `top_logprobs: 5` on the upstream request automatically. You do not need
> to set these in the body.

---

## 3. Health Check

Verify the worker is alive before running tests:

```bash
curl https://sdag-gate.alex-buiko.workers.dev/health
```

Expected response:

```json
{"status":"ok","version":"v0.9-cf"}
```

---

## 4. Quick Test (cURL)

Execute the following command to verify the stream and soft-stop behaviour:

```bash
curl -N -X POST "https://sdag-gate.alex-buiko.workers.dev/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer demo" \
  -H "X-Target-URL: https://<YOUR_GPU_HOST_OR_POD>/v1/chat/completions" \
  -d '{
    "model": "Qwen/Qwen2.5-7B-Instruct",
    "messages": [
      {"role": "user", "content": "List 5 key features of Python 3.12."}
    ],
    "max_tokens": 512,
    "temperature": 0
  }'
```

The `-N` flag disables curl output buffering so you see the SSE stream in real time.

---

## 5. Test Prompts by Category

Use these prompts to exercise each detection path:

| Category | Prompt | Expected `stop_reason` |
|---|---|---|
| **lists** | `List 5 key features of Python 3.12.` | `structure_closed_boundary` |
| **lists** | `Give 8 methods for optimizing database queries.` | `structure_closed_boundary` |
| **lists** | `Provide 10 best practices for REST API design.` | `structure_closed_boundary` |
| **tables** | `Create a table comparing SQL vs NoSQL across 7 metrics.` | `structure_closed_boundary` |
| **tables** | `Compare Docker vs Kubernetes across 5 features in a table.` | `structure_closed_boundary` |
| **guides** | `Explain CI/CD setup in 6 steps.` | `structure_closed_boundary` |
| **guides** | `Provide a 7-step guide to implement OAuth2 authentication.` | `structure_closed_boundary` |
| **prose** | `What is the CAP theorem in distributed systems?` | *(no stop — model finishes naturally)* |
| **water** | `Explain Agile development and be very verbose and repetitive.` | `water_pattern_and_low_entropy` |

---

## 6. Reading the Response

### 6a. Normal completion (no soft-stop)

The stream ends with the standard vLLM finish event:

```plaintext
data: {"choices":[{"delta":{},"finish_reason":"stop"}]}

data: [DONE]
```

### 6b. Soft-stop triggered

The stream ends with a **metrics packet** followed by `[DONE]`:

```plaintext
data: {"choices":[{"delta":{},"finish_reason":"monitoring_soft_stop"}],"monitoring_metrics":{...}}

data: [DONE]
```

The `monitoring_metrics` object contains:

| Field | Type | Description |
|---|---|---|
| `tokens_evaluated` | `int` | Total tokens processed before stop |
| `stop_at_token` | `int` | Token index where the stop was triggered |
| `stop_reason` | `string` | `structure_closed_boundary` or `water_pattern_and_low_entropy` |
| `grace_exit_reason` | `string` | `boundary`, `countdown`, or `boundary_lookahead` |
| `grace_steps_spent` | `int` | Tokens generated during the grace window |
| `internal_errors` | `int` | Internal evaluator errors (should be `0`) |
| `unclosed_blocked` | `bool` | `true` if a stop was blocked by an unclosed container |
| `water_match_pos` | `int \| null` | Character position of the water pattern match |
| `early_exit` | `bool` | Always `true` when soft-stop fires |

### 6c. Response headers

| Header | Value |
|---|---|
| `X-Monitoring-Engine` | `v0.9-cf` |
| `X-Target-Items` | Extracted item count from prompt (or `null`) |
| `X-Request-Mode` | `chat` or `table` |

---

## 7. JavaScript Test Client

```javascript
const WORKER_URL = "https://sdag-gate.alex-buiko.workers.dev/v1/chat/completions";
const GPU_URL    = "https://<YOUR_GPU_HOST_OR_POD>/v1/chat/completions";

async function testSoftStop(prompt) {
  const response = await fetch(WORKER_URL, {
    method: "POST",
    headers: {
      "Content-Type":  "application/json",
      "Authorization": "Bearer demo",
      "X-Target-URL":  GPU_URL,
    },
    body: JSON.stringify({
      model: "Qwen/Qwen2.5-7B-Instruct",
      messages: [{ role: "user", content: prompt }],
      max_tokens: 512,
      temperature: 0,
    }),
  });

  const reader     = response.body.getReader();
  const decoder    = new TextDecoder();
  let fullText     = "";
  let metrics      = null;
  let finishReason = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    for (const line of decoder.decode(value, { stream: true }).split("\n")) {
      const trimmed = line.trim();
      if (!trimmed.startsWith("data: ") || trimmed === "data: [DONE]") continue;

      try {
        const json = JSON.parse(trimmed.slice(6));
        fullText += json.choices?.[0]?.delta?.content || "";

        if (json.monitoring_metrics) metrics = json.monitoring_metrics;
        if (json.choices?.[0]?.finish_reason) finishReason = json.choices[0].finish_reason;
      } catch (_) {}
    }
  }

  console.log("=== Text ===\n", fullText);
  console.log("=== finish_reason ===", finishReason);
  if (metrics) {
    console.log("=== Soft-Stop Metrics ===");
    console.table(metrics);
  }
}

// Run tests
testSoftStop("List 5 key features of Python 3.12.");
testSoftStop("Create a table comparing SQL vs NoSQL across 7 metrics.");
testSoftStop("What is the CAP theorem?");
```

---

## 8. Supported Backends

The worker proxies to any OpenAI-compatible inference server:

| Backend | Example `X-Target-URL` |
|---|---|
| vLLM | `http://<host>:8000/v1/chat/completions` |
| SGLang | `http://<host>:30000/v1/chat/completions` |
| TGI | `http://<host>:8080/v1/chat/completions` |
| RunPod | `https://<pod-id>-8888.proxy.runpod.net/v1/chat/completions` |
| OpenAI | `https://api.openai.com/v1/chat/completions` |

> **Requirement:** The backend must support `logprobs` in streaming mode.
> vLLM ≥ 0.4, SGLang ≥ 0.2, and OpenAI API all support this.

---

## 9. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `400: Missing 'X-Target-URL' header` | Header not sent | Add `X-Target-URL` with your GPU endpoint |
| `405: Monitoring Layer expects POST` | Wrong HTTP method | Use `POST` |
| Upstream returns `404` | Wrong path in `X-Target-URL` | Ensure URL ends with `/v1/chat/completions` |
| No `monitoring_metrics` in response | Soft-stop did not trigger | Use a list/table prompt; prose prompts finish naturally |
| `internal_errors > 0` | Evaluator exception | Check the prompt for unusual encoding; report the issue |
| Stream cuts immediately | GPU server unreachable | Verify `X-Target-URL` is accessible from the public internet |
| `finish_reason: "length"` with no stop | Baseline hit `max_tokens` | Increase `max_tokens` or use a shorter prompt |

---

## 10. Architecture Overview

```plaintext
Client ──POST──▶ Cloudflare Worker ──POST──▶ vLLM / SGLang / TGI
                      │
                      ├── Intercepts SSE stream token-by-token
                      ├── Tracks: lists, tables, JSON, code fences, inline code
                      ├── Computes: self-normalized entropy z-score (MAD-based)
                      ├── Detects: water patterns, structural boundaries
                      ├── Applies: grace window + one-token lookahead
                      │
                      ├── On soft-stop:
                      │     ├── Sends metrics packet to client
                      │     ├── Sends data: [DONE]
                      │     └── Aborts upstream HTTP connection (frees KV-cache)
                      │
                      └── On natural finish:
                            └── Passes through unchanged
```

---

*Guide version: v0.9-cf · Last updated: 2026-08-21*
