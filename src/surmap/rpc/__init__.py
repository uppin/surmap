"""One base for every SurMap server shape.

A service is composed from **bricks** — each claims some of the service's methods and owns only its
own dependencies — and the composition is exact: a method no brick claims, or two bricks claim, is
refused by name. A **`ServerDescription`** lists a server's services, HTTP routes, WebSocket routes
and closeables; it is static in shape and lazy in dependencies. **Hosts** mount a description: on
hypercorn for production, in memory for tests.
"""
