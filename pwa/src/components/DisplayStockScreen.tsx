import { useEffect, useRef, useState } from "preact/hooks";
import type { Snapshot } from "../domain/contracts";
import { setTier, stockText, tierQty, type Cart } from "../domain/order-cart";
import type { OrderUom } from "../domain/order-pricing";
import { unitOptions } from "../domain/product-units";
import type { FieldStore } from "../storage/store";
import { ActionCaption, Button, Callout, Screen, ScreenHeader } from "../ui";
import { Icon } from "./Icon";
import { useBackLayer } from "../ui/navigation";
import { DisplayPhoto } from "./DisplayPhoto";
import type { EvidenceRef } from "./Evidence";

/** Draf lokal "Display & stok toko". Kontrak belum punya command untuk ini. */
export interface DisplayDraft {
    evidence?: EvidenceRef;
    stock?: Cart;
}

export const displayKey = (outletId: string) => `display:${outletId}`;
const LISTED = 8;

/** Layar penuh Display & stok toko (DS: Display_stok). Prasyarat order. */
export function DisplayStockScreen({
    snapshot,
    outletId,
    owner,
    store,
    close,
}: {
    snapshot: Snapshot;
    outletId: string;
    owner: string;
    store: FieldStore;
    close: () => void;
}) {
    const outlet = snapshot.outlets.find((o) => o.id === outletId);
    const [evidence, setEvidence] = useState<EvidenceRef>();
    const [stock, setStock] = useState<Cart>({});
    const [restored, setRestored] = useState(false);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");
    useBackLayer(true, close);
    const opener = useRef<Element | null>(document.activeElement);
    useEffect(
        () => () => {
            const el = opener.current;
            if (el instanceof HTMLElement && el.isConnected)
                setTimeout(() => el.focus(), 0);
        },
        [],
    );
    useEffect(() => {
        let active = true;
        void store
            .draft(owner, displayKey(outletId))
            .then((value) => {
                if (!active) return;
                const v = (value ?? {}) as DisplayDraft;
                if (v.evidence) setEvidence(v.evidence);
                if (v.stock) setStock(v.stock);
                setRestored(true);
            })
            .catch(() => {
                setError("Draft display tidak dapat dibaca.");
                setRestored(true);
            });
        return () => {
            active = false;
        };
    }, []);
    // Daftar SKU = riwayat order toko ini (ikut sync harian). Tanpa riwayat dari
    // server, jatuh ke urutan katalog dan diberi tahu (hutang backend, DS_RECONCILIATION).
    const history = snapshot.order_history?.find(
        (h) => h.outlet_id === outletId,
    );
    const listed = history
        ? history.product_ids
              .map((id) => snapshot.products.find((p) => p.id === id))
              .filter((p): p is Snapshot["products"][number] => !!p)
        : snapshot.products.slice(0, LISTED);
    async function save() {
        if (!evidence || busy) return;
        setBusy(true);
        setError("");
        try {
            await store.draft(owner, displayKey(outletId), {
                evidence,
                stock,
            } satisfies DisplayDraft);
            close();
        } catch {
            setError("Display & stok gagal disimpan. Periksa penyimpanan.");
        } finally {
            setBusy(false);
        }
    }
    return (
        <Screen
            label="Display dan stok toko"
            class="ui-screen--over"
            header={
                <ScreenHeader
                    title="Display & stok toko"
                    onBack={() => {
                        if (!busy) close();
                    }}
                />
            }
            footer={
                <>
                    <Button
                        icon="check"
                        disabled={!restored || !evidence || busy}
                        onClick={() => void save()}
                    >
                        {busy ? "Menyimpan…" : "Simpan display & stok"}
                    </Button>
                    <ActionCaption>
                        {evidence
                            ? "Foto display tersimpan di perangkat."
                            : "Foto display toko wajib sebelum order."}
                    </ActionCaption>
                </>
            }
        >
            <DisplayPhoto
                store={store}
                owner={owner}
                value={evidence}
                outletName={outlet?.name ?? "Outlet"}
                coordinates={
                    outlet
                        ? {
                              latitude: outlet.latitude,
                              longitude: outlet.longitude,
                          }
                        : undefined
                }
                onChange={setEvidence}
            />
            <Callout tone="neu">
                {history
                    ? "Daftar SKU dari riwayat order toko ini. Ikut sync harian, jadi selalu terbaru."
                    : "Riwayat order toko ini belum dikirim server; menampilkan SKU pertama katalog."}
            </Callout>
            <h2 class="ui-sectionlabel">Stok aktual di toko</h2>
            {listed.map((product) => {
                const options = unitOptions(product, snapshot.catalog_version);
                return (
                    <fieldset class="stock-row" key={product.id}>
                        <legend>
                            {product.name}
                            <span class="stock-row__sys">
                                <Icon name="box" size={14} />{" "}
                                {stockText(
                                    product,
                                    product.stock,
                                    snapshot.catalog_version,
                                )}
                            </span>
                        </legend>
                        <div class="stock-row__grid">
                            {options.map((option) => (
                                <label class="ui-field" key={option.uom}>
                                    <span class="ui-field__label">
                                        {option.label}
                                    </span>
                                    <input
                                        class="ui-field__input stock-row__input"
                                        aria-label={`Stok toko ${product.name} ${option.label}`}
                                        type="number"
                                        inputMode="numeric"
                                        min="0"
                                        max="9999"
                                        value={tierQty(
                                            stock,
                                            product.id,
                                            option.uom as OrderUom,
                                        )}
                                        onInput={(event) =>
                                            setStock((current) =>
                                                setTier(
                                                    current,
                                                    product.id,
                                                    option.uom as OrderUom,
                                                    Math.min(
                                                        9999,
                                                        Math.max(
                                                            0,
                                                            Math.trunc(
                                                                Number(
                                                                    event
                                                                        .currentTarget
                                                                        .value,
                                                                ),
                                                            ) || 0,
                                                        ),
                                                    ),
                                                ),
                                            )
                                        }
                                    />
                                </label>
                            ))}
                        </div>
                    </fieldset>
                );
            })}
            {error ? (
                <Callout tone="bad" alert>
                    {error}
                </Callout>
            ) : null}
        </Screen>
    );
}
