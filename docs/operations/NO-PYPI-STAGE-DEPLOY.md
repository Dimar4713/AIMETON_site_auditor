# Stage deploy without PyPI

Status: accepted for stage deployment.

The stage deployment workflow must not install Python packages from PyPI at deploy time.

Operational contract:

- deploy runs only with tools already present on the self-hosted stage runner;
- OpenStack SDK installation is not a deployment prerequisite;
- local Docker, stack directory, stage health and exact SHA checks are the preflight gate;
- missing local prerequisites fail closed before bundle switching;
- provider credentials remain GitHub Environment secrets;
- Tavily and Yandex are enabled only inside explicit free-tier quotas and mission budgets;
- exhaustion of quota must stop further calls rather than create unapproved spend.

Related: #336.
