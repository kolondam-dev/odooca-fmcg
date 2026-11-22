import { describe, expect, it } from "vitest";
import {
    approvalPreviewText,
    previewApproval,
    type ApprovalTiers,
} from "../src/domain/approval-preview";

const block = (free: number | null) => ({
    free_zone_max: free,
    tiers: [
        { min_discount: 0.01, approver: "Supervisor" },
        { min_discount: 3, approver: "Branch Manager" },
        { min_discount: 7, approver: "Direksi" },
    ],
});
const tiers = (
    scope: ApprovalTiers["discount"]["scope"] = "order",
    usage: ApprovalTiers["discount"]["usage"] = [],
    principals: ApprovalTiers["discount"]["principals"] = {},
): ApprovalTiers => ({
    discount: { scope, default: block(2), principals, usage },
});
const base = {
    principal: "10",
    outletId: "5",
    gross: 1_000_000,
    hasProgram: false,
    hasManual: true,
};

describe("previewApproval", () => {
    it("tanpa konfigurasi atau bruto 0 → null (perilaku lama)", () => {
        expect(
            previewApproval({
                ...base,
                tiers: undefined,
                discount: 10,
            }),
        ).toBeNull();
        expect(
            previewApproval({ ...base, tiers: tiers(), gross: 0, discount: 0 }),
        ).toBeNull();
    });
    it("tanpa diskon → none", () => {
        const p = previewApproval({
            ...base,
            tiers: tiers(),
            discount: 0,
            hasManual: false,
        })!;
        expect(p.status).toBe("none");
        expect(approvalPreviewText(p)).toBe("");
    });
    it("di dalam zona bebas (≤ batas) → free dengan sisa Rp", () => {
        const p = previewApproval({
            ...base,
            tiers: tiers(),
            discount: 15_000,
        })!;
        expect(p.status).toBe("free");
        expect(p.pct).toBe(1.5);
        expect(p.headroom).toBe(5_000);
    });
    it("tepat di batas masih zona bebas; lewat sedikit → perlu approval", () => {
        expect(
            previewApproval({ ...base, tiers: tiers(), discount: 20_000 })!
                .status,
        ).toBe("free");
        const p = previewApproval({
            ...base,
            tiers: tiers(),
            discount: 20_001,
        })!;
        expect(p.status).toBe("needs");
        expect(p.chain).toEqual(["Supervisor"]);
    });
    it("rantai berjenjang mengikuti min_discount (≥)", () => {
        const at3 = previewApproval({
            ...base,
            tiers: tiers(),
            discount: 30_000,
        })!;
        expect(at3.chain).toEqual(["Supervisor", "Branch Manager"]);
        expect(at3.next).toEqual({ min_discount: 7, approver: "Direksi" });
        const at8 = previewApproval({
            ...base,
            tiers: tiers(),
            discount: 80_000,
        })!;
        expect(at8.chain).toEqual(["Supervisor", "Branch Manager", "Direksi"]);
        expect(at8.next).toBeNull();
        expect(approvalPreviewText(at8)).toBe(
            "Diskon 8% → perlu Supervisor → Branch Manager → Direksi",
        );
    });
    it("tanpa zona bebas (null) diskon kecil pun perlu tier pertama", () => {
        const t: ApprovalTiers = {
            discount: {
                scope: "order",
                default: block(null),
                principals: {},
                usage: [],
            },
        };
        const p = previewApproval({ ...base, tiers: t, discount: 1_000 })!;
        expect(p.status).toBe("needs");
        expect(p.chain).toEqual(["Supervisor"]);
        expect(p.headroom).toBeNull();
    });
    it("batas khusus principal menimpa batas umum; principal lain memakai umum", () => {
        const t = tiers("order", [], { "10": block(5) });
        expect(
            previewApproval({ ...base, tiers: t, discount: 40_000 })!.status,
        ).toBe("free");
        expect(
            previewApproval({
                ...base,
                principal: "11",
                tiers: t,
                discount: 40_000,
            })!.status,
        ).toBe("needs");
    });
    it("outlet_month: pemakaian outlet+principal yang sama ikut; outlet lain tidak", () => {
        const usage = [
            {
                outlet_id: "5",
                principal: "10",
                discount_amount: 15_000,
                gross_amount: 1_000_000,
            },
            {
                outlet_id: "6",
                principal: "10",
                discount_amount: 900_000,
                gross_amount: 1_000_000,
            },
            {
                outlet_id: "5",
                principal: "11",
                discount_amount: 900_000,
                gross_amount: 1_000_000,
            },
        ];
        // Order 2,5% + pemakaian 1,5% → kumulatif 2% tepat batas (nilai berbobot).
        const p = previewApproval({
            ...base,
            tiers: tiers("outlet_month", usage),
            discount: 25_000,
        })!;
        expect(p.pct).toBe(2);
        expect(p.orderPct).toBe(2.5);
        expect(p.cumulative).toBe(true);
        expect(p.status).toBe("free");
        const over = previewApproval({
            ...base,
            tiers: tiers("outlet_month", usage),
            discount: 30_000,
        })!;
        expect(over.status).toBe("needs");
        expect(approvalPreviewText(over)).toContain("kumulatif");
    });
    it("salesman_day: semua pemakaian principal (outlet null) ikut", () => {
        const usage = [
            {
                outlet_id: null,
                principal: "10",
                discount_amount: 50_000,
                gross_amount: 1_000_000,
            },
        ];
        const p = previewApproval({
            ...base,
            tiers: tiers("salesman_day", usage),
            discount: 10_000,
        })!;
        expect(p.pct).toBe(3);
        expect(p.chain).toEqual(["Supervisor", "Branch Manager"]);
    });
    it("cakupan order mengabaikan pemakaian", () => {
        const usage = [
            {
                outlet_id: "5",
                principal: "10",
                discount_amount: 900_000,
                gross_amount: 1_000_000,
            },
        ];
        const p = previewApproval({
            ...base,
            tiers: tiers("order", usage),
            discount: 10_000,
        })!;
        expect(p.status).toBe("free");
        expect(p.cumulative).toBe(false);
    });
    it("promo resmi dalam zona bebas → pemantauan Supervisor", () => {
        const p = previewApproval({
            ...base,
            tiers: tiers(),
            discount: 10_000,
            hasProgram: true,
        })!;
        expect(p.status).toBe("free");
        expect(p.promoMonitoring).toBe(true);
        expect(approvalPreviewText(p)).toBe("Pemantauan promo: Supervisor");
    });
    it("promo tanpa diskon nominal tetap dipantau", () => {
        const p = previewApproval({
            ...base,
            tiers: tiers(),
            discount: 0,
            hasProgram: true,
        })!;
        expect(p.promoMonitoring).toBe(true);
    });
    it("tier kosong tetapi di atas zona bebas → perlu approver tanpa nama", () => {
        const t: ApprovalTiers = {
            discount: {
                scope: "order",
                default: { free_zone_max: 1, tiers: [] },
                principals: {},
                usage: [],
            },
        };
        const p = previewApproval({ ...base, tiers: t, discount: 50_000 })!;
        expect(p.status).toBe("needs");
        expect(approvalPreviewText(p)).toBe("Diskon 5% → perlu approver");
    });
    it("promo resmi murni 8% tanpa diskon manual → hanya pemantauan Supervisor", () => {
        const p = previewApproval({
            ...base,
            tiers: tiers(),
            discount: 80_000,
            hasProgram: true,
            hasManual: false,
        })!;
        expect(p.status).toBe("free");
        expect(p.chain).toEqual([]);
        expect(p.promoMonitoring).toBe(true);
        expect(approvalPreviewText(p)).toBe("Pemantauan promo: Supervisor");
    });
    it("order baru tanpa diskon tidak perlu approval walau histori outlet melewati Tier 0", () => {
        const usage = [
            {
                outlet_id: "5",
                principal: "10",
                discount_amount: 100_000,
                gross_amount: 1_000_000,
            },
        ];
        const p = previewApproval({
            ...base,
            tiers: tiers("outlet_month", usage),
            discount: 0,
            hasManual: false,
        })!;
        expect(p.status).toBe("none");
        expect(p.chain).toEqual([]);
        expect(approvalPreviewText(p)).toBe("");
    });
    it("diskon manual kecil + promo + histori: persentase kumulatif tetap menentukan rantai", () => {
        const usage = [
            {
                outlet_id: "5",
                principal: "10",
                discount_amount: 40_000,
                gross_amount: 1_000_000,
            },
        ];
        const p = previewApproval({
            ...base,
            tiers: tiers("outlet_month", usage),
            discount: 50_000,
            hasProgram: true,
            hasManual: true,
        })!;
        expect(p.pct).toBe(4.5);
        expect(p.status).toBe("needs");
        expect(p.chain).toEqual(["Supervisor", "Branch Manager"]);
    });
});
