"""HttpRule (`google.api.http`) REST transcoding for the connect-python services.

A REST request is matched against each method's HTTP rule, decoded from its path, query and body
into the request message, dispatched in process to the connect-python application that serves the
method, and the response is encoded back to proto3 JSON — or, for a server-streaming method, to
NDJSON lines in the grpc-gateway style. Only methods that carry a rule are reachable.
"""
