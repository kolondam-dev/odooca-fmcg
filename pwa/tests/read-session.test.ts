import { afterEach, expect, it, vi } from "vitest";
import { ReadSession, witaDate } from "../src/data/read-session";
import { HttpProvider } from "../src/data/provider";
import {
    ApiError,
    type Command,
    type Identity,
    type Snapshot,
} from "../src/domain/contracts";
const identity: Identity = {
    id: "1",
    companyId: "2",
    name: "Sales",
    title: "",
    roles: ["sales"],
    businessDate: "2026-10-29",
};
const snapshot: Snapshot = {
    catalog_version: 2,
    scope: {
        user_id: "1",
        company_id: "2",
        warehouse_id: "3",
        business_date: "2026-10-29",
    },
    version: "one",
    updatedAt: "2026-10-29T01:00:00Z",
    products: [],
    outlets: [],
    deliveries: [],
};
function fixture() {
    const api = {
        bootstrap: vi.fn(async () => identity),
        snapshot: vi.fn(async () => snapshot),
        invalidate: vi.fn(),
    };
    const state = new ReadSession(api, undefined, () => "2026-10-29");
    return { api, state };
}
function deferred<T>() {
    let resolve!: (value: T) => void;
    const promise = new Promise<T>((r) => {
        resolve = r;
    });
    return { promise, resolve };
}
afterEach(() => vi.unstubAllGlobals());
it("loads identity first and revalidates bootstrap before every daily read without persistence", async () => {
    const { api, state } = fixture();
    await state.load();
    expect(state.state.phase).toBe("ready");
    expect(state.state.snapshot).toBeUndefined();
    expect(api.snapshot).not.toHaveBeenCalled();
    await state.load(true);
    expect(api.bootstrap).toHaveBeenCalledTimes(2);
    expect(state.state).toMatchObject({ phase: "synced", snapshot });
});
it.each([401, 403, 409, 422, 503])(
    "removes previous identity and lists on snapshot %s",
    async (status) => {
        const { api, state } = fixture();
        await state.load(true);
        api.snapshot.mockRejectedValueOnce(
            new ApiError(status, "raw server details"),
        );
        await state.load(true);
        expect(state.state).toMatchObject({ phase: "error" });
        expect(state.state.identity).toBeUndefined();
        expect(state.state.snapshot).toBeUndefined();
        expect(state.state.message).not.toContain("raw server details");
    },
);
it("rejects previous day and a day rollover while snapshot is in flight", async () => {
    const { api } = fixture();
    let day = "2026-10-29";
    const state = new ReadSession(api, undefined, () => day);
    const pending = deferred<Snapshot>();
    api.snapshot.mockReturnValueOnce(pending.promise);
    const load = state.load(true);
    await vi.waitFor(() => expect(api.snapshot).toHaveBeenCalledOnce());
    day = "2026-10-30";
    pending.resolve(snapshot);
    await load;
    expect(state.state.phase).toBe("error");
    expect(state.state.snapshot).toBeUndefined();
    await state.load();
    expect(state.state.phase).toBe("error");
});
it("expires the visible list exactly at midnight WITA", async () => {
    const { api } = fixture();
    let day = "2026-10-29";
    const state = new ReadSession(api, undefined, () => day);
    await state.load(true);
    day = "2026-10-30";
    state.checkDay();
    expect(state.state).toMatchObject({ phase: "idle" });
    expect(state.state.snapshot).toBeUndefined();
    expect(witaDate(new Date("2026-10-29T15:59:59.999Z"))).toBe("2026-10-29");
    expect(witaDate(new Date("2026-10-29T16:00:00Z"))).toBe("2026-10-30");
});
it("ignores stale sync success after clear, and stale error after a newer session", async () => {
    const { api, state } = fixture();
    const pending = deferred<Snapshot>();
    api.snapshot.mockReturnValueOnce(pending.promise);
    const old = state.load(true);
    await vi.waitFor(() => expect(api.snapshot).toHaveBeenCalledOnce());
    state.clear();
    pending.resolve(snapshot);
    await old;
    expect(state.state.phase).toBe("idle");
    let reject!: (reason: Error) => void;
    api.bootstrap.mockReturnValueOnce(
        new Promise((_, r) => {
            reject = r;
        }),
    );
    const stale = state.load();
    await state.load(true);
    reject(new ApiError(401, "old"));
    await stale;
    expect(state.state.phase).toBe("synced");
});
it("read-only adapter blocks commands before any network access", async () => {
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    await expect(
        new HttpProvider({ readOnly: true }).submit({} as Command),
    ).rejects.toMatchObject({ status: 405 });
    expect(fetch).not.toHaveBeenCalled();
});
it("invalidate cancels an in-flight bootstrap and blocks snapshot/submit", async () => {
    const pending = deferred<Response>();
    vi.stubGlobal(
        "fetch",
        vi.fn(() => pending.promise),
    );
    const provider = new HttpProvider();
    const bootstrap = provider.bootstrap();
    provider.invalidate();
    pending.resolve(
        new Response(JSON.stringify({ ...identity, csrfToken: "old" })),
    );
    await expect(bootstrap).rejects.toMatchObject({ status: 409 });
    await expect(provider.snapshot()).rejects.toMatchObject({ status: 401 });
    await expect(provider.submit({} as Command)).rejects.toMatchObject({
        status: 401,
    });
});
