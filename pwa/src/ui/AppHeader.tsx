import type { ComponentChildren } from "preact";
import { IconButton } from "./IconButton";
import { StatusDot } from "./StatusDot";

/** Kepala tab DS: tanggal kecil + judul, dan klaster status (koneksi, sinkron, avatar). */
export function AppHeader({
    title,
    eyebrow,
    online,
    pending,
    initial,
    onSync,
    onProfile,
    extra,
}: {
    title: ComponentChildren;
    eyebrow?: ComponentChildren;
    online: boolean;
    pending: number;
    initial: string;
    onSync: () => void;
    onProfile: () => void;
    /** Mis. pil mode operasi (demo/live). */
    extra?: ComponentChildren;
}) {
    return (
        <header class="ui-hdr ui-hdr--tab">
            <div class="ui-hdr__col">
                {eyebrow ? <span class="ui-hdr__date">{eyebrow}</span> : null}
                <h1 class="ui-hdr__title">{title}</h1>
            </div>
            {extra}
            <span class="ui-conn" role="status">
                <StatusDot online={online} />
                <span class="ui-visually-hidden">
                    {online ? "Online" : "Offline"}
                </span>
            </span>
            <IconButton
                icon="sync"
                label="Lihat antrean sinkronisasi"
                badge={pending}
                onClick={onSync}
            />
            <button
                type="button"
                class="ui-avatar"
                aria-label="Profil dan Sesi Akun"
                onClick={onProfile}
            >
                {initial}
            </button>
        </header>
    );
}
