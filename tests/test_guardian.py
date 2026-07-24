import importlib.machinery
import importlib.util
import json
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
        if endpoint.endswith("/retry") and method == "POST":
            self.mutations.append(("retry", fields))
            return {"id": 56, "status": "pending"}
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

    def test_failed_ci_is_retried_once_per_pipeline_when_enabled(self):
        mr = base_mr(
            detailed_merge_status="ci_must_pass",
            head_pipeline={
                "id": 56,
                "status": "failed",
                "web_url": "https://gitlab.example.com/team/project/-/pipelines/56",
            },
        )
        state = guardian.StateStore(Path("/tmp/unused-guardian-state.json"))
        policy = config(retry_failed_pipeline_once=True)

        client = FakeClient(mr)
        rows, events = guardian.run_cycle(client, policy, state, mutate=True)

        self.assertEqual(rows[0]["phase"], "pipeline_retry_requested")
        self.assertTrue(rows[0]["managed"])
        self.assertEqual(client.mutations, [("retry", None)])
        self.assertEqual(events[0]["event"], "PIPELINE_RETRY_REQUESTED")

        # The same pipeline fails again after the retry: report only, no second retry.
        client = FakeClient(mr)
        rows, events = guardian.run_cycle(client, policy, state, mutate=True)

        self.assertEqual(rows[0]["phase"], "waiting_for_successful_ci")
        self.assertEqual(client.mutations, [])
        self.assertEqual([event["event"] for event in events], ["CI_FAILED"])

    def test_need_rebase_with_failed_ci_rebases_when_enabled(self):
        mr = base_mr(
            detailed_merge_status="need_rebase",
            head_pipeline={
                "id": 56,
                "status": "failed",
                "web_url": "https://gitlab.example.com/team/project/-/pipelines/56",
            },
        )
        state = guardian.StateStore(Path("/tmp/unused-guardian-state.json"))

        client = FakeClient(mr)
        rows, events = guardian.run_cycle(
            client, config(rebase_when_ci_failed=True), state, mutate=True
        )

        self.assertEqual(rows[0]["phase"], "rebase_requested")
        self.assertTrue(rows[0]["managed"])
        self.assertEqual(client.mutations, [("rebase", None)])
        self.assertEqual(events[0]["event"], "REBASE_REQUESTED")

        # Default configuration leaves the MR untouched.
        client = FakeClient(mr)
        rows, events = guardian.run_cycle(
            client, config(), guardian.StateStore(Path("/tmp/unused-2.json")), mutate=True
        )

        self.assertEqual(rows[0]["phase"], "waiting_for_successful_ci")
        self.assertEqual(client.mutations, [])

    def test_advisory_reviewer_discussions_do_not_block(self):
        mr = base_mr(detailed_merge_status="discussions_not_resolved")
        client = FakeClient(
            mr,
            discussions=[
                {
                    "notes": [
                        {
                            "resolvable": True,
                            "resolved": False,
                            "author": {"username": "AI-Reviewer"},
                        }
                    ]
                },
            ],
        )
        state = guardian.StateStore(Path("/tmp/unused-guardian-state.json"))

        rows, events = guardian.run_cycle(
            client, config(advisory_reviewers=["ai-reviewer"]), state, mutate=True
        )

        self.assertEqual(rows[0]["phase"], "merged")
        self.assertEqual(rows[0]["advisory_unresolved"], 1)
        self.assertEqual(
            client.mutations,
            [("merge", {"auto_merge": True, "sha": "abc123"})],
        )

    def test_human_note_in_advisory_thread_still_blocks(self):
        mr = base_mr(detailed_merge_status="discussions_not_resolved")
        client = FakeClient(
            mr,
            discussions=[
                {
                    "notes": [
                        {
                            "resolvable": True,
                            "resolved": False,
                            "author": {"username": "ai-reviewer"},
                        },
                        {
                            "resolvable": True,
                            "resolved": False,
                            "author": {"username": "human-reviewer"},
                        },
                    ]
                },
            ],
        )
        state = guardian.StateStore(Path("/tmp/unused-guardian-state.json"))

        rows, events = guardian.run_cycle(
            client, config(advisory_reviewers=["ai-reviewer"]), state, mutate=True
        )

        self.assertEqual(rows[0]["phase"], "paused_for_review")
        self.assertEqual(rows[0]["advisory_unresolved"], 1)
        self.assertEqual(client.mutations, [])

    def test_manage_all_approved_refreshes_pipeline_without_history(self):
        mr = base_mr(
            head_pipeline={
                "id": 56,
                "status": "skipped",
                "web_url": "https://gitlab.example.com/team/project/-/pipelines/56",
            }
        )
        # No successful pipeline anywhere in the MR's history.
        history = [{"id": 56, "status": "skipped", "sha": "abc123"}]

        client = FakeClient(mr, pipeline_history=history)
        rows, events = guardian.run_cycle(
            client,
            config(manage_all_approved=True),
            guardian.StateStore(Path("/tmp/unused-guardian-state.json")),
            mutate=True,
        )

        self.assertEqual(rows[0]["phase"], "pipeline_requested")
        self.assertTrue(rows[0]["managed"])
        self.assertEqual(client.mutations, [("pipeline", None)])

        # Default configuration still requires a previously successful pipeline.
        client = FakeClient(mr, pipeline_history=history)
        rows, events = guardian.run_cycle(
            client,
            config(),
            guardian.StateStore(Path("/tmp/unused-2.json")),
            mutate=True,
        )

        self.assertEqual(rows[0]["phase"], "waiting_for_successful_ci")
        self.assertFalse(rows[0]["managed"])
        self.assertEqual(client.mutations, [])

    def test_manage_all_approved_reports_ci_failure_without_history(self):
        mr = base_mr(
            detailed_merge_status="ci_must_pass",
            head_pipeline={
                "id": 56,
                "status": "failed",
                "web_url": "https://gitlab.example.com/team/project/-/pipelines/56",
            },
        )
        client = FakeClient(mr)
        rows, events = guardian.run_cycle(
            client,
            config(manage_all_approved=True),
            guardian.StateStore(Path("/tmp/unused-guardian-state.json")),
            mutate=True,
        )

        self.assertEqual(rows[0]["phase"], "waiting_for_successful_ci")
        self.assertTrue(rows[0]["managed"])
        self.assertEqual(client.mutations, [])
        self.assertEqual([event["event"] for event in events], ["CI_FAILED"])

    def test_old_merge_request_is_out_of_scope_by_default(self):
        client = FakeClient(base_mr(updated_at="2020-01-01T00:00:00+00:00"))
        state = guardian.StateStore(Path("/tmp/unused-guardian-state.json"))

        rows, events = guardian.run_cycle(client, config(), state, mutate=True)

        self.assertEqual(rows, [])
        self.assertEqual(events, [])
        self.assertEqual(client.mutations, [])


