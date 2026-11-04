"""Native ORM regression for complete receipt-to-storage quantity coverage."""
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestReceivingDwell(TransactionCase):
    def setUp(self):
        super().setUp()
        self.wh = self.env["stock.warehouse"].search([("company_id", "=", self.env.company.id)], limit=1)
        self.input = self.env["stock.location"].create({"name": "Dwell receiving input",
            "usage": "internal", "location_id": self.wh.view_location_id.id,
            "company_id": self.env.company.id})
        self.products = self.env["product.product"].create([
            {"name": "Dwell product " + name, "type": "consu", "is_storable": True} for name in ("A", "B")])
        self.supplier = self.env.ref("stock.stock_location_suppliers")

    def _operation(self, picking_type, source, dest, items, unit=None):
        return self.env["stock.picking"].create({"picking_type_id": picking_type.id,
            "location_id": source.id, "location_dest_id": dest.id,
            "move_ids": [(0, 0, {"product_id": product.id,
                "product_uom": (unit or product.uom_id).id, "product_uom_qty": qty,
                "quantity": qty, "state": "assigned", "picked": True,
                "location_id": source.id, "location_dest_id": dest.id,
                "move_orig_ids": [(6, 0, origins.ids)]}) for product, qty, origins in items]})

    def _receipt(self, both=True, destination=None):
        empty = self.env["stock.move"]
        receipt = self._operation(self.wh.in_type_id, self.supplier, destination or self.input,
            [(p, 10, empty) for p in (self.products if both else self.products[:1])])
        clock = self.env["id.warehouse.clock"].create({"name": "Receipt elapsed",
            "picking_id": receipt.id, "kind": "receiving_dwell"})
        clock.action_start()
        receipt.move_ids.state = "done"
        return receipt, clock

    def _put(self, root, qty=10, destination=None):
        put = self._operation(self.wh.int_type_id, root.location_dest_id,
            destination or self.wh.lot_stock_id, [(root.product_id, qty, root)])
        put.move_ids.state = "done"
        return put

    def _blocked(self, clock):
        with self.assertRaises(UserError):
            clock.action_complete()
        self.assertEqual(clock.state, "running")
        self.assertFalse(clock.ended_at)

    def test_missing_second_storage_branch_blocks_then_full_receipt_completes(self):
        receipt, clock = self._receipt()
        a, b = receipt.move_ids.sorted("id")
        put_a = self._put(a)
        clock.completion_picking_id = put_a
        self._blocked(clock)  # old code accepted A while B still sat at input
        self._put(b)
        clock.action_complete()
        self.assertEqual(clock.state, "done")
        facts = (clock.started_at, clock.ended_at, clock.started_by, clock.ended_by)
        clock.action_complete()
        self.assertEqual((clock.started_at, clock.ended_at, clock.started_by, clock.ended_by), facts)

    def test_cancelled_second_putaway_is_not_storage_arrival(self):
        receipt, clock = self._receipt()
        a, b = receipt.move_ids.sorted("id")
        put_a = self._put(a)
        cancelled = self._put(b)
        cancelled.move_ids.state = "cancel"
        clock.completion_picking_id = put_a
        self._blocked(clock)

    def test_split_quantities_and_pending_backorder_must_be_complete(self):
        receipt, clock = self._receipt(both=False)
        root = receipt.move_ids
        first = self._put(root, 6)
        clock.completion_picking_id = first
        self._blocked(clock)  # 6 of 10 physically forwarded
        remainder = self._operation(self.wh.int_type_id, self.input, self.wh.lot_stock_id,
            [(root.product_id, 4, root)])
        remainder.move_ids.quantity = 0
        self._blocked(clock)  # zero recorded done quantity cannot hide pending work
        remainder.move_ids.quantity = 4
        remainder.move_ids.state = "done"
        clock.action_complete()
        self.assertEqual(clock.state, "done")

    def test_overforwarded_quantities_fail_closed(self):
        receipt, clock = self._receipt(both=False)
        clock.completion_picking_id = self._put(receipt.move_ids, 11)
        self._blocked(clock)

    def test_wrong_warehouse_and_unrelated_completion_are_rejected(self):
        receipt, clock = self._receipt(both=False)
        other = self.env["stock.warehouse"].create({"name": "Dwell other warehouse", "code": "DW2",
            "company_id": self.env.company.id})
        clock.completion_picking_id = self._put(receipt.move_ids, destination=other.lot_stock_id)
        self._blocked(clock)

    def test_unrelated_completion_cannot_replace_a_fully_arrived_receipt(self):
        receipt, clock = self._receipt(both=False)
        self._put(receipt.move_ids)
        unrelated = self._operation(self.wh.int_type_id, self.input, self.wh.lot_stock_id,
            [(self.products[0], 10, self.env["stock.move"])])
        unrelated.move_ids.state = "done"
        clock.completion_picking_id = unrelated
        self._blocked(clock)

    def test_one_step_receipt_finishes_at_storage_without_downstream_chain(self):
        receipt, clock = self._receipt(destination=self.wh.lot_stock_id)
        clock.action_complete()
        self.assertEqual(clock.state, "done")

    def test_shared_origin_cannot_reuse_one_storage_quantity_twice(self):
        receipt, clock = self._receipt(both=False)
        foreign = self._operation(self.wh.in_type_id, self.supplier, self.input,
            [(receipt.move_ids.product_id, 10, self.env["stock.move"])])
        foreign.move_ids.state = "done"
        put = self._put(receipt.move_ids)
        put.move_ids.move_orig_ids = [(6, 0, (receipt.move_ids | foreign.move_ids).ids)]
        clock.completion_picking_id = put
        self._blocked(clock)

    def test_onward_quantities_use_native_uom_conversion(self):
        receipt, clock = self._receipt(both=False)
        pack = self.env["uom.uom"].create({"name": "Dwell pair", "relative_factor": 2,
            "relative_uom_id": receipt.move_ids.product_id.uom_id.id})
        put = self._operation(self.wh.int_type_id, self.input, self.wh.lot_stock_id,
            [(receipt.move_ids.product_id, 5, receipt.move_ids)], unit=pack)
        put.move_ids.state = "done"
        clock.completion_picking_id = put
        clock.action_complete()
        self.assertEqual(clock.state, "done")

    def test_pending_shipment_after_first_storage_does_not_block_receiving(self):
        receipt, clock = self._receipt(both=False)
        put = self._put(receipt.move_ids)
        self._operation(self.wh.out_type_id, self.wh.lot_stock_id,
            self.env.ref("stock.stock_location_customers"), [(put.move_ids.product_id, 1, put.move_ids)])
        clock.completion_picking_id = put
        clock.action_complete()
        self.assertEqual(clock.state, "done")
