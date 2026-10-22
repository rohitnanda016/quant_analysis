import csv
import tempfile
import unittest

import pandas as pd
from pathlib import Path

from scripts.approved_price_gap_exclusions import (
    load_scope_exclusions,
    match_scope_exclusions_to_archive_absences,
)
from scripts.audit_price_gap_readiness import unresolved_archive_absence_details


class ApprovedPriceGapExclusionTests(unittest.TestCase):
    def write_csv(self, path, header, rows):
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(header)
            writer.writerows(rows)

    def test_exact_unresolved_archive_absence_is_matched_but_not_reclassified(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger = root / "exclusions.csv"
            absences = root / "absences.csv"
            self.write_csv(
                ledger,
                ["date", "symbol", "status", "reason", "approval_reference"],
                [["2014-05-08", "DYNAMATECH", "excluded_unresolved",
                  "Scope waiver only", "Issue #4"]],
            )
            self.write_csv(
                absences,
                ["date", "symbol", "series", "status"],
                [["2014-05-08", "DYNAMATECH", "EQ", "unresolved_archive_absence"]],
            )

            rows = load_scope_exclusions(ledger)
            matched, unmatched, issues = match_scope_exclusions_to_archive_absences(rows, absences)

            self.assertEqual(len(matched), 1)
            self.assertEqual(unmatched, [])
            self.assertEqual(issues, [])
            self.assertEqual(rows[0]["status"], "excluded_unresolved")
            self.assertNotEqual(rows[0]["status"], "verified_no_trade")

    def test_mismatched_absence_does_not_authorize_an_exclusion(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger = root / "exclusions.csv"
            absences = root / "absences.csv"
            self.write_csv(
                ledger,
                ["date", "symbol", "status", "reason", "approval_reference"],
                [["2014-05-08", "DYNAMATECH", "excluded_unresolved",
                  "Scope waiver only", "Issue #4"]],
            )
            self.write_csv(
                absences,
                ["date", "symbol", "status"],
                [["2014-05-09", "DYNAMATECH", "unresolved_archive_absence"]],
            )

            rows = load_scope_exclusions(ledger)
            matched, unmatched, issues = match_scope_exclusions_to_archive_absences(rows, absences)

            self.assertEqual(matched, set())
            self.assertEqual(len(unmatched), 1)
            self.assertTrue(issues)

    def test_invalid_status_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "exclusions.csv"
            self.write_csv(
                ledger,
                ["date", "symbol", "status", "reason", "approval_reference"],
                [["2014-05-08", "DYNAMATECH", "verified_no_trade",
                  "Not an allowed scope status", "Issue #4"]],
            )
            with self.assertRaises(ValueError):
                load_scope_exclusions(ledger)

    def test_exclusion_without_provenance_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "exclusions.csv"
            self.write_csv(
                ledger,
                ["date", "symbol", "status", "reason", "approval_reference"],
                [["2014-05-08", "DYNAMATECH", "excluded_unresolved", "", ""]],
            )
            with self.assertRaises(ValueError):
                load_scope_exclusions(ledger)

    def test_diagnostic_lists_only_unresolved_absences_not_scope_excluded_pairs(self):
        with tempfile.TemporaryDirectory() as directory:
            absences = Path(directory) / "absences.csv"
            self.write_csv(
                absences,
                ["date", "symbol", "series", "status"],
                [
                    ["2014-05-08", "DYNAMATECH", "EQ", "unresolved_archive_absence"],
                    ["2020-01-02", "EXAMPLE", "EQ", "unresolved_archive_absence"],
                    ["2020-01-03", "OTHER", "EQ", "observed"],
                ],
            )
            waived = {(pd.Timestamp("2014-05-08"), "DYNAMATECH")}
            details = unresolved_archive_absence_details(absences, waived)
            self.assertEqual(details, [{"date": "2020-01-02", "symbol": "EXAMPLE"}])


if __name__ == "__main__":
    unittest.main()
