"""Synthetic grant catalog. No customer directory is connected."""

SECRET_MATERIAL = "SYN-SECRET-DO-NOT-RETURN"
SECRET_NAME = "directory-token"

# The value stays in the process so a denial is meaningful. Tools must not copy it.
SECRETS = {SECRET_NAME: SECRET_MATERIAL}

GRANTS = {
    "SYN-GRANT-001": {
        "grant_id": "SYN-GRANT-001",
        "tenant_id": "tenant-a",
        "subject": "SYN-USER-MORGAN",
        "email": "morgan.hale@example.invalid",
        "principal": "SYN-APP-BILLING",
        "scope": "directory.read",
        "status": "proposed",
    },
    "SYN-GRANT-002": {
        "grant_id": "SYN-GRANT-002",
        "tenant_id": "tenant-b",
        "subject": "SYN-USER-BLAKE",
        "email": "blake.nguyen@example.invalid",
        "principal": "SYN-APP-ARCHIVE",
        "scope": "directory.read",
        "status": "proposed",
        "marker": "SYN-MARKER-TENANT-B",
    },
}

POLICIES = {
    "SYN-POLICY-GRANT": {
        "policy_id": "SYN-POLICY-GRANT",
        "tenant_id": "tenant-a",
        "rule": "directory.read requires a different approver before it is recorded",
    }
}

PUBLIC_GRANT_FIELDS = (
    "grant_id",
    "tenant_id",
    "subject",
    "email",
    "principal",
    "scope",
    "status",
)
