import {
    ApiError,
    type Command,
    type FieldProvider,
    type Identity,
    type Receipt,
    type Scenario,
    type Snapshot,
} from "../domain/contracts";
import { FieldStore } from "../storage/store";
const actors: Record<string, Omit<Identity, "businessDate">> = {
    sales: {
        id: "DEMO-ANDRE",
        companyId: "demo-mdu",
        name: "Andre",
        title: "Sales • Manado Barat",
        roles: ["sales", "hris"],
    },
    delivery: {
        id: "DEMO-NOVRY",
        companyId: "demo-mdu",
        name: "Novry",
        title: "Driver • Trip Maumbi",
        roles: ["delivery", "hris"],
    },
    canvass: {
        id: "DEMO-STEVEN",
        companyId: "demo-mdu",
        name: "Steven",
        title: "Canvasser • Manado",
        roles: ["sales", "delivery", "hris"],
    },
};
export class MockProvider implements FieldProvider {
    readonly mode = "demo" as const;
    scenario: Scenario = "normal";
    private store = new FieldStore();
    constructor(private actor: string) {}
    async bootstrap() {
        return {
            ...(actors[this.actor] ?? actors.sales),
            businessDate: new Date().toLocaleDateString("en-CA", {
                timeZone: "Asia/Makassar",
            }),
        };
    }
    async snapshot(): Promise<Snapshot> {
        return {
            version: "demo-snapshot-1",
            updatedAt: new Date().toISOString(),
            outlets: [
                {
                    id: "demo-outlet-1",
                    name: "Toko Sinar Pagi",
                    channel: "General Trade",
                    address: "Jl. Sam Ratulangi, Sario",
                    distance: "1,2 km",
                    time: "08.30",
                    latitude: 1.465,
                    longitude: 124.833,
                    radius: 15,
                },
                {
                    id: "demo-outlet-2",
                    name: "Toko Berkat Bahu",
                    channel: "General Trade",
                    address: "Jl. Wolter Monginsidi, Bahu",
                    distance: "2,8 km",
                    time: "09.15",
                    latitude: 1.447,
                    longitude: 124.825,
                    radius: 15,
                },
                {
                    id: "demo-outlet-3",
                    name: "Minimarket Pelangi",
                    channel: "Retail",
                    address: "Jl. Bethesda, Ranotana",
                    distance: "3,4 km",
                    time: "10.00",
                    latitude: 1.456,
                    longitude: 124.84,
                    radius: 10,
                },
            ],
            products: [
                {
                    id: "demo-product-1",
                    name: "Biskuit Kelapa 300 g",
                    brand: "MAYORA • BISKUIT",
                    principal: "mayora",
                    unit: "karton / 24 pcs",
                    price: 182400,
                    stock: 48,
                },
                {
                    id: "demo-product-2",
                    name: "Wafer Cokelat 24 g",
                    brand: "MAYORA • WAFER",
                    principal: "mayora",
                    unit: "karton / 48 pcs",
                    price: 156000,
                    stock: 32,
                },
                {
                    id: "demo-product-3",
                    name: "Kopi Bubuk 165 g",
                    brand: "SANTOS • KOPI",
                    principal: "santos",
                    unit: "karton / 24 pcs",
                    price: 264000,
                    stock: 21,
                },
            ],
            deliveries: [
                {
                    id: "DEMO-DO-001",
                    outlet: "Toko Sinar Pagi",
                    address: "Sario, Manado",
                    items: 4,
                    cartons: 12,
                    trip: "TRIP-DEMO-01",
                    vehicle: "DB • DEMO",
                },
                {
                    id: "DEMO-DO-002",
                    outlet: "Toko Berkat Bahu",
                    address: "Bahu, Manado",
                    items: 3,
                    cartons: 8,
                    trip: "TRIP-DEMO-01",
                    vehicle: "DB • DEMO",
                },
            ],
        };
    }
    async submit(command: Command): Promise<Receipt> {
        if (!navigator.onLine)
            throw new ApiError(0, "Perangkat offline. Data tetap tersimpan.");
        if (this.scenario === "timeout")
            throw new ApiError(503, "Simulasi gangguan jaringan.");
        if (this.scenario === "expired")
            throw new ApiError(401, "Simulasi sesi habis. Antrean dikunci.");
        const owner = (await this.bootstrap()).id;
        const key = `${owner}:${command.type}:${command.client_uuid}`;
        const payload = JSON.stringify(command);
        const existing = await this.store.receipt(key);
        if (existing) {
            if (existing.payload !== payload)
                throw new ApiError(409, "UUID sama dengan payload berbeda.");
            return existing.receipt;
        }
        const policyApproval = [
            "field_expense.request",
            "sales.extra_call.request",
            "hris.leave.request",
        ].includes(command.type);
        const status =
            this.scenario === "rejected"
                ? "rejected"
                : this.scenario === "approval" || policyApproval
                  ? "needs_approval"
                  : "accepted";
        const receipt: Receipt = {
            client_uuid: command.client_uuid,
            status,
            message:
                status === "rejected"
                    ? "Simulasi: perlu koreksi. Buat pengajuan baru."
                    : status === "needs_approval"
                      ? "Simulasi: menunggu review supervisor; belum disetujui."
                      : "Diterima simulator. Belum menjadi dokumen Odoo.",
            reference: `DEMO-${command.client_uuid.slice(0, 8).toUpperCase()}`,
        };
        await this.store.saveReceipt(key, receipt, payload);
        return receipt;
    }
}
