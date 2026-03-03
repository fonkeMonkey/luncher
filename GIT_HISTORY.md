# Git Commit History

This document explains the logical progression of commits in the Luncher project.

## 📋 Commit Structure

The project has been organized into **14 logical commits** following the natural implementation flow:

### Phase 1: Project Setup (Commits 1-2)
```
8b6bfd1 chore: initialize project with gitignore and env template
c59366c build: add project dependencies and build configuration
```
- Project structure
- Dependency management
- Environment configuration

### Phase 2: Core Foundation (Commits 3-4)
```
0c1a494 feat: add core data models and cache system
fae2dba feat: add configuration system
```
- Data models (MenuItem, DailyMenu, RestaurantConfig)
- File-based caching with TTL
- YAML configuration system
- Settings loader

### Phase 3: Scraper Architecture (Commit 5)
```
ea06820 feat: implement scraper foundation and registry
📍 Tag: v0.1.0-foundation
```
- BaseScraper abstract class
- ScraperRegistry for pluggable architecture
- Helper methods (price parsing, weekday names)
- Error handling

### Phase 4: Restaurant Scrapers (Commits 6-10)
```
94e14d3 feat: add U Telleru restaurant scraper
8da7fe8 feat: add Spravovna restaurant scraper
398fbff feat: add Pub Na Plech restaurant scraper
e5da836 feat: add Chilli & Lime restaurant scraper
fa03d77 feat: add PORKE restaurant scraper with Playwright
📍 Tag: v0.1.0-scrapers
```
Each scraper committed separately for clear history:
- **U Telleru**: Static HTML with BeautifulSoup
- **Spravovna**: Static HTML with menu detection
- **Pub Na Plech**: Static HTML with table parsing
- **Chilli & Lime**: Dynamic JSON from Next.js
- **PORKE**: Browser automation with Playwright

### Phase 5: User Interfaces (Commits 11-12)
```
c5c51b5 feat: implement CLI interface with Typer and Rich
ebe909d feat: implement web interface with FastAPI
```
- Beautiful CLI with colored tables
- Async command execution
- Web server with JSON API
- Responsive HTML/CSS frontend

### Phase 6: Documentation & Tools (Commits 13-14)
```
fc2481d docs: add comprehensive documentation
203d1a3 chore: add setup helper script
📍 Tag: v0.1.0-alpha (HEAD)
```
- README, QUICKSTART, IMPLEMENTATION_SUMMARY
- Automated setup script

## 🏷️ Version Tags

| Tag | Commit | Description |
|-----|--------|-------------|
| `v0.1.0-foundation` | ea06820 | Scraper architecture complete |
| `v0.1.0-scrapers` | fa03d77 | All 5 scrapers implemented |
| `v0.1.0-alpha` | 203d1a3 | Full alpha release |

## 📊 Statistics

```bash
Total Commits: 14
Total Files: 26 Python files + docs
Lines of Code: ~6,000 LOC
```

### Commit Breakdown by Type
- `feat:` 10 commits (features)
- `docs:` 1 commit (documentation)
- `build:` 1 commit (dependencies)
- `chore:` 2 commits (setup & tools)

## 🔄 Viewing History

### Show all commits with graph
```bash
git log --oneline --graph --decorate
```

### Show commits with files changed
```bash
git log --stat
```

### Show commits between tags
```bash
git log v0.1.0-foundation..v0.1.0-scrapers --oneline
```

### Show specific commit details
```bash
git show 94e14d3  # U Telleru scraper
```

### View file at specific commit
```bash
git show 0c1a494:src/luncher/core/models.py
```

## 🌳 Branch Structure

Currently on: `master` (single branch)

Future branches could include:
- `develop` - Development branch
- `feature/*` - Feature branches
- `fix/*` - Bug fix branches
- `refactor/*` - Refactoring branches

## 📝 Commit Message Convention

We follow conventional commits:

- `feat:` - New feature
- `fix:` - Bug fix
- `docs:` - Documentation
- `chore:` - Maintenance
- `build:` - Build system/dependencies
- `refactor:` - Code refactoring
- `test:` - Tests

## 🎯 Clean History Benefits

Each commit represents a **logical unit of work**:

1. ✅ **Easy to understand** - Clear progression
2. ✅ **Easy to review** - One feature per commit
3. ✅ **Easy to revert** - Isolated changes
4. ✅ **Easy to cherry-pick** - Self-contained commits
5. ✅ **Good documentation** - Commit messages tell the story

## 🔍 Example: Tracing a Feature

Want to see how the CLI was built?

```bash
# Show the CLI commit
git show c5c51b5

# Show what files were changed
git diff c5c51b5^..c5c51b5

# Show the commit in context
git log --oneline --graph c5c51b5
```

## 🚀 Next Steps

Future development suggestions:

1. **Create `develop` branch**
   ```bash
   git checkout -b develop
   ```

2. **Feature branches for improvements**
   ```bash
   git checkout -b feature/fix-scraper-prices
   git checkout -b feature/add-tests
   ```

3. **Tag releases**
   ```bash
   git tag -a v0.2.0 -m "Beta release"
   ```

## 📚 References

- [Conventional Commits](https://www.conventionalcommits.org/)
- [Semantic Versioning](https://semver.org/)
- [Git Best Practices](https://git-scm.com/book/en/v2)

---

*Generated with ❤️ by Claude Code*
