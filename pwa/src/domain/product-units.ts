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
// Presentation labels only. Ratios stay in PackagingSchema and prices stay on
// a carton basis; a missing label falls back to a neutral name.
export const UnitLabelSchema = z.string().trim().min(1).max(24);
export type UnitTier = "carton" | "pack" | "pcs";
export type UnitLabels = { carton: string; pack: string; pcs: string };
export interface UnitOption {
    uom: UnitTier;
    label: string;
    /** Pieces contained in one unit of this tier. */
    per: number;
}
type LabelledProduct = {
    packaging?: Packaging;
    carton_label?: string;
    pack_label?: string;
    unit_label?: string;
};
const DEFAULT_LABELS: UnitLabels = {
    carton: "Karton",
    pack: "Pack",
    pcs: "Pcs",
};
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
export function productUnitLabels(product: LabelledProduct): UnitLabels {
    return {
        carton: product.carton_label?.trim() || DEFAULT_LABELS.carton,
        pack: product.pack_label?.trim() || DEFAULT_LABELS.pack,
        pcs: product.unit_label?.trim() || DEFAULT_LABELS.pcs,
    };
}
/**
 * Orderable tiers of one SKU, largest first. A SKU whose pack equals one piece
 * only offers the carton and the base retail unit.
 */
export function unitOptions(
    product: LabelledProduct,
    catalogVersion?: 2,
): UnitOption[] {
    const packaging = productPackaging(product, catalogVersion);
    const labels = productUnitLabels(product);
    const options: UnitOption[] = [
        { uom: "carton", label: labels.carton, per: packaging.carton },
    ];
    if (packaging.pack > 1)
        options.push({ uom: "pack", label: labels.pack, per: packaging.pack });
    options.push({ uom: "pcs", label: labels.pcs, per: 1 });
    return options;
}
/** "1 Karton = 144 Pcs · 1 Renceng = 12 Pcs" */
export function conversionLabel(
    product: LabelledProduct,
    catalogVersion?: 2,
): string {
    return unitOptions(product, catalogVersion)
        .slice(0, -1)
        .map((option) => `1 ${option.label} = ${option.per} Pcs`)
        .join(" · ");
}
export function unitLabelFor(
    product: LabelledProduct,
    uom: UnitTier,
    catalogVersion?: 2,
): string {
    const labels = productUnitLabels(product);
    // A pack tier without its own ratio is the base retail unit.
    if (uom === "pack" && productPackaging(product, catalogVersion).pack === 1)
        return labels.pcs;
    return labels[uom];
}
export function pcsPerUnit(
    product: { packaging?: Packaging },
    uom: UnitTier,
    catalogVersion?: 2,
): number {
    return productPackaging(product, catalogVersion)[uom];
}
