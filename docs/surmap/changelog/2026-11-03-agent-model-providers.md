# The survey agent chats through Muse on the Responses API or a local Ollama model

**Date:** 2026-11-03
**Feature:** Survey agent / chat model providers (`#survey-agent` 5/9, PR #81)

- **Muse.** `surmap.agent.llm.MetaResponsesChatModel`, a LangChain
  `BaseChatModel` over the Meta Responses API with bound function tools
  and images. Defaults `muse-wonder-1.0`, effort `medium`, 8192 output
  tokens. Request and reply mapping are the pure functions
  `responses_request` and `parse_responses`. Usage was recorded in the ledger
  as provider `meta`, and a `before_call` budget check
  (`UsageLedger.check`) ran before every request.
- **Ollama.** `ollama_chat_model` builds `ChatOllama` against
  `SURMAP_OLLAMA_URL`; `ollama_models` lists `GET /api/tags`.
- **Registry.** `ChatModelRegistry` lists `meta:<model>` (when
  `MODEL_API_KEY` is set) and `ollama:<model>` ids and builds any of
  them.
- **Dependency.** `langchain-ollama>=1.1,<2`.
- **Verification.** Offline suite 1482 passed, 32 skipped. Live Ollama
  tool round trip passed against `fastcontext-tools:latest`. Live Muse
  not run (no `MODEL_API_KEY` on the dev host): Meta function-tool
  support is unverified; the shapes are assumed from the OpenAI-style
  Responses API.
