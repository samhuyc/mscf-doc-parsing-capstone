# Source this file from zsh or bash. It never starts a model or a server.
if [ -n "${ZSH_VERSION:-}" ]; then
  MC8_CONFIDENCE_ROOT="${${(%):-%N}:A:h}"
else
  MC8_CONFIDENCE_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
fi
export MC8_CONFIDENCE_ROOT
export PATH="$MC8_CONFIDENCE_ROOT/.venv/bin:$PATH"
export TESSDATA_PREFIX="$MC8_CONFIDENCE_ROOT/.local/models/tessdata"
export OMP_NUM_THREADS=1
export OMP_THREAD_LIMIT=2
export PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True
export TOKENIZERS_PARALLELISM=false
export HF_HUB_OFFLINE=1
export PADDLE_PDX_CACHE_HOME="$MC8_CONFIDENCE_ROOT/.local/cache/paddlex"
export PADDLE_HOME="$MC8_CONFIDENCE_ROOT/.local/cache/paddle"
export HF_HOME="$MC8_CONFIDENCE_ROOT/.local/cache/hf"
export XDG_CACHE_HOME="$MC8_CONFIDENCE_ROOT/.local/cache/xdg"
export MPLCONFIGDIR="$MC8_CONFIDENCE_ROOT/.local/cache/matplotlib"
mkdir -p "$PADDLE_PDX_CACHE_HOME" "$PADDLE_HOME" "$HF_HOME" "$XDG_CACHE_HOME" "$MPLCONFIGDIR"
