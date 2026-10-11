import unittest

from pagination import paginate


class PaginateTests(unittest.TestCase):
    def test_first_page_starts_at_first_item(self):
        self.assertEqual(paginate(list(range(10)), 1, 3), [0, 1, 2])

    def test_last_page_holds_the_remainder(self):
        self.assertEqual(paginate(list(range(10)), 4, 3), [9])

    def test_rejects_page_zero(self):
        with self.assertRaises(ValueError):
            paginate([1, 2, 3], 0, 2)


if __name__ == "__main__":
    unittest.main()
