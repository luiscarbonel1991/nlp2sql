---
name: db
description: Start/stop Docker test databases
argument-hint: "[up|down]"
---

Manage test databases:
- `cd docker && docker compose up -d` (default/up)
- `cd docker && docker compose down` (down)

Connection strings:
- Simple: postgresql://testuser:testpass@localhost:5432/testdb
- Enterprise: postgresql://demo:demo123@localhost:5433/enterprise
