---
name: review-pr
description: Reviews a pull request for quality, security, and correctness. Use when the user asks to review a PR, check a pull request, or provides a PR number to review.
---

# Review PR

Review a pull request for quality, security, and correctness.

## Checklist

1. **Read the PR**: Run `gh pr view <pr-number>` and `gh pr diff <pr-number>`
2. **Understand scope**: What is this PR trying to accomplish?
3. **Review for correctness**:
   - Does the code do what it claims?
   - Are there edge cases not handled?
   - Are there off-by-one errors, null pointer risks, or race conditions?
4. **Review for architecture**:
   - Does this follow existing patterns in the codebase?
   - Is there code duplication that should be extracted?
   - Are new dependencies justified?
5. **Review for security**:
   - Input validation on external data?
   - SQL injection, XSS, or other OWASP risks?
   - Secrets or credentials exposed?
6. **Review for testing**:
   - Are new behaviors covered by tests?
   - Are edge cases tested?
7. **Summarize**: Provide a clear summary with specific, actionable feedback