class ConfigurationTests(unittest.TestCase):
    def test_manifest_does_not_declare_native_user_config(self):
        manifest_path = SCRIPT.parents[1] / ".claude-plugin" / "plugin.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        self.assertNotIn("userConfig", manifest)
        self.assertEqual(guardian.validate_config({})["include_projects"], [])

    def test_monitor_command_uses_plugin_data_dir_without_user_config(self):
        monitor_path = SCRIPT.parents[1] / "monitors" / "monitors.json"
        monitor = json.loads(monitor_path.read_text(encoding="utf-8"))[0]

        self.assertNotIn("${user_config.", monitor["command"])
        self.assertIn("--plugin-data-dir", monitor["command"])
        self.assertIn("${CLAUDE_PLUGIN_DATA}", monitor["command"])

    def test_skills_do_not_reference_user_config(self):
        skills_root = SCRIPT.parents[1] / "skills"
        for skill in sorted(skills_root.glob("*/SKILL.md")):
            self.assertNotIn(
                "${user_config.",
                skill.read_text(encoding="utf-8"),
                msg=f"{skill} still references ${{user_config.*}}",
            )

    def test_configure_persists_settings_read_by_all_commands(self):
        with tempfile.TemporaryDirectory() as temporary:
            configure_args = guardian.build_parser().parse_args(
                [
                    "--plugin-data-dir",
                    temporary,
                    "configure",
                    "--hostname",
                    "gitlab.example.com",
                    "--auto-rebase",
                    "true",
                    "--poll-interval-seconds",
                    "1800",
                ]
            )
            with patch.object(guardian, "emit"), patch.dict(os.environ, {}, clear=True):
                self.assertEqual(guardian.command_configure(configure_args), 0)

                settings_file = (Path(temporary) / "settings.json").resolve()
                self.assertTrue(settings_file.is_file())
                saved = json.loads(settings_file.read_text(encoding="utf-8"))
                self.assertEqual(saved["hostname"], "gitlab.example.com")
                self.assertTrue(saved["auto_rebase"])

                monitor_args = guardian.build_parser().parse_args(
                    ["--plugin-data-dir", temporary, "status"]
                )
                loaded, path, source = guardian.load_runtime_config(monitor_args)

        self.assertEqual(source, "plugin-settings-file")
        self.assertEqual(path, settings_file)
        self.assertEqual(loaded["hostname"], "gitlab.example.com")
        self.assertTrue(loaded["auto_rebase"])
        self.assertEqual(loaded["poll_interval_seconds"], 1800)
        self.assertFalse(loaded["auto_merge"])

    def test_configure_merges_with_existing_settings(self):
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(guardian, "emit"), patch.dict(os.environ, {}, clear=True):
                first = guardian.build_parser().parse_args(
                    [
                        "--plugin-data-dir",
                        temporary,
                        "configure",
                        "--hostname",
                        "gitlab.example.com",
                    ]
                )
                guardian.command_configure(first)
                second = guardian.build_parser().parse_args(
                    ["--plugin-data-dir", temporary, "configure", "--auto-merge", "true"]
                )
                guardian.command_configure(second)

                saved = json.loads(
                    (Path(temporary) / "settings.json").read_text(encoding="utf-8")
                )

        self.assertEqual(saved["hostname"], "gitlab.example.com")
        self.assertTrue(saved["auto_merge"])

    def test_settings_file_overrides_plugin_environment_options(self):
        with tempfile.TemporaryDirectory() as temporary:
            settings_file = Path(temporary) / "settings.json"
            settings_file.write_text(
                '{"hostname": "settings.example.com"}\n', encoding="utf-8"
            )
            environment = {
                "CLAUDE_PLUGIN_DATA": temporary,
                "CLAUDE_PLUGIN_OPTION_hostname": "env.example.com",
                "CLAUDE_PLUGIN_OPTION_auto_rebase": "true",
            }
            with patch.dict(os.environ, environment, clear=True):
                loaded, path, source = guardian.load_config()

        self.assertEqual(source, "plugin-settings-file")
        self.assertEqual(loaded["hostname"], "settings.example.com")
        self.assertTrue(loaded["auto_rebase"])

    def test_monitor_control_defaults_to_stopped_and_persists(self):
        with tempfile.TemporaryDirectory() as temporary:
            loaded = guardian.validate_config({"plugin_data_dir": temporary})

            self.assertFalse(guardian.monitor_control_enabled(loaded))
            guardian.set_monitor_control(loaded, True)
            self.assertTrue(guardian.monitor_control_enabled(loaded))
            guardian.set_monitor_control(loaded, False)
            self.assertFalse(guardian.monitor_control_enabled(loaded))

    def test_start_and_stop_commands_toggle_monitor_control(self):
        with tempfile.TemporaryDirectory() as temporary:
            start_args = guardian.build_parser().parse_args(
                ["--plugin-data-dir", temporary, "start"]
            )
            stop_args = guardian.build_parser().parse_args(
                ["--plugin-data-dir", temporary, "stop"]
            )
            loaded = guardian.validate_config({"plugin_data_dir": temporary})

            with patch.object(guardian, "emit"):
                self.assertEqual(
                    guardian.command_start_or_stop(start_args, enabled=True),
                    0,
                )
                self.assertTrue(guardian.monitor_control_enabled(loaded))
                self.assertEqual(
                    guardian.command_start_or_stop(stop_args, enabled=False),
                    0,
                )
                self.assertFalse(guardian.monitor_control_enabled(loaded))

    def test_runtime_arguments_override_missing_plugin_environment(self):
        args = guardian.build_parser().parse_args(
            [
                "--plugin-data-dir",
                "/tmp/guardian-plugin-data",
                "--runtime-hostname",
                "gitlab.example.com",
                "--runtime-poll-interval-seconds",
                "1800",
                "--runtime-auto-rebase",
                "true",
                "--runtime-auto-merge",
                "false",
                "--runtime-trigger-pipeline-when-missing-or-skipped",
                "true",
                "--runtime-max-mr-age-days",
                "90",
                "--runtime-report-ci-failures",
                "true",
                "status",
            ]
        )
        with patch.object(
            guardian,
            "load_config",
            return_value=(guardian.validate_config({}), None, "built-in-defaults"),
        ):
            loaded, _path, _source = guardian.load_runtime_config(args)

        self.assertEqual(loaded["hostname"], "gitlab.example.com")
        self.assertEqual(loaded["poll_interval_seconds"], 1800)
        self.assertTrue(loaded["auto_rebase"])
        self.assertFalse(loaded["auto_merge"])
        self.assertEqual(
            loaded["plugin_data_dir"],
            "/tmp/guardian-plugin-data",
        )

    def test_default_poll_interval_is_one_hour(self):
        loaded = guardian.validate_config({})

        self.assertEqual(loaded["poll_interval_seconds"], 3600)

    def test_guarded_rebase_is_on_by_default_but_merge_is_not(self):
        loaded = guardian.validate_config({})

        self.assertTrue(loaded["auto_rebase"])
        self.assertFalse(loaded["auto_merge"])
        self.assertFalse(loaded["allow_rebase_that_resets_approvals"])

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
                "XDG_CACHE_HOME": temporary,
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

        self.assertEqual(path.parent, Path("/tmp/example-plugin-data").resolve())
        self.assertTrue(path.name.startswith("state-"))
        self.assertEqual(path.suffix, ".json")


if __name__ == "__main__":
    unittest.main()
