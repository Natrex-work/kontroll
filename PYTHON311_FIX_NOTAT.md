# Python 3.11-fiks

Denne pakken er den fullstendige v73-koden med Render/Python 3.11-fiks inkludert.

Endring:
- `app/config.py`: rettet en `f-string` som ga `SyntaxError: f-string: unmatched '('` på Python 3.11.

Korrigert linje:
```python
raw = f"https://{raw.lstrip('/')}"
```
