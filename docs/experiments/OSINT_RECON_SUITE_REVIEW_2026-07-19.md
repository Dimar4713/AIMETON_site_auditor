# Review: Panda1847/osint-recon-suite

Date: 2026-07-19

## Executive conclusion

`Panda1847/osint-recon-suite` is useful as a taxonomy of OSINT capabilities and as a checklist of possible reconnaissance stages, but it is not ready to be adopted as an executable dependency for AIMETON Site Auditor.

The repository presents itself as a comprehensive framework with automated scripts for company, person and domain reconnaissance. However, the inspected repository is extremely small, and a representative advertised executable path (`scripts/company_recon.sh`) is absent. The available material is dominated by a large README and a dependency list. Therefore the project should be treated as a concept catalogue, not as a verified implementation.

## Positive findings

The README contains a useful decomposition of OSINT work into:

- corporate OSINT;
- technical and domain OSINT;
- news and mentions;
- technology stack;
- social presence;
- public corporate records;
- reporting and correlation;
- passive and active reconnaissance phases.

For AIMETON, the most valuable concepts are:

1. passive domain intelligence: DNS, WHOIS, public certificates, subdomains and ASN data;
2. passive technology fingerprinting from public pages and headers;
3. corporate registration and company identity resolution;
4. news and mention collection;
5. employee and vacancy signals;
6. correlation into a structured company dossier;
7. separation of passive and active reconnaissance.

The repository contains an MIT license. This permits reuse of actual code if such code is later verified and attribution requirements are followed.

## Critical gaps

### 1. Advertised scripts are not present

The README describes commands such as:

```bash
./scripts/company_recon.sh "Example Corp"
./scripts/domain_recon.sh example.com
./scripts/passive_recon.sh target.com
./scripts/active_recon.sh target.com
```

At least the inspected `scripts/company_recon.sh` path does not exist. Code search also returned the README rather than executable implementations.

### 2. README maturity exceeds repository maturity

The README claims:

- 20+ automated workflows;
- complete company intelligence;
- automated setup;
- verification scripts;
- structured reports;
- broad multi-platform support.

These claims are not supported by the visible repository contents inspected in this review.

### 3. Dependency risks

The requirements include many externally maintained OSINT packages with varying update quality and terms of service. Some categories are inappropriate for AIMETON's commercial hunting mode, especially:

- breach-data tools;
- personal account enumeration;
- active port scanning;
- aggressive social-media scraping;
- dark-web monitoring without a specific lawful objective.

### 4. Active reconnaissance conflicts with the default AIMETON mode

Site Auditor should operate as a passive business-intelligence system. Port scans, active enumeration and direct infrastructure probing are not necessary for identifying commercial opportunities and may create legal, ethical and operational risk.

## Integration decision

Do not vendor or install the suite as a whole.

Adopt only the following concepts as independently implemented adapters:

- passive DNS and WHOIS;
- public certificate transparency (`crt.sh` or equivalent);
- public web technology fingerprinting;
- official company and legal registries;
- news and mention search;
- vacancies and organizational signals;
- public corporate contact roles;
- structured timeline and evidence correlation.

Explicitly exclude from the default commercial workflow:

- Nmap and port scans;
- breach-data searches;
- email-account enumeration;
- personal dossiers;
- dark-web collection;
- unauthorized social-network scraping;
- active infrastructure probing.

## Architecture impact

The AIMETON OSINT catalogue was extended with:

- `passive_domain_intelligence`;
- `technology_fingerprint`;
- `public_contact_resolution`;
- technical-infrastructure and digital-maturity scent dimensions;
- rules separating passive research from active scanning;
- prohibition on using leaked data and personal dossiers for commercial contact.

## Canonical role in Esseter

The external repository contributes to the `обнаружение экономических сигналов` stage only when the information is publicly available, lawfully accessed and commercially relevant.

Its technical ideas support the sequence:

```text
публичный цифровой след
→ пассивная техническая идентификация
→ изменение цифровой зрелости
→ экономическая гипотеза
→ квалификация коммерческой возможности
```

They must not transform Site Auditor into a vulnerability scanner or personal-surveillance toolkit.
