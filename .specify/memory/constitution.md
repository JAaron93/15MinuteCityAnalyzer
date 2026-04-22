# 15MinuteCityAnalyzer Constitution

## Core Principles

### I. Code Quality
All code must follow PEP 8 style guidelines with type hints throughout. Functions should be small, focused, and well-documented with docstrings. Maximum complexity: 10 McCabe score. Code review required for all PRs. No raw data processing in notebooks without corresponding production-ready modules.

### II. Testing Standards (NON-NEGOTIABLE)
Minimum 80% code coverage required. All new features require tests before implementation (TDD). Unit tests with pytest for all modules. Integration tests for data pipelines and ML model training workflows. Property-based testing for data transformation functions. Tests must pass in CI before merge.

### III. User Experience Consistency
All CLI tools follow consistent argument patterns (--input, --output, --verbose). Visualization outputs use standardized color palettes and accessible themes. API endpoints follow REST conventions with consistent error response formats. Documentation includes runnable examples for every public function. Breaking changes require deprecation warnings across 2 minor versions.

### IV. Performance Requirements
Data loading operations must stream or chunk for datasets >100MB. Vectorized numpy/pandas operations preferred over loops. ML model inference must complete in <500ms per request. Caching strategy for expensive geospatial computations. Memory profiling required for production data pipelines. Benchmark tests for critical paths.

## Technology Constraints

- Python 3.10+ required
- Dependencies pinned in requirements.txt with minimum versions
- No vendor-locked geospatial APIs without abstraction layer
- All data transformations must be reproducible with seeded random states
- ML models versioned alongside code (DVC or similar)

## Development Workflow

1. Create spec document for new features
2. Write tests first (failing CI expected)
3. Implement to satisfy tests
4. Performance benchmark critical paths
5. Code review by at least one maintainer
6. Merge only when all checks pass

## Governance

This constitution supersedes all other development practices. Amendments require documentation update and team approval. All PRs must verify compliance through automated checks. Complexity must be justified with performance or UX benefits.

**Version**: 1.0.0 | **Ratified**: 2026-04-19 | **Last Amended**: 2026-04-19
