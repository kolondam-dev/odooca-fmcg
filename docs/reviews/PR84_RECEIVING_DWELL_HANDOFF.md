# PR84 receiving-dwell repair

Every actually received positive-quantity branch must reach first storage in the same warehouse. Each intermediate split must conserve native-UoM quantity. Missing, cancelled, pending, short, excessive or shared-origin onward sources fail closed. Completion must be an actual first-storage operation in the fully covered chain. A separate incoming backorder is a separate receipt/clock; later customer shipment does not reopen receiving.

Ten native ORM regressions cover incomplete/full multi-product chains, cancelled putaway, split/pending backorder, overcoverage, wrong warehouse, unrelated completion, one-step receipt, shared origins, UoM conversion and later shipment. Fixture operations persist native records; they are validation fixtures, not full inventory/accounting workflow acceptance. Local Ruff, manifests, Python parsing and19dashboard JS tests passed; exact-SHA native/upgrade/visual CI pending.

Integrated main2b7cdd2. Original stage5 handoff/log entries remain in parent a29f984 and central main history; scoped repair notes avoid duplicating historical operational logs. This repair does not modify posted transactions, seed data or production services.
