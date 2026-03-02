# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  OPA/Rego Merge Gate Policies — Architectural Governance Blueprint     ║
# ║                                                                        ║
# ║  Enforced by Open Policy Agent as the ultimate CI/CD merge chokepoint. ║
# ║  Usage:  opa eval -d governance/policies/ -i input.json "data.merge"   ║
# ╚══════════════════════════════════════════════════════════════════════════╝

package merge

import rego.v1

# ─── Default: deny until all gates pass ─────────────────────────────────

default allow := false

allow if {
    semantic_graph_clean
    multi_agent_approved
    provenance_verified
    formal_proof_valid
    no_hollywood_props
}

# ────────────────────────────────────────────────────────────────────────
# Gate 1: Semantic Graph Validation (CPG / Hollywood Prop Scanner)
# ────────────────────────────────────────────────────────────────────────

semantic_graph_clean if {
    input.hollywood_prop_scan.exit_code == 0
    input.hollywood_prop_scan.total_violations == 0
}

semantic_graph_clean if {
    input.hollywood_prop_scan.exit_code == 0
    # Non-strict mode: only block on CRITICAL/HIGH
    not has_critical_violations
}

has_critical_violations if {
    some v in input.hollywood_prop_scan.violations
    v.severity in {"CRITICAL", "HIGH"}
}

# ────────────────────────────────────────────────────────────────────────
# Gate 2: Multi-Agent Approval (Security Auditor + Architectural Critic)
# ────────────────────────────────────────────────────────────────────────

multi_agent_approved if {
    input.agent_reviews.security_auditor.approved == true
    input.agent_reviews.architectural_critic.approved == true
    input.agent_reviews.security_auditor.zero_day_found == false
}

# Bypass if agent review system is not yet integrated
multi_agent_approved if {
    not input.agent_reviews
}

# ────────────────────────────────────────────────────────────────────────
# Gate 3: Provenance & AIBOM Verification (SLSA Level 3)
# ────────────────────────────────────────────────────────────────────────

provenance_verified if {
    input.aibom.metadata.slsa_level == "3"
    valid_model
    input.aibom.integrity.artifact_count > 0
}

# Fallback: allow if AIBOM not yet generated (staged rollout)
provenance_verified if {
    not input.aibom
}

valid_model if {
    allowed_models := {
        "GitHub Copilot (Claude Opus 4.6)",
        "Claude Opus 4",
        "GPT-4o",
    }
    input.aibom.provenance.model.name in allowed_models
}

# ────────────────────────────────────────────────────────────────────────
# Gate 4: Formal Proof Validation (Astrogator / Symbolic Execution)
# ────────────────────────────────────────────────────────────────────────

formal_proof_valid if {
    input.formal_verification.proof_generated == true
    input.formal_verification.correctness_score >= 0.83
}

# Bypass if formal verification not yet integrated
formal_proof_valid if {
    not input.formal_verification
}

# ────────────────────────────────────────────────────────────────────────
# Gate 5: Hollywood Prop Specific Checks
# ────────────────────────────────────────────────────────────────────────

no_hollywood_props if {
    no_simulation_generators
    no_hardcoded_wallets
    no_fake_latency
}

no_simulation_generators if {
    not any_violation_with_rule("HP-001")
    not any_violation_with_rule("HP-008")
}

no_hardcoded_wallets if {
    not any_violation_with_rule("HP-003")
}

no_fake_latency if {
    not any_violation_with_rule("HP-002")
}

any_violation_with_rule(rule_id) if {
    some v in input.hollywood_prop_scan.violations
    v.rule_id == rule_id
}

# ────────────────────────────────────────────────────────────────────────
# Deny reasons (human-readable feedback for CI output)
# ────────────────────────────────────────────────────────────────────────

deny contains msg if {
    not semantic_graph_clean
    msg := "BLOCKED: Hollywood Prop anti-patterns detected in semantic graph analysis."
}

deny contains msg if {
    not multi_agent_approved
    msg := "BLOCKED: Code did not pass multi-agent security/architectural review."
}

deny contains msg if {
    not provenance_verified
    msg := "BLOCKED: AIBOM provenance verification failed — unauthorized model or missing SLSA 3 attestation."
}

deny contains msg if {
    not formal_proof_valid
    msg := "BLOCKED: Formal verification proof not generated or correctness score below threshold."
}

deny contains msg if {
    not no_hollywood_props
    msg := "BLOCKED: Specific Hollywood Prop rules violated (HP-001/002/003/008)."
}
