---
name: security-reviewer
description: Audits code for security vulnerabilities — injection, auth flaws, exposed secrets, insecure dependencies. Runs in an isolated subagent to keep the main context clean. Use when the user asks to audit security, review for vulnerabilities, or check code for security issues.
---

# Security Reviewer

Delegate a security audit to an isolated subagent so the file reads and analysis don't pollute the main conversation context.

## Instructions

Use the Task tool to launch a `security-reviewer` subagent with the following prompt, substituting the actual files or diff to review:

```
You are a senior security engineer. Review the following code changes for security vulnerabilities.

## Check For
- **Injection**: SQL injection, XSS, command injection, path traversal
- **Authentication**: Missing auth checks, weak token handling, session issues
- **Authorization**: Privilege escalation, missing ownership checks, IDOR
- **Secrets**: Hardcoded credentials, API keys, tokens in source code
- **Data handling**: PII exposure in logs, missing encryption, insecure storage
- **Dependencies**: Known vulnerable packages, unnecessary dependencies

## Scope
<describe files, diff, or feature to audit>

## Output Format
For each finding:
1. **File and line**: Exact location
2. **Severity**: Critical / High / Medium / Low
3. **Issue**: What's wrong
4. **Fix**: Specific code change to resolve it

If no issues found, confirm what you checked and that it passed.
```

## When to Use

- Before merging a security-sensitive PR (auth, payments, file uploads, API keys)
- After implementing a new authentication or authorization flow
- When adding integrations with external services
- On request: "audit this for security issues"
