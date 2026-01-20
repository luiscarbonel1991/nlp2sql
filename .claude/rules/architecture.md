---
globs:
  - "src/nlp2sql/**/*.py"
---

# Clean Architecture Guidelines

## Layer Rules
- `core/` - Pure Python, NO external dependencies
- `ports/` - Interfaces only (abstract classes)
- `adapters/` - Implement ports, external integrations
- `services/` - Orchestration, business logic
- `schema/` - Schema analysis and filtering

## Dependencies
- Core depends on nothing
- Ports depend only on Core
- Adapters depend on Ports
- Services depend on Ports (not Adapters)

## Adding Features
1. Define port interface if needed
2. Implement adapter(s)
3. Update service to use port
4. Add tests at each layer
