"""Original synthetic Northstar Workshop fixtures; never real incident resolution truth."""

import json
from pathlib import Path

from opspilot.domain import Ticket
from opspilot.store import Store

# service, symptom, safe checks, escalation. Three distinct runbooks per service.
TOPICS = [
    (
        "vpn",
        "VPN certificate expired",
        "Check certificate expiry and device clock",
        "Identity team",
    ),
    ("vpn", "VPN tunnel timeout", "Check gateway status and UDP reachability", "Network team"),
    ("vpn", "VPN split tunnel DNS", "Compare internal DNS answers on and off VPN", "Network team"),
    (
        "identity",
        "MFA enrollment failure",
        "Verify enrollment policy and approved factor",
        "Identity team",
    ),
    (
        "identity",
        "Account locked sign in",
        "Inspect lockout timestamps and stale clients",
        "Identity team",
    ),
    (
        "identity",
        "SSO token expired",
        "Check token audience and device time drift",
        "Identity team",
    ),
    (
        "m365",
        "Teams meeting audio",
        "Check selected audio device and client permissions",
        "Collaboration team",
    ),
    (
        "m365",
        "SharePoint access denied",
        "Compare requested site with group membership",
        "Site owner",
    ),
    (
        "m365",
        "OneDrive sync conflict",
        "Check quota and preserve both file versions",
        "Collaboration team",
    ),
    (
        "email",
        "Email delivery delayed",
        "Check mail queue age and service health",
        "Messaging team",
    ),
    (
        "email",
        "Mailbox quota full",
        "Inspect usage and retention policy before deletion",
        "Messaging team",
    ),
    (
        "email",
        "Email phishing attachment",
        "Preserve message headers and isolate attachment",
        "Security team",
    ),
    (
        "network",
        "Internal DNS resolution",
        "Query configured resolver and compare TTL",
        "Network team",
    ),
    (
        "network",
        "Office WiFi disconnect",
        "Inspect signal strength and access point health",
        "Network team",
    ),
    (
        "network",
        "DHCP address exhaustion",
        "Inspect lease pool usage without changing leases",
        "Network team",
    ),
    (
        "device",
        "Laptop disk space",
        "Inspect disk usage and approved cleanup policy",
        "Device team",
    ),
    (
        "device",
        "Laptop boot recovery",
        "Record recovery screen and verify asset ownership",
        "Device team",
    ),
    (
        "device",
        "Device update pending",
        "Check update history and maintenance window",
        "Device team",
    ),
    (
        "cicd",
        "CI runner offline",
        "Check runner heartbeat and queued pipeline jobs",
        "Platform team",
    ),
    (
        "cicd",
        "Pipeline artifact missing",
        "Check retention and producing job result",
        "Platform team",
    ),
    (
        "cicd",
        "Deploy registry authentication",
        "Check service identity scope and token expiry",
        "Platform team",
    ),
    (
        "business",
        "ERP invoice timeout",
        "Check application health and database read latency",
        "Business apps team",
    ),
    (
        "business",
        "CRM report unavailable",
        "Check report permissions and scheduled refresh",
        "Business apps team",
    ),
    (
        "business",
        "Payroll export validation",
        "Check schema version and redacted error code",
        "Business apps team",
    ),
]


def seed(store: Store, kb_dir: Path) -> dict:
    kb_dir.mkdir(parents=True, exist_ok=True)
    for i, (service, symptom, checks, owner) in enumerate(TOPICS):
        doc = f"kb-{i + 1:02d}"
        content = (
            f"# {symptom}\n\nDocument-ID: {doc}\nService: {service}\n"
            f"Origin: SYNTHETIC Northstar Workshop\nOwner: {owner}\n\n"
            f"## Symptoms\n{symptom} reported by a Northstar employee.\n\n"
            f"## Read-only investigation\n1. {checks}.\n"
            f"2. Compare incident onset with the {service} service health fixture.\n"
            "3. Collect timestamps, affected scope and sanitized error messages.\n\n"
            "## Safe resolution guidance\nUse the approved service recovery process after "
            "the owner confirms the cause. Do not reset accounts, delete files, restart "
            "services or change permissions automatically. Record an investigation note "
            "for review. An uncertain diagnosis should be escalated.\n\n"
            f"## Escalation\nContact {owner} with evidence and impact. "
            "Preserve logs; do not include credentials or personal data.\n"
        )
        (kb_dir / f"{doc}-{service}.md").write_text(content, encoding="utf-8")
    for i in range(32):
        service, symptom, checks, owner = TOPICS[i % len(TOPICS)]
        ticket = Ticket(
            id=f"DEMO-{i + 1:03d}",
            title=symptom,
            description=f"{symptom}. Employee cannot continue work. {checks}.",
            severity="medium",
            origin="SYNTHETIC",
        )
        store.put("tickets", ticket.id, ticket.model_dump())
        store.put(
            "incidents",
            f"HIST-{i + 1:03d}",
            {
                "id": f"HIST-{i + 1:03d}",
                "service": service,
                "symptom": symptom,
                "resolution": f"{owner} verified the cause and confirmed recovery under policy.",
                "origin": "SYNTHETIC",
                "checks": checks,
            },
        )
    for service in sorted({t[0] for t in TOPICS}):
        store.put(
            "health",
            service,
            {
                "service": service,
                "status": "degraded" if service == "vpn" else "operational",
                "observed_at": "2026-01-01T12:00:00Z",
                "origin": "SYNTHETIC frozen fixture",
            },
        )
    queries = [
        {"query": symptom, "relevant_documents": [f"kb-{i + 1:02d}"]}
        for i, (_, symptom, _, _) in enumerate(TOPICS)
    ]
    (kb_dir.parent / "retrieval_eval.json").write_text(json.dumps(queries, indent=2), "utf-8")
    return {"tickets": 32, "incidents": 32, "runbooks": len(TOPICS), "origin": "SYNTHETIC"}
