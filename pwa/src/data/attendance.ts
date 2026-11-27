import { ApiError, ReceiptSchema, type Identity } from "../domain/contracts";
import type { EvidenceReference } from "../domain/evidence-package";
import {
    AttendanceEvidenceMetadataSchema,
    AttendanceEvidenceReceiptSchema,
} from "../domain/official-evidence";

export class AttendanceRecaptureRequired extends ApiError {
    constructor(message: string) {
        super(422, message);
    }
}

export type AttendanceEvent = "check_in" | "check_out";

export async function postAttendance(
    identity: Identity,
    event: AttendanceEvent,
    evidence: EvidenceReference,
    photo: Blob,
    fixAt: string,
) {
    if (!identity.csrfToken || !identity.attendanceOffice)
        throw new ApiError(401, "Muat ulang sesi untuk mencatat absensi.");
    const options = {
        method: "POST",
        credentials: "same-origin",
        redirect: "error",
        cache: "no-store",
    } as const;
    const metadata = AttendanceEvidenceMetadataSchema.parse({
        client_uuid: evidence.id,
        attendance_event: event,
        business_date: identity.businessDate,
        photo_selected_at: evidence.capturedAt,
        device_recorded_at: evidence.capturedAt,
        fix_sampled_at: fixAt,
        latitude: evidence.latitude,
        longitude: evidence.longitude,
        accuracy: evidence.accuracy,
    });
    const form = new FormData();
    form.set("csrf_token", identity.csrfToken);
    form.set("metadata", JSON.stringify(metadata));
    form.set("photo", photo, "attendance.jpg");
    const upload = await fetch("/api/v1/evidence", {
        ...options,
        body: form,
        signal: AbortSignal.timeout(15000),
    });
    if (upload.status === 422)
        throw new AttendanceRecaptureRequired(
            "Bukti ditolak. Periksa lokasi kantor, perbarui GPS, lalu ambil foto ulang.",
        );
    if (!upload.ok)
        throw new ApiError(
            upload.status,
            "Bukti belum terkonfirmasi. Coba kirim ulang.",
        );
    const uploaded = AttendanceEvidenceReceiptSchema.parse(await upload.json());
    if (
        uploaded.client_uuid !== evidence.id ||
        uploaded.company_id !== identity.companyId ||
        uploaded.user_id !== identity.id ||
        uploaded.office_id !== identity.attendanceOffice.id ||
        uploaded.attendance_event !== event ||
        uploaded.business_date !== identity.businessDate
    )
        throw new ApiError(409, "Bukti tidak sesuai dengan sesi absensi.");

    const response = await fetch("/api/v1/sync/commands", {
        ...options,
        headers: {
            "Content-Type": "application/json",
            "X-CSRF-Token": identity.csrfToken,
        },
        body: JSON.stringify({
            schema_version: 1,
            client_uuid: evidence.id,
            occurred_at: evidence.capturedAt,
            type: "hris.attendance.capture",
            payload: { evidence_uuid: evidence.id },
        }),
        signal: AbortSignal.timeout(15000),
    });
    if (response.status === 422) {
        const rejection = await response.json().catch(() => null);
        if (rejection?.error === "attendance_evidence_expired")
            throw new AttendanceRecaptureRequired(
                "Bukti absensi kedaluwarsa. Ambil foto dan lokasi baru.",
            );
    }
    if (!response.ok)
        throw new ApiError(
            response.status,
            response.status === 409 || response.status === 422
                ? "Absensi perlu ditinjau. Coba lagi atau hubungi HR."
                : "Status absensi belum terkonfirmasi. Coba kirim ulang.",
        );
    const receipt = ReceiptSchema.parse(await response.json());
    if (
        receipt.client_uuid !== evidence.id ||
        receipt.status !== "accepted" ||
        !/^hr\.attendance:[1-9]\d*$/.test(receipt.reference)
    )
        throw new ApiError(422, "Konfirmasi absensi Odoo tidak sesuai.");
}
