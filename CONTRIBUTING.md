# Contributing to nlp2sql

Thank you for your interest in contributing to nlp2sql! This project follows enterprise development practices to ensure high quality, maintainability, and reliability.

## Development Philosophy

nlp2sql is built with enterprise production environments in mind:

- **Clean Architecture**: Ports & Adapters pattern for maintainability
- **Type Safety**: Full type annotations with mypy validation
- **Test-Driven Development**: Comprehensive test coverage
- **Performance First**: Optimized for enterprise scale (1000+ tables)
- **Multi-Provider**: Avoid vendor lock-in from day one

## Getting Started

### Prerequisites

- Python 3.9+
- UV package manager (recommended) or pip
- PostgreSQL (for testing)
- Docker & Docker Compose (for test databases)

### Development Setup

```bash
# Clone the repository
git clone https://github.com/luiscarbonel1991/nlp2sql.git
cd nlp2sql

# Install in development mode
./install-dev.sh

# Set up test databases
cd docker && docker-compose up -d

# Set environment variables
export OPENAI_API_KEY=your-test-key
export ANTHROPIC_API_KEY=your-test-key  # optional
export GOOGLE_API_KEY=your-test-key     # optional

# Verify installation
uv run nlp2sql --help
uv run nlp2sql validate
```

## Development Workflow

### 1. Code Quality Standards

We maintain high code quality through automated tools:

```bash
# Format code
uv run ruff format .

# Lint code
uv run ruff check .

# Type checking
uv run mypy src/

# Run all quality checks
make quality  # or run individually
```

### 2. Testing Requirements

All contributions must include comprehensive tests:

```bash
# Run unit tests
uv run pytest tests/unit/

# Run integration tests
uv run pytest tests/integration/

# Run end-to-end tests
uv run pytest tests/e2e/

# Run all tests with coverage
uv run pytest --cov=nlp2sql --cov-report=html
```

### 3. Architecture Guidelines

Follow Clean Architecture principles:

```
src/nlp2sql/
├── core/           # Business entities (pure Python, no dependencies)
├── ports/          # Interfaces/abstractions (define contracts)
├── adapters/       # External integrations (AI providers, databases)
├── services/       # Application services (orchestrate use cases)
├── schema/         # Schema management strategies
├── config/         # Configuration management
└── exceptions/     # Custom exceptions
```

### 4. Coding Standards

- **Type annotations**: All functions must have type hints
- **Docstrings**: All public functions need comprehensive docstrings
- **Error handling**: Use custom exceptions from `exceptions/`
- **Async first**: Use async/await for I/O operations
- **Dependency injection**: Use ports/adapters pattern

Example:

```python
from typing import Dict, Any, Optional
from ..ports.ai_provider import AIProviderPort
from ..core.entities import DatabaseType, QueryResponse
from ..exceptions import ProviderException

class ExampleAdapter(AIProviderPort):
    """Example AI provider adapter following enterprise patterns."""

    def __init__(self, api_key: Optional[str] = None) -> None:
        """Initialize adapter with configuration.

        Args:
            api_key: API key for the provider

        Raises:
            ProviderException: If configuration is invalid
        """
        if not api_key:
            raise ProviderException("API key is required")
        self._api_key = api_key

    async def generate_query(self, context: QueryContext) -> QueryResponse:
        """Generate SQL query from natural language.

        Args:
            context: Query generation context with question and schema

        Returns:
            Generated query response with SQL and metadata

        Raises:
            ProviderException: If query generation fails
        """
        try:
            # Implementation here
            pass
        except Exception as e:
            raise ProviderException(f"Query generation failed: {e}") from e
```

## Contribution Types

### Bug Fixes

1. **Create issue** describing the bug with reproduction steps
2. **Write test** that reproduces the bug
3. **Fix the bug** ensuring test passes
4. **Update documentation** if behavior changes

### New Features

1. **Discuss in issue** before implementing large features
2. **Follow architecture** patterns (ports/adapters)
3. **Add comprehensive tests** (unit, integration, e2e)
4. **Update documentation** and examples
5. **Consider enterprise impact** (scale, performance, security)

### Enterprise Features

