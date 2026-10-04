class Advisor:
    RULES = {
        "DIRECT_ICMP_FAILED": "A->B ICMP lost. Check tunnel UP on both sides, and firewall on B.",
        "DIRECT_TCP_FAILED": "A->B TCP payload lost. TCP receiver on B may not be listening, or firewall drops TCP.",
        "DIRECT_UDP_FAILED": "A->B UDP payload lost. UDP receiver on B may not be listening, or firewall drops UDP.",
        "REVERSE_ICMP_FAILED": "B->A ICMP lost. Asymmetric route or firewall on A.",
        "REVERSE_TCP_FAILED": "B->A TCP payload lost. TCP receiver on A may not be listening.",
        "REVERSE_UDP_FAILED": "B->A UDP payload lost. UDP receiver on A may not be listening.",
        "IFACE_A_DOWN": "Interface on A is missing or down. Check kernel module on A.",
        "IFACE_B_DOWN": "Interface on B is missing or down. Check kernel module on B.",
        "REMOTE_ERROR": "Server B reported an error. See agent.log.",
        "TIMEOUT": "Operation timed out. Check public connectivity between A and B.",
        "CLEANUP_ERROR": "Cleanup failed. Manual cleanup may be needed.",
        "UNKNOWN": "Unknown failure. Inspect session log.",
    }

    def explain(self, result: dict) -> str:
        tunnel = result.get("tunnel", "?").upper()
        status = result.get("status", "FAIL")
        lines = [f"[{tunnel}] {status}"]
        stages = result.get("stages", {})
        for k, v in stages.items():
            mark = "OK" if v else "FAIL"
            lines.append(f"  {k}: {mark}")
        if status != "PASS":
            reason = result.get("reason", "UNKNOWN")
            hint = self.RULES.get(reason, self.RULES["UNKNOWN"])
            lines.append(f"  reason: {reason}")
            lines.append(f"  hint:   {hint}")
        return "\n".join(lines)

    def summary(self, results: list) -> str:
        total = len(results)
        passed = sum(1 for r in results if r.get("status") == "PASS")
        failed = total - passed
        return "\n".join([
            "",
            "========== SUMMARY ==========",
            f"  tested: {total}",
            f"  passed: {passed}",
            f"  failed: {failed}",
            "=============================",
        ])