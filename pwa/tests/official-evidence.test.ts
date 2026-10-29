import { afterEach, expect, it, vi } from "vitest";
import { uploadOfficialEvidence } from "../src/data/official-evidence";
import {
    photoHash,
    type OfficialEvidenceMetadata,
} from "../src/domain/official-evidence";
const metadata: OfficialEvidenceMetadata = {
    client_uuid: "38f3d9e8-3ac5-42d4-b4e9-fc98c21630e8",
    outlet_id: "12",
    business_date: "2026-10-29",
    snapshot_version: "v1",
    photo_selected_at: "2026-10-29T01:00:00Z",
    device_recorded_at: "2026-10-29T01:00:00Z",
    fix_sampled_at: "2026-10-29T01:00:00Z",
    latitude: 1.465,
    longitude: 124.833,
    accuracy: 1,
};
const scope = { userId: "1", companyId: "2", warehouseId: "3" };
const photo = new File(["image"], "photo.png", { type: "image/png" });
async function receipt() {
    return {
        ...metadata,
        user_id: "1",
        company_id: "2",
        warehouse_id: "3",
        assignment_id: "4",
        received_at: "2026-10-29T01:00:01Z",
        master_latitude: 1.465,
        master_longitude: 124.833,
        distance_m: 0,
        radius_m: 10,
        original_sha256: await photoHash(photo),
        watermarked_sha256: await photoHash(photo),
        binding_sha256: "a".repeat(64),
        original_url: `/api/v1/evidence/${metadata.client_uuid}/original`,
        watermarked_url: `/api/v1/evidence/${metadata.client_uuid}/watermarked`,
    };
}
afterEach(() => vi.unstubAllGlobals());
it("sends native multipart CSRF, checks owner-bound receipt and verifies the derivative hash", async () => {
    const fetch = vi
        .fn()
        .mockResolvedValueOnce(
            new Response(JSON.stringify(await receipt()), { status: 201 }),
        )
        .mockResolvedValueOnce(new Response(photo));
    vi.stubGlobal("fetch", fetch);
    const result = await uploadOfficialEvidence(
        metadata,
        photo,
        "native-csrf",
        new AbortController().signal,
        scope,
    );
    expect(result.receipt.client_uuid).toBe(metadata.client_uuid);
    const [path, options] = fetch.mock.calls[0];
    expect(path).toBe("/api/v1/evidence");
    expect(options).toMatchObject({
        method: "POST",
        credentials: "same-origin",
        redirect: "error",
        cache: "no-store",
    });
    expect(options.body.get("csrf_token")).toBe("native-csrf");
    expect(JSON.parse(options.body.get("metadata"))).toEqual(metadata);
    expect(options.headers).toBeUndefined();
});
it.each([
    "user_id",
    "company_id",
    "warehouse_id",
    "client_uuid",
    "outlet_id",
    "snapshot_version",
    "original_url",
    "latitude",
    "device_recorded_at",
])("rejects changed receipt %s before reading any media", async (key) => {
    const value = await receipt();
    const changed = {
        ...value,
        [key]:
            key === "outlet_id"
                ? "99"
                : key === "latitude"
                  ? 2
                  : key === "device_recorded_at"
                    ? "2026-10-29T02:00:00Z"
                    : key === "client_uuid"
                      ? "c88b89d7-0c4a-4a6a-a0e3-2c97176f3bc0"
                      : "different",
    };
    const fetch = vi
        .fn()
        .mockResolvedValue(new Response(JSON.stringify(changed)));
    vi.stubGlobal("fetch", fetch);
    await expect(
        uploadOfficialEvidence(
            metadata,
            photo,
            "csrf",
            new AbortController().signal,
            scope,
        ),
    ).rejects.toMatchObject({ status: 422 });
    expect(fetch).toHaveBeenCalledTimes(1);
});
it("rejects media content which does not match the server hash", async () => {
    vi.stubGlobal(
        "fetch",
        vi
            .fn()
            .mockResolvedValueOnce(
                new Response(JSON.stringify(await receipt())),
            )
            .mockResolvedValueOnce(new Response("tampered")),
    );
    await expect(
        uploadOfficialEvidence(
            metadata,
            photo,
            "csrf",
            new AbortController().signal,
            scope,
        ),
    ).rejects.toMatchObject({ status: 422 });
});
it("rejects missing CSRF and oversized files before network access", async () => {
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    await expect(
        uploadOfficialEvidence(
            metadata,
            photo,
            "",
            new AbortController().signal,
            scope,
        ),
    ).rejects.toMatchObject({ status: 422 });
    const huge = new File([new Uint8Array(5 * 1024 * 1024 + 1)], "huge.png", {
        type: "image/png",
    });
    await expect(
        uploadOfficialEvidence(
            metadata,
            huge,
            "csrf",
            new AbortController().signal,
            scope,
        ),
    ).rejects.toMatchObject({ status: 422 });
    expect(fetch).not.toHaveBeenCalled();
});
