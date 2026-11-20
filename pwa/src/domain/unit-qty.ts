import { productPackaging } from "./product-units.ts";
import type { Packaging } from "./product-units.ts";

/** Jumlah per tingkat satuan; tingkat yang tidak dipakai bernilai 0. */
export type UnitParts = { carton: number; pack: number; pcs: number };

export const UNIT_NAMES = {
    carton: "karton",
    pack: "pack",
    pcs: "pcs",
} as const;

/** Pecah total pcs menjadi karton → pack → pcs memakai rasio SKU. */
export function splitUnits(
    totalPcs: number,
    per: { carton: number; pack: number },
): UnitParts {
    let rest = Math.max(0, Math.round(totalPcs));
    const carton = per.carton > 1 ? Math.floor(rest / per.carton) : 0;
    rest -= carton * per.carton;
    const hasPack = per.pack > 1 && per.pack !== per.carton;
    const pack = hasPack ? Math.floor(rest / per.pack) : 0;
    rest -= pack * per.pack;
    return { carton, pack, pcs: rest };
}

/** Stok sistem (basis karton, boleh pecahan) dipecah ke tingkat satuan. */
export function stockUnits(
    product: { packaging?: Packaging },
    cartons: number,
    catalogVersion?: 2,
): UnitParts {
    const per = productPackaging(product, catalogVersion);
    return splitUnits(cartons * per.carton, per);
}

/** Teks untuk pembaca layar dan tes: "1 karton, 2 pack, 3 pcs". */
export function unitLabel(parts: Partial<UnitParts>): string {
    const out = (["carton", "pack", "pcs"] as const)
        .filter((u) => (parts[u] ?? 0) > 0)
        .map((u) => `${parts[u]} ${UNIT_NAMES[u]}`);
    return out.length ? out.join(", ") : "0";
}
