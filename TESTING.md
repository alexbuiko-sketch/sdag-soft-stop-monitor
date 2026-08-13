# Monitoring Layer / SDAG Gateway — Integration & Testing Guide

This guide provides instructions for connecting to the **SDAG (Systematic Defect Awareness & Guidance)** proxy gateway to test real-time entropy tracking, byte-level validation, and compute optimization streams.

---

## 1. Connection Parameters

* **Gateway Endpoint:** `[https://sdag-gate.alex-buiko.workers.dev/v1/chat/completions](https://sdag-gate.alex-buiko.workers.dev/v1/chat/completions)`
* **HTTP Method:** `POST`
* **Demo Period:** Active until **August 31, 2026** *(Token authorization is temporarily disabled; any placeholder string can be used).*

---

## 2. Required Headers

* `Content-Type`: `application/json`
* `Authorization`: `Bearer demo` *(Any placeholder token is accepted during the demo period)*
* `X-Target-URL`: `https://<YOUR_GPU_HOST_OR_POD>/v1/chat/completions` *(URL of your active vLLM, SGLang, or OpenAI-compatible inference endpoint)*

---

## 3. Quick Test (cURL)

Execute the following command in your terminal to verify the stream:

```bash
curl -N -X POST "https://sdag-gate.alex-buiko.workers.dev/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer demo" \
  -H "X-Target-URL: https://<YOUR_GPU_HOST_OR_POD>/v1/chat/completions" \
  -d '{
    "model": "meta-llama/Llama-3.1-8B-Instruct",
    "messages": [{"role": "user", "content": "Ping"}],
    "stream": true,
    "logprobs": true,
    "top_logprobs": 3
  }'

```
Multi-GPU Cluster Validation
The gateway architecture is fully transparent to your underlying topology. You can route traffic through the SDAG proxy to benchmark performance not only on single-GPU pods but also across multi-GPU clusters running Tensor Parallelism (TP) or Pipeline Parallelism (PP). Simply point the X-Target-URL to your multi-GPU inference cluster endpoint
---

## 4. What the Gateway Monitors & Controls

During the test, the monitoring layer transparently intercepts and evaluates the Server-Sent Events (SSE) stream:

1. **Shannon Entropy Calculation:** Evaluates model confidence in real-time based on `top_logprobs`.
2. **Structural Integrity Check:** Monitors syntax boundaries (JSON/array open/close states) to detect degeneration or hallucination loops.
3. **Soft-Stop & Dead Compute Prevention:** Automatically triggers an early exit (`monitoring_soft_stop`) upon detecting an entropy flatline and structural completion, sending an upstream abort signal to free up GPU KV-cache resources instantly.
