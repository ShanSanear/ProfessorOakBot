# Running Tests (for cursor/copilot)

```bash
# Activate virtual environment
.\.venv\Scripts\Activate.ps1

# Run all tests
python -m pytest tests -v

# Run specific test
python -m pytest tests/test_graphics_monitor.py::TestDateParser::test_invalid_date_format_single_date -v
```
