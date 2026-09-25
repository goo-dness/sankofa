# Connection handling reference

Typical `.env.example` entry:
```
DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@localhost/sankofa_db
```

**Validation snippet**:
```python
import os, re
from sqlalchemy import create_engine
url = os.getenv('DATABASE_URL')
if not url or not re.match(r'^postgresql://', url.strip()):
    raise ValueError('Invalid or missing DATABASE_URL')
engine = create_engine(url.strip())
```

**Common errors**:
- `ArgumentError: Expected string or URL object, got None` – means `DATABASE_URL` is unset.
- `OperationalError` – wrong credentials or DB not running.

**Fixes**:
- Ensure `.env` is sourced (`source .env`) or the variable is exported.
- Verify the password and host are correct.
- Use `psql $DATABASE_URL` to test connectivity.
