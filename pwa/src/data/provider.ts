import {
    ApiError,
    IdentitySchema,
    ReceiptSchema,
    SnapshotSchema,
    type Command,
    type FieldProvider,
} from "../domain/contracts";
export class HttpProvider implements FieldProvider {
    readonly mode = "live" as const;
    private csrf?: string;
    private async request(path: string, body?: unknown) {
        const response = await fetch(`/api/v1/${path}`, {
            credentials: "same-origin",
            cache: "no-store",
            signal: AbortSignal.timeout(15000),
            headers: {
                Accept: "application/json",
                ...(body
                    ? {
                          "Content-Type": "application/json",
                          "X-CSRF-Token": this.csrf ?? "",
                      }
                    : {}),
            },
            method: body ? "POST" : "GET",
            ...(body ? { body: JSON.stringify(body) } : {}),
        });
        if (!response.ok)
            throw new ApiError(
                response.status,
                response.status === 401
                    ? "Sesi resmi belum tersedia. Silakan login melalui layanan perusahaan."
                    : `Layanan belum siap (${response.status}).`,
            );
        return response.json();
    }
    async bootstrap() {
        const identity = IdentitySchema.parse(
            await this.request("me/bootstrap"),
        );
        this.csrf = identity.csrfToken;
        return identity;
    }
    async snapshot() {
        return SnapshotSchema.parse(await this.request("sync/snapshot"));
    }
    async submit(command: Command) {
        if (!this.csrf) throw new ApiError(401, "CSRF/session belum tersedia.");
        return ReceiptSchema.parse(
            await this.request("sync/commands", command),
        );
    }
}
export async function createProvider(actor: string): Promise<FieldProvider> {
    if (__DEMO__) {
        const { MockProvider } = await import("./mock");
        return new MockProvider(actor);
    }
    return new HttpProvider();
}
