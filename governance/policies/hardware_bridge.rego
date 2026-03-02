# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  Hardware Bridge Verification Policy                                    ║
# ║                                                                        ║
# ║  Validates that hardware telemetry data flows through verified         ║
# ║  connectors and is never synthetically generated.                      ║
# ╚══════════════════════════════════════════════════════════════════════════╝

package merge.hardware

import rego.v1

# Every hardware data source must have a verified connector
default hardware_bridge_valid := false

hardware_bridge_valid if {
    input.hardware.sources_verified == true
    input.hardware.synthetic_data == false
    all_connectors_authenticated
}

# Bypass when hardware telemetry isn't part of this PR
hardware_bridge_valid if {
    not input.hardware
}

all_connectors_authenticated if {
    every connector in input.hardware.connectors {
        connector.authenticated == true
        connector.last_heartbeat_age_seconds < 300
    }
}

# ────────────────────────────────────────────────────────────────────────
# Database Bridge Checks
# ────────────────────────────────────────────────────────────────────────

default database_bridge_valid := false

database_bridge_valid if {
    input.database.connection_verified == true
    input.database.using_orm == true
    input.database.raw_sql_injection_scan == "clean"
}

database_bridge_valid if {
    not input.database
}
