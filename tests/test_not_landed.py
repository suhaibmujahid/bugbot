# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import unittest
from unittest.mock import MagicMock, patch


class TestNotLandedReviewerNeedinfo(unittest.TestCase):
    """Regression tests for issue #1527: reviewer needinfo had no comment
    because nickname was hardcoded to None."""

    def _make_rule(self):
        with patch("bugbot.rules.not_landed.PhabricatorAPI"), patch(
            "bugbot.rules.not_landed.utils.get_login_info",
            return_value={"phab_api_key": "fake"},
        ):
            from bugbot.rules.not_landed import NotLanded

            return NotLanded()

    def _patch_bugzilla_user(self, users_payload):
        """Patch BugzillaUser so that instantiating it immediately invokes
        the provided handler with each user dict in users_payload."""

        class FakeBugzillaUser:
            def __init__(
                self,
                user_names=None,
                include_fields=None,
                user_handler=None,
                user_data=None,
                **kwargs,
            ):
                for user in users_payload:
                    user_handler(user, user_data)

            def wait(self):
                return self

        return patch("bugbot.rules.not_landed.BugzillaUser", FakeBugzillaUser)

    def test_get_bz_userid_returns_mail_and_nickname(self):
        rule = self._make_rule()
        rule.phab.load_bz_account = MagicMock(
            return_value=[{"phid": "PHID-USER-rev", "id": "42"}]
        )

        users = [{"id": 42, "name": "rev@example.com", "nick": "revnick"}]
        with self._patch_bugzilla_user(users):
            result = rule.get_bz_userid({"PHID-USER-rev"})

        self.assertEqual(result, {"PHID-USER-rev": ("rev@example.com", "revnick")})

    def test_get_bz_userid_handles_missing_nick(self):
        rule = self._make_rule()
        rule.phab.load_bz_account = MagicMock(
            return_value=[{"phid": "PHID-USER-rev", "id": "43"}]
        )

        users = [{"id": 43, "name": "nonick@example.com", "nick": ""}]
        with self._patch_bugzilla_user(users):
            result = rule.get_bz_userid({"PHID-USER-rev"})

        self.assertEqual(result, {"PHID-USER-rev": ("nonick@example.com", "")})

    def test_reviewer_add_auto_ni_includes_nickname(self):
        """The reviewer add_auto_ni call must pass the reviewer's real nick
        (not None), so set_needinfo renders the comment template."""
        rule = self._make_rule()

        rule.get_bz_userid = MagicMock(
            return_value={"PHID-USER-rev": ("rev@example.com", "revnick")}
        )
        rule.get_nicks = MagicMock(side_effect=lambda nicks: nicks)
        rule.filter_bugs = MagicMock(side_effect=lambda bugs: bugs)
        rule.get_patch_data = MagicMock(
            return_value={
                "100": {
                    "count": 1,
                    "author": {"dev@example.com": 1},
                    "reviewers_phid": {"PHID-USER-rev"},
                }
            }
        )

        with patch(
            "bugbot.bzcleaner.BzCleaner.get_bugs",
            return_value={
                "100": {
                    "assigned_to": "dev@example.com",
                    "nickname": "devnick",
                    "deps": set(),
                }
            },
        ):
            captured = []
            rule.add_auto_ni = lambda bugid, data: captured.append((bugid, data))
            rule.get_bugs()

        reviewer_call = next(
            (d for _, d in captured if d["mail"] == "rev@example.com"), None
        )
        self.assertIsNotNone(reviewer_call, "reviewer add_auto_ni was not called")
        self.assertEqual(reviewer_call["nickname"], "revnick")

    def test_reviewer_nickname_falls_back_to_email_local_part(self):
        """When Bugzilla returns an empty nick, the reviewer needinfo must
        still receive a truthy nickname so the template renders."""
        rule = self._make_rule()

        rule.get_bz_userid = MagicMock(
            return_value={"PHID-USER-rev": ("nonick@example.com", "")}
        )
        rule.get_nicks = MagicMock(side_effect=lambda nicks: nicks)
        rule.filter_bugs = MagicMock(side_effect=lambda bugs: bugs)
        rule.get_patch_data = MagicMock(
            return_value={
                "200": {
                    "count": 1,
                    "author": {"dev@example.com": 1},
                    "reviewers_phid": {"PHID-USER-rev"},
                }
            }
        )

        with patch(
            "bugbot.bzcleaner.BzCleaner.get_bugs",
            return_value={
                "200": {
                    "assigned_to": "dev@example.com",
                    "nickname": "devnick",
                    "deps": set(),
                }
            },
        ):
            captured = []
            rule.add_auto_ni = lambda bugid, data: captured.append((bugid, data))
            rule.get_bugs()

        reviewer_call = next(
            (d for _, d in captured if d["mail"] == "nonick@example.com"), None
        )
        self.assertIsNotNone(reviewer_call, "reviewer add_auto_ni was not called")
        self.assertEqual(reviewer_call["nickname"], "nonick")


if __name__ == "__main__":
    unittest.main()
