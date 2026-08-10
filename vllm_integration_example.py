from vllm import LLM, SamplingParams
import torch

# Initialize vLLM engine with an open-weights model (e.g., Qwen or Llama)
llm = LLM(
    model="Qwen/Qwen2.5-7B-Instruct",
    tensor_parallel_size=1,
    trust_remote_code=True
)

# Import the monitoring_layer module for the SDAG-protocol / soft-stop-protocol
from monitoring_layer import SDAGLogitsProcessor

# Retrieve the end-of-sequence (EOS) token ID for the specific model tokenizer
eos_token_id = llm.llm_engine.tokenizer.tokenizer.eos_token_id

# Instantiate the SDAG-protocol / soft-stop-protocol processor with a target structural boundary limit (e.g., exactly 6 list items)
sdag_processor = SDAGLogitsProcessor(
    target_items=6, 
    eos_token_id=eos_token_id
)

# Configure sampling parameters
# Note: max_tokens is set to 512 (as used in initial benchmarks); 
# however, it can be safely increased to 1024 or higher to provide sufficient headroom 
# for deep reasoning tasks, ensuring the model avoids premature truncation while the soft-stop-protocol 
# engine guarantees precise termination at the exact structural boundary.
sampling_params = SamplingParams(
    temperature=0.0,
    max_tokens=512,
    logits_processors=[sdag_processor]
)

# Execute text generation for the structured prompt
prompt = "List exactly 6 key principles of clean code architecture."
outputs = llm.generate([prompt], sampling_params)

# Output the cleanly truncated result without syntax damage
print(outputs[0].outputs[0].text)
