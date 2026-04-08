# Security Controls Matrix

## Data Protection

- hosted client data at rest: AES-256 managed encryption
- database backup storage: AES-256 server-side encryption
- endpoint full disk encryption: BitLocker on managed Windows devices
- external communications: TLS 1.2 or higher

## Access Control

- MFA required for administrative access
- privileged accounts reviewed monthly
- role-based access used for service desk, infrastructure, and security functions

## Monitoring

- centralized logging to Azure Monitor and SIEM
- endpoint protection through SentinelOne
- firewall alert review during business hours with severity-based escalation

## Continuity

- daily backup validation for tier-1 hosted workloads
- quarterly disaster recovery exercise
- replication target for tier-1 systems: 15-minute RPO by Q3 2025
