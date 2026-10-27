import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { FieldStore } from "../src/storage/store";
import { Outbox } from "../src/domain/outbox";
import { ApiError, type FieldProvider } from "../src/domain/contracts";
import { MockProvider } from "../src/data/mock";
let store: FieldStore;
const provider = (status = 0): FieldProvider => ({
    mode: "demo",
    bootstrap: vi.fn(),
    snapshot: vi.fn(),
    submit: vi.fn(async (c) => {
        if (status) throw new ApiError(status, "test failure");
        return {
            client_uuid: c.client_uuid,
            status: "accepted" as const,
            reference: "DEMO",
            message: "simulated",
        };
    }),
});
beforeEach(() => {
    store = new FieldStore(`test-${crypto.randomUUID()}`);
    vi.stubGlobal("navigator", { onLine: true });
});
afterEach(async () => {
    await store.close();
    vi.unstubAllGlobals();
});
describe("durable outbox", () => {
    it("persists before success and restores a draft/outbox through a second store connection", async () => {
        const name = `persist-${crypto.randomUUID()}`;
        const first = new FieldStore(name);
        await first.draft("a", "order", { qty: 3 });
        await new Outbox(first, "a", provider()).enqueue(
            "sales.order.submit",
            { qty: "3" },
            "Order",
        );
        await first.close();
        const restored = new FieldStore(name);
        expect(await restored.draft("a", "order")).toEqual({ qty: 3 });
        expect(await restored.list("a")).toHaveLength(1);
        await restored.close();
    });
    it("isolates drafts, evidence and commands across identities", async () => {
        await store.draft("a", "order", { secret: "private draft" });
        await store.saveEvidence({
            key: "a:photo",
            owner: "a",
            blob: new Blob(["photo"]),
            capturedAt: "",
            mapStatus: "pending",
        });
        await new Outbox(store, "a", provider()).enqueue(
            "sales.order.submit",
            {},
            "private",
        );
        expect(await store.draft("b", "order")).toBeUndefined();
        expect(await store.list("b")).toEqual([]);
        expect(await store.listEvidence("b")).toEqual([]);
    });
    it("keeps the same command UUID through timeout/retry and does not resend accepted items", async () => {
        const p = provider(503);
        const engine = new Outbox(store, "a", p);
        const item = await engine.enqueue("sales.order.submit", {}, "order");
        await engine.flush();
        expect((await store.list("a"))[0]).toMatchObject({
            state: "queued",
            attempts: 1,
        });
        p.submit = vi.fn(async (c) => ({
            client_uuid: c.client_uuid,
            status: "accepted" as const,
            reference: "r",
            message: "",
        }));
        await engine.retry();
        await engine.flush();
        expect(p.submit).toHaveBeenCalledTimes(1);
        expect((await store.list("a"))[0].command.client_uuid).toBe(
            item.command.client_uuid,
        );
    });
    it("serializes overlapping flush calls for this client engine", async () => {
        const p = provider();
        const engine = new Outbox(store, "a", p);
        await engine.enqueue("sales.order.submit", {}, "order");
        await Promise.all([engine.flush(), engine.flush(), engine.flush()]);
        expect(p.submit).toHaveBeenCalledTimes(1);
    });
    it("holds 401 and terminal rejection instead of retrying them forever", async () => {
        const p = provider(401);
        const engine = new Outbox(store, "a", p);
        await engine.enqueue("sales.order.submit", {}, "order");
        await engine.flush();
        await engine.retry();
        expect((await store.list("a"))[0].state).toBe("auth_required");
        expect(p.submit).toHaveBeenCalledTimes(1);
        const rejected = new Outbox(store, "b", provider(403));
        await rejected.enqueue("sales.order.submit", {}, "order");
        await rejected.flush();
        expect((await store.list("b"))[0].state).toBe("rejected");
    });
    it("does not accept an unrelated or malformed receipt", async () => {
        const p = provider();
        p.submit = vi.fn(async () => ({
            client_uuid: crypto.randomUUID(),
            status: "accepted" as const,
            reference: "x",
            message: "",
        }));
        const engine = new Outbox(store, "a", p);
        await engine.enqueue("sales.order.submit", {}, "order");
        await engine.flush();
        expect((await store.list("a"))[0].state).toBe("queued");
    });
    it("simulator receipt survives adapter recreation and rejects a changed payload", async () => {
        const p = new MockProvider("sales");
        const engine = new Outbox(store, "a", p);
        const item = await engine.enqueue(
            "sales.order.submit",
            { qty: "1" },
            "order",
        );
        const receipt = await p.submit(item.command);
        expect(await new MockProvider("sales").submit(item.command)).toEqual(
            receipt,
        );
        await expect(
            p.submit({
                ...item.command,
                type: "sales.order.submit",
                payload: { qty: "2" },
            }),
        ).rejects.toMatchObject({ status: 409 });
    });
    it("fails explicitly when local persistence fails", async () => {
        vi.spyOn(store, "put").mockRejectedValue(
            new Error("QuotaExceededError"),
        );
        await expect(
            new Outbox(store, "a", provider()).enqueue(
                "sales.order.submit",
                {},
                "order",
            ),
        ).rejects.toThrow("QuotaExceededError");
    });
});
