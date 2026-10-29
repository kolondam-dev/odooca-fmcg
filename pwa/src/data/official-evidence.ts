import { ApiError } from "../domain/contracts";
import {
    OfficialEvidenceMetadataSchema,
    OfficialEvidenceReceiptSchema,
    photoHash,
    type OfficialEvidenceMetadata,
} from "../domain/official-evidence";
export async function uploadOfficialEvidence(
    metadata: OfficialEvidenceMetadata,
    photo: File,
    csrf: string,
    signal: AbortSignal,
) {
    OfficialEvidenceMetadataSchema.parse(metadata);
    if (
        !csrf ||
        !photo.size ||
        photo.size > 5 * 1024 * 1024 ||
        !["image/jpeg", "image/png"].includes(photo.type)
    )
        throw new ApiError(
            422,
            "Pilih foto JPEG/PNG maksimal 5 MiB dan hubungkan sesi kembali.",
        );
    const originalHash = await photoHash(photo);
    const form = new FormData();
    form.set("metadata", JSON.stringify(metadata));
    form.set("csrf_token", csrf);
    form.set("photo", photo);
    const response = await fetch("/api/v1/evidence", {
        method: "POST",
        body: form,
        credentials: "same-origin",
        redirect: "error",
        cache: "no-store",
        signal,
    });
    if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        const messages: Record<string, string> = {
            geofence_outside: "Lokasi berada di luar geofence outlet.",
            geofence_uncertain:
                "Akurasi GPS belum memastikan posisi di dalam geofence. Ambil lokasi ulang.",
            stale_location_or_photo:
                "Waktu foto/GPS kedaluwarsa atau jam perangkat tidak sesuai. Ambil ulang.",
            invalid_photo:
                "Isi foto tidak valid atau ukurannya melebihi batas.",
        };
        throw new ApiError(
            response.status,
            messages[error.error] ??
                "Unggah ditolak. Hubungkan sesi dan daily sync kembali.",
        );
    }
    const parsed = OfficialEvidenceReceiptSchema.safeParse(
        await response.json(),
    );
    if (!parsed.success)
        throw new ApiError(
            422,
            "Receipt bukti tidak valid. Hubungkan sesi kembali.",
        );
    const receipt = parsed.data;
    const prefix = `/api/v1/evidence/${metadata.client_uuid}/`;
    if (
        receipt.client_uuid !== metadata.client_uuid ||
        receipt.outlet_id !== metadata.outlet_id ||
        receipt.business_date !== metadata.business_date ||
        receipt.snapshot_version !== metadata.snapshot_version ||
        receipt.original_sha256 !== originalHash ||
        receipt.original_url !== prefix + "original" ||
        receipt.watermarked_url !== prefix + "watermarked"
    )
        throw new ApiError(422, "Receipt bukti tidak sesuai dengan unggahan.");
    for (const key of ["latitude", "longitude", "accuracy"] as const)
        if (receipt[key] !== metadata[key])
            throw new ApiError(422, "Metadata lokasi receipt tidak sesuai.");
    for (const key of [
        "photo_selected_at",
        "device_recorded_at",
        "fix_sampled_at",
    ] as const)
        if (Date.parse(receipt[key]) !== Date.parse(metadata[key]))
            throw new ApiError(422, "Timestamp receipt tidak sesuai.");
    const media = await fetch(receipt.watermarked_url, {
        credentials: "same-origin",
        redirect: "error",
        cache: "no-store",
        signal,
    });
    if (!media.ok)
        throw new ApiError(media.status, "Foto hasil belum dapat dibaca.");
    const watermarked = await media.blob();
    if ((await photoHash(watermarked)) !== receipt.watermarked_sha256)
        throw new ApiError(422, "Hash foto hasil tidak sesuai.");
    return { receipt, watermarked };
}
