import unittest
from src.evidence.revocation_lint import RevocationLint, RevocationLintError

class TestRevocationLint(unittest.TestCase):
    def test_valid_notice_passes(self):
        notice = (
            "This grant is hereby revoked. Please note that this revocation "
            "terminates the legal license but does not un-train the model."
        )
        self.assertTrue(RevocationLint.check_notice(notice))

    def test_understatement_fails_no_termination(self):
        # Has disclaimer, but no explicit termination statement
        notice = "This notice does not un-train the model."
        with self.assertRaisesRegex(RevocationLintError, "Notice must explicitly state"):
            RevocationLint.check_notice(notice)

    def test_understatement_fails_no_disclaimer(self):
        # Has termination, but no disclaimer (HOD-350 core requirement)
        notice = "This grant is hereby terminated."
        with self.assertRaisesRegex(RevocationLintError, "Notice must contain an explicit disclaimer"):
            RevocationLint.check_notice(notice)

    def test_overstatement_fails(self):
        # Has termination and disclaimer, but also includes an overclaim
        notice = (
            "This grant is revoked. This does not un-train the model, "
            "but your work will be removed from the model weights eventually."
        )
        with self.assertRaisesRegex(RevocationLintError, "contains model-removal overclaim"):
            RevocationLint.check_notice(notice)

    def test_paraphrase_overstatement_fails(self):
        notice = "We revoke this. This does not un-train the model, however it deletes your data from their system."
        with self.assertRaisesRegex(RevocationLintError, "contains model-removal overclaim"):
            RevocationLint.check_notice(notice)

if __name__ == '__main__':
    unittest.main()
