import { readFileSync } from "node:fs";
import { describe, expect, it, vi } from "vitest";
import {
    canOpen,
    CommandSchema,
    IdentitySchema,
    ReceiptSchema,
    validateOrder,
} from "../src/domain/contracts";
import { HttpProvider } from "../src/data/provider";
import { geofence } from "../src/domain/format";
const identity = {
    id: "one",
    companyId: "c",
    name: "Tester",
    title: "",
    roles: ["sales", "hris"],
    businessDate: "2026-10-27",
    csrfToken: "test-csrf",
};
const snapshot = {
    version: "v1",
    updatedAt: "",
    outlets: [],
    deliveries: [],
    products: [
        {
            id: "p1",
            name: "",
            brand: "",
            principal: "a",
            unit: "carton",
            price: 1,
            stock: 0,
        },
        {
            id: "p2",
            name: "",
            brand: "",
            principal: "b",
            unit: "carton",
            price: 2,
            stock: 1,
        },
    ],
};
describe("contract boundaries", () => {
    it("rejects forged/unrecognised role and malformed command/receipt", () => {
        expect(
            IdentitySchema.safeParse({ ...identity, roles: ["owner"] }).success,
        ).toBe(false);
        expect(
            CommandSchema.safeParse({ type: "account.move.post", payload: {} })
                .success,
        ).toBe(false);
        expect(
            ReceiptSchema.safeParse({
                client_uuid: crypto.randomUUID(),
                status: "posted",
            }).success,
        ).toBe(false);
    });
    it("supports stacked field roles while hiding unassigned navigation", () => {
        expect(canOpen(["sales", "hris"], "delivery")).toBe(false);
        expect(canOpen(["sales", "delivery", "hris"], "delivery")).toBe(true);
    });
    it("rejects mixed principals and invalid quantities, without treating cached stock as authority", () => {
        expect(
            validateOrder(
                [
                    { productId: "p1", quantity: 1 },
                    { productId: "p2", quantity: 1 },
                ],
                snapshot,
            ),
        ).toMatch(/principal/);
        expect(
            validateOrder([{ productId: "p1", quantity: -1 }], snapshot),
        ).toBeTruthy();
        expect(
            validateOrder([{ productId: "p1", quantity: 1 }], snapshot),
        ).toBeNull();
    });
    it("holds uncertain geofence rather than expanding radius with poor accuracy", () => {
        expect(geofence(4, 3, 10)).toBe("inside");
        expect(geofence(4, 20, 10)).toBe("uncertain");
        expect(geofence(40, 5, 10)).toBe("outside");
        expect(geofence(0, -1, 10)).toBe("uncertain");
    });
    it("HTTP provider never falls back to fixtures on an auth failure", async () => {
        vi.stubGlobal(
            "fetch",
            vi.fn().mockResolvedValue(new Response("{}", { status: 401 })),
        );
        await expect(new HttpProvider().bootstrap()).rejects.toMatchObject({
            status: 401,
        });
        vi.unstubAllGlobals();
    });
    it("HTTP writes require CSRF bootstrap and preserve command UUID / session credentials", async () => {
        const provider = new HttpProvider();
        const uuid = crypto.randomUUID();
        const command = CommandSchema.parse({
            schema_version: 1,
            client_uuid: uuid,
            type: "sales.order.submit",
            occurred_at: new Date().toISOString(),
            payload: {},
        });
        await expect(provider.submit(command)).rejects.toMatchObject({
            status: 401,
        });
        const fetch = vi
            .fn()
            .mockResolvedValueOnce(new Response(JSON.stringify(identity)))
            .mockResolvedValueOnce(
                new Response(
                    JSON.stringify({
                        client_uuid: uuid,
                        status: "needs_approval",
                        reference: "r",
                        message: "pending",
                    }),
                ),
            );
        vi.stubGlobal("fetch", fetch);
        await provider.bootstrap();
        await provider.submit(command);
        expect(fetch.mock.calls[1][1]).toMatchObject({
            credentials: "same-origin",
            method: "POST",
            body: JSON.stringify(command),
            headers: { "X-CSRF-Token": "test-csrf" },
        });
        vi.unstubAllGlobals();
    });
});

it("exports paired visit photo fields for DTOs and command payloads while retaining legacy optional fields", () => {
    const spec = JSON.parse(
        readFileSync(
            new URL("../contracts/openapi.json", import.meta.url),
            "utf8",
        ),
    );
    const schemas = spec.components.schemas;
    const pair = {
        evidence_version: ["evidence"],
        evidence: ["evidence_version"],
    };
    for (const name of ["VisitCheckIn", "VisitCheckOut"]) {
        expect(schemas[name].dependentRequired).toEqual(pair);
        expect(schemas[name].required).not.toContain("evidence");
    }
    const photoBranches = schemas.Command.anyOf.filter(
        (v: any) => v.properties.payload.properties?.evidence_version,
    );
    expect(photoBranches).toHaveLength(2);
    for (const branch of photoBranches)
        expect(branch.properties.payload.dependentRequired).toEqual(pair);
});
