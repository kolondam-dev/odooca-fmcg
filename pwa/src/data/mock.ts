import {
    ApiError,
    type Command,
    type FieldProvider,
    type Identity,
    type Receipt,
    type Scenario,
    type Snapshot,
} from "../domain/contracts";
import { orderHasDiscountRequest } from "../domain/order-pricing";
import { ExpenseRealizationSchema } from "../domain/settlement-contracts";
import { FieldStore } from "../storage/store";
import { isDemoMode } from "../domain/running-mode";
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
        capabilities: ["collection.capture"],
    },
    canvass: {
        id: "DEMO-STEVEN",
        companyId: "demo-mdu",
        name: "Steven",
        title: "Canvasser • Manado",
        roles: ["sales", "delivery", "hris"],
        capabilities: ["collection.capture"],
    },
};
export class MockProvider implements FieldProvider {
    readonly mode = "demo" as const;
    scenario: Scenario = "normal";
    private store = new FieldStore();
    constructor(
        private actor: string,
        private _relaxedLocation?: boolean,
        private authenticated?: Pick<
            FieldProvider,
            "bootstrap" | "snapshot"
        > & {
            submit?: FieldProvider["submit"];
        },
    ) {}
    get relaxedLocation(): boolean {
        return this._relaxedLocation !== undefined
            ? this._relaxedLocation
            : isDemoMode();
    }
    async bootstrap() {
        if (this.authenticated) return this.authenticated.bootstrap();
        return {
            ...(actors[this.actor] ?? actors.sales),
            businessDate: new Date().toLocaleDateString("en-CA", {
                timeZone: "Asia/Makassar",
            }),
        };
    }
    async snapshot(): Promise<Snapshot> {
        if (this.authenticated) {
            const snapshot = await this.authenticated.snapshot();
            const fallbackDeliveries =
                this.actor === "delivery" || this.actor === "canvass"
                    ? snapshot.outlets.map((outlet) => ({
                          id: `DEMO-DO-OUTLET-${encodeURIComponent(outlet.id)}`,
                          outlet: outlet.name,
                          address: outlet.address,
                          items: 3,
                          cartons: 12,
                          trip: "TRIP-01",
                          vehicle: "DB 8471 MD",
                      }))
                    : [];
            const deliveries =
                snapshot.deliveries && snapshot.deliveries.length > 0
                    ? snapshot.deliveries
                    : fallbackDeliveries;
            // Preserve the existing remote-demo allowance only in the local
            // workflow. The HTTP payload and official evidence gates stay strict.
            return {
                ...snapshot,
                deliveries,
                outlets: this.relaxedLocation
                    ? snapshot.outlets.map((outlet) => ({
                          ...outlet,
                          demo_unrestricted: true as const,
                      }))
                    : snapshot.outlets,
            };
        }
        const identity = await this.bootstrap();
        return {
            catalog_version: 2,
            scope: {
                company_id: identity.companyId,
                user_id: identity.id,
                business_date: identity.businessDate,
                warehouse_id: "SIM-WH-MAUMBI",
            },
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
                    ...(this.relaxedLocation
                        ? { demo_unrestricted: true as const }
                        : {}),
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
                    ...(this.relaxedLocation
                        ? { demo_unrestricted: true as const }
                        : {}),
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
                    ...(this.relaxedLocation
                        ? { demo_unrestricted: true as const }
                        : {}),
                },
            ],
            products: [
                {
                    id: "demo-product-1",
                    name: "Biskuit Kelapa 300 g",
                    brand: "MAYORA • BISKUIT",
                    principal: "mayora",
                    unit: "Karton 144 pcs · Renceng 12 pcs",
                    price: 187200,
                    stock: 48,
                    sku_code: "SIM-SKU-1",
                    price_basis: "carton",
                    stock_basis: "carton",
                    packaging: { carton: 144, pack: 12, pcs: 1 },
                    carton_label: "Karton",
                    pack_label: "Renceng",
                    unit_label: "Pcs",
                },
                {
                    id: "demo-product-2",
                    name: "Wafer Cokelat 24 g",
                    brand: "MAYORA • WAFER",
                    principal: "mayora",
                    unit: "Karton 144 pcs · Pack 12 pcs",
                    price: 158400,
                    stock: 32,
                    sku_code: "SIM-SKU-2",
                    price_basis: "carton",
                    stock_basis: "carton",
                    packaging: { carton: 144, pack: 12, pcs: 1 },
                    carton_label: "Karton",
                    pack_label: "Pack",
                    unit_label: "Pcs",
                },
                {
                    id: "demo-product-3",
                    name: "Kopi Bubuk 165 g",
                    brand: "SANTOS • KOPI",
                    principal: "santos",
                    unit: "Karton 144 pcs · Renceng 12 pcs",
                    price: 273600,
                    stock: 21,
                    sku_code: "SIM-SKU-3",
                    price_basis: "carton",
                    stock_basis: "carton",
                    packaging: { carton: 144, pack: 12, pcs: 1 },
                    carton_label: "Karton",
                    pack_label: "Renceng",
                    unit_label: "Pcs",
                },
                {
                    id: "demo-product-4",
                    sku_code: "SIM-SKU-4",
                    name: "Biskuit Mini 24 pcs",
                    brand: "MAYORA • BISKUIT",
                    principal: "mayora",
                    unit: "Box 24 pcs · Pack 6 pcs",
                    price_basis: "carton",
                    stock_basis: "carton",
                    packaging: { carton: 24, pack: 6, pcs: 1 },
                    carton_label: "Box",
                    pack_label: "Pack",
                    unit_label: "Pcs",
                    price: 24000,
                    stock: 40,
                },
            ],
            order_history: [
                {
                    outlet_id: "demo-outlet-1",
                    product_ids: ["demo-product-1", "demo-product-2"],
                },
            ],
            discount_programs: [
                {
                    id: "demo-promo-biskuit",
                    name: "Gebyar Promo Biskuit Q4 (simulasi)",
                    scope: "line" as const,
                    principal: "mayora",
                    product_ids: ["demo-product-1"],
                    max_percent: 10,
                    budget_remaining: 12500000,
                },
                {
                    id: "demo-promo-footer",
                    name: "Potongan Footer Q4 (simulasi)",
                    scope: "footer" as const,
                    principal: "mayora",
                    max_amount: 100000,
                    budget_remaining: 1000000,
                },
            ],
            deliveries: [
                {
                    id: "DEMO-DO-001",
                    outlet: "Toko Sinar Pagi",
                    address: "Sario, Manado",
                    items: 3,
                    cartons: 12,
                    trip: "TRIP-01",
                    vehicle: "DB 8471 MD",
                },
                {
                    id: "DEMO-DO-002",
                    outlet: "Toko Berkat Bahu",
                    address: "Bahu, Manado",
                    items: 3,
                    cartons: 8,
                    trip: "TRIP-01",
                    vehicle: "DB 8471 MD",
                },
            ],
        };
    }
    async deliveryTasks() {
        const owner = await this.bootstrap();
        const snapshot = await this.snapshot();
        return snapshot.deliveries.map((d, i) => {
            // Generated DO identity carries its assignment relation, so array
            // reordering cannot bind a simulated delivery to another outlet.
            const outlet = d.id.startsWith("DEMO-DO-OUTLET-")
                ? snapshot.outlets.find(
                      (candidate) =>
                          d.id ===
                          `DEMO-DO-OUTLET-${encodeURIComponent(candidate.id)}`,
                  )
                : snapshot.outlets[i];
            if (!outlet)
                throw new ApiError(
                    409,
                    "Outlet manifest tidak tersedia dalam penugasan.",
                );
            return {
                workflow_version: 2 as const,
                id: d.id,
                trip: d.trip,
                vehicle: d.vehicle,
                outlet: d.outlet,
                address: d.address,
                owner: `${owner.companyId}:${owner.id}`,
                business_date: owner.businessDate,
                version: "SIM-MANIFEST-1",
                outlet_id: outlet.id,
                site: {
                    latitude: outlet.latitude,
                    longitude: outlet.longitude,
                    radius: outlet.radius,
                    ...(outlet.demo_unrestricted
                        ? { demo_unrestricted: true as const }
                        : {}),
                },
                lines: [
                    {
                        id: `${d.id}-1`,
                        name: "Biskuit Kelapa 300 g (contoh)",
                        quantity: (d.cartons - 2) * 144,
                        unit: "pcs",
                    },
                    {
                        id: `${d.id}-2`,
                        name: "Wafer Cokelat (contoh)",
                        quantity: 144,
                        unit: "pcs",
                    },
                    {
                        id: `${d.id}-3`,
                        name: "Kopi Bubuk (contoh)",
                        quantity: 144,
                        unit: "pcs",
                    },
                ],
            };
        });
    }
    async collectionTasks() {
        return (await this.deliveryTasks()).map((delivery, i) => ({
            delivery,
            receivable_reference: `SIM-TAGIHAN-${i + 1}`,
            amount_due: "1000000",
            currency: "IDR" as const,
            version: "SIM-COLLECTION-1",
            issued_at: new Date().toISOString(),
            capture_allowed: true as const,
        }));
    }
    async expensePolicy() {
        // Fixture only, never a company approval limit.
        return { version: "SIM-EXPENSE-POLICY-1", supervisor_limit: "250000" };
    }
    async submit(command: Command): Promise<Receipt> {
        if (!navigator.onLine)
            throw new ApiError(0, "Perangkat offline. Data tetap tersimpan.");
        if (this.scenario === "timeout")
            throw new ApiError(503, "Simulasi gangguan jaringan.");
        if (this.scenario === "expired")
            throw new ApiError(401, "Simulasi sesi habis. Antrean dikunci.");

        if (
            this.authenticated &&
            typeof this.authenticated.submit === "function" &&
            command.type === "sales.order.submit"
        ) {
            // Forward live sales orders to backend. Delivery commands (POD and trip closure)
            // remain simulated locally because deliveries in current snapshot are local fallback DOs.
            return await this.authenticated.submit(command);
        }

        const owner = (await this.bootstrap()).id;
        const key = `${owner}:${command.type}:${command.client_uuid}`;
        const payload = JSON.stringify(command);
        const existing = await this.store.receipt(key);
        if (existing) {
            if (existing.payload !== payload)
                throw new ApiError(409, "UUID sama dengan payload berbeda.");
            return existing.receipt;
        }
        if (
            command.type === "field_expense.realization.submit" &&
            !ExpenseRealizationSchema.safeParse(command.payload).success
        )
            throw new ApiError(
                422,
                "Data realisasi tidak sesuai kontrak simulator.",
            );
        const discounted =
            (command.type === "sales.order.submit" ||
                command.type === "sales.order.revise") &&
            orderHasDiscountRequest(command.payload);
        const policyApproval = [
            "sales.order.revise",
            "delivery.pod.submit",
            "collection.receipt.submit",
            "field_expense.request",
            "field_expense.realization.submit",
            "sales.extra_call.request",
            "hris.leave.request",
        ].includes(command.type);
        const status =
            this.scenario === "rejected"
                ? "rejected"
                : this.scenario === "approval" || policyApproval || discounted
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
                      : discounted
                        ? "SIMULASI: diskon diminta disetujui seluruhnya; total sesuai pengajuan. Bukan approval Odoo."
                        : "Diterima simulator. Belum menjadi dokumen Odoo.",
            reference: `DEMO-${command.client_uuid.slice(0, 8).toUpperCase()}`,
        };
        await this.store.saveReceipt(key, receipt, payload);
        return receipt;
    }
}
