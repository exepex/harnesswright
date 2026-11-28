# Key table

The table in `docs/config.md` looks like this, one row per key, sorted by key.

| Key | Type | Default | What it changes |
|---|---|---|---|
| `http.port` | integer | `8080` | The port the service listens on. |
| `cache.ttl_seconds` | integer | `300` | How long a cached price stays fresh. |
| `payments.sandbox` | boolean | `false` | Sends payments to the provider's test account. |
