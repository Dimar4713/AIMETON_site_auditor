# Dependency Vault adoption — AIMETON Site Auditor

Статус: обязательный project contract.

Каноническая политика: `Dimar4713/aimeton-architecture/Docs/Governance/AIMETON_DEPENDENCY_VAULT_POLICY.md`.
Эталонная реализация: `Dimar4713/aimeton-infrastructure/dependency-vault`.

## Правила проекта

- stage/prod deploy не устанавливает Python-пакеты из публичных registry;
- exact dependency set импортируется controlled workflow в Dependency Vault;
- обязательны hashes, provenance, SBOM, лицензии, vulnerability evidence и offline smoke;
- findings переводят candidate в `review_required`;
- автоматический promotion и автоматическое изменение active bundle запрещены;
- отсутствие внутреннего bundle или evidence означает fail closed;
- изменение `requirements.txt` требует нового exact-SHA import и повторного security gate;
- merge PR с зависимостями не завершает миссию до подтверждения внутреннего bundle и stage evidence.

## CI/deploy enforcement

Deployment workflow и regression tests должны запрещать:

- `pip install` во время stage/prod deploy;
- обращения к `pypi.org` и иным публичным package registries в deploy critical path;
- установку непроверенных зависимостей вне Dependency Vault.

Исключение возможно только отдельным архитектурным решением с явным владельцем риска и сроком устранения.