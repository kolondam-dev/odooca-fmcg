import {
    ApiError,
    CommandSchema,
    ReceiptSchema,
    type Command,
    type FieldProvider,
} from "./contracts";
import { FieldStore, type QueueItem } from "../storage/store";
export class Outbox {
    private running?: Promise<void>;
    constructor(
        private store: FieldStore,
        private owner: string,
        private provider: FieldProvider,
        private changed: () => void = () => {},
    ) {}
    async enqueue(
        type: Command["type"],
        payload: Record<string, unknown>,
        label: string,
        uuid = crypto.randomUUID(),
    ) {
        const command = CommandSchema.parse({
            schema_version: 1,
            client_uuid: uuid,
            type,
            occurred_at: new Date().toISOString(),
            payload,
        });
        const existing = (await this.store.list(this.owner)).find(
            (x) => x.command.client_uuid === uuid,
        );
        if (existing) throw new Error("Command UUID sudah digunakan.");
        const item: QueueItem = {
            key: `${this.owner}:${uuid}`,
            owner: this.owner,
            command,
            label,
            state: "queued",
            attempts: 0,
            nextAttempt: 0,
        };
        await this.store.put(item);
        this.changed();
        return item;
    }
    flush() {
        if (this.running) return this.running;
        this.running = this.send().finally(() => {
            this.running = undefined;
        });
        return this.running;
    }
    private async send() {
        for (const item of await this.store.list(this.owner)) {
            if (
                !["queued", "sending"].includes(item.state) ||
                item.nextAttempt > Date.now()
            )
                continue;
            item.state = "sending";
            item.attempts++;
            await this.store.put(item);
            this.changed();
            try {
                const receipt = ReceiptSchema.parse(
                    await this.provider.submit(item.command),
                );
                if (receipt.client_uuid !== item.command.client_uuid)
                    throw new Error("Receipt UUID tidak cocok.");
                item.receipt = receipt;
                item.state = receipt.status;
                delete item.error;
            } catch (error) {
                const status = error instanceof ApiError ? error.status : 0;
                item.error =
                    error instanceof Error
                        ? error.message
                        : "Sinkronisasi gagal.";
                item.state =
                    status === 401
                        ? "auth_required"
                        : status >= 400 &&
                            status < 500 &&
                            ![408, 429].includes(status)
                          ? "rejected"
                          : "queued";
                item.nextAttempt =
                    Date.now() +
                    Math.min(120_000, 1000 * 2 ** Math.min(item.attempts, 7));
            }
            await this.store.put(item);
            this.changed();
            if (item.state === "auth_required") break;
        }
    }
    async retry() {
        for (const item of await this.store.list(this.owner)) {
            // Terminal business rejections need a new corrected command, never a blind replay.
            if (item.state === "queued") {
                item.nextAttempt = 0;
                await this.store.put(item);
            }
        }
        await this.flush();
    }
}
