# Contributing to OpenCursor

First off, thanks for taking the time to contribute! All types of contributions are encouraged and valued.

> Please make sure to read the relevant section before making your contribution. It will smooth out the experience for everyone involved.

## Code of Conduct

This project and everyone participating in it is governed by the [OpenCursor Code of Conduct](.github/CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code. Please report unacceptable behaviour to <k4cpergadomski@gmail.com>.

## I Have a Question

Before you ask a question, it's best to search for existing [Issues](https://github.com/alteredorange/opencursor/issues) that might help you. If you find a suitable issue and still need clarification, you can write your question in that issue.

If you still feel the need to ask a question:

- Open an [Issue](https://github.com/alteredorange/opencursor/issues/new)
- Provide as much context as you can about what you're running into
- Include your OS, Python version, and model adapter you're using

## Ways to Contribute

### Bug Reports

A good bug report shouldn't leave others needing to chase you down for more information. Please investigate carefully, collect information, and describe the issue in detail in your report.

- Make sure that you are using the latest version
- Confirm that your issue is actually a bug and not a configuration error (e.g., missing API keys, unsupported model)
- Check if there is already a bug report for your issue in the [issue tracker](https://github.com/alteredorange/opencursor/issues)
- Collect relevant information:
  - OS and Python version
  - Model adapter and model ID being used
  - Stack trace (if applicable)
  - Steps to reproduce the issue
  - Expected vs actual behaviour

> **Important**: If you find a **security vulnerability**, please do NOT report it in the issue tracker. Instead, refer to our [Security Policy](.github/SECURITY.md).

### Enhancement Suggestions

Enhancement suggestions are tracked as [GitHub issues](https://github.com/alteredorange/opencursor/issues).

- Use a **clear and descriptive title** for the issue
- Provide a **step-by-step description** of the suggested enhancement
- **Describe the current behaviour** and **explain which behaviour you expected** instead, and why
- **Explain why this enhancement would be useful** to most OpenCursor users, not just your use case

### Code Contributions

Ready to contribute code? Here's how:

1. Fork the repository and create a branch from `main`
2. Set up your development environment:
   ```bash
   git clone https://github.com/your-username/opencursor.git
   cd opencursor
   pip install -r requirements.txt
   ```
3. Make your changes, following the existing code style and patterns
4. Test your changes manually with a few different model adapters if relevant
5. Submit a pull request with a clear description of what you changed and why

#### Architecture Notes

If you're adding a new model adapter, see the [README](../README.md#adding-a-new-model-adapter) for the pattern. Key points:
- Extend `ModelAdapter` from `adapters/base.py`
- Implement `build_client()`, `_call_api()`, and `get_prompt_overrides()`
- Register it in `adapters/__init__.py`

#### Style Guidelines

- Keep it simple and explicit over clever
- DRY: avoid repetition, use the base class helpers
- Handle edge cases thoroughly
- Don't over-abstract; three similar lines is better than a premature helper

### Documentation

Improvements to the README, docstrings, or inline comments are always welcome. If you've found something confusing or undocumented, chances are others have too.

## Your First Code Contribution

Not sure where to start? Look for issues tagged with `good first issue` or `help wanted`. These are typically well-scoped and beginner-friendly.

## Attribution

By contributing, you agree that your contributions will be licensed under the [MIT License](../LICENSE).
