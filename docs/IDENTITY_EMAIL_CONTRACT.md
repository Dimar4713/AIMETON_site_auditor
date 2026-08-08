# AIMETON Site Auditor — Identity & Email Contract

**Status:** adopted  
**Canonical architecture:** `Dimar4713/aimeton-architecture/Docs/ADR/ADR-011_AIMETON_Identity_and_Email_Namespace.md`

## Product rule

Site Auditor MUST use the AIMETON-wide identity model and MUST NOT create its own incompatible account/email namespace.

Identity classes are:

- Human
- Role
- Agent
- Service

## Site Auditor identities

### Product/service identity

- `auditor@aimeton.ru` — Site Auditor service identity for product-originated communication where a reply-capable service address is appropriate.
- `noreply@aimeton.ru` — notification-only sender where replies are intentionally unsupported.

### Customer-facing role

- `support@aimeton.ru` — support role address. It belongs to the support function, not to a specific person.

### Agents

Every durable Site Auditor agent MUST receive its own AIMETON Agent Identity and independent credentials. Examples may include `auditor-agent@aimeton.ru` or more stable role-neutral names registered in the central identity registry.

`agents@aimeton.ru` MAY be used as a group/dispatcher address but MUST NOT be used as a shared password/account for Site Auditor agents.

## Security requirements

1. SMTP/API credentials MUST be stored as deployment secrets, never in source control.
2. Each machine sender SHOULD have independently revocable credentials.
3. Email sender identity MUST match the actual actor class: service, agent, role, or human.
4. Site Auditor MUST NOT send automated mail as a human mailbox.
5. Production outbound mail requires valid SPF/DKIM/DMARC alignment for `aimeton.ru`.
6. Logs SHOULD capture the AIMETON identity id responsible for sending, while never logging secret credentials.

## Configuration direction

Preferred future configuration is identity-oriented rather than hard-coded email strings, for example:

```yaml
mail:
  sender_identity: aimeton.service.site-auditor
  support_identity: aimeton.role.support
  notification_identity: aimeton.service.noreply
```

Runtime resolution maps those identities to current addresses and secret references.

## Delivery stages

1. Establish `aimeton.ru` mail service and domain authentication.
2. Create/reserve `support@aimeton.ru`, `auditor@aimeton.ru`, and `noreply@aimeton.ru`.
3. Add secret-backed mail transport configuration to Stage.
4. Implement a minimal outbound notification path with test evidence.
5. Assign individual identities to operational Site Auditor agents.
6. Add audit logging tying outbound communication to AIMETON identity ids.

## Acceptance

The identity/email integration is accepted only when:

- no mail credential is committed to Git;
- sender authentication passes SPF/DKIM and DMARC alignment checks;
- support and service identities are distinct;
- agent identities are individually attributable/revocable;
- Stage evidence demonstrates successful delivery without exposing secrets.
