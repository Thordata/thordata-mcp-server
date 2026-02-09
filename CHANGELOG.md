# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.6.0] - 2026-02-09

### Added
- Comprehensive error handling with detailed diagnostic information
- Special character detection in search queries with helpful error messages
- Empty result hints for better user experience (Chinese queries, Bing engine)
- Batch operation support with error isolation
- HTTP status code mapping (404, 500, 403, etc.) with clear error messages
- Smart tool selection in `smart_scrape` with automatic fallback

### Fixed
- HTTP 200 status code no longer incorrectly identified as error
- Special character handling now provides detailed error information
- Batch search empty results now include helpful notes
- `unlocker_batch` now properly identifies 404 errors with `ok=false`
- `smart_scrape` timeout issues resolved

### Improved
- Error messages are now more descriptive and actionable
- Batch operations have better error handling and isolation
- Performance optimizations for response times
- LLM-friendly tool descriptions and parameter documentation

### Changed
- Enhanced error response format with structured error details
- Improved batch operation response format with per-item status

## [0.5.0] - Previous Version

### Initial Release
- Core MCP server implementation
- Basic tool set (search_engine, unlocker, browser, smart_scrape)
- SERP API integration
- Browser automation support

---

[0.6.0]: https://github.com/thordata/thordata-mcp-server/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/thordata/thordata-mcp-server/releases/tag/v0.5.0
