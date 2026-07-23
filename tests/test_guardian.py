import importlib.machinery
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "bin" / "gitlab-mr-guardian"
LOADER = importlib.machinery.SourceFileLoader("guardian", str(SCRIPT))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
guardian = importlib.util.module_from_spec(SPEC)
LOADER.exec_module(guardian)


def base_mr(**overrides):
    payload = {
        "id": 10,
        "iid": 7,
        "project_id": 1,
        "title": "Ship guarded MR",
        "web_url": "https://gitlab.example.com/team/project/-/merge_requests/7",
        "sha": "abc123",
        "draft": False,
        "updated_at": "2099-01-01T00:00:00+00:00",
        "references": {"full": "team/project!7"},
        "detailed_merge_status": "mergeable",
        "rebase_in_progress": False,
        "head_pipeline": {
            "id": 55,
            "status": "success",
            "web_url": "https://gitlab.example.com/team/project/-/pipelines/55",
        },
    }
    payload.update(overrides)
    return payload


class FakeClient:
    def __init__(
        self,
        mr,
        approvals=None,
        discussions=None,
        reset_approvals=False,
        pipeline_history=None,
    ):
        self.mr = mr
        self.approvals = approvals or {
            "approved": True,
            "approved_by": [{"user": {"username": "reviewer"}}],
        }
        self.discussions = discussions or []
        self.reset_approvals = reset_approvals
        self.pipeline_history = pipeline_history or []
        self.mutations = []

    def api(self, endpoint, *, method="GET", query=None, fields=None):
        if endpoint == "merge_requests":
            return [self.mr]
        if endpoint.endswith("/approvals") and endpoint.startswith("projects/1/merge_requests"):
            return self.approvals
        if endpoint == "projects/1/approvals":
            return {"reset_approvals_on_push": self.reset_approvals}
        if endpoint == "projects/1/merge_requests/7":
            return self.mr
        if endpoint.endswith("/pipelines") and method == "GET":
            return self.pipeline_history
        if endpoint.endswith("/pipelines") and method == "POST":
            self.mutations.append(("pipeline", fields))
            return {
                "id": 57,
                "status": "pending",
                "web_url": "https://gitlab.example.com/team/project/-/pipelines/57",
            }
        if endpoint.endswith("/rebase") and method == "PUT":
            self.mutations.append(("rebase", fields))
            return None
        if endpoint.endswith("/merge") and method == "PUT":
            self.mutations.append(("merge", fields))
            return {"state": "merged"}
        raise AssertionError(f"Unexpected API call: {method} {endpoint}")

    def paginated(self, endpoint, query=None):
        if endpoint.endswith("/discussions"):
            return self.discussions
        raise AssertionError(f"Unexpected paginated API call: {endpoint}")


def config(**overrides):
    return guardian.validate_config(
        {
            "auto_rebase": True,
            "auto_merge": True,
            **overrides,
        }
    )


class GuardianCycleTests(unittest.TestCase):
    def test_unresolved_review_pauses_without_mutation(self):
        client = FakeClient(
            base_mr(),
            discussions=[
                {"notes": [{"resolvable": True, "resolved": False}]},
            ],
        )
        state = guardian.StateStore(Path("/tmp/unused-guardian-state.json"))

        rows, events = guardian.run_cycle(client, config(), state, mutate=True)

        self.assertEqual(rows[0]["phase"], "paused_for_review")
        self.assertEqual(client.mutations, [])
        self.assertEqual(events, [])

    def test_need_rebase_requests_rebase_when_approvals_are_preserved(self):
        client = FakeClient(base_mr(detailed_merge_status="need_rebase"))
        state = guardian.StateStore(Path("/tmp/unused-guardian-state.json"))

        rows, events = guardian.run_cycle(client, config(), state, mutate=True)

        self.assertEqual(rows[0]["phase"], "rebase_requested")
        self.assertEqual(client.mutations, [("rebase", None)])
        self.assertEqual(events[0]["event"], "REBASE_REQUESTED")

    def test_managed_ci_failure_reports_without_retry_or_merge(self):
        mr = base_mr(
            detailed_merge_status="ci_must_pass",
            head_pipeline={
                "id": 56,
                "status": "failed",
                "web_url": "https://gitlab.example.com/team/project/-/pipelines/56",
            },
        )
        client = FakeClient(mr)
        state = guardian.StateStore(Path("/tmp/unused-guardian-state.json"))
        state.data["mrs"]["1!7"] = {"managed": True, "sha": "abc123"}

        rows, events = guardian.run_cycle(client, config(), state, mutate=True)

        self.assertEqual(rows[0]["phase"], "waiting_for_successful_ci")
        self.assertEqual(client.mutations, [])
        self.assertEqual([event["event"] for event in events], ["CI_FAILED"])

    def test_eligible_mr_requests_auto_merge_with_reviewed_sha(self):
        client = FakeClient(base_mr())
        state = guardian.StateStore(Path("/tmp/unused-guardian-state.json"))

        rows, events = guardian.run_cycle(client, config(), state, mutate=True)

        self.assertEqual(rows[0]["phase"], "merged")
        self.assertEqual(
            client.mutations,
            [("merge", {"auto_merge": True, "sha": "abc123"})],
        )
        self.assertEqual(events[0]["event"], "MERGED")

    def test_skipped_pipeline_is_refreshed_after_historical_success(self):
        mr = base_mr(
            head_pipeline={
                "id": 56,
                "status": "skipped",
                "web_url": "https://gitlab.example.com/team/project/-/pipelines/56",
            }
        )
        client = FakeClient(
            mr,
            pipeline_history=[
                {"id": 56, "status": "skipped", "sha": "abc123"},
                {"id": 55, "status": "success", "sha": "older-sha"},
            ],
        )
        state = guardian.StateStore(Path("/tmp/unused-guardian-state.json"))

        rows, events = guardian.run_cycle(client, config(), state, mutate=True)

        self.assertEqual(rows[0]["phase"], "pipeline_requested")
        self.assertTrue(rows[0]["managed"])
        self.assertEqual(client.mutations, [("pipeline", None)])
        self.assertEqual(events[0]["event"], "PIPELINE_REQUESTED")

    def test_old_merge_request_is_out_of_scope_by_default(self):
        client = FakeClient(base_mr(updated_at="2020-01-01T00:00:00+00:00"))
        state = guardian.StateStore(Path("/tmp/unused-guardian-state.json"))

        rows, events = guardian.run_cycle(client, config(), state, mutate=True)

        self.assertEqual(rows, [])
        self.assertEqual(events, [])
        self.assertEqual(client.mutations, [])


