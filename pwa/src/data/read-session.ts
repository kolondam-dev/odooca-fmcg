import { ApiError, type Identity, type Snapshot } from "../domain/contracts";
import { HttpProvider } from "./provider";

export const witaDate = (now = new Date()) =>
    new Intl.DateTimeFormat("en-CA", {
        timeZone: "Asia/Makassar",
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
    }).format(now);

type ReadApi = Pick<HttpProvider, "bootstrap" | "snapshot" | "invalidate">;
export type ReadState = {
    phase: "idle" | "connecting" | "ready" | "syncing" | "synced" | "error";
    identity?: Identity;
    snapshot?: Snapshot;
    message?: string;
};

// Volatile, read-only view: no FieldStore, attendance, outbox or demo fallback.
export class ReadSession {
    state: ReadState = { phase: "idle" };
    private generation = 0;
    constructor(
        private api: ReadApi = new HttpProvider({ readOnly: true }),
        private changed: (state: ReadState) => void = () => {},
        private today: () => string = witaDate,
    ) {}
    private publish(state: ReadState) {
        this.state = state;
        this.changed(state);
    }
    clear(message?: string) {
        ++this.generation;
        this.api.invalidate();
        this.publish({ phase: "idle", message });
    }
    checkDay() {
        if (
            this.state.identity &&
            this.state.identity.businessDate !== this.today()
        )
            this.clear(
                "Hari WITA berganti. Hubungkan sesi dan lakukan daily sync kembali.",
            );
    }
    async load(sync = false) {
        const generation = ++this.generation;
        this.api.invalidate();
        this.publish({ phase: sync ? "syncing" : "connecting" });
        try {
            // Revalidate the actual cookie session for every sync; never reuse an
            // identity/snapshot from a previous user, permission or company scope.
            const identity = await this.api.bootstrap();
            if (generation !== this.generation) return;
            if (identity.businessDate !== this.today())
                throw new ApiError(409, "Hari sesi berubah.");
            const snapshot = sync ? await this.api.snapshot() : undefined;
            if (generation !== this.generation) return;
            if (identity.businessDate !== this.today())
                throw new ApiError(409, "Hari sesi berubah.");
            this.publish({
                phase: snapshot ? "synced" : "ready",
                identity,
                snapshot,
            });
        } catch (error) {
            if (generation !== this.generation) return;
            this.api.invalidate();
            const status = error instanceof ApiError ? error.status : 0;
            const messages: Record<number, string> = {
                401: "Sesi Odoo berakhir atau belum login. Silakan masuk melalui Odoo.",
                403: "Akses atau penugasan hari ini tidak tersedia. Hubungi admin.",
                409: "Sesi atau hari WITA berubah. Hubungkan sesi kembali.",
                422: "Konfigurasi atau scope data belum sesuai. Hubungi admin.",
            };
            this.publish({
                phase: "error",
                message:
                    messages[status] ??
                    "Data belum dapat dibaca. Periksa koneksi dan coba kembali.",
            });
        }
    }
}
