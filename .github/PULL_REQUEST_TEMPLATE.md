## BCM Operation Request

### Operation Details

| Field | Value |
|-------|-------|
| **Operation** | <!-- e.g., day2_reboot, debug_bundle, day2_cordon --> |
| **Target Node(s)** | <!-- e.g., dgx-b200-042 --> |
| **Ticket/Incident** | <!-- e.g., INC-12345, NV-CASE-44210 --> |
| **Urgency** | <!-- 🔴 Critical / 🟠 High / 🟡 Normal --> |

### Reason

<!-- Why is this operation needed? What symptoms or alerts triggered it? -->

### Pre-Checks Completed

- [ ] Verified node status in BCM monitoring dashboard
- [ ] Checked for active customer workloads on the node
- [ ] Customer notified (if applicable)
- [ ] Operation YAML file added to `operation-requests/`

### Rollback Plan

<!-- What happens if this operation fails? How do we revert? -->
- For reboot: Node should come back automatically; if not, escalate to L2
- For cordon: Uncordon via separate PR if issue was false positive
- For debug bundle: No rollback needed (read-only operation)

### Reviewer Checklist

- [ ] Operation YAML is valid and targets correct node(s)
- [ ] Reason is documented and justified
- [ ] No conflicting operations in-flight
- [ ] Approve and merge to execute

---

> ⚠️ **On merge, this operation will be automatically executed via Ansible Tower.**
> Results will be posted as a comment on this PR.
