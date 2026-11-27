import { afterEach, expect, it, vi } from "vitest";
import { ApiError, type Command } from "../src/domain/contracts";
import { HttpProvider } from "../src/data/provider";
import { MockProvider } from "../src/data/mock";

vi.mock("../src/domain/evidence-package", async (importOriginal) => ({
    ...(await importOriginal<
        typeof import("../src/domain/evidence-package")
    >()),
    // Integrity is exercised by the real browser/outbox; this test isolates
    // the official upload -> immutable command transport boundary.
    assertLocalEvidence: vi.fn(async () => undefined),
}));
const upload = vi.hoisted(() => vi.fn());
vi.mock("../src/data/official-evidence", () => ({
    uploadOfficialEvidence: upload,
}));
afterEach(() => {
    vi.unstubAllGlobals();
    upload.mockReset();
});

function setup() {
    vi.stubGlobal("__QA_TOOLS__", false);
    const owner = "1:40";
    const id = crypto.randomUUID();
    const now = new Date().toISOString();
    const source = {
        id: "WH/OUT/06409",
        outlet_id: "8",
        trip: "TRIP-ACC-20261127-01",
        version: "odoo-delivery-v1:exact",
        owner,
        business_date: "2026-11-27",
    };
    const cmd = {
        schema_version: 1,
        client_uuid: crypto.randomUUID(),
        occurred_at: now,
        type: "delivery.pod.submit",
        payload: {
            source,
            evidence: {
                id,
                capturedAt: now,
                latitude: 1.458,
                longitude: 124.825,
                accuracy: 3,
                packageHash: "a".repeat(64),
            },
        },
    } as Command;
    const provider = new HttpProvider();
    Object.assign(provider, {
        identity: { id: "40", companyId: "1", businessDate: "2026-11-27" },
        csrf: "test-csrf",
        lastSnapshot: {
            version: "server-snapshot-v1",
            scope: {
                company_id: "1",
                user_id: "40",
                warehouse_id: "1",
                business_date: "2026-11-27",
            },
            deliveries: [source],
        },
    });
    const row = {
        owner,
        key: `${owner}:${id}`,
        capturedAt: now,
        blob: new Blob(["jpeg"], { type: "image/jpeg" }),
        visual: { selectedAt: now, fixSampledAt: now },
    };
    const store = { getEvidence: vi.fn(async () => row) };
    return { provider, cmd, store, owner, id, source };
}

it("uploads the exact local POD photo before Odoo command and translates only the wire hash", async () => {
    const { provider, cmd, store, owner, id, source } = setup();
    const events: string[] = [];
    const serverHash = "b".repeat(64);
    upload.mockImplementation(async (metadata) => {
        events.push("evidence");
        expect(metadata).toMatchObject({
            client_uuid: id,
            outlet_id: source.outlet_id,
            snapshot_version: "server-snapshot-v1",
            business_date: source.business_date,
        });
        return { receipt: { original_sha256: serverHash } };
    });
    vi.stubGlobal(
        "fetch",
        vi.fn(async (_url, options) => {
            events.push("command");
            const posted = JSON.parse(options.body);
            expect(posted.client_uuid).toBe(cmd.client_uuid);
            expect(posted.payload.evidence.packageHash).toBe(serverHash);
            return {
                ok: true,
                json: async () => ({
                    client_uuid: cmd.client_uuid,
                    status: "accepted",
                    message: "Saved",
                    reference: "POD-OFFICIAL",
                }),
            };
        }),
    );
    const result = await provider.submitWithEvidence(
        cmd,
        store as never,
        owner,
    );
    expect(result.reference).toBe("POD-OFFICIAL");
    expect(events).toEqual(["evidence", "command"]);
    if (cmd.type !== "delivery.pod.submit") throw new Error("wrong fixture");
    expect(cmd.payload.evidence.packageHash).toBe("a".repeat(64));
});

it("fails closed when official evidence is rejected or the authenticated uploader is missing", async () => {
    const { provider, cmd, store, owner } = setup();
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    upload.mockRejectedValue(new ApiError(422, "geofence_outside"));
    await expect(
        provider.submitWithEvidence(cmd, store as never, owner),
    ).rejects.toMatchObject({ status: 422 });
    expect(fetch).not.toHaveBeenCalled();
    const fixture = new MockProvider("delivery");
    const wrapped = new MockProvider("delivery", true, {
        bootstrap: () => fixture.bootstrap(),
        snapshot: () => fixture.snapshot(),
        submit: vi.fn(),
    });
    await expect(
        wrapped.submitWithEvidence(cmd, store as never, owner),
    ).rejects.toMatchObject({ status: 409 });
});
