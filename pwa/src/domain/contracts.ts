import { z } from "zod";
export const Role = z.enum(["sales", "delivery", "hris"]);
export const IdentitySchema = z.object({
    id: z.string().min(1),
    companyId: z.string().min(1),
    name: z.string().min(1),
    title: z.string(),
    roles: z.array(Role),
    businessDate: z.string(),
    csrfToken: z.string().optional(),
});
export type Identity = z.infer<typeof IdentitySchema>;
export const CommandType = z.enum([
    "sales.order.submit",
    "sales.extra_call.request",
    "delivery.proof.submit",
    "hris.attendance.capture",
    "hris.leave.request",
    "field_expense.request",
]);
export const CommandSchema = z.object({
    schema_version: z.literal(1),
    client_uuid: z.string().uuid(),
    type: CommandType,
    occurred_at: z.string().datetime(),
    payload: z.record(z.string(), z.unknown()),
});
export type Command = z.infer<typeof CommandSchema>;
export const ReceiptSchema = z.object({
    client_uuid: z.string().uuid(),
    status: z.enum(["accepted", "needs_approval", "rejected"]),
    message: z.string(),
    reference: z.string(),
});
export type Receipt = z.infer<typeof ReceiptSchema>;
export const SnapshotSchema = z.object({
    version: z.string(),
    updatedAt: z.string(),
    outlets: z.array(
        z.object({
            id: z.string(),
            name: z.string(),
            channel: z.string(),
            address: z.string(),
            distance: z.string(),
            time: z.string(),
            latitude: z.number(),
            longitude: z.number(),
            radius: z.number().min(5).max(15),
        }),
    ),
    products: z.array(
        z.object({
            id: z.string(),
            name: z.string(),
            brand: z.string(),
            principal: z.string(),
            unit: z.string(),
            price: z.number().nonnegative(),
            stock: z.number().nonnegative(),
        }),
    ),
    deliveries: z.array(
        z.object({
            id: z.string(),
            outlet: z.string(),
            address: z.string(),
            items: z.number(),
            cartons: z.number(),
            trip: z.string(),
            vehicle: z.string(),
        }),
    ),
});
export type Snapshot = z.infer<typeof SnapshotSchema>;
export type Scenario =
    | "normal"
    | "approval"
    | "rejected"
    | "timeout"
    | "expired";
export class ApiError extends Error {
    status: number;
    constructor(status: number, message: string) {
        super(message);
        this.status = status;
    }
}
export interface FieldProvider {
    readonly mode: "demo" | "live";
    bootstrap(): Promise<Identity>;
    snapshot(): Promise<Snapshot>;
    submit(command: Command): Promise<Receipt>;
    scenario?: Scenario;
}
export function ownerKey(identity: Identity): string {
    return `${identity.companyId}:${identity.id}`;
}
export function canOpen(roles: Identity["roles"], page: string): boolean {
    return (
        (page !== "sales" && page !== "delivery") ||
        roles.includes(page as "sales" | "delivery")
    );
}
export function validateOrder(
    lines: { productId: string; quantity: number }[],
    snapshot: Snapshot,
): string | null {
    if (!lines.length) return "Pilih sedikitnya satu produk.";
    const principals = new Set<string>();
    for (const line of lines) {
        const product = snapshot.products.find((p) => p.id === line.productId);
        if (
            !product ||
            !Number.isInteger(line.quantity) ||
            line.quantity < 1 ||
            line.quantity > 999
        )
            return "Kuantitas harus 1–999 karton.";
        principals.add(product.principal);
    }
    return principals.size > 1
        ? "Satu SO hanya untuk satu principal. Pisahkan keranjang."
        : null;
}
