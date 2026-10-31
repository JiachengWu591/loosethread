"""Language-model backends (optional extra `llm`).

An OpenAI-compatible chat client for DeepSeek and a local llama.cpp server, a model-backed question
parser and a model-backed line writer. Both build their prompts from `ParseRequest` and
`LineRequest` only (see `loosethread.npc`), so a model never receives the truth. Model names and
prices come from `backends.toml`; API keys come from the environment variable it names and are
never written, printed or logged.
"""
