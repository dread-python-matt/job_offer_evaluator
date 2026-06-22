# User Profile

## Summary
Python Developer with 2 years of commercial software engineering experience in C# and embedded systems. 
Focused on backend engineering and clean, maintainable Python code. Continuously improving skills in modern 
backend development, testing, automation and AI-related solutions.

## Skills
- Python: 4
- Django: 3
- SQL: 3
- Docker: 2
- pytest: 3
- Git: 3
- PostgreSQL: 2
- Clean Code: 4
- REST API: 3
- LLM integration: 3
- fastapi: 3
- Alembic: 3
- Pydantic: 3

## Projects
### Institute of Alternative Zoology
- Repository: https://github.com/romanroman008/institute_of_alternative_zoology
- Period: 2026-01 - 2026-06
- Tech Stack: Python, Django, PostgreSQL, Docker, Gunicorn, Render, Tailwind

Built a simple Django web application to practice views, routing, templates and project configuration.
Deployed on Render platform

### Article Scraper
- Repository: https://github.com/romanroman008/article_scraper
- Period: 2025-10 - 2025-10
- Tech Stack: Python, Django, DRF, PostgreSQL, Docker, BeautifulSoup, requests

Built a Django application for scraping articles from provided URLs and storing metadata in PostgreSQL.
Implemented a management command for running the scraper with custom or default URL inputs.
Exposed article data through REST API endpoints with list, detail and source-domain filtering

### NLP engine for Polish ingredient parsing
- Repository: https://github.com/romanroman008/ingredient_regex_engine
- Period: 2026-01 - 2026-05
- Tech Stack: Python, Pydantic, OpenAI Agents SDK, Morfeusz2, SQLAlchemy, Alembic, pytest, GitHub Actions

Built a production-oriented NLP engine for extracting structured ingredient data from semi-structured 
Polish text.
Designed a hybrid LLM + regex pipeline where LLMs generate reusable parsing patterns, while runtime 
extraction remains fully deterministic and model-free.
Implemented Polish inflection-aware normalization using Morfeusz2, supporting morphological variants of 
ingredient names, units and conditions.
Designed the system using Hexagonal Architecture / Ports & Adapters to separate domain logic, parsing, 
persistence and infrastructure concerns.
Maintained 84%+ test coverage with pytest and automated validation in GitHub Actions

## Experience
### Junior .NET Developer
- Company: Wojskowe Zakłady Uzbrojenia
- Period: 2023-02 - 2025-02
- Tech Stack: c#

Designed and implemented modular C# components for embedded systems used in military hardware.
Developed desktop applications supporting internal engineering and hardware-related workflows.
Implemented UDP-based network communication between software components and external devices.
Worked with system-level constraints, hardware integration and reliability-focused development
