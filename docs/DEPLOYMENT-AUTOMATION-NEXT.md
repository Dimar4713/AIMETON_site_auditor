# Следующая инфраструктурная задача

После завершения SA-01 выявлен разрыв между merge в `main` и фактическим stage deployment.

Текущий VPS-контур использует deployment bundle:

```text
/opt/aimeton/auditor-stack/app-source
/opt/aimeton/auditor-stack/app-source-sha.txt
Dockerfile
Docker Compose service: auditor
```

Self-hosted GitHub Actions runner установлен в `/home/ubuntu/actions-runner`, но автоматическая доставка свежего `main` в bundle и пересборка контейнера не подтверждена.

Следующая задача должна обеспечить:

1. запуск только после зелёного CI для `main`;
2. доставку точного commit SHA в новый временный bundle;
3. проверку обязательных файлов до переключения;
4. резервную копию предыдущего `app-source`;
5. атомарную замену bundle;
6. `docker compose build auditor` и `up -d --force-recreate auditor`;
7. ожидание healthy;
8. smoke-проверки `/api/health`, `/mcp` и MCP initialize;
9. автоматический rollback при неуспешном health/smoke;
10. запись развернутого SHA и результата deployment.
