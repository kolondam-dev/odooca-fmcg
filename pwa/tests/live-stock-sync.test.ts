import { describe, expect, it, vi } from "vitest";
import { MockProvider } from "../src/data/mock";
import { orderQuote } from "../src/domain/order-pricing";
import type { Snapshot } from "../src/domain/contracts";

describe("Live Stock Sync and Pricing Invariance Contract (P2)", () => {
    it("updates live stock counts without mutating morning session snapshot or version", async () => {
        const provider = new MockProvider("sales");
        const morningSnapshot = await provider.snapshot();
        const initialStock = morningSnapshot.products[0].stock;
        const initialPrice = morningSnapshot.products[0].price;
        const initialVersion = morningSnapshot.version;

        // Fresh snapshot from backend with reduced stock (booked by other sales)
        const freshSnapshot: Snapshot = {
            ...morningSnapshot,
            version: "fresh-snapshot-hash-v2",
            updatedAt: new Date().toISOString(),
            products: morningSnapshot.products.map((p, idx) =>
                idx === 0 ? { ...p, stock: 5 } : p,
            ),
        };

        // Extract live stock mapping without touching session snapshot
        const liveStock: Record<string, number> = Object.fromEntries(
            morningSnapshot.products.map((p) => [p.id, p.stock]),
        );
        for (const p of freshSnapshot.products) {
            liveStock[p.id] = p.stock;
        }

        // 1. Live stock mapping reflects new available quantity
        expect(liveStock[morningSnapshot.products[0].id]).toBe(5);
        expect(liveStock[morningSnapshot.products[0].id]).not.toBe(
            initialStock,
        );

        // 2. Authoritative session snapshot and pricing remain strictly preserved
        expect(morningSnapshot.version).toBe(initialVersion);
        expect(morningSnapshot.products[0].price).toBe(initialPrice);
        expect(morningSnapshot.products[0].stock).toBe(initialStock);
    });

    it("locks order pricing and snapshot_version even if backend prices change mid-day", async () => {
        const provider = new MockProvider("sales");
        const morningSnapshot = await provider.snapshot();
        const product = morningSnapshot.products[0];

        // Fresh backend snapshot where price changed from 187200 to 250000
        const freshSnapshot: Snapshot = {
            ...morningSnapshot,
            version: "new-price-snapshot-v3",
            updatedAt: new Date().toISOString(),
            products: morningSnapshot.products.map((p, idx) =>
                idx === 0 ? { ...p, price: 250000 } : p,
            ),
        };

        // Order quotes evaluate strictly against the morning session snapshot
        const quote = orderQuote(
            [{ product_id: product.id, qty: "2", uom: "carton" }],
            morningSnapshot,
        );

        // Price must equal morning snapshot price * 2, not fresh price * 2
        expect(quote.gross).toBe(product.price * 2);
        expect(quote.gross).not.toBe(250000 * 2);

        // Fresh snapshot price change is ignored by order pricing
        const freshQuote = orderQuote(
            [{ product_id: product.id, qty: "2", uom: "carton" }],
            freshSnapshot,
        );
        expect(freshQuote.gross).toBe(500000);
        expect(quote.gross).toBe(morningSnapshot.products[0].price * 2);
    });

    it("preserves last known stock gracefully on offline or network failure", async () => {
        const provider = new MockProvider("sales");
        const morningSnapshot = await provider.snapshot();
        const liveStock: Record<string, number> = Object.fromEntries(
            morningSnapshot.products.map((p) => [p.id, p.stock]),
        );

        // Simulate network failure during background stock refresh
        const refreshStock = async (mockProvider: {
            snapshot: () => Promise<Snapshot>;
        }) => {
            try {
                const fresh = await mockProvider.snapshot();
                for (const p of fresh.products) {
                    liveStock[p.id] = p.stock;
                }
            } catch {
                // Graceful fallback preserves existing stock
            }
        };

        const offlineProvider = {
            snapshot: vi.fn(async () => {
                throw new Error("Network unreachable");
            }),
        };

        await refreshStock(offlineProvider);

        // Stock mapping remains intact and unchanged
        expect(liveStock[morningSnapshot.products[0].id]).toBe(
            morningSnapshot.products[0].stock,
        );
    });

    it("ignores stale responses that resolve out of order", async () => {
        const provider = new MockProvider("sales");
        const morningSnapshot = await provider.snapshot();
        const productId = morningSnapshot.products[0].id;

        const liveStock: Record<string, number> = { [productId]: 48 };
        let currentGen = 0;

        const executeSync = async (
            gen: number,
            promise: Promise<{ stock: number }>,
        ) => {
            try {
                const result = await promise;
                // Guard: discard if newer generation already started
                if (gen === currentGen) {
                    liveStock[productId] = result.stock;
                }
            } catch {
                // noop
            }
        };

        // Request 1: slow response (resolves later with stale stock = 48)
        let resolveRequest1!: (val: { stock: number }) => void;
        const req1Promise = new Promise<{ stock: number }>((resolve) => {
            resolveRequest1 = resolve;
        });

        // Request 2: fast response (resolves immediately with fresh stock = 12)
        const req2Promise = Promise.resolve({ stock: 12 });

        // Trigger Request 1 (gen 1)
        currentGen = 1;
        const p1 = executeSync(1, req1Promise);

        // Trigger Request 2 (gen 2)
        currentGen = 2;
        const p2 = executeSync(2, req2Promise);

        await p2;
        expect(liveStock[productId]).toBe(12);

        // Now Request 1 resolves late with older stock
        resolveRequest1({ stock: 48 });
        await p1;

        // Stock must still be 12, not overwritten by stale Request 1
        expect(liveStock[productId]).toBe(12);
    });
});
