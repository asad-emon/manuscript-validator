"""Settings store: SecretBox protocol and platform factory.

Abstraction sits at *encryption*, not at "settings": the file layout, JSON
schema, atomic write, and error contract are identical on every platform, and
only the cipher differs.

`get_api_key()` returns None and never raises -- for a missing file, an absent
key, a failed decrypt, a scheme mismatch, or unparseable JSON. Spec section 4.2
requires the caller treat that exactly like a network failure.

The stored file records which scheme encrypted it, so a config written by the
dev backend is detected and rejected on Windows rather than producing a garbage
decrypt that surfaces later as an unexplained "key rejected" from Gemini.
"""
