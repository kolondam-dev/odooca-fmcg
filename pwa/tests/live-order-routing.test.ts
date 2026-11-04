import { afterEach, expect, it, vi } from "vitest";
import { MockProvider } from "../src/data/mock";
import { HttpProvider } from "../src/data/provider";
import { FieldStore } from "../src/storage/store";
import type { Command, Receipt } from "../src/domain/contracts";

const identity = {
    id: "live-salesman",
    companyId: "company",
    name: "Salesman",
    title: "Sales",
    roles: ["sales"],
    businessDate: "2026-11-04",
    csrfToken: "csrf-test",
};
const order = (discounted: boolean): Command => ({
    schema_version: 1,
    client_uuid: crypto.randomUUID(),
    type: "sales.order.submit",
    occurred_at: new Date().toISOString(),
    payload: {
        outlet_id: "41",
        snapshot_version: "morning-v1",
        lines: [{ product_id: "51", qty: "1", uom: "carton" }],
        ...(discounted
            ? { discount_request: { percent: 5, reason: "Promo pelanggan" } }
            : {}),
    },
});
afterEach(() => vi.unstubAllGlobals());

it.each([false, true])(
    "forwards SO (discount=%s) through HttpProvider with original payload and official receipt",
    async (discounted) => {
        vi.stubGlobal("navigator", { onLine: true });
        const command = order(discounted);
        const receipt: Receipt = {
            client_uuid: command.client_uuid,
            status: discounted ? "needs_approval" : "accepted",
            reference: "SO0001",
            message: "Odoo receipt",
        };
        const fetcher = vi
            .fn()
            .mockResolvedValueOnce(Response.json(identity))
            .mockResolvedValueOnce(Response.json(receipt));
        vi.stubGlobal("fetch", fetcher);
        const http = new HttpProvider();
        await http.bootstrap();
        const provider = new MockProvider("sales", true, http);
        expect(await provider.submit(command)).toEqual(receipt);
        expect(fetcher).toHaveBeenCalledTimes(2);
        const [path, request] = fetcher.mock.calls[1];
        expect(path).toBe("/api/v1/sync/commands");
        expect(JSON.parse(request.body)).toEqual(command);
        expect(request.headers["X-CSRF-Token"]).toBe("csrf-test");
    },
);

it.each([401, 409, 422, 503])(
    "propagates backend %s for discounted SO without caching a simulator receipt",
    async (status) => {
        vi.stubGlobal("navigator", { onLine: true });
        const command = order(true);
        const fetcher = vi
            .fn()
            .mockResolvedValueOnce(Response.json(identity))
            .mockResolvedValueOnce(new Response("Rejected", { status }));
        vi.stubGlobal("fetch", fetcher);
        const http = new HttpProvider();
        await http.bootstrap();
        const provider = new MockProvider("sales", true, http);
        await expect(provider.submit(command)).rejects.toMatchObject({
            status,
        });
        expect(
            await new FieldStore().receipt(
                `${identity.id}:${command.type}:${command.client_uuid}`,
            ),
        ).toBeUndefined();
    },
);

it("refuses local simulator decisions on an official Odoo receipt even in a demo-capable build", async () => {
    const command = order(true);
    const row = {
        owner: identity.id,
        command,
        state: "needs_approval" as const,
        key: "official",
        label: "Order",
        attempts: 1,
        nextAttempt: 0,
        receipt: {
            client_uuid: command.client_uuid,
            status: "needs_approval" as const,
            reference: "SO0001",
            message: "Menunggu approval Odoo",
        },
    };
    await expect(
        new FieldStore().decideDemoDiscount(
            identity.id,
            row,
            true,
            "Manager approved",
        ),
    ).rejects.toThrow("Approval SO resmi");
    expect(row.state).toBe("needs_approval");
});
