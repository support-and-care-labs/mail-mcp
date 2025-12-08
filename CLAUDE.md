# CLAUDE.md - mail-mcp

This file provides guidance to Claude Code (claude.ai/code) when working with the **mail-mcp** project.

## Project Overview

The **mail-mcp** project is an MCP (Model Context Protocol) server for accessing and analyzing Apache Maven mailing list archives. It provides tools to retrieve and process historical email discussions from Maven mailing lists (primarily dev@maven.apache.org).

## Part of maven-mcps

This is one MCP server within the **maven-mcps** umbrella project. See `../CLAUDE.md` for the overall repository structure.

### Sibling MCP Projects

*(Currently mail-mcp is the only project. Future siblings will be listed here with 1-2 line descriptions. Read their CLAUDE.md files for details.)*

## Data Structure

- `data/dev/` - Contains 276+ monthly mbox files from 2002-present (~743MB total)
  - Format: `YYYY-MM.mbox` (e.g., `2024-10.mbox`)
  - Content: ASCII/SGML text in standard Unix mbox format
- `src/mail_mcp/` - Python source code
- `docs/` - Project-specific documentation in AsciiDoc format
- `docs/adr/` - Architecture Decision Records
- `tests/` - Test files (future)
- `tmp/` - Temporary files during processing
- `README.adoc` - Project overview and getting started guide
- `../docs/adr/` - Project-wide Architecture Decision Records (at root level)

## Common Commands

### Retrieve Mailing List Archives

```bash
# Download a specific month
poetry run retrieve-mbox --date 2024-10

# Download from a different list
poetry run retrieve-mbox --date 2024-09 --list users@maven.apache.org

# Show help
poetry run retrieve-mbox --help
```

### Update Current Month (Scheduled Task)

```bash
# Manually update and re-index the current month's mbox
poetry run update-current-month --list dev@maven.apache.org --data-dir ./data

# This runs automatically every hour via the scheduler container
```

### Script Details: retrieve-mbox (Python)

- **Purpose**: Downloads mbox files from Apache's mail archive API
- **API Endpoint**: `https://lists.apache.org/api/mbox.lua`
- **Dependencies**: Python 3.11+, httpx (managed via Poetry)
- **Installation**: `poetry install` (creates virtual environment automatically)
- **Arguments**:
  - `--date <yyyy-mm>` (required): Year and month to retrieve
  - `--list <list@domain>` (optional): Mail list address (default: dev@maven.apache.org)
- **Output**: Creates `<yyyy-mm>.mbox` in current directory
- **Error Handling**: Validates date format, checks HTTP status, uses atomic file moves
- **Location**: `src/mail_mcp/cli/retrieve_mbox.py`

### Script Details: update-current-month (Python)

- **Purpose**: Downloads and re-indexes the current month's mbox file
- **Use Case**: Keeps the Elasticsearch index up-to-date with latest emails
- **Dependencies**: Python 3.11+, httpx, elasticsearch client
- **Arguments**:
  - `--list <list@domain>` (optional): Mail list address (default: dev@maven.apache.org)
  - `--data-dir <path>` (optional): Data directory (default: /app/data)
- **Location**: `src/mail_mcp/cli/update_current_month.py`

### Docker Compose Services

The `docker-compose.yml` defines the following services:

- **elasticsearch**: Elasticsearch 8.11 for storing and searching email data
- **kibana**: Kibana for data visualization
- **mail-mcp**: The MCP server (HTTP transport on port 58080)
- **scheduler**: Runs hourly to fetch and re-index the current month's mbox

```bash
# Start all services including scheduler
docker compose up -d

# View scheduler logs
docker compose logs -f scheduler

# Manually trigger an update (runs inside scheduler container)
docker compose exec scheduler update-current-month
```

## Architecture

### Current State
- **Python 3.11+**: Single-language codebase using Python
- **Poetry**: Dependency management and virtual environment
- **Data retrieval infrastructure**: CLI tool for downloading mbox files
- **No MCP server implementation yet**: Server component planned (see ADR-0002)
- **Data storage**: mbox files NOT tracked in Git (regenerable)

### Technology Stack
- **Python 3.11+**: Implementation language
- **httpx**: Async HTTP client for Apache API requests
- **Elasticsearch 8.11+**: Planned storage backend (see ADR-0001)
- **mcp SDK**: Model Context Protocol server framework (planned)
- **mbox format**: Standard Unix mailbox format
- **Apache Lists API**: REST API for accessing mail archives

## Development Notes

### Documentation Standards
- **All documentation must be in AsciiDoc format** (`.adoc` files)
- **AsciiDoc formatting conventions (lists, line breaks, etc.) are defined in `~/.claude/CLAUDE.md`** (global configuration)
- See `../CLAUDE.md` for full documentation standards and project structure
- See `../docs/adr/0001-documentation-standards.adoc` for project-wide ADRs
- Project overview: `README.adoc`
- Project-specific detailed documentation: `docs/`
- Project-specific architecture decisions: `docs/adr/`

### Architecture Decisions
- `docs/adr/0001-storage-and-access-strategy.adoc` - Storage backend selection (Elasticsearch chosen)
- `docs/adr/0002-technology-stack.adoc` - Technology stack (Python 3.11+, libraries, project structure)

### Data Management
- **Data files are NOT tracked in Git** - the `data/` directory is excluded from version control
- All mbox files can be regenerated at any time using `poetry run retrieve-mbox`
- This keeps the repository size manageable (~743MB of data not in Git)
- When cloning this repository, retrieve needed data using: `poetry install && poetry run retrieve-mbox --date YYYY-MM`

### Virtual Environment
- **Poetry manages dependencies** - automatically creates `.venv/` directory
- **Setup**: `poetry config virtualenvs.in-project true && poetry install`
- **Activation**:
  - Manual: `poetry shell` (or use `poetry run <command>`)
  - Automatic: `direnv` (optional) - see README.adoc for `.envrc` example
- **No system pollution**: All Python packages installed in isolated virtual environment

### Future MCP Implementation
When implementing the MCP server component:
- Expose tools for searching/querying mbox files
- Provide resources for accessing email threads and metadata
- Consider indexing for faster searches across 20+ years of archives

## Context for Future Claude Instances

**Remember**:
- This project is part of the maven-mcps multi-project repository
- Check `../CLAUDE.md` for overall repository context
- When referencing other MCP servers, read their specific CLAUDE.md files
- This file is the single source of truth for mail-mcp implementation details
