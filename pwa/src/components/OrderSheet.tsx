import { useEffect, useMemo, useRef, useState } from "preact/hooks";
import type { Snapshot } from "../domain/contracts";
import {
    lineQuote,
    orderSummary,
    type OrderUom,
} from "../domain/order-pricing";
import {
    conversionLabel,
    productUnitLabels,
    unitOptions,
} from "../domain/product-units";
import { money } from "../domain/format";
import { Icon } from "./Icon";

const principalName = (id: string) => id.charAt(0).toUpperCase() + id.slice(1);

const cartonText = (value: number) =>
    Number.isInteger(value)
        ? String(value)
        : value.toFixed(2).replace(/\.?0+$/, "");

function ProductRow({
    product,
    catalogVersion,
    quantity,
    uom,
    stock,
    onQuantity,
    onUom,
}: {
    product: Snapshot["products"][number];
    catalogVersion?: 2;
    quantity: number;
    uom: OrderUom;
    stock?: number;
    onQuantity: (value: number) => void;
    onUom: (value: OrderUom) => void;
}) {
    const currentStock = stock !== undefined ? stock : product.stock;
    const options = unitOptions(product, catalogVersion);
    const labels = productUnitLabels(product);
    const selected = options.find((o) => o.uom === uom) ?? options[0];
    const line =
        quantity > 0 ? lineQuote(product, quantity, uom, catalogVersion) : null;
    const isOutOfStock = currentStock <= 0;
    const isOverStock = Boolean(line && line.cartons > currentStock);
    const set = (value: number) =>
        onQuantity(Math.min(999, Math.max(0, Math.trunc(value) || 0)));
    return (
        <article class={`product-card${quantity > 0 ? " picked" : ""}`}>
            <div class="product-head">
                <div>
                    <strong>{product.name}</strong>
                    <small>
                        {product.brand} · {product.sku_code ?? product.id}
                    </small>
                </div>
                <span class="product-price">
                    {money(product.price)}
                    <small>/{labels.carton}</small>
                </span>
            </div>
            <p class="conversion">{conversionLabel(product, catalogVersion)}</p>
            <div class="stock-status-bar">
                <span
                    class={`stock-badge ${isOutOfStock ? "out" : currentStock <= 5 ? "low" : "ok"}`}
                >
                    ●{" "}
                    {isOutOfStock
                        ? "Stok Habis"
                        : `Stok aktual: ${cartonText(currentStock)} ${labels.carton}`}
                </span>
                {isOverStock && (
                    <span class="stock-warning-badge">
                        ⚠️ Order ({cartonText(line!.cartons)}) melebihi stok
                        aktual ({cartonText(currentStock)})
                    </span>
                )}
            </div>
            <div
                class="uom-chips"
                role="group"
                aria-label={`Satuan ${product.name}`}
            >
                {options.map((option) => (
                    <button
                        key={option.uom}
                        type="button"
                        aria-pressed={option.uom === uom}
                        onClick={() => onUom(option.uom)}
                    >
                        {option.label}
                    </button>
                ))}
            </div>
            <div class="qty-row">
                <button
                    type="button"
                    class="step"
                    aria-label={`Kurangi ${product.name}`}
                    disabled={quantity <= 0}
                    onClick={() => set(quantity - 1)}
                >
                    −
                </button>
                <input
                    aria-label={`Kuantitas ${product.name}`}
                    type="number"
                    min="0"
                    max="999"
                    step="1"
                    inputMode="numeric"
                    value={quantity}
                    onInput={(e) => set(Number(e.currentTarget.value))}
                />
                <button
                    type="button"
                    class="step"
                    aria-label={`Tambah ${product.name}`}
                    disabled={quantity >= 999}
                    onClick={() => set(quantity + 1)}
                >
                    +
                </button>
                <span class="line-total">
                    {line ? money(line.subtotal) : "—"}
                </span>
            </div>
            <small class="line-note">
                {quantity > 0 && line
                    ? `${quantity} ${selected.label} = ${line.pcs} Pcs · ${cartonText(line.cartons)} ${labels.carton}`
                    : `Tersedia ${cartonText(currentStock)} ${labels.carton} · harga per ${labels.carton}`}
            </small>
        </article>
    );
}

