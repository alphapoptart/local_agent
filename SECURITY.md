# Security Policy

## Protect your data

Local Agent can read and write files, run code, and access locally configured services. Run it with the same care you would use for any automation tool with access to your computer.

- Keep API keys, tokens, credentials, private prompts, and personal data out of commits.
- Store machine-specific values in environment variables or ignored local configuration files.
- Review commands and generated code before running the agent against important files.
- Use a dedicated workspace and least-privilege permissions where practical.
- Do not expose the local Ollama endpoint or agent process directly to the public internet.

Runtime memory, sessions, workspaces, generated media, logs, and local environment files are excluded by `.gitignore`.

## Reporting a vulnerability

Please report suspected vulnerabilities privately through GitHub's security-advisory reporting feature rather than opening a public issue. Include reproduction steps, affected files or versions, and the potential impact. Do not include real credentials or personal data in the report.
