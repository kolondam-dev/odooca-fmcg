import { z } from "zod";
export const PackagingSchema = z
    .object({
        carton: z.number().int().positive().max(1000000),
        pack: z.number().int().positive().max(1000000),
        pcs: z.literal(1),
    })
    .strict()
    .refine(
        (p) => p.carton >= p.pack && p.carton % p.pack === 0,
        "Pack harus membagi karton dalam pcs utuh.",
    );
export type Packaging = z.infer<typeof PackagingSchema>;
export const SnapshotScopeSchema = z
    .object({
        company_id: z.string().min(1),
        user_id: z.string().min(1),
        warehouse_id: z.string().min(1),
        business_date: z.iso.date(),
    })
    .strict();
export function productPackaging(
    product: { packaging?: Packaging },
    catalogVersion?: 2,
): Packaging {
    if (product.packaging !== undefined)
        return PackagingSchema.parse(product.packaging);
    // Only old simulator snapshots used this implicit conversion. Never infer
    // units for a new catalog or an HTTP/live product with missing metadata.
    if (__DEMO__ && catalogVersion === undefined)
        return { carton: 144, pack: 12, pcs: 1 };
    throw new Error("Rasio satuan SKU wajib tersedia pada snapshot.");
}
