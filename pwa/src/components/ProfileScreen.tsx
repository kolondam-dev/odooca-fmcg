import type { Identity, Snapshot } from "../domain/contracts";
import { Card, KV, Screen, ScreenHeader } from "../ui";
import { useBackLayer } from "../ui/navigation";
import { Icon } from "./Icon";

/** Profil dan sesi akun (layar penuh DS): identitas, konteks kerja, ganti akun, keluar. */
export function ProfileScreen({
    identity,
    snapshot,
    workStatus,
    close,
}: {
    identity: Identity;
    snapshot: Snapshot;
    workStatus: string;
    close: () => void;
}) {
    useBackLayer(true, close);
    const warehouse =
        snapshot.warehouseName ??
        (snapshot.scope?.warehouse_id
            ? `Gudang ${snapshot.scope.warehouse_id}`
            : "Belum tersedia");
    return (
        <Screen
            label="Profil dan sesi akun"
            class="ui-screen--over ui-screen--top"
            header={<ScreenHeader title="Profil & Sesi Akun" onBack={close} />}
        >
            <Card>
                <div class="ui-profile">
                    <span
                        class="ui-avatar ui-profile__avatar"
                        aria-hidden="true"
                    >
                        {identity.name[0]}
                    </span>
                    <div class="ui-profile__who">
                        <h2 class="ui-profile__name">{identity.name}</h2>
                        <p class="ui-profile__title">{identity.title}</p>
                    </div>
                </div>
            </Card>
            <Card>
                <KV label="Perusahaan" value="PT Manado Distribusi Utama" />
                <KV label="Gudang & Hub" value={warehouse} />
                <KV label="Rute & Sesi" value={workStatus} />
            </Card>
            <a
                href="/web/login?redirect=/field/"
                class="ui-btn ui-btn--pri ui-btn--lg"
            >
                <Icon name="user" size={20} />
                Masuk Akun Odoo / Ganti Akun
            </a>
            <a
                href="/web/session/logout?redirect=/field/"
                class="ui-btn ui-btn--danger ui-btn--lg"
            >
                <Icon name="close" size={20} />
                Keluar dari Sesi (Logout)
            </a>
        </Screen>
    );
}
