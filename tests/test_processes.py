import unittest

from examples.lost_update import experiment


class ProcessTests(unittest.TestCase):
    def test_spawned_read_check_write_is_rejected_and_transactional_cas_has_witness(
        self,
    ):
        for fixed in (False, True):
            report = experiment(fixed)
            self.assertEqual(
                report["audit"]["status"],
                "linearizable" if fixed else "nonlinearizable",
            )
            if not fixed:
                self.assertTrue(all(op["output"] for op in report["history"]["operations"]))
                self.assertTrue(report["audit"]["counterexample"]["one_minimal"])


if __name__ == "__main__":
    unittest.main()
