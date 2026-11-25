import { afterEach, describe, expect, it, vi } from "vitest";
import { postAttendance } from "../src/data/attendance";
import type { Identity } from "../src/domain/contracts";

const identity: Identity = {
    id: "42",
    companyId: "8",
    name: "Employee",
    title: "",
    roles: ["sales"],
    businessDate: "2026-11-25",
    csrfToken: "csrf",
    attendanceOffice: {
        id: "12",
        name: "Office",
        latitude: 1.493,
        longitude: 124.841,
        radius: 100,
        coordinate_status: "verified",
    },
};
const evidence = {
    id: "d1890bdf-e068-49ee-9ff3-209bbdccaabe",
    capturedAt: "2026-11-25T00:00:10.000Z",
    latitude: 1.493,
    longitude: 124.841,
    accuracy: 2,
};
const photo = new Blob(["test"], { type: "image/jpeg" });
const fixAt = "2026-11-25T00:00:00.000Z";
const evidenceReceipt = {
    client_uuid: evidence.id,
    company_id: identity.companyId,
    user_id: identity.id,
    office_id: identity.attendanceOffice?.id,
    photo_selected_at: evidence.capturedAt,
    device_recorded_at: evidence.capturedAt,
    fix_sampled_at: fixAt,
    received_at: evidence.capturedAt,
    latitude: evidence.latitude,
    longitude: evidence.longitude,
    accuracy: evidence.accuracy,
    distance_m: 0,
    radius_m: 100,
    original_sha256: "a".repeat(64),
    watermarked_sha256: "b".repeat(64),
    original_url: `/api/v1/evidence/${evidence.id}/original`,
    watermarked_url: `/api/v1/evidence/${evidence.id}/watermarked`,
    attendance_event: "check_in",
    business_date: identity.businessDate,
};
const commandReceipt = {
    client_uuid: evidence.id,
    status: "accepted",
    message: "PWA attendance recorded.",
    reference: "hr.attendance:14",
};

afterEach(() => vi.unstubAllGlobals());

describe("pilot attendance posting", () => {
    it("retries with identical evidence metadata and command after a lost response", async () => {
        const send = vi
            .fn<typeof fetch>()
            .mockResolvedValueOnce(Response.json(evidenceReceipt))
            .mockRejectedValueOnce(new TypeError("Connection lost"))
            .mockResolvedValueOnce(Response.json(evidenceReceipt))
            .mockResolvedValueOnce(Response.json(commandReceipt));
        vi.stubGlobal("fetch", send);

        await expect(
            postAttendance(identity, "check_in", evidence, photo, fixAt),
        ).rejects.toThrow("Connection lost");
        await postAttendance(identity, "check_in", evidence, photo, fixAt);

        const [upload, command, retryUpload, retryCommand] = send.mock.calls;
        expect(upload?.[0]).toBe("/api/v1/evidence");
        expect((upload?.[1]?.body as FormData).get("metadata")).toEqual(
            (retryUpload?.[1]?.body as FormData).get("metadata"),
        );
        expect(command?.[0]).toBe("/api/v1/sync/commands");
        expect(command?.[1]?.body).toEqual(retryCommand?.[1]?.body);
        expect(JSON.parse(String(command?.[1]?.body))).toMatchObject({
            type: "hris.attendance.capture",
            client_uuid: evidence.id,
            payload: { evidence_uuid: evidence.id },
        });
    });

    it("stops before posting when evidence belongs to a different company", async () => {
        const send = vi
            .fn<typeof fetch>()
            .mockResolvedValue(
                Response.json({ ...evidenceReceipt, company_id: "9" }),
            );
        vi.stubGlobal("fetch", send);

        await expect(
            postAttendance(identity, "check_in", evidence, photo, fixAt),
        ).rejects.toThrow("Bukti tidak sesuai");
        expect(send).toHaveBeenCalledTimes(1);
    });
});
