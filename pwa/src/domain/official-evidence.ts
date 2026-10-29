import { z } from "zod";
export const OfficialEvidenceMetadataSchema = z
    .object({
        client_uuid: z.uuid(),
        outlet_id: z.string().regex(/^\d+$/),
        business_date: z.string(),
        snapshot_version: z.string(),
        photo_selected_at: z.iso.datetime(),
        device_recorded_at: z.iso.datetime(),
        fix_sampled_at: z.iso.datetime(),
        latitude: z.number().min(-90).max(90),
        longitude: z.number().min(-180).max(180),
        accuracy: z.number().positive().max(10000),
    })
    .strict();
export type OfficialEvidenceMetadata = z.infer<
    typeof OfficialEvidenceMetadataSchema
>;
const hash = z.string().regex(/^[a-f0-9]{64}$/);
export const OfficialEvidenceReceiptSchema =
    OfficialEvidenceMetadataSchema.omit({ snapshot_version: true })
        .extend({
            snapshot_version: z.string(),
            received_at: z.iso.datetime(),
            master_latitude: z.number(),
            master_longitude: z.number(),
            distance_m: z.number().nonnegative(),
            radius_m: z.number().min(5).max(15),
            original_sha256: hash,
            watermarked_sha256: hash,
            binding_sha256: hash,
            original_url: z.string(),
            watermarked_url: z.string(),
        })
        .strict();
export type OfficialEvidenceReceipt = z.infer<
    typeof OfficialEvidenceReceiptSchema
>;
export async function photoHash(photo: Blob) {
    return [
        ...new Uint8Array(
            await crypto.subtle.digest("SHA-256", await photo.arrayBuffer()),
        ),
    ]
        .map((x) => x.toString(16).padStart(2, "0"))
        .join("");
}
