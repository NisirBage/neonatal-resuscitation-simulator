# Contributing

Thank you for your interest in the Neonatal Resuscitation Simulator.

## Before You Begin

- Read the [README](README.md) to understand the architecture and deployment model.
- Check open issues before opening a new one to avoid duplicates.

## Development Setup

```bash
# 1. Clone the repository
git clone https://github.com/NisirBage/neonatal-resuscitation-simulator.git
cd neonatal-resuscitation-simulator

# 2. Backend
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
cp ../.env.local.example ../.env
cd ..

# 3. Frontend
cd frontend
npm install
```

See the **Quick Start** section in [README.md](README.md) for full run instructions.

## Running Tests

```bash
# Backend (from backend/)
pytest tests/ -v

# TypeScript check (from frontend/)
npx tsc --noEmit
```

## Contribution Guidelines

### What is in scope

- Bug fixes
- Documentation improvements
- New scenario files (JSON)
- Test coverage improvements
- Performance improvements (without changing external API contracts)

### What is out of scope

- Changes to the FSM logic that alter scenario behaviour
- New clinical workflows (these require subject-matter expert review)
- Breaking changes to REST API contracts or WebSocket event schemas

### Pull Request Process

1. Fork the repository and create a feature branch from `main`.
2. Write tests for any new behaviour.
3. Ensure `pytest` and `npx tsc --noEmit` both pass.
4. Open a pull request with a clear description of what changed and why.
5. One maintainer review is required before merging.

## Code Style

- **Python**: follow PEP 8; use `ruff` or `black` for formatting.
- **TypeScript**: follow the existing project conventions; run `tsc --noEmit` before committing.
- Comments should explain *why*, not *what* — well-named identifiers speak for themselves.

## Commit Messages

Use the imperative mood: `Add X`, `Fix Y`, `Remove Z`.  
Reference issue numbers where relevant: `Fix WebSocket reconnect on backend restart (#42)`.
