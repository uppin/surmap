"""The survey agent's chat server: `python -m surmap.agent`.

- `hub` — `ChatHub`: the server's conversations, one `AgentSession` each, and the fan-out of
  their events to `StreamTurn` and `WatchConversation` subscribers.
- `chat_service` — the `ChatService` and `AgentJobs` handlers, and the runtime-event →
  `surmap.agent.v1.TurnEvent` mapping.
- `binding` — the `SurveyTools` handlers and the job tools as the tools a conversation binds.
- `routes` — `GET /health`, `/geometry/<run>/<object>.glb`, `/frames/<run>/<frame>.jpg`, CORS.
- `app` — `AgentServerConfig` and the `ServerDescription` that wires all of it together.
"""
