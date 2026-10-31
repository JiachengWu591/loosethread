# Local model backend (llama.cpp)

The `local` backend in `src/loosethread/llm/backends.toml` talks to a llama.cpp server through its
OpenAI-compatible API. No key and no network are needed.

Model used so far: Qwen2.5-7B-Instruct, GGUF Q4_K_M (two split files, about 4.7 GB). With all
layers on the GPU and a 4096-token context it fits in 8 GB of VRAM (RTX 4060 Laptop).

Start the server (paths as on the development machine; adjust to yours):

```powershell
E:\llama.cpp\b11829\bin\llama-server.exe -m E:\models\qwen2.5-7b-instruct-gguf\qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf --alias qwen2.5-7b-instruct -ngl 99 -c 4096 --port 8080
```

`--alias` must match `model` in `backends.toml`: every client lists the server's models before
first use and refuses to run if the configured name is missing. Then:

```powershell
uv run --extra llm python -m loosethread.play --backend local
```
