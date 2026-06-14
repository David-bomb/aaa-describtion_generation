$ErrorActionPreference = "Stop"

$model = if ($env:QWEN_MODEL_ID) { $env:QWEN_MODEL_ID } else { "Qwen/Qwen3-VL-4B-Instruct" }
$portValue = if ($env:VLLM_PORT) { $env:VLLM_PORT } else { "8000" }
$maxModelLen = if ($env:VLLM_MAX_MODEL_LEN) { $env:VLLM_MAX_MODEL_LEN } else { "2048" }
$gpuMemoryUtilization = if ($env:VLLM_GPU_MEMORY_UTILIZATION) { $env:VLLM_GPU_MEMORY_UTILIZATION } else { "0.90" }

vllm serve $model `
  --served-model-name $model `
  --host 0.0.0.0 `
  --port $portValue `
  --dtype float16 `
  --quantization bitsandbytes `
  --load-format bitsandbytes `
  --max-model-len $maxModelLen `
  --max-num-seqs 1 `
  --gpu-memory-utilization $gpuMemoryUtilization `
  --limit-mm-per-prompt '{"image": 1}' `
  --trust-remote-code
