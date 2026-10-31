import { z } from "zod";
import { PackagingSchema, UnitLabelSchema } from "../domain/product-units.ts";
import type { Snapshot } from "../domain/contracts";
// Sanitized read-model proposed for the backend; not a raw ORM/RPC response.
// Prices and stock must already have an explicit carton basis and authorized
// company/warehouse scope. ACL and pricing remain backend responsibilities.
export const CatalogRowSchema = z
    .object({
        product_id: z.number().int().positive(),
        default_code: z.string().trim().min(1),
        name: z.string().trim().min(1),
        principal_id: z.number().int().positive(),
        brand_name: z.string(),
        carton_qty: z.number().int().positive(),
        inner_qty: z.number().int().positive(),
        price_per_carton: z.number().nonnegative().finite(),
        stock_cartons: z.number().nonnegative().finite(),
        carton_label: UnitLabelSchema.optional(),
        pack_label: UnitLabelSchema.optional(),
        unit_label: UnitLabelSchema.optional(),
    })
    .strict();
export function mapCatalogProducts(value: unknown): Snapshot["products"] {
    const rows = z.array(CatalogRowSchema).parse(value);
    if (
        new Set(rows.map((r) => r.product_id)).size !== rows.length ||
        new Set(rows.map((r) => r.default_code)).size !== rows.length
    )
        throw new Error("Identitas/kode SKU ganda pada katalog.");
    return rows.map((row) => ({
        id: String(row.product_id),
        sku_code: row.default_code,
        name: row.name,
        principal: String(row.principal_id),
        brand: row.brand_name,
        unit: `karton ${row.carton_qty} pcs / pack ${row.inner_qty} pcs`,
        packaging: PackagingSchema.parse({
            carton: row.carton_qty,
            pack: row.inner_qty,
            pcs: 1,
        }),
        price: row.price_per_carton,
        stock: row.stock_cartons,
        ...(row.carton_label ? { carton_label: row.carton_label } : {}),
        ...(row.pack_label ? { pack_label: row.pack_label } : {}),
        ...(row.unit_label ? { unit_label: row.unit_label } : {}),
        price_basis: "carton" as const,
        stock_basis: "carton" as const,
    }));
}