class ConfigurationTests(unittest.TestCase):
    def test_default_poll_interval_is_one_hour(self):
        loaded = guardian.validate_config({})

        self.assertEqual(loaded["poll_interval_seconds"], 3600)

    def test_native_plugin_options_are_parsed(self):
        environment = {
            "CLAUDE_PLUGIN_OPTION_hostname": "gitlab.example.com",
            "CLAUDE_PLUGIN_OPTION_poll_interval_seconds": "600",
            "CLAUDE_PLUGIN_OPTION_auto_rebase": "true",
            "CLAUDE_PLUGIN_OPTION_auto_merge": "false",
            "CLAUDE_PLUGIN_OPTION_include_projects": "team/project, 42",
        }
        with patch.dict(os.environ, environment, clear=True):
            loaded = guardian.plugin_options_config()

        self.assertEqual(loaded["hostname"], "gitlab.example.com")
        self.assertEqual(loaded["poll_interval_seconds"], 600)
        self.assertTrue(loaded["auto_rebase"])
        self.assertFalse(loaded["auto_merge"])
        self.assertEqual(loaded["include_projects"], ["team/project", "42"])

    def test_native_plugin_config_does_not_read_user_fallback_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            user_file = Path(temporary) / "gitlab-mr-guardian" / "config.json"
            user_file.parent.mkdir(parents=True)
            user_file.write_text(
                '{"hostname":"file.example.com","auto_rebase":false}\n',
                encoding="utf-8",
            )
            environment = {
                "XDG_CONFIG_HOME": temporary,
                "CLAUDE_PLUGIN_OPTION_hostname": "plugin.example.com",
                "CLAUDE_PLUGIN_OPTION_auto_rebase": "true",
            }
            with patch.dict(os.environ, environment, clear=True):
                loaded, path, source = guardian.load_config()

        self.assertEqual(loaded["hostname"], "plugin.example.com")
        self.assertTrue(loaded["auto_rebase"])
        self.assertIsNone(path)
        self.assertEqual(source, "plugin-user-config")

    def test_development_config_uses_xdg_user_directory(self):
        with patch.dict(
            os.environ,
            {"XDG_CONFIG_HOME": "/tmp/example-config-root"},
            clear=True,
        ):
            path = guardian.default_user_config_path()

        self.assertEqual(
            path,
            Path("/tmp/example-config-root/gitlab-mr-guardian/config.json"),
        )

    def test_state_uses_claude_plugin_data_directory(self):
        environment = {
            "CLAUDE_PLUGIN_DATA": "/tmp/example-plugin-data",
        }
        with patch.dict(os.environ, environment, clear=True):
            path = guardian.state_path({"hostname": "gitlab.example.com"})

        self.assertEqual(path.parent, Path("/tmp/example-plugin-data"))
        self.assertTrue(path.name.startswith("state-"))
        self.assertEqual(path.suffix, ".json")


if __name__ == "__main__":
    unittest.main()
