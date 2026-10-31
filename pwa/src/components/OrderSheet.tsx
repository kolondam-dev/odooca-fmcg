import { useState } from "preact/hooks";
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
    onQuantity,
    onUom,
}: {
    product: Snapshot["products"][number];
    catalogVersion?: 2;
    quantity: number;
    uom: OrderUom;
    onQuantity: (value: number) => void;
    onUom: (value: OrderUom) => void;
}) {
    const options = unitOptions(product, catalogVersion);
    const labels = productUnitLabels(product);
    const selected = options.find((o) => o.uom === uom) ?? options[0];
    const line =
        quantity > 0 ? lineQuote(product, quantity, uom, catalogVersion) : null;
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
                    : `Stok ${cartonText(product.stock)} ${labels.carton} · harga per ${labels.carton}`}
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
}: {
    snapshot: Snapshot;
    principal: string;
    onPrincipal: (value: string) => void;
    qty: Record<string, number>;
    onQty: (value: Record<string, number>) => void;
    units: Record<string, OrderUom>;
    onUnits: (value: Record<string, OrderUom>) => void;
}) {
    const [query, setQuery] = useState("");
    const term = query.trim().toLowerCase();
    const principals = [
        ...new Set(snapshot.products.map((product) => product.principal)),
    ];
    const active = principals.includes(principal)
        ? principal
        : (principals[0] ?? principal);
    const products = snapshot.products.filter(
        (p) =>
            p.principal === active &&
            (!term ||
                `${p.name} ${p.sku_code ?? ""} ${p.brand}`
                    .toLowerCase()
                    .includes(term)),
    );
    return (
        <>
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
                {principals.map((p) => (
                    <button
                        key={p}
                        type="button"
                        aria-pressed={p === active}
                        onClick={() => {
                            onPrincipal(p);
                            onQty({});
                        }}
                    >
                        {principalName(p)}
                    </button>
                ))}
            </div>
            <div class="product-list">
                {products.length === 0 && (
                    <p class="empty">Tidak ada produk yang cocok.</p>
                )}
                {products.map((product) => (
                    <ProductRow
                        key={product.id}
                        product={product}
                        catalogVersion={snapshot.catalog_version}
                        quantity={qty[product.id] ?? 0}
                        uom={units[product.id] ?? "carton"}
                        onQuantity={(value) =>
                            onQty({ ...qty, [product.id]: value })
                        }
                        onUom={(value) =>
                            onUnits({ ...units, [product.id]: value })
                        }
                    />
                ))}
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
                    <dt>Item</dt>
                    <dd>{summary.items}</dd>
                </div>
                <div>
                    <dt>Karton</dt>
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
