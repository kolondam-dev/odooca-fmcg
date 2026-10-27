import { ReceiptSchema, type Command } from "./contracts";
import { VisitCheckoutSchema, VisitContextSchema } from "./visit-contracts";
import type { QueueItem } from "../storage/store";
export function visitDependenciesReady(
    command: Command,
    owner: string,
    rows: QueueItem[],
): boolean {
    const context =
        command.type === "sales.order.submit" && command.payload.visit_context
            ? VisitContextSchema.parse(command.payload.visit_context)
            : command.type === "sales.visit.check_out"
              ? VisitCheckoutSchema.parse(command.payload)
              : undefined;
    if (!context) return true;
    const first = rows.find(
        (q) =>
            q.owner === owner &&
            q.key === `${owner}:${context.visit_uuid}` &&
            q.command.type === "sales.visit.check_in" &&
            q.command.client_uuid === context.visit_uuid,
    );
    const receipt = ReceiptSchema.safeParse(first?.receipt);
    if (
        !first ||
        first.state !== "accepted" ||
        !receipt.success ||
        receipt.data.status !== "accepted" ||
        receipt.data.client_uuid !== context.visit_uuid
    )
        return false;
    if (command.type === "sales.visit.check_out")
        for (const id of command.payload.order_uuids) {
            const order = rows.find(
                (q) =>
                    q.owner === owner &&
                    q.key === `${owner}:${id}` &&
                    q.command.client_uuid === id &&
                    q.command.type === "sales.order.submit",
            );
            const r = ReceiptSchema.safeParse(order?.receipt);
            if (
                !order ||
                order.command.type !== "sales.order.submit" ||
                VisitContextSchema.safeParse(
                    order.command.payload.visit_context,
                ).data?.visit_uuid !== context.visit_uuid ||
                !r.success ||
                r.data.client_uuid !== id ||
                r.data.status !== order.state ||
                !["accepted", "needs_approval", "rejected"].includes(
                    order.state,
                )
            )
                return false;
        }
    return true;
}
