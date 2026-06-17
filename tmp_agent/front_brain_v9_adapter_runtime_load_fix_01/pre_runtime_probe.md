# Pre Runtime Probe

## health
- ok: `True`
- status_code: `200`
- error: `None`

```
{"status":"healthy","sessions":2,"version":"9.0.0","safe_mode":false}
```

## models
- ok: `False`
- status_code: `404`
- error: `HTTPError`

```
{"detail":"Not Found"}
```

## chat_completions
- ok: `False`
- status_code: `404`
- error: `HTTPError`

```
{"detail":"Not Found"}
```

- runtime_already_loaded_adapter: `False`
