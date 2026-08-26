import unittest

from nexus_harness.pretool import evaluate_pretool


def _bash(command: str, **extra) -> dict:
    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": command},
    }
    payload.update(extra)
    return payload


class PretoolCommandPolicyTests(unittest.TestCase):
    def test_echo_production_documentation_is_safe(self):
        code, output = evaluate_pretool(_bash('echo "production documentation"'))
        self.assertEqual(code, 0)
        self.assertTrue(output.get("allowed"))

    def test_printf_rm_rf_prose_is_safe(self):
        code, output = evaluate_pretool(_bash("printf 'rm -rf is dangerous'"))
        self.assertEqual(code, 0)
        self.assertTrue(output.get("allowed"))

    def test_ssh_is_protected(self):
        code, output = evaluate_pretool(_bash("ssh example-host uname"))
        self.assertEqual(code, 2)
        self.assertEqual(output.get("reason"), "production requires approval")

    def test_scp_is_protected(self):
        code, output = evaluate_pretool(_bash("scp file example-host:/tmp/file"))
        self.assertEqual(code, 2)
        self.assertEqual(output.get("reason"), "production requires approval")

    def test_docker_compose_up_is_protected(self):
        code, output = evaluate_pretool(_bash("docker compose up -d"))
        self.assertEqual(code, 2)
        self.assertEqual(output.get("reason"), "production requires approval")

    def test_kubectl_apply_is_protected(self):
        code, output = evaluate_pretool(_bash("kubectl apply -f manifest.yaml"))
        self.assertEqual(code, 2)
        self.assertEqual(output.get("reason"), "production requires approval")

    def test_helm_upgrade_is_protected(self):
        code, output = evaluate_pretool(_bash("helm upgrade web chart/"))
        self.assertEqual(code, 2)
        self.assertEqual(output.get("reason"), "production requires approval")

    def test_rm_rf_is_protected(self):
        code, output = evaluate_pretool(_bash("rm -rf target"))
        self.assertEqual(code, 2)
        self.assertEqual(output.get("reason"), "destructive action requires approval")

    def test_nested_bash_lc_rm_rf_is_protected(self):
        code, output = evaluate_pretool(_bash("bash -lc 'rm -rf target'"))
        self.assertEqual(code, 2)
        self.assertEqual(output.get("reason"), "destructive action requires approval")

    def test_nested_sh_c_kubectl_is_protected(self):
        code, output = evaluate_pretool(_bash("sh -c 'kubectl apply -f x'"))
        self.assertEqual(code, 2)
        self.assertEqual(output.get("reason"), "production requires approval")

    def test_malformed_sensitive_fails_closed(self):
        code, output = evaluate_pretool(_bash("ssh 'unterminated"))
        self.assertEqual(code, 2)
        self.assertTrue(output.get("denied"))

    def test_explicit_production_approval_permits_ssh(self):
        code, output = evaluate_pretool(
            _bash("ssh example-host uname", approvals_recorded=["production"])
        )
        self.assertEqual(code, 0)
        self.assertTrue(output.get("allowed"))

    def test_invalid_approval_does_not_permit_ssh(self):
        code, output = evaluate_pretool(
            _bash("ssh example-host uname", approvals_recorded=["destructive"])
        )
        self.assertEqual(code, 2)
        self.assertEqual(output.get("reason"), "production requires approval")

    def test_argv_list_is_preferred_over_command_string(self):
        payload = {
            "tool_name": "Bash",
            "tool_input": {
                "command": 'echo "ignore this ssh host"',
                "argv": ["ssh", "example-host", "true"],
            },
        }
        code, output = evaluate_pretool(payload)
        self.assertEqual(code, 2)
        self.assertEqual(output.get("reason"), "production requires approval")


if __name__ == "__main__":
    unittest.main()
