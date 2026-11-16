import math
import unittest

from regions import assign_units, padded_box, pool_assignment, table_summary, deduplicate_tables


class RegionTests(unittest.TestCase):
    def test_nested_detections_keep_context_and_adjacent_tables(self):
        outer = dict(coordinate=[0, 0, 100, 100], score=.6)
        inner = dict(coordinate=[80, 10, 100, 90], score=.9)
        adjacent = dict(coordinate=[0, 110, 100, 200], score=.8)
        kept, dropped = deduplicate_tables([inner, outer, adjacent])
        self.assertEqual(kept, [outer, adjacent])
        self.assertEqual(dropped[0]['detection'], inner)

    def test_identical_boxes_count_once(self):
        box = dict(coordinate=[0, 0, 100, 100], score=.7)
        kept, dropped = deduplicate_tables([box, box])
        self.assertEqual(len(kept), 1)
        self.assertEqual(len(dropped), 1)

    def test_padding_clamps_to_source(self):
        self.assertEqual(padded_box([0, 0, 100, 100], 100, 100), [0, 0, 100, 100])
        with self.assertRaises(ValueError):
            padded_box([10, 10, 0, 0], 100, 100)

    def test_scaled_coordinates_and_exclusive_overlap(self):
        page = dict(status='success', width=200, height=200,
                    units=[dict(text='1', score=.8, bbox=[20, 20, 40, 40])])
        regions = [dict(bbox_px=[0, 0, 30, 30]), dict(bbox_px=[0, 0, 50, 50])]
        assigned = assign_units(page, regions, (100, 100))
        self.assertEqual(sum(len(a['units']) for a in assigned), 1)
        self.assertEqual(assigned[0]['ambiguous_units'], [0])

    def test_outside_and_boundary_units(self):
        page = dict(status='success', width=100, height=100, units=[
            dict(text='outside', score=.9, bbox=[60, 60, 80, 80]),
            dict(text='edge', score=.8, bbox=[20, 20, 40, 40])])
        assigned = assign_units(page, [dict(bbox_px=[0, 0, 30, 50])], (100, 100))[0]
        self.assertEqual(assigned['source_unit_indices'], [1])
        self.assertEqual(assigned['boundary_units'], [1])

    def test_character_pooling_not_line_mean_pooling(self):
        assignment = dict(units=[dict(text='12', score=.5, characters=[
            dict(text='1', score=.2, unit_kind='character'),
            dict(text='2', score=.8, unit_kind='character')])])
        pooled = pool_assignment(assignment, 'paddle')['confidence']
        self.assertAlmostEqual(pooled['geometric_mean'], .4)
        self.assertEqual(pooled['scored_units'], 2)
        self.assertIsNone(pooled['probability_table_correct'])

    def test_v1_never_substitutes_for_characters(self):
        with self.assertRaises(ValueError):
            pool_assignment(dict(units=[dict(text='12', score=.9)]), 'paddle')

    def test_empty_and_zero_are_distinct(self):
        self.assertIsNone(table_summary([])['geometric_mean'])
        self.assertEqual(table_summary([dict(text='x', score=0)])['geometric_mean'], 0)
        with self.assertRaises(ValueError):
            table_summary([dict(text='x', score=math.nan)])


if __name__ == '__main__':
    unittest.main()