Priority areas for enterprise contributions:

- **New AI providers** (AWS Bedrock, Azure OpenAI, etc.)
- **Database support** (MySQL, SQLite, Oracle, MSSQL)
- **Performance optimizations** (caching, schema handling)
- **Security features** (audit logging, sanitization)
- **Monitoring** (metrics, health checks, alerting)

### Documentation

- **API documentation** (docstrings, type hints)
- **User guides** (tutorials, best practices)
- **Enterprise guides** (deployment, scaling, security)
- **Migration guides** (from other frameworks)

## Pull Request Process

### 1. Before Submitting

- [ ] Create/update tests for your changes
- [ ] Run full test suite (`uv run pytest`)
- [ ] Check code quality (`uv run ruff check .`)
- [ ] Update documentation if needed
- [ ] Test with example databases (`docker-compose up -d`)

### 2. PR Requirements

- **Clear description** of changes and motivation
- **Link to issue** (create one if none exists)
- **Test coverage** for new code
- **No breaking changes** without major version bump
- **Documentation updates** for user-facing changes

### 3. PR Template

```markdown
## Description
Brief description of changes and why they're needed.

## Type of Change
- [ ] Bug fix (non-breaking change fixing an issue)
- [ ] New feature (non-breaking change adding functionality)
- [ ] Breaking change (fix or feature causing existing functionality to change)
- [ ] Documentation update

## Testing
- [ ] Unit tests added/updated
- [ ] Integration tests added/updated
- [ ] Manual testing completed
- [ ] All tests pass

## Checklist
- [ ] Code follows style guidelines
- [ ] Self-review completed
- [ ] Documentation updated
- [ ] No new warnings introduced
```

### 4. Review Process

1. **Automated checks** must pass (CI/CD)
2. **Code review** by maintainer(s)
3. **Testing** in development environment
4. **Documentation review** for user-facing changes
5. **Merge** after approval

## Enterprise Contribution Guidelines

### Performance Considerations

- **Benchmark new features** with large schemas (1000+ tables)
- **Profile memory usage** for optimization opportunities
- **Test concurrent usage** patterns
- **Consider cache implications** for all changes

### Security Requirements

- **Never log sensitive data** (API keys, user data)
- **Validate all inputs** to prevent injection attacks
- **Use parameterized queries** for database operations
- **Follow least-privilege principles**

### Compatibility Standards

- **Backward compatibility** must be maintained
- **API changes** require deprecation notices
- **Database schema changes** need migration scripts
- **Multi-provider** changes should support all providers

## Development Priorities

### Current Focus Areas

1. **Database Support Expansion**
   - MySQL adapter implementation
   - SQLite support for local development
   - Oracle enterprise database support

2. **AI Provider Expansion**
   - AWS Bedrock integration
   - Azure OpenAI support
   - Custom model support (local/self-hosted)

3. **Enterprise Features**
   - Advanced audit logging
   - Role-based access control
   - Multi-tenant schema isolation

4. **Performance Optimization**
   - Query result caching
   - Schema embedding optimization
   - Connection pooling improvements

### Long-term Roadmap

- **Real-time query suggestions**
- **SQL query optimization recommendations**
- **Advanced analytics and reporting**
- **GraphQL support**
- **Streaming large result sets**

## Getting Help

### Communication Channels

- **GitHub Issues**: Bug reports, feature requests
- **GitHub Discussions**: Design discussions, questions
- **Email**: devhighlevel@gmail.com (enterprise inquiries)

### Response Times

- **Bug reports**: 24-48 hours
- **Feature requests**: 1-2 weeks
- **Pull requests**: 2-5 business days
- **Enterprise inquiries**: 24 hours

## Recognition

Contributors are recognized in multiple ways:

- **GitHub contributors list**
- **Release notes** for significant contributions
- **Enterprise contributor program** for ongoing contributors
- **Conference speaking opportunities** for major features

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

## Thank You

Every contribution helps make nlp2sql better for enterprise users worldwide. Whether it's a bug fix, new feature, documentation improvement, or performance optimization, your work is valued and appreciated!

For questions about contributing, please reach out through GitHub issues or email devhighlevel@gmail.com.
