import { ReceiptSchema } from "./contracts";
import type { QueueItem } from "../storage/store";
// Transport rejection without a matching business receipt must stay locked.
export function businessRejected(item: QueueItem | undefined): boolean {
    if (!item || item.state !== "rejected") return false;
    const parsed = ReceiptSchema.safeParse(item.receipt);
    return (
        parsed.success &&
        parsed.data.status === "rejected" &&
        parsed.data.client_uuid === item.command.client_uuid
    );
}
