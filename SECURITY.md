# Security Policy

## Scope and threat model

`iac-llm-wrapper` is a design-time decision harness. It does not make cloud API calls and does not deploy infrastructure directly. Security focus is therefore:

- software supply chain risk in dependencies
- insecure coding patterns in repository code
- safe handling of decision artifacts and user inputs

## Raw LLM evidence

LLM-backed runs can preserve raw prompt/response evidence for auditability. That
evidence is useful and should be kept with the handoff bundle, but it can contain
customer design prose, account names, topology, control requirements, and model
outputs. Store it in restricted output locations, keep secrets out of design
docs, pass API keys through environment variables or `--api-key`, and redact raw
evidence before sharing outside the project team.

## Secret references

Do not put secret values in design docs, eval fixtures, prompts, raw evidence, or
handoff artifacts. Use secret-store references and expected parameter names so
secret values do not travel through the model, local evidence files, Git, review
HTML, or downstream handoff bundles. Acceptable inputs are references such as
`aws-secretsmanager://team/app/db#password`,
`aws-ssm-parameter://team/app/api-key`, or an approved enterprise vault URI plus
the owner and validation expectation. Downstream IaC or deployment tooling is
responsible for resolving those references under its own access controls.

## CI security checks

The `security` CI job runs:

- `pip-audit --skip-editable`
- `bandit -c bandit.yaml -r src -q -ll`

Policy:

- Fail on any unresolved dependency vulnerability from `pip-audit`.
- Fail on Bandit findings with medium/high severity (`-ll`).
- Fix findings in code. Document in the pull request only if a finding is a confirmed false positive.

## Reporting vulnerabilities

If you find a vulnerability, open a private security advisory or contact maintainers directly. Please include:

- affected version and component
- reproduction steps
- impact assessment
- suggested remediation (if known)