export function OrderCatalog({
    snapshot,
    principal,
    onPrincipal,
    qty,
    onQty,
    units,
    onUnits,
    liveStock,
    onRefreshStock,
    refreshingStock,
    stockSyncedAt,
}: {
    snapshot: Snapshot;
    principal: string;
    onPrincipal: (value: string) => void;
    qty: Record<string, number>;
    onQty: (value: Record<string, number>) => void;
    units: Record<string, OrderUom>;
    onUnits: (value: Record<string, OrderUom>) => void;
    liveStock?: Record<string, number>;
    onRefreshStock?: () => void;
    refreshingStock?: boolean;
    stockSyncedAt?: Date;
}) {
    const [query, setQuery] = useState("");
    const term = query.trim().toLowerCase();
    const principals = [
        ...new Set(snapshot.products.map((product) => product.principal)),
    ];
    const active = principals.includes(principal)
        ? principal
        : (principals[0] ?? principal);
    const products = useMemo(
        () =>
            snapshot.products.filter(
                (p) =>
                    p.principal === active &&
                    (!term ||
                        `${p.name} ${p.sku_code ?? ""} ${p.brand}`
                            .toLowerCase()
                            .includes(term)),
            ),
        [snapshot.products, active, term],
    );
    const [limit, setLimit] = useState(60);
    const more = useRef<HTMLButtonElement>(null);
    useEffect(() => setLimit(60), [active, term]);
    useEffect(() => {
        if (!more.current || !globalThis.IntersectionObserver) return;
        const observer = new IntersectionObserver(
            (entries) => {
                if (entries.some((entry) => entry.isIntersecting))
                    setLimit((value) => value + 60);
            },
            { rootMargin: "120px" },
        );
        observer.observe(more.current);
        return () => observer.disconnect();
    }, [products, limit]);
    return (
        <>
            <div class="pos-toolbar">
                <div class="stock-sync-bar">
                    <span class="stock-sync-indicator">
                        <span class="pulse-dot">●</span> Stok Aktual Realtime
                        {stockSyncedAt
                            ? ` (${stockSyncedAt.toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit", second: "2-digit" })})`
                            : ""}
                    </span>
                    {onRefreshStock && (
                        <button
                            type="button"
                            class="stock-refresh-btn"
                            disabled={refreshingStock}
                            onClick={onRefreshStock}
                        >
                            {refreshingStock ? "Sync…" : "↻ Perbarui"}
                        </button>
                    )}
                </div>
                <div class="principal-rule-bar">
                    <span>
                        🏢 Prinsipal:{" "}
                        <strong>
                            {snapshot.products.find(
                                (p) => p.principal === active,
                            )?.principal_name ?? principalName(active)}
                        </strong>{" "}
                        · 1 order per prinsipal
                    </span>
                </div>
                <label class="search product-search">
                    <Icon name="bag" size={18} />
                    <input
                        aria-label="Cari produk"
                        placeholder="Cari produk atau SKU"
                        value={query}
                        onInput={(e) => setQuery(e.currentTarget.value)}
                    />
                </label>
                <div class="segmented" role="group" aria-label="Principal">
                    {principals.map((p) => {
                        const name =
                            snapshot.products.find(
                                (product) => product.principal === p,
                            )?.principal_name ?? principalName(p);
                        return (
                            <button
                                key={p}
                                type="button"
                                aria-pressed={p === active}
                                title="1 pesanan hanya untuk 1 prinsipal"
                                onClick={() => {
                                    if (p === active) return;
                                    const currentCount = Object.values(
                                        qty,
                                    ).filter((v) => v > 0).length;
                                    if (currentCount > 0) {
                                        const confirmed = window.confirm(
                                            `1 pesanan hanya berlaku untuk 1 prinsipal FMCG. Berpindah prinsipal akan mengosongkan keranjang saat ini (${currentCount} item). Lanjutkan?`,
                                        );
                                        if (!confirmed) return;
                                        onQty({});
                                    }
                                    onPrincipal(p);
                                }}
                            >
                                {name}
                            </button>
                        );
                    })}
                </div>
            </div>
            <div class="product-list">
                {products.length === 0 && (
                    <p class="empty">Tidak ada produk yang cocok.</p>
                )}
                {products.slice(0, limit).map((product) => (
                    <ProductRow
                        key={product.id}
                        product={product}
                        catalogVersion={snapshot.catalog_version}
                        quantity={qty[product.id] ?? 0}
                        uom={units[product.id] ?? "carton"}
                        stock={liveStock?.[product.id]}
                        onQuantity={(value) =>
                            onQty({ ...qty, [product.id]: value })
                        }
                        onUom={(value) =>
                            onUnits({ ...units, [product.id]: value })
                        }
                    />
                ))}
                {limit < products.length && (
                    <button
                        ref={more}
                        type="button"
                        class="secondary"
                        onClick={() => setLimit((value) => value + 60)}
                    >
                        Tampilkan produk berikutnya (
                        {Math.min(limit, products.length)}/{products.length})
                    </button>
                )}
            </div>
        </>
    );
}

export function OrderSummary({
    snapshot,
    qty,
    units,
    discount,
    note,
}: {
    snapshot: Snapshot;
    qty: Record<string, number>;
    units: Record<string, OrderUom>;
    discount: number;
    note?: string;
}) {
    const lines = Object.entries(qty)
        .filter(([, value]) => value > 0)
        .map(([product_id, value]) => ({
            product_id,
            qty: String(value),
            uom: units[product_id] ?? "carton",
        }));
    const summary = orderSummary(lines, snapshot);
    const afterDiscount =
        summary.subtotal - Math.round((summary.subtotal * discount) / 100);
    return (
        <div class="order-summary" aria-label="Ringkasan order">
            <dl>
                <div>
                    <dt>SKU</dt>
                    <dd>{lines.length}</dd>
                </div>
                <div>
                    <dt>Karton setara</dt>
                    <dd>{cartonText(summary.cartons)}</dd>
                </div>
                <div class="total">
                    <dt>{discount > 0 ? "Setelah diskon" : "Subtotal"}</dt>
                    <dd>{money(afterDiscount)}</dd>
                </div>
            </dl>
            {note && <p class="summary-note">{note}</p>}
        </div>
    );
}
